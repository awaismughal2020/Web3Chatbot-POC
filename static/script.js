class EnhancedChatbot {
    constructor() {
        this.chatMessages = document.getElementById('chatMessages');
        this.chatForm = document.getElementById('chatForm');
        this.chatInput = document.getElementById('chatInput');
        this.sendButton = document.getElementById('sendButton');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.statusText = document.getElementById('status-text');
        this.responseTimeElement = document.getElementById('response-time');
        this.conversationIdElement = document.getElementById('conversation-id');
        this.conversationsList = document.getElementById('conversationsList');
        this.searchBox = document.getElementById('searchBox');

        this.isProcessing = false;
        this.messageCount = 0;
        this.currentConversationId = null;
        this.userId = this.getUserId();
        this.conversations = [];
        this.userStats = null;

        this.initializeEventListeners();
        this.initialize();
    }

    async initialize() {
        // Display user ID
        document.getElementById('userIdDisplay').textContent = `User: ${this.userId}`;

        // Check health
        await this.checkHealth();

        // Load user data
        await this.loadUserStats();
        await this.loadConversations();
    }

    initializeEventListeners() {
        this.chatForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleSendMessage();
        });

        this.chatInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.handleSendMessage();
            }
        });

        this.searchBox.addEventListener('input', (e) => {
            this.searchConversations(e.target.value);
        });

        // Auto-resize input
        this.chatInput.addEventListener('input', () => {
            this.chatInput.style.height = 'auto';
            this.chatInput.style.height = this.chatInput.scrollHeight + 'px';
        });
    }

    async handleSendMessage() {
        const message = this.chatInput.value.trim();
        if (!message || this.isProcessing) return;

        this.isProcessing = true;
        this.updateUI(true);

        // Add user message to UI
        this.addMessage(message, 'user');

        // Clear input
        this.chatInput.value = '';
        this.chatInput.style.height = 'auto';

        // Show typing indicator
        this.showTyping();

        try {
            await this.sendStreamingMessage(message);
        } catch (error) {
            this.hideTyping();
            this.addMessage('Sorry, I encountered an error. Please try again.', 'bot', 'error');
            console.error('Chat error:', error);
        }

        this.isProcessing = false;
        this.updateUI(false);
    }

    async sendStreamingMessage(message) {
        const startTime = Date.now();

        try {
            const response = await fetch('/chat/stream', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    user_id: this.userId,
                    conversation_id: this.currentConversationId
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            let botMessageElement = null;
            let fullResponse = '';
            let intent = '';

            this.hideTyping();

            while (true) {
                const { done, value } = await reader.read();

                if (done) break;

                const chunk = decoder.decode(value);
                const lines = chunk.split('\n');

                for (const line of lines) {
                    if (line.startsWith('data: ')) {
                        try {
                            const data = JSON.parse(line.slice(6));

                            switch (data.type) {
                                case 'start':
                                    // Initial acknowledgment
                                    break;

                                case 'intent':
                                    intent = data.intent;
                                    break;

                                case 'conversation_id':
                                    if (!this.currentConversationId) {
                                        this.currentConversationId = data.conversation_id;
                                        this.conversationIdElement.textContent = `Conv: ${data.conversation_id.slice(0, 8)}...`;
                                    }
                                    break;

                                case 'content':
                                    if (!botMessageElement) {
                                        botMessageElement = this.addMessage('', 'bot');
                                    }
                                    fullResponse += data.content;
                                    this.updateMessageContent(botMessageElement, fullResponse);
                                    break;

                                case 'complete':
                                    const responseTime = Date.now() - startTime;
                                    this.updateResponseTime(responseTime);
                                    this.updateMessageInfo(botMessageElement, intent, responseTime);

                                    // Refresh conversations list
                                    await this.loadConversations();
                                    break;

                                case 'error':
                                    this.hideTyping();
                                    this.addMessage(`Error: ${data.message}`, 'bot', 'error');
                                    break;
                            }
                        } catch (e) {
                            console.warn('Failed to parse SSE data:', line);
                        }
                    }
                }
            }

        } catch (error) {
            console.error('Streaming error:', error);
            throw error;
        }
    }

    async loadConversations() {
        try {
            const response = await fetch(`/api/conversations?user_id=${this.userId}&limit=20`);
            const data = await response.json();

            this.conversations = data.conversations || [];
            this.renderConversations();

        } catch (error) {
            console.error('Error loading conversations:', error);
        }
    }

    renderConversations() {
        const listElement = this.conversationsList;
        listElement.innerHTML = '';

        if (this.conversations.length === 0) {
            listElement.innerHTML = '<p style="text-align: center; color: #6c757d;">No conversations yet</p>';
            return;
        }

        this.conversations.forEach(conv => {
            const item = document.createElement('div');
            item.className = 'conversation-item';
            if (conv.id === this.currentConversationId) {
                item.className += ' active';
            }

            const title = conv.title || 'Untitled Conversation';
            const date = new Date(conv.updated_at * 1000).toLocaleString();
            const messageCount = conv.message_count || 0;

            item.innerHTML = `
                <div class="conversation-title">${title}</div>
                <div class="conversation-meta">
                    ${messageCount} messages • ${date}
                </div>
            `;

            item.onclick = () => this.loadConversation(conv.id);

            listElement.appendChild(item);
        });
    }

    async loadConversation(conversationId) {
        try {
            const response = await fetch(`/api/conversations/${conversationId}/messages?limit=100`);
            const data = await response.json();

            // Clear current messages
            this.chatMessages.innerHTML = '';

            // Set current conversation
            this.currentConversationId = conversationId;
            this.conversationIdElement.textContent = `Conv: ${conversationId.slice(0, 8)}...`;

            // Add messages
            data.messages.forEach(msg => {
                if (msg.role === 'user' || msg.role === 'assistant') {
                    const element = this.addMessage(
                        msg.content,
                        msg.role === 'user' ? 'user' : 'bot',
                        msg.error ? 'error' : 'normal',
                        false
                    );

                    // Update message info
                    const timestamp = new Date(msg.timestamp * 1000);
                    const infoElement = element.querySelector('.message-info');
                    infoElement.textContent = `${msg.role === 'user' ? 'You' : 'Bot'} • ${this.formatTime(timestamp)}`;
                }
            });

            // Add typing indicator back
            this.chatMessages.appendChild(this.typingIndicator);

            // Update active state
            this.renderConversations();

            // Scroll to bottom
            this.scrollToBottom();

        } catch (error) {
            console.error('Error loading conversation:', error);
        }
    }

    async loadUserStats() {
        try {
            const response = await fetch(`/api/users/${this.userId}/stats`);
            this.userStats = await response.json();

            // Update stats display
            document.getElementById('totalConversations').textContent = this.userStats.total_conversations || 0;
            document.getElementById('totalMessages').textContent = this.userStats.total_messages || 0;

            if (this.userStats.created_at) {
                const createdDate = new Date(this.userStats.created_at * 1000).toLocaleDateString();
                document.getElementById('memberSince').textContent = createdDate;
            }

            if (this.userStats.last_active) {
                const lastActiveDate = new Date(this.userStats.last_active * 1000).toLocaleString();
                document.getElementById('lastActive').textContent = lastActiveDate;
            }

            // Display common intents
            if (this.userStats.common_intents && this.userStats.common_intents.length > 0) {
                const intentsHtml = `
                    <h3 style="margin-top: 20px; margin-bottom: 10px;">Common Topics</h3>
                    ${this.userStats.common_intents.map(intent =>
                        `<span style="display: inline-block; padding: 5px 10px; margin: 2px; background: #e9ecef; border-radius: 15px; font-size: 0.8rem;">${intent}</span>`
                    ).join('')}
                `;
                document.getElementById('commonIntents').innerHTML = intentsHtml;
            }

        } catch (error) {
            console.error('Error loading user stats:', error);
        }
    }

    async searchConversations(query) {
        if (!query) {
            this.renderConversations();
            return;
        }

        try {
            const response = await fetch('/api/search', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    user_id: this.userId,
                    query: query
                })
            });

            const data = await response.json();

            // Filter conversations based on search results
            const matchingConvIds = new Set(data.results.map(r => r.conversation_id));
            const filteredConversations = this.conversations.filter(c => matchingConvIds.has(c.id));

            // Temporarily update the display
            this.conversations = filteredConversations;
            this.renderConversations();

        } catch (error) {
            console.error('Error searching:', error);
        }
    }

    addMessage(content, sender, type = 'normal', animate = true) {
        const messageElement = document.createElement('div');
        messageElement.className = `message ${sender}`;
        if (!animate) {
            messageElement.style.animation = 'none';
        }

        const contentElement = document.createElement('div');
        contentElement.className = 'message-content';
        if (type === 'error') {
            contentElement.className += ' error-message';
        }

        const infoElement = document.createElement('div');
        infoElement.className = 'message-info';

        if (sender === 'user') {
            contentElement.textContent = content;
            infoElement.textContent = `You • ${this.formatTime(new Date())}`;
        } else {
            contentElement.innerHTML = this.formatBotMessage(content);
            infoElement.textContent = `Bot • ${this.formatTime(new Date())}`;
        }

        messageElement.appendChild(contentElement);
        messageElement.appendChild(infoElement);

        // Insert before typing indicator
        this.chatMessages.insertBefore(messageElement, this.typingIndicator);
        this.scrollToBottom();

        this.messageCount++;

        return messageElement;
    }

    updateMessageContent(messageElement, content) {
        const contentElement = messageElement.querySelector('.message-content');
        contentElement.innerHTML = this.formatBotMessage(content);
        this.scrollToBottom();
    }

    updateMessageInfo(messageElement, intent, responseTime) {
        const infoElement = messageElement.querySelector('.message-info');
        const timeStr = this.formatTime(new Date());
        const intentStr = intent ? ` • ${intent}` : '';
        const timeInfo = responseTime ? ` • ${responseTime}ms` : '';
        infoElement.textContent = `Bot${intentStr}${timeInfo} • ${timeStr}`;
    }

    formatBotMessage(content) {
        // Convert markdown-like formatting
        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    showTyping() {
        this.typingIndicator.style.display = 'flex';
        this.scrollToBottom();
    }

    hideTyping() {
        this.typingIndicator.style.display = 'none';
    }

    updateUI(processing) {
        this.sendButton.disabled = processing;
        this.chatInput.disabled = processing;

        if (processing) {
            this.sendButton.textContent = '...';
            this.statusText.textContent = 'Processing';
        } else {
            this.sendButton.textContent = 'Send';
            this.statusText.textContent = 'Connected';
        }
    }

    updateResponseTime(time) {
        this.responseTimeElement.textContent = `Response time: ${time}ms`;

        // Color code based on speed
        if (time < 1000) {
            this.responseTimeElement.style.color = '#28a745'; // Green
        } else if (time < 3000) {
            this.responseTimeElement.style.color = '#ffc107'; // Yellow
        } else {
            this.responseTimeElement.style.color = '#dc3545'; // Red
        }
    }

    scrollToBottom() {
        this.chatMessages.scrollTop = this.chatMessages.scrollHeight;
    }

    formatTime(date) {
        return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    getUserId() {
        // Generate or retrieve user ID
        let userId = localStorage.getItem('chatbot_user_id');
        if (!userId) {
            userId = 'user_' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem('chatbot_user_id', userId);
        }
        return userId;
    }

    async checkHealth() {
        try {
            const response = await fetch('/health');
            const data = await response.json();

            if (data.status === 'healthy') {
                this.statusText.textContent = 'Connected';
                this.statusText.style.color = '#28a745';
            } else {
                this.statusText.textContent = 'Degraded';
                this.statusText.style.color = '#ffc107';
            }
        } catch (error) {
            this.statusText.textContent = 'Disconnected';
            this.statusText.style.color = '#dc3545';
        }
    }
}

// Global functions for UI actions
function switchTab(tabName) {
    const conversationsTab = document.getElementById('conversationsTab');
    const statsTab = document.getElementById('statsTab');
    const tabs = document.querySelectorAll('.sidebar-tab');

    tabs.forEach(tab => tab.classList.remove('active'));

    if (tabName === 'conversations') {
        conversationsTab.style.display = 'block';
        statsTab.style.display = 'none';
        tabs[0].classList.add('active');
    } else {
        conversationsTab.style.display = 'none';
        statsTab.style.display = 'block';
        tabs[1].classList.add('active');

        // Refresh stats when switching to stats tab
        if (window.chatbotInstance) {
            window.chatbotInstance.loadUserStats();
        }
    }
}

async function exportHistory() {
    if (!window.chatbotInstance) return;

    try {
        const userId = window.chatbotInstance.userId;
        const response = await fetch(`/api/export/user/${userId}`);

        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `chat_history_${userId}_${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            alert('Chat history exported successfully!');
        }
    } catch (error) {
        console.error('Export error:', error);
        alert('Failed to export chat history');
    }
}

async function clearHistory() {
    if (!window.chatbotInstance) return;

    if (!confirm('Are you sure you want to clear all chat history? This cannot be undone.')) {
        return;
    }

    try {
        const conversations = window.chatbotInstance.conversations;

        for (const conv of conversations) {
            await fetch(`/api/conversations/${conv.id}`, {
                method: 'DELETE'
            });
        }

        // Clear local storage
        localStorage.removeItem('chatbot_user_id');

        // Reload the page
        window.location.reload();

    } catch (error) {
        console.error('Clear history error:', error);
        alert('Failed to clear chat history');
    }
}

function sendDemoMessage(message) {
    const chatbot = window.chatbotInstance;
    if (chatbot && !chatbot.isProcessing) {
        chatbot.chatInput.value = message;
        chatbot.handleSendMessage();
    }
}

// Initialize chatbot when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.chatbotInstance = new EnhancedChatbot();

    console.log('🤖 Enhanced Web3 Chatbot with History initialized!');
    console.log('💡 Features: Chat history, search, export, statistics');
    console.log('🗄️ Storage: Typesense for fast search and retrieval');
});

// Utility functions for development/debugging
window.chatDebug = {
    clearMessages: () => {
        const messages = document.querySelectorAll('.message:not(.system)');
        messages.forEach(msg => msg.remove());
        window.chatbotInstance.messageCount = 0;
    },

    testHealth: async () => {
        const response = await fetch('/health');
        return await response.json();
    },

    getMetrics: async () => {
        const response = await fetch('/metrics');
        return await response.json();
    },

    getUserStats: async () => {
        const userId = window.chatbotInstance.userId;
        const response = await fetch(`/api/users/${userId}/stats`);
        return await response.json();
    },

    searchHistory: async (query) => {
        const userId = window.chatbotInstance.userId;
        const response = await fetch('/api/search', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({user_id: userId, query: query})
        });
        return await response.json();
    },

    simulateSlowNetwork: (delay = 2000) => {
        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            await new Promise(resolve => setTimeout(resolve, delay));
            return originalFetch(...args);
        };
        console.log(`Network delay simulation: ${delay}ms`);
    }
};
