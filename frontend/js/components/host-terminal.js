/* Host Terminal Component */
const HostTerminal = {
    term: null,
    fitAddon: null,
    ws: null,
    hostId: null,
    container: null,

    async render(container, hostId) {
        this.cleanup();
        this.container = container;
        this.hostId = hostId;

        // 渲染终端容器
        container.innerHTML = `
            <div class="host-terminal-container">
                <div class="host-terminal-header">
                    <div class="host-terminal-title">
                        <i data-lucide="terminal"></i>
                        终端会话
                    </div>
                    <div class="host-terminal-actions">
                        <button class="btn btn-sm btn-secondary" id="terminal-clear" title="清屏">
                            <i data-lucide="trash-2"></i>
                        </button>
                        <button class="btn btn-sm btn-secondary" id="terminal-reconnect" title="重新连接">
                            <i data-lucide="refresh-cw"></i>
                        </button>
                    </div>
                </div>
                <div id="terminal-wrapper" class="host-terminal-wrapper"></div>
            </div>
        `;

        DOM.createIcons();

        // 绑定按钮事件
        DOM.$('#terminal-clear')?.addEventListener('click', () => {
            if (this.term) this.term.clear();
        });

        DOM.$('#terminal-reconnect')?.addEventListener('click', () => {
            this._connect();
        });

        // 初始化 xterm.js
        this._initTerminal();
        this._connect();

        return () => this.cleanup();
    },

    _initTerminal() {
        if (typeof Terminal === 'undefined') {
            console.error('xterm.js not loaded');
            return;
        }

        // 创建终端实例
        this.term = new Terminal({
            cursorBlink: true,
            fontSize: 14,
            fontFamily: 'JetBrains Mono, Consolas, monospace',
            theme: {
                background: '#1e1e1e',
                foreground: '#d4d4d4',
                cursor: '#ffffff',
                black: '#000000',
                red: '#cd3131',
                green: '#0dbc79',
                yellow: '#e5e510',
                blue: '#2472c8',
                magenta: '#bc3fbc',
                cyan: '#11a8cd',
                white: '#e5e5e5',
                brightBlack: '#666666',
                brightRed: '#f14c4c',
                brightGreen: '#23d18b',
                brightYellow: '#f5f543',
                brightBlue: '#3b8eea',
                brightMagenta: '#d670d6',
                brightCyan: '#29b8db',
                brightWhite: '#e5e5e5'
            },
            scrollback: 1000,
            tabStopWidth: 4
        });

        // 创建 fit addon
        if (typeof FitAddon !== 'undefined') {
            this.fitAddon = new FitAddon.FitAddon();
            this.term.loadAddon(this.fitAddon);
        }

        // 打开终端
        const wrapper = DOM.$('#terminal-wrapper');
        if (wrapper) {
            this.term.open(wrapper);
            if (this.fitAddon) {
                this.fitAddon.fit();
            }
        }

        // 只绑定一次用户输入监听器
        this.term.onData((data) => {
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'input', data }));
            }
        });

        // 监听窗口大小变化
        window.addEventListener('resize', this._handleResize.bind(this));
    },

    _connect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        if (!this.term) return;

        // 显示连接提示
        this.term.writeln('\x1b[1;32m正在连接到主机...\x1b[0m');

        // 建立 WebSocket 连接
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/terminal/${this.hostId}`;

        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            this.term.writeln('\x1b[1;32m连接成功！\x1b[0m\r\n');

            // 发送初始终端大小
            if (this.fitAddon) {
                const { cols, rows } = this.term;
                this.ws.send(JSON.stringify({ type: 'resize', cols, rows }));
            }
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                if (msg.type === 'output') {
                    this.term.write(msg.data);
                } else if (msg.type === 'error') {
                    this.term.writeln(`\r\n\x1b[1;31m错误: ${msg.message}\x1b[0m\r\n`);
                }
            } catch (e) {
                console.error('Failed to parse WebSocket message:', e);
            }
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.term.writeln('\r\n\x1b[1;31m连接错误\x1b[0m\r\n');
        };

        this.ws.onclose = () => {
            this.term.writeln('\r\n\x1b[1;33m连接已断开\x1b[0m\r\n');
        };
    },

    _handleResize() {
        if (this.fitAddon && this.term) {
            this.fitAddon.fit();
            const { cols, rows } = this.term;
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify({ type: 'resize', cols, rows }));
            }
        }
    },

    cleanup() {
        window.removeEventListener('resize', this._handleResize.bind(this));

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        if (this.term) {
            this.term.dispose();
            this.term = null;
        }

        this.fitAddon = null;
        this.container = null;
        this.hostId = null;
    }
};
