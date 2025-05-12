class Logger {
    constructor() {
        this.autoScroll = true;
        this.maxLogEntries = 1000; // 增加日志显示数量
        this.isCollapsed = false;
        this.isVisible = false;
        this.container = null;
        this.init();
        this.checkDevMode();
    }

    init() {
        // Create logger container
        const container = document.createElement('div');
        container.className = 'logger-container';
        container.style.display = 'none'; // Initially hidden
        container.innerHTML = `
            <div class="logger-header">
                <div class="logger-title">
                    <span>Developer Logs</span>
                    <span class="logger-toggle" id="loggerToggle">▼</span>
                </div>
                <div class="logger-controls">
                    <button class="logger-button active" id="autoScrollBtn">
                        <span class="icon">⟳</span>
                        <span>Auto Scroll</span>
                    </button>
                    <button class="logger-button" id="clearLogsBtn">
                        <span class="icon">⌫</span>
                        <span>Clear</span>
                    </button>
                </div>
            </div>
            <div class="logger-content" id="loggerContent"></div>
        `;
        document.body.appendChild(container);

        // Get elements
        this.container = container;
        this.content = document.getElementById('loggerContent');
        this.autoScrollBtn = document.getElementById('autoScrollBtn');
        this.clearLogsBtn = document.getElementById('clearLogsBtn');
        this.toggleBtn = document.getElementById('loggerToggle');

        // Bind events
        this.autoScrollBtn.addEventListener('click', () => this.toggleAutoScroll());
        this.clearLogsBtn.addEventListener('click', () => this.clearLogs());
        this.toggleBtn.addEventListener('click', () => this.toggleCollapse());

        // Initialize WebSocket connection
        this.initWebSocket();
    }

    checkDevMode() {
        // 每秒检查一次Vue实例的devMode状态
        setInterval(() => {
            const vueApp = document.getElementById('app')?.__vue__;
            if (vueApp) {
                const shouldBeVisible = vueApp.devMode === true;
                if (this.isVisible !== shouldBeVisible) {
                    this.isVisible = shouldBeVisible;
                    this.container.style.display = shouldBeVisible ? 'flex' : 'none';
                }
            }
        }, 1000);
    }

    initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        this.ws = new WebSocket(wsUrl);
        
        this.ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.log(data);
            } catch (e) {
                this.log({
                    type: 'error',
                    level: 'ERROR',
                    logger: 'System',
                    message: `Failed to parse WebSocket message: ${event.data}`
                });
            }
        };

        this.ws.onclose = () => {
            this.log({
                type: 'log',
                level: 'ERROR',
                logger: 'System',
                message: 'WebSocket connection closed. Attempting to reconnect...'
            });
            setTimeout(() => this.initWebSocket(), 5000);
        };
    }

    log(data) {
        // 如果不在开发者模式，不记录日志
        const vueApp = document.getElementById('app')?.__vue__;
        if (!vueApp?.devMode) {
            return;
        }

        const entry = document.createElement('div');
        
        // Determine the log level
        let level = (data.level || 'INFO').toUpperCase();
        if (data.type === 'error' && level !== 'ERROR') {
            level = 'ERROR';
        }
        
        entry.className = `log-entry ${level.toLowerCase()}`;
        
        // Create timestamp element
        const timestamp = document.createElement('span');
        timestamp.className = 'log-timestamp';
        timestamp.textContent = data.timestamp ? 
            new Date(data.timestamp * 1000).toLocaleTimeString() :
            new Date().toLocaleTimeString();
        
        // Create logger name element if present
        const loggerEl = document.createElement('span');
        loggerEl.className = 'log-logger';
        loggerEl.textContent = data.logger ? `[${data.logger}]` : '';
        
        // Create message element
        const messageEl = document.createElement('span');
        messageEl.className = 'log-message';
        
        let message = '';
        if (typeof data === 'string') {
            message = data;
        } else if (data.type === 'connection') {
            message = `[${data.status}] ${data.message}`;
        } else {
            message = data.message || JSON.stringify(data);
            // 处理多行消息
            if (message.includes('\n')) {
                const lines = message.split('\n');
                message = lines[lines.length - 1]; // 取最后一行，通常是实际消息
            }
            // 解码Unicode转义序列
            try {
                message = decodeURIComponent(JSON.parse('"' + message.replace(/\"/g, '\\"') + '"'));
            } catch (e) {
                // 如果解码失败，使用原始消息
                console.warn('Failed to decode message:', e);
                this.log({
                    type: 'error',
                    level: 'ERROR',
                    logger: 'System',
                    message: `Failed to decode message: ${e.message}` // Display error in logger UI
                });
            }
        }
        messageEl.textContent = message;
        
        // Combine elements
        entry.appendChild(timestamp);
        if (data.logger) {
            entry.appendChild(loggerEl);
        }
        entry.appendChild(messageEl);
        
        // Add the new entry
        this.content.appendChild(entry);

        // Keep only the specified number of log entries
        while (this.content.children.length > this.maxLogEntries) {
            this.content.removeChild(this.content.firstChild);
        }

        // Handle auto-scroll
        if (this.autoScroll && !this.isCollapsed) {
            this.scrollToBottom();
        }
    }

    scrollToBottom() {
        requestAnimationFrame(() => {
            this.content.scrollTop = this.content.scrollHeight;
        });
    }

    toggleAutoScroll() {
        this.autoScroll = !this.autoScroll;
        this.autoScrollBtn.classList.toggle('active', this.autoScroll);
        if (this.autoScroll) {
            this.scrollToBottom();
        }
    }

    toggleCollapse() {
        this.isCollapsed = !this.isCollapsed;
        this.container.classList.toggle('collapsed', this.isCollapsed);
        this.toggleBtn.textContent = this.isCollapsed ? '▲' : '▼';
        
        if (!this.isCollapsed && this.autoScroll) {
            this.scrollToBottom();
        }
    }

    clearLogs() {
        this.content.innerHTML = '';
    }
}

// Initialize logger when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.logger = new Logger();
}); 