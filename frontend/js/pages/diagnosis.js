/* AI Diagnosis page */
const DiagnosisPage = {
    ws: null,
    currentSessionId: null,
    selectedModelId: null,

    async render() {
        const content = DOM.$('#page-content');

        // Header with connection and model selectors only
        const headerActions = DOM.el('div', { className: 'flex gap-8' });
        const connSelect = DOM.el('select', { className: 'form-select', style: { minWidth: '200px' } });
        connSelect.appendChild(DOM.el('option', { value: '', textContent: 'Select connection...' }));

        try {
            const connections = await API.getConnections();
            Store.set('connections', connections);
            const current = Store.get('currentConnection');
            for (const c of connections) {
                const opt = DOM.el('option', { value: c.id, textContent: `${c.name} (${c.db_type})` });
                if (current && c.id === current.id) opt.selected = true;
                connSelect.appendChild(opt);
            }
        } catch (e) { /* ignore */ }

        connSelect.addEventListener('change', () => {
            const id = parseInt(connSelect.value);
            if (id) {
                const conns = Store.get('connections') || [];
                Store.set('currentConnection', conns.find(c => c.id === id));
            }
        });

        // Model selector
        const modelSelect = DOM.el('select', { className: 'form-select', style: { minWidth: '200px' } });
        modelSelect.appendChild(DOM.el('option', { value: '', textContent: 'Default model' }));

        try {
            const models = await API.getAIModels();
            for (const m of models) {
                const opt = DOM.el('option', { value: m.id, textContent: m.name });
                if (m.is_default) opt.selected = true;
                modelSelect.appendChild(opt);
            }
        } catch (e) { /* ignore */ }

        modelSelect.addEventListener('change', () => {
            this.selectedModelId = modelSelect.value ? parseInt(modelSelect.value) : null;
        });

        headerActions.appendChild(connSelect);
        headerActions.appendChild(modelSelect);
        Header.render('AI Diagnosis', headerActions);

        // Two-column layout: sessions sidebar + chat area
        content.innerHTML = '';
        const layout = DOM.el('div', { style: { display: 'flex', height: 'calc(100vh - 56px)', gap: '0' } });

        // Left sidebar: session list
        const sidebar = DOM.el('div', {
            style: {
                width: '280px',
                borderRight: '1px solid var(--border-color)',
                display: 'flex',
                flexDirection: 'column',
                background: 'var(--bg-secondary)'
            }
        });

        const sidebarHeader = DOM.el('div', {
            style: {
                padding: '12px',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex',
                gap: '8px'
            }
        });
        sidebarHeader.appendChild(DOM.el('button', {
            className: 'btn btn-primary btn-sm',
            innerHTML: '<i data-lucide="plus"></i> New',
            style: { flex: '1' },
            onClick: () => this._createSession()
        }));
        sidebarHeader.appendChild(DOM.el('button', {
            className: 'btn btn-danger btn-sm',
            innerHTML: '<i data-lucide="trash-2"></i>',
            onClick: () => this._deleteSession()
        }));

        const sessionList = DOM.el('div', {
            id: 'session-list',
            style: { flex: '1', overflowY: 'auto', padding: '8px' }
        });

        sidebar.appendChild(sidebarHeader);
        sidebar.appendChild(sessionList);

        // Right area: chat
        const chatContainer = DOM.el('div', {
            className: 'chat-container',
            style: { flex: '1', display: 'flex', flexDirection: 'column' }
        });

        chatContainer.appendChild(ChatWidget.createMessagesContainer());
        chatContainer.appendChild(ChatWidget.createInputBar((text) => this._sendMessage(text)));

        ChatWidget.onStop = () => this._stopGeneration();
        ChatWidget.onClear = () => this._clearSession();

        layout.appendChild(sidebar);
        layout.appendChild(chatContainer);
        content.appendChild(layout);
        lucide.createIcons();

        await this._loadSessions();

        return () => this._cleanup();
    },

    async _loadSessions() {
        try {
            const sessions = await API.getChatSessions();
            Store.set('chatSessions', sessions);
            const list = DOM.$('#session-list');
            if (!list) return;
            list.innerHTML = '';

            if (sessions.length === 0) {
                await this._createSession();
                return;
            }

            for (const s of sessions) {
                const item = DOM.el('div', {
                    className: `session-item ${this.currentSessionId === s.id ? 'active' : ''}`,
                    style: {
                        padding: '10px 12px',
                        marginBottom: '4px',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        background: this.currentSessionId === s.id ? 'var(--accent-blue)' : 'transparent',
                        color: this.currentSessionId === s.id ? '#fff' : 'var(--text-primary)',
                        fontSize: '14px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap'
                    },
                    textContent: s.title.substring(0, 40) || 'Session ' + s.id,
                    onClick: () => this._switchSession(s.id)
                });
                item.addEventListener('mouseenter', () => {
                    if (this.currentSessionId !== s.id) {
                        item.style.background = 'var(--bg-hover)';
                    }
                });
                item.addEventListener('mouseleave', () => {
                    if (this.currentSessionId !== s.id) {
                        item.style.background = 'transparent';
                    }
                });
                list.appendChild(item);
            }

            if (!this.currentSessionId && sessions.length > 0) {
                this._switchSession(sessions[0].id);
            }
        } catch (e) {
            Toast.error('Failed to load sessions');
        }
    },

    async _createSession() {
        const conn = Store.get('currentConnection');
        try {
            const session = await API.createChatSession({
                connection_id: conn?.id || null,
                title: 'New Session'
            });
            this.currentSessionId = session.id;
            await this._loadSessions();
            this._switchSession(session.id);
        } catch (e) {
            Toast.error('Failed to create session: ' + e.message);
        }
    },

    async _switchSession(sessionId) {
        this.currentSessionId = sessionId;
        this._connectWebSocket(sessionId);

        // Update tab styles
        DOM.$$('#session-tabs .btn').forEach(btn => {
            btn.className = 'btn btn-sm btn-secondary';
        });
        const tabs = DOM.$$('#session-tabs .btn');
        const sessions = Store.get('chatSessions') || [];
        const idx = sessions.findIndex(s => s.id === sessionId);
        if (idx >= 0 && tabs[idx]) {
            tabs[idx].className = 'btn btn-sm btn-primary';
        }

        // Load messages
        try {
            const messages = await API.getSessionMessages(sessionId);
            ChatWidget.loadMessages(messages);
        } catch (e) {
            // Empty session
            const container = DOM.$('#chat-messages');
            if (container) {
                container.innerHTML = `
                    <div class="empty-state" style="padding:40px">
                        <i data-lucide="bot"></i>
                        <h3>DBMaster AI</h3>
                        <p>Ask me anything about your database. I can analyze performance, diagnose issues, review configurations, and suggest optimizations.</p>
                    </div>
                `;
                lucide.createIcons();
            }
        }
    },

    _connectWebSocket(sessionId) {
        if (this.ws) {
            this.ws.disconnect();
        }
        this.ws = new WSManager(`/ws/chat/${sessionId}`);
        this.ws.on('message', (data) => this._handleWSMessage(data));
        this.ws.on('error', () => Toast.error('Chat connection error'));
        this.ws.connect();
    },

    _sendMessage(text) {
        if (!text || ChatWidget.isStreaming) return;
        if (!this.ws || !this.currentSessionId) {
            Toast.warning('No active session');
            return;
        }

        const conn = Store.get('currentConnection');
        ChatWidget.addUserMessage(text);
        ChatWidget.startAssistantMessage();
        ChatWidget.isStreaming = true;

        this.ws.send({
            message: text,
            connection_id: conn?.id || null,
            model_id: this.selectedModelId
        });
    },

    _handleWSMessage(data) {
        switch (data.type) {
            case 'content':
                ChatWidget.appendContent(data.content);
                break;
            case 'tool_call':
                ChatWidget.addToolCall(data.tool_name, data.tool_args);
                break;
            case 'tool_result':
                ChatWidget.addToolResult(data.tool_name, data.result);
                break;
            case 'done':
                ChatWidget.finishAssistantMessage();
                break;
            case 'error':
                ChatWidget.showError(data.content);
                break;
        }
    },

    async _clearSession() {
        if (!this.currentSessionId) {
            Toast.warning('No active session');
            return;
        }
        if (!confirm('Clear all messages in this session? This cannot be undone.')) return;
        try {
            await API.clearSessionMessages(this.currentSessionId);
            const container = DOM.$('#chat-messages');
            if (container) {
                container.innerHTML = `
                    <div class="empty-state" style="padding:40px">
                        <i data-lucide="bot"></i>
                        <h3>DBMaster AI</h3>
                        <p>Ask me anything about your database. I can analyze performance, diagnose issues, review configurations, and suggest optimizations.</p>
                    </div>
                `;
                lucide.createIcons();
            }
            // Update session tab title
            await this._loadSessions();
            Toast.success('Session cleared');
        } catch (e) {
            Toast.error('Failed to clear session: ' + e.message);
        }
    },

    _stopGeneration() {
        if (this.ws) {
            this.ws.disconnect();
            this._connectWebSocket(this.currentSessionId);
        }
        ChatWidget.finishAssistantMessage();
        Toast.info('Generation stopped');
    },

    async _deleteSession() {
        if (!this.currentSessionId) {
            Toast.warning('No active session');
            return;
        }
        const sessions = Store.get('chatSessions') || [];
        const session = sessions.find(s => s.id === this.currentSessionId);
        if (!confirm(`Delete session "${session?.title || 'Session ' + this.currentSessionId}"?`)) return;
        try {
            await API.deleteChatSession(this.currentSessionId);
            Toast.success('Session deleted');
            this.currentSessionId = null;
            await this._loadSessions();
        } catch (e) {
            Toast.error('Failed to delete session: ' + e.message);
        }
    },

    async _deleteSession() {
        if (!this.currentSessionId) {
            Toast.warning('No active session');
            return;
        }
        try {
            await API.deleteChatSession(this.currentSessionId);
            this.currentSessionId = null;
            await this._loadSessions();
            Toast.success('Session deleted');
        } catch (e) {
            Toast.error('Failed to delete session: ' + e.message);
        }
    },

    _cleanup() {
        if (this.ws) {
            this.ws.disconnect();
            this.ws = null;
        }
        this.currentSessionId = null;
    }
};
