from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///messenger.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# User sessions storage
active_users = {}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy=True)
    received_messages = db.relationship('Message', foreign_keys='Message.receiver_id', backref='receiver', lazy=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

class Connection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    connected_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, accepted, rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/')
@login_required
def index():
    return render_template('messenger.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('index'))
        
        flash('Invalid email or password')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('signup'))
            
        if User.query.filter_by(username=username).first():
            flash('Username already taken')
            return redirect(url_for('signup'))
        
        hashed_password = generate_password_hash(password)
        user = User(username=username, email=email, password=hashed_password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('index'))
    
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/search_users')
@login_required
def search_users():
    query = request.args.get('query', '')
    if not query:
        return jsonify([])
    
    users = User.query.filter(
        User.username.ilike(f'%{query}%'),
        User.id != current_user.id
    ).all()
    
    results = []
    for user in users:
        connection = Connection.query.filter(
            ((Connection.user_id == current_user.id) & (Connection.connected_user_id == user.id)) |
            ((Connection.user_id == user.id) & (Connection.connected_user_id == current_user.id))
        ).first()
        
        status = None
        if connection:
            status = connection.status
        
        results.append({
            'id': user.id,
            'username': user.username,
            'connection_status': status
        })
    
    return jsonify(results)

@app.route('/send_invitation/<int:user_id>')
@login_required
def send_invitation(user_id):
    existing_connection = Connection.query.filter(
        ((Connection.user_id == current_user.id) & (Connection.connected_user_id == user_id)) |
        ((Connection.user_id == user_id) & (Connection.connected_user_id == current_user.id))
    ).first()
    
    if existing_connection:
        return jsonify({'status': 'exists'})
    
    connection = Connection(user_id=current_user.id, connected_user_id=user_id)
    db.session.add(connection)
    db.session.commit()
    
    return jsonify({'status': 'success'})

@app.route('/accept_invitation/<int:connection_id>')
@login_required
def accept_invitation(connection_id):
    connection = Connection.query.get_or_404(connection_id)
    if connection.connected_user_id == current_user.id:
        connection.status = 'accepted'
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'})

@app.route('/get_messages/<int:user_id>')
@login_required
def get_messages(user_id):
    messages = Message.query.filter(
        ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id)) |
        ((Message.sender_id == user_id) & (Message.receiver_id == current_user.id))
    ).order_by(Message.timestamp).all()
    
    return jsonify([{
        'content': msg.content,
        'sender_id': 'self' if msg.sender_id == current_user.id else msg.sender_id,
        'sender_name': User.query.get(msg.sender_id).username,
        'timestamp': msg.timestamp.isoformat(),
        'read': msg.read
    } for msg in messages])

@app.route('/get_conversations')
@login_required
def get_conversations():
    connections = Connection.query.filter(
        ((Connection.user_id == current_user.id) |
         (Connection.connected_user_id == current_user.id)) &
        (Connection.status == 'accepted')
    ).all()
    
    conversations = []
    for conn in connections:
        other_user_id = conn.connected_user_id if conn.user_id == current_user.id else conn.user_id
        other_user = User.query.get(other_user_id)
        
        last_message = Message.query.filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == other_user_id)) |
            ((Message.sender_id == other_user_id) & (Message.receiver_id == current_user.id))
        ).order_by(Message.timestamp.desc()).first()
        
        conversations.append({
            'id': other_user_id,
            'username': other_user.username,
            'last_message': last_message.content if last_message else None,
            'last_message_time': last_message.timestamp.strftime('%H:%M') if last_message else None,
            'unread_count': Message.query.filter_by(
                sender_id=other_user_id,
                receiver_id=current_user.id,
                read=False
            ).count()
        })
    
    return jsonify(conversations)

@socketio.on('connect')
def handle_connect():
    if current_user.is_authenticated:
        active_users[current_user.id] = request.sid
        emit('user_status', {
            'user_id': current_user.id,
            'status': 'Online'
        }, broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if current_user.is_authenticated:
        active_users.pop(current_user.id, None)
        emit('user_status', {
            'user_id': current_user.id,
            'status': 'Offline'
        }, broadcast=True)

@socketio.on('private_message')
def handle_private_message(data):
    if not current_user.is_authenticated:
        return
    
    message = Message(
        content=data['message'],
        sender_id=current_user.id,
        receiver_id=data['receiver_id']
    )
    db.session.add(message)
    db.session.commit()
    
    receiver_sid = active_users.get(data['receiver_id'])
    if receiver_sid:
        emit('new_message', {
            'message': message.content,
            'sender_id': current_user.id,
            'sender_name': current_user.username,
            'timestamp': message.timestamp.isoformat()
        }, room=receiver_sid)
@app.route('/get_pending_invitations')
@login_required
def get_pending_invitations():
    pending_invitations = Connection.query.filter_by(
        connected_user_id=current_user.id,
        status='pending'
    ).all()
    
    return jsonify([{
        'id': inv.id,
        'sender_username': User.query.get(inv.user_id).username,
        'timestamp': inv.created_at.isoformat()
    } for inv in pending_invitations])

@app.route('/reject_invitation/<int:connection_id>')
@login_required
def reject_invitation(connection_id):
    connection = Connection.query.get_or_404(connection_id)
    if connection.connected_user_id == current_user.id:
        db.session.delete(connection)
        db.session.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'})
if __name__ == "__main__":
    socket.run(app, allow_unsafe_werkzeug=True, debug=True)


