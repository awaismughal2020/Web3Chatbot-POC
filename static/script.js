class FastChatbot {
    constructor() {
        this.chatMessages = document.getElementById('chatMessages');
        this.chatForm = document.getElementById('chatForm');
        this.chatInput = document.getElementById('chatInput');
        this.sendButton = document.getElementById('sendButton');
        this.typingIndicator = document.getElementById('typingIndicator');
        this.statusText = document.getElementById('status-text');
        this.responseTimeElement = document.getElementById('response-time');

        this.isProcessing = false;
        this.messageCount = 0;

        this.initializeEventListeners();
        this.checkHealth();
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

        // Add user message
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
                    user_id: this.getUserId()
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

    addMessage(content, sender, type = 'normal') {
        const messageElement = document.createElement('div');
        messageElement.className = `message ${sender}`;

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

    // Alternative non-streaming method (fallback)
    async sendRegularMessage(message) {
        const startTime = Date.now();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: message,
                    user_id: this.getUserId()
                })
            });

            const data = await response.json();

            this.hideTyping();

            const responseTime = Date.now() - startTime;
            this.updateResponseTime(responseTime);

            const botMessage = this.addMessage(data.response, 'bot');
            this.updateMessageInfo(botMessage, data.intent, data.response_time * 1000);

        } catch (error) {
            this.hideTyping();
            this.addMessage('Sorry, I encountered an error. Please try again.', 'bot', 'error');
            throw error;
        }
    }
}

// Demo button functionality
function sendDemoMessage(message) {
    const chatbot = window.chatbotInstance;
    if (chatbot && !chatbot.isProcessing) {
        chatbot.chatInput.value = message;
        chatbot.handleSendMessage();
    }
}

// Initialize chatbot when page loads
document.addEventListener('DOMContentLoaded', () => {
    window.chatbotInstance = new FastChatbot();

    // Optional: Add some demo data
    console.log('🤖 Fast Web3 Chatbot initialized!');
    console.log('💡 Features: Streaming responses, intent detection, Redis caching');
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

    simulateSlowNetwork: (delay = 2000) => {
        const originalFetch = window.fetch;
        window.fetch = async (...args) => {
            await new Promise(resolve => setTimeout(resolve, delay));
            return originalFetch(...args);
        };
        console.log(`Network delay simulation: ${delay}ms`);
    }
};
