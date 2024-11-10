const socket = io();
let currentChat = null;
let currentUserName = '';

document.addEventListener('DOMContentLoaded', () => {
    initializeUI();
    setupEventListeners();
    setupSocketListeners();
    updateConversationsList();
    loadPendingInvitations();
    setInterval(loadPendingInvitations, 30000);
});

function initializeUI() {
    currentUserName = document.querySelector('.user-info span').textContent;
    const chatArea = document.getElementById('chatArea');
    chatArea.style.display = 'none';
}

function setupEventListeners() {
    const modal = document.getElementById('searchModal');
    const newChatBtn = document.getElementById('newChatBtn');
    const closeModal = document.querySelector('.close-modal');
    const searchInput = document.getElementById('searchInput');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');

    newChatBtn.onclick = () => {
        modal.style.display = 'block';
        searchInput.focus();
    };

    closeModal.onclick = () => modal.style.display = 'none';

    window.onclick = (event) => {
        if (event.target === modal) modal.style.display = 'none';
    };

    let searchTimeout;
    searchInput.addEventListener('input', (e) => {
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => searchUsers(e.target.value), 300);
    });

    sendButton.onclick = sendMessage;
    messageInput.onkeypress = (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    };
}

function setupSocketListeners() {
    socket.on('connect', () => console.log('Connected to server'));

    socket.on('new_message', (data) => {
        if (currentChat === data.sender_id) {
            addMessageToUI({
                content: data.message,
                sender_id: data.sender_id,
                timestamp: data.timestamp,
                sender_name: data.sender_name
            });
        }
        updateConversationsList();
    });
}

async function searchUsers(query) {
    if (!query.trim()) {
        document.getElementById('searchResults').innerHTML = '';
        return;
    }

    try {
        const response = await fetch(`/search_users?query=${encodeURIComponent(query)}`);
        const users = await response.json();
        
        const resultsDiv = document.getElementById('searchResults');
        resultsDiv.innerHTML = users.map(user => `
            <div class="search-result-item">
                <span>${user.username}</span>
                ${getConnectionButton(user)}
            </div>
        `).join('');
    } catch (error) {
        console.error('Error searching users:', error);
    }
}

function getConnectionButton(user) {
    if (user.connection_status === 'accepted') {
        return '<span class="status-text">Connected</span>';
    } else if (user.connection_status === 'pending') {
        return '<span class="status-text">Pending</span>';
    }
    return `<button class="send-invitation-btn" onclick="initiateChat(${user.id}, '${user.username}')">
                Send Invitation
            </button>`;
}

async function loadPendingInvitations() {
    try {
        const response = await fetch('/get_pending_invitations');
        const invitations = await response.json();
        
        const invitationsSection = document.getElementById('invitationsSection');
        const invitationsDiv = document.getElementById('pendingInvitations');
        
        if (invitations.length > 0) {
            invitationsSection.classList.add('has-invitations');
            invitationsDiv.innerHTML = invitations.map(inv => `
                <div class="invitation-item">
                    <span>${inv.sender_username} wants to connect</span>
                    <div class="invitation-actions">
                        <button class="accept-btn" onclick="handleInvitation(${inv.id}, 'accept')">Accept</button>
                        <button class="reject-btn" onclick="handleInvitation(${inv.id}, 'reject')">Reject</button>
                    </div>
                </div>
            `).join('');
        } else {
            invitationsSection.classList.remove('has-invitations');
        }
    } catch (error) {
        console.error('Error loading invitations:', error);
    }
}

async function handleInvitation(connectionId, action) {
    try {
        const response = await fetch(`/${action}_invitation/${connectionId}`);
        const data = await response.json();
        
        if (data.status === 'success') {
            loadPendingInvitations();
            updateConversationsList();
        }
    } catch (error) {
        console.error('Error handling invitation:', error);
    }
}
async function startChat(userId, username) {
    currentChat = userId;
    const chatArea = document.getElementById('chatArea');
    chatArea.style.display = 'flex';
    
    document.getElementById('chatHeader').innerHTML = `
        <div class="chat-user">
            <span class="username">${username}</span>
        </div>
    `;
    
    document.getElementById('messages').innerHTML = '';
    loadChatHistory(userId);
    
    document.querySelectorAll('.conversation-item').forEach(item => {
        item.classList.remove('active');
    });
    document.querySelector(`[data-user-id="${userId}"]`)?.classList.add('active');
    
    document.getElementById('messageInput').focus();
}

function sendMessage() {
    if (!currentChat) return;
    
    const messageInput = document.getElementById('messageInput');
    const content = messageInput.value.trim();
    
    if (!content) return;

    socket.emit('private_message', {
        receiver_id: currentChat,
        message: content
    });

    addMessageToUI({
        content,
        sender_id: 'self',
        timestamp: new Date().toISOString(),
        sender_name: currentUserName
    });

    messageInput.value = '';
    updateConversationsList();
}

function addMessageToUI(message) {
    const messagesDiv = document.getElementById('messages');
    const messageElement = document.createElement('div');
    const isSelf = message.sender_id === 'self';
    
    messageElement.className = `message ${isSelf ? 'sent' : 'received'}`;
    
    const time = new Date(message.timestamp).toLocaleTimeString([], { 
        hour: '2-digit', 
        minute: '2-digit' 
    });
    
    messageElement.innerHTML = `
        <div class="message-bubble">
            <div class="message-content">${message.content}</div>
            <div class="message-info">
                <span class="message-time">${time}</span>
                ${isSelf ? '<span class="message-status">✓</span>' : ''}
            </div>
        </div>
    `;
    
    messagesDiv.appendChild(messageElement);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

async function loadChatHistory(userId) {
    try {
        const response = await fetch(`/get_messages/${userId}`);
        const messages = await response.json();
        
        const messagesDiv = document.getElementById('messages');
        messagesDiv.innerHTML = '';
        
        messages.forEach(message => addMessageToUI(message));
    } catch (error) {
        console.error('Error loading chat history:', error);
    }
}

async function updateConversationsList() {
    try {
        const response = await fetch('/get_conversations');
        const conversations = await response.json();
        
        const conversationsList = document.getElementById('conversationsList');
        conversationsList.innerHTML = conversations.map(conv => `
            <div class="conversation-item ${conv.id === currentChat ? 'active' : ''}" 
                 data-user-id="${conv.id}"
                 onclick="startChat(${conv.id}, '${conv.username}')">
                <div class="conversation-info">
                    <div class="conversation-name">${conv.username}</div>
                    <div class="conversation-last-message">
                        ${conv.last_message || 'Start a conversation'}
                    </div>
                </div>
                ${conv.unread_count ? `
                    <div class="unread-badge">${conv.unread_count}</div>
                ` : ''}
            </div>
        `).join('');
    } catch (error) {
        console.error('Error updating conversations:', error);
    }
}

async function initiateChat(userId, username) {
    try {
        const response = await fetch(`/send_invitation/${userId}`);
        const data = await response.json();
        
        if (data.status === 'success') {
            document.getElementById('searchModal').style.display = 'none';
            document.getElementById('searchInput').value = '';
            updateConversationsList();
        }
    } catch (error) {
        console.error('Error initiating chat:', error);
    }
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    
    if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
    
    return date.toLocaleDateString([], { 
        month: 'short', 
        day: 'numeric'
    });
}
