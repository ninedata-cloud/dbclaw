/* AI Diagnosis page */
const DiagnosisPage = {
    ws: null,
    currentSessionId: null,
    selectedModelId: null,
    selectedKBIds: [],
    disabledTools: [],
    highRiskTools: [],

    async render() {
        const content = DOM.$('#page-content');

        // Load high-risk tools list
        try {
            this.highRiskTools = await API.getHighRiskTools();
        } catch (e) { /* ignore */ }

        // Header with connection, model, KB selectors, and tool safety toggle
        const headerActions = DOM.el('div', { className: 'flex gap-8' });
        const connSelect = DOM.el('select', { className: 'form-select', style: { minWidth: '200px' } });
        connSelect.appendChild(DOM.el('option', { value: '', textContent: '选择数据源...' }));

        try {
            const datasources = await API.getDatasources();
            Store.set('datasources', datasources);
            const current = Store.get('currentDatasource');
            for (const c of datasources) {
                const opt = DOM.el('option', { value: c.id, textContent: `${c.name} (${c.db_type})` });
                if (current && c.id === current.id) opt.selected = true;
                connSelect.appendChild(opt);
            }
        } catch (e) { /* ignore */ }

        connSelect.addEventListener('change', () => {
            const id = parseInt(connSelect.value);
            if (id) {
                const conns = Store.get('datasources') || [];
                Store.set('currentDatasource', conns.find(c => c.id === id));
            }
        });

        // Model selector
        const modelSelect = DOM.el('select', { className: 'form-select', style: { minWidth: '200px' } });
        modelSelect.appendChild(DOM.el('option', { value: '', textContent: '默认模型' }));

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

        // Knowledge Base multi-select
        const kbSelect = DOM.el('select', {
            className: 'form-select',
            style: { minWidth: '200px' },
            multiple: true,
            size: 1
        });
        kbSelect.appendChild(DOM.el('option', { value: '', textContent: '无知识库', disabled: true }));

        try {
            const kbs = await API.getKnowledgeBases();
            if (kbs.length > 0) {
                kbSelect.innerHTML = '';
                for (const kb of kbs.filter(k => k.is_active)) {
                    const opt = DOM.el('option', { value: kb.id, textContent: kb.name });
                    kbSelect.appendChild(opt);
                }
            }
        } catch (e) { /* ignore */ }

        kbSelect.addEventListener('change', () => {
            this.selectedKBIds = Array.from(kbSelect.selectedOptions).map(opt => parseInt(opt.value));
        });

        // Tool safety settings button
        const toolSafetyBtn = DOM.el('button', {
            className: 'btn btn-sm btn-secondary',
            innerHTML: '<i data-lucide="shield"></i> 工具安全',
            title: 'Configure high-risk tool permissions',
            onClick: () => this._showToolSafetyModal()
        });

        headerActions.appendChild(connSelect);
        headerActions.appendChild(modelSelect);
        headerActions.appendChild(kbSelect);
        headerActions.appendChild(toolSafetyBtn);
        Header.render('AI 诊断', headerActions);

        // Two-column layout: sessions sidebar + chat area
        content.innerHTML = '';
        const layout = DOM.el('div', { style: { display: 'flex', height: 'calc(100vh - 56px)', gap: '0', position: 'relative' } });

        // Left sidebar: session list
        const sidebar = DOM.el('div', {
            id: 'session-sidebar',
            style: {
                width: '280px',
                height: '100%',
                borderRight: '1px solid var(--border-color)',
                display: 'flex',
                flexDirection: 'column',
                background: 'var(--bg-secondary)',
                transition: 'width 0.3s ease',
                overflow: 'hidden'
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

        const sessionList = DOM.el('div', {
            id: 'session-list',
            style: { flex: '1', overflowY: 'auto', padding: '8px' }
        });

        sidebar.appendChild(sidebarHeader);
        sidebar.appendChild(sessionList);

        // Right area: chat with tool panel
        const chatContainer = DOM.el('div', {
            className: 'chat-container',
            style: { flex: '1', display: 'flex', flexDirection: 'row', gap: '0', height: '100%' }
        });

        // Main chat area
        const chatMain = DOM.el('div', {
            style: { flex: '1', display: 'flex', flexDirection: 'column', minWidth: '0', position: 'relative', height: '100%' }
        });

        // Toggle buttons container (floating on chat area)
        const toggleButtonsContainer = DOM.el('div', {
            style: {
                position: 'absolute',
                top: '12px',
                left: '12px',
                right: '12px',
                display: 'flex',
                justifyContent: 'space-between',
                zIndex: '10',
                pointerEvents: 'none'
            }
        });

        // Left sidebar toggle button
        const toggleSidebarBtn = DOM.el('button', {
            className: 'btn btn-sm btn-secondary',
            innerHTML: '<i data-lucide="panel-left-close"></i>',
            title: 'Hide sessions',
            id: 'toggle-sidebar-btn',
            style: {
                padding: '6px 10px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                pointerEvents: 'auto'
            },
            onClick: () => {
                const sidebar = DOM.$('#session-sidebar');
                const btn = DOM.$('#toggle-sidebar-btn');
                if (sidebar && btn) {
                    const isCollapsed = sidebar.style.width === '0px' || sidebar.style.width === '0';
                    if (isCollapsed) {
                        sidebar.style.width = '280px';
                        sidebar.style.display = 'flex';
                        btn.innerHTML = '<i data-lucide="panel-left-close"></i>';
                        btn.title = 'Hide sessions';
                    } else {
                        sidebar.style.width = '0px';
                        sidebar.style.display = 'none';
                        btn.innerHTML = '<i data-lucide="panel-left-open"></i>';
                        btn.title = 'Show sessions';
                    }
                    requestAnimationFrame(() => DOM.createIcons());
                }
            }
        });

        // Right tool panel toggle button
        const togglePanelBtn = DOM.el('button', {
            className: 'btn btn-sm btn-secondary',
            innerHTML: '<i data-lucide="panel-right-close"></i>',
            title: 'Hide tool panel',
            id: 'toggle-tool-panel-btn',
            style: {
                padding: '6px 10px',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                pointerEvents: 'auto'
            },
            onClick: () => {
                const panel = DOM.$('#tool-execution-panel');
                const btn = DOM.$('#toggle-tool-panel-btn');
                if (panel && btn) {
                    const isCollapsed = panel.style.width === '0px' || panel.style.width === '0';
                    if (isCollapsed) {
                        panel.style.width = '400px';
                        panel.style.display = 'flex';
                        btn.innerHTML = '<i data-lucide="panel-right-close"></i>';
                        btn.title = 'Hide tool panel';
                    } else {
                        panel.style.width = '0px';
                        panel.style.display = 'none';
                        btn.innerHTML = '<i data-lucide="panel-right-open"></i>';
                        btn.title = 'Show tool panel';
                    }
                    requestAnimationFrame(() => DOM.createIcons());
                }
            }
        });

        toggleButtonsContainer.appendChild(toggleSidebarBtn);
        toggleButtonsContainer.appendChild(togglePanelBtn);

        chatMain.appendChild(toggleButtonsContainer);
        chatMain.appendChild(ChatWidget.createMessagesContainer());
        chatMain.appendChild(ChatWidget.createInputBar(
            (text, attachments) => this._sendMessage(text, attachments),
            () => this.currentSessionId
        ));

        // Tool execution panel (right side)
        const toolPanel = DOM.el('div', {
            id: 'tool-execution-panel',
            style: {
                width: '400px',
                height: '100%',
                borderLeft: '1px solid var(--border-color)',
                background: 'var(--bg-secondary)',
                display: 'flex',
                flexDirection: 'column',
                overflow: 'hidden',
                transition: 'width 0.3s ease'
            }
        });

        const toolPanelHeader = DOM.el('div', {
            style: {
                padding: '12px 16px',
                borderBottom: '1px solid var(--border-color)',
                fontWeight: '600',
                fontSize: '13px',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
            }
        });

        const toolHeaderLeft = DOM.el('div', {
            style: { flex: '1', display: 'flex', alignItems: 'center', gap: '8px' }
        });
        toolHeaderLeft.innerHTML = '<i data-lucide="activity"></i> skill调用';

        const clearToolsBtn = DOM.el('button', {
            className: 'btn btn-sm btn-secondary',
            innerHTML: '<i data-lucide="trash-2"></i>',
            title: 'Clear tool history',
            style: { padding: '4px 8px' },
            onClick: () => {
                const toolPanelContent = DOM.$('#tool-panel-content');
                if (toolPanelContent) {
                    toolPanelContent.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:12px;">暂无skill调用记录</div>';
                    DOM.createIcons();
                }
            }
        });

        toolPanelHeader.appendChild(toolHeaderLeft);
        toolPanelHeader.appendChild(clearToolsBtn);

        const toolPanelContent = DOM.el('div', {
            id: 'tool-panel-content',
            style: {
                flex: '1',
                overflowY: 'auto',
                padding: '12px'
            }
        });
        toolPanelContent.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:12px;">暂无skill调用记录</div>';

        toolPanel.appendChild(toolPanelHeader);
        toolPanel.appendChild(toolPanelContent);

        chatContainer.appendChild(chatMain);
        chatContainer.appendChild(toolPanel);

        ChatWidget.onStop = () => this._stopGeneration();
        ChatWidget.onClear = () => this._clearSession();

        layout.appendChild(sidebar);
        layout.appendChild(chatContainer);
        content.appendChild(layout);
        DOM.createIcons();

        await this._loadSessions();

        return () => this._cleanup();
    },

    _showToolSafetyModal() {
        if (this.highRiskTools.length === 0) {
            Toast.info('No high-risk tools available to configure');
            return;
        }

        // Categorize tools by danger level
        const dangerousTools = this.highRiskTools.filter(t => t.description.includes('⚠️ DANGEROUS'));
        const normalTools = this.highRiskTools.filter(t => !t.description.includes('⚠️ DANGEROUS'));

        const renderToolSection = (tools, title, warningText = null) => {
            if (tools.length === 0) return '';

            const toolItems = tools.map(tool => {
                const is已禁用 = this.disabledTools.includes(tool.name);
                const isDangerous = tool.description.includes('⚠️ DANGEROUS');
                const cleanDesc = tool.description.replace('⚠️ DANGEROUS: ', '');

                return `
                    <label style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:6px;cursor:pointer;background:var(--bg-secondary);margin-bottom:6px;border-left:3px solid ${isDangerous ? 'var(--accent-red)' : 'var(--accent-blue)'};">
                        <input type="checkbox" class="tool-toggle" data-tool="${tool.name}" ${is已禁用 ? '' : 'checked'}>
                        <div style="flex:1;">
                            <div style="font-weight:500;font-size:14px;display:flex;align-items:center;gap:6px;">
                                ${isDangerous ? '<span style="color:var(--accent-red);">⚠️</span>' : ''}
                                ${tool.name}
                            </div>
                            <div style="font-size:12px;opacity:0.7;">${cleanDesc}</div>
                        </div>
                        <span class="badge ${is已禁用 ? 'badge-danger' : 'badge-success'}" id="badge-${tool.name}">
                            ${is已禁用 ? '已禁用' : '已启用'}
                        </span>
                    </label>
                `;
            }).join('');

            return `
                <div style="margin-bottom:20px;">
                    <h4 style="font-size:14px;font-weight:600;margin-bottom:8px;color:var(--text-primary);">${title}</h4>
                    ${warningText ? `<div style="background:rgba(248,81,73,0.1);border-left:3px solid var(--accent-red);padding:8px 12px;margin-bottom:10px;font-size:12px;border-radius:4px;">${warningText}</div>` : ''}
                    ${toolItems}
                </div>
            `;
        };

        Modal.show({
            title: '🛡️ 工具安全 Settings',
            content: `
                <p style="margin-bottom:16px;font-size:13px;opacity:0.8;">
                    Control which tools the AI is allowed to use during diagnosis.
                    已禁用 tools will be blocked for new sessions. Changes apply when creating a new session.
                </p>
                <div id="tool-safety-list">
                    ${renderToolSection(normalTools, '📊 Standard Diagnostic Tools', null)}
                    ${renderToolSection(dangerousTools, '⚠️ Dangerous Administrative Tools',
                        '<strong>WARNING:</strong> These tools can modify database data, structure, and system configuration. Only enable if you fully understand the risks and trust the AI to make changes.')}
                </div>
            `,
            buttons: [
                { text: 'Cancel', variant: 'secondary', onClick: () => Modal.hide() },
                { text: 'Apply Settings', variant: 'primary', onClick: () => this._applyToolSafety() }
            ]
        });

        // Add live badge toggle on checkbox change
        document.querySelectorAll('.tool-toggle').forEach(cb => {
            cb.addEventListener('change', () => {
                const badge = document.getElementById(`badge-${cb.dataset.tool}`);
                if (badge) {
                    badge.className = `badge ${cb.checked ? 'badge-success' : 'badge-danger'}`;
                    badge.textContent = cb.checked ? '已启用' : '已禁用';
                }
            });
        });
    },

    _applyToolSafety() {
        const checkboxes = document.querySelectorAll('.tool-toggle');
        this.disabledTools = [];
        checkboxes.forEach(cb => {
            if (!cb.checked) {
                this.disabledTools.push(cb.dataset.tool);
            }
        });
        Modal.hide();
        if (this.disabledTools.length > 0) {
            Toast.info(`${this.disabledTools.length} tool(s) disabled. Takes effect on next new session.`);
        } else {
            Toast.success('All high-risk tools enabled.');
        }
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
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        position: 'relative'
                    }
                });
                item._sessionId = s.id;

                const titleSpan = DOM.el('span', {
                    style: {
                        flex: '1',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap'
                    },
                    textContent: s.title.substring(0, 40) || '会话 ' + s.id
                });

                const deleteBtn = DOM.el('button', {
                    className: 'session-delete-btn',
                    innerHTML: '<i data-lucide="trash-2" style="width:14px;height:14px;"></i>',
                    style: {
                        opacity: '0',
                        padding: '4px',
                        background: 'rgba(248,81,73,0.2)',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        transition: 'opacity 0.2s ease',
                        color: 'var(--accent-red)'
                    },
                    onClick: (e) => {
                        e.stopPropagation();
                        this._deleteSessionById(s.id);
                    }
                });

                item.appendChild(titleSpan);
                item.appendChild(deleteBtn);

                item.addEventListener('click', () => this._switchSession(s.id));
                item.addEventListener('mouseenter', () => {
                    if (this.currentSessionId !== s.id) {
                        item.style.background = 'var(--bg-hover)';
                    }
                    deleteBtn.style.opacity = '1';
                });
                item.addEventListener('mouseleave', () => {
                    if (this.currentSessionId !== s.id) {
                        item.style.background = 'transparent';
                    }
                    deleteBtn.style.opacity = '0';
                });
                list.appendChild(item);
            }

            if (!this.currentSessionId && sessions.length > 0) {
                this._switchSession(sessions[0].id);
            }
        } catch (e) {
            Toast.error('加载失败 sessions');
        }
    },

    async _createSession() {
        const conn = Store.get('currentDatasource');
        try {
            const session = await API.createChatSession({
                datasource_id: conn?.id || null,
                title: '新建会话',
                ai_model_id: this.selectedModelId,
                kb_ids: this.selectedKBIds.length > 0 ? this.selectedKBIds : null,
                disabled_tools: this.disabledTools.length > 0 ? this.disabledTools : null
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

        // Update sidebar highlight
        const list = DOM.$('#session-list');
        if (list) {
            list.querySelectorAll('.session-item').forEach(item => {
                const isActive = item._sessionId === sessionId;
                item.style.background = isActive ? 'var(--accent-blue)' : 'transparent';
                item.style.color = isActive ? '#fff' : 'var(--text-primary)';
            });
        }

        // Load messages
        try {
            const messages = await API.getSessionMessages(sessionId);
            console.log(`Loaded ${messages.length} messages for session ${sessionId}`, messages);

            if (messages && messages.length > 0) {
                ChatWidget.loadMessages(messages);
            } else {
                // Empty session - show welcome message
                const container = DOM.$('#chat-messages');
                if (container) {
                    container.innerHTML = `
                        <div class="empty-state" style="padding:40px">
                            <i data-lucide="bot"></i>
                            <h3>数据库智能卫士</h3>
                            <p>关于您的数据库，有任何问题都可以问我。我可以分析性能、诊断问题、审查配置并提出优化建议。</p>
                        </div>
                    `;
                    DOM.createIcons();
                }
            }
        } catch (e) {
            console.error('加载失败 messages:', e);
            Toast.error('加载失败 session messages: ' + e.message);
            // Show empty state on error
            const container = DOM.$('#chat-messages');
            if (container) {
                container.innerHTML = `
                    <div class="empty-state" style="padding:40px">
                        <i data-lucide="alert-circle"></i>
                        <h3>Error Loading Messages</h3>
                        <p>${e.message}</p>
                    </div>
                `;
                DOM.createIcons();
            }
        }
    },

    _connectWebSocket(sessionId) {
        if (this.ws) {
            this.ws.shouldReconnect = false; // Disable reconnect before manual disconnect
            this.ws.disconnect();
        }

        const ws = new WSManager(`/ws/chat/${sessionId}`);
        this.ws = ws;

        ws.on('message', (data) => this._handleWSMessage(data));
        ws.on('error', (error) => {
            // Log error for debugging
            console.error('WebSocket error:', error);
            // Error details will be provided in close event
        });
        ws.on('close', (event) => {
            // Log close event for debugging
            console.log('WebSocket closed:', {
                code: event?.code,
                reason: event?.reason,
                wasClean: event?.wasClean,
                shouldReconnect: ws.shouldReconnect
            });

            if (event && event.code === 1008) {
                // Authentication error
                Toast.error('Session expired. Please log in again.');
                setTimeout(() => {
                    localStorage.removeItem('auth_token');
                    window.location.href = '#/login';
                }, 2000);
            } else if (event && event.code === 1000) {
                // Normal closure - no error needed
                console.log('WebSocket closed normally');
            } else if (event && event.code === 1001) {
                // Going away (e.g., page navigation) - no error needed
                console.log('WebSocket closed: going away');
            } else if (event && ws.shouldReconnect) {
                // Abnormal closure and not manually disconnected
                const reason = event.reason || 'Unknown error';
                const errorMsg = `Chat connection lost (code ${event.code}): ${reason}. Please refresh the page.`;
                console.error('WebSocket abnormal closure:', event.code, reason);

                // Show error in chat widget
                ChatWidget.showError(errorMsg);

                // Also show toast
                Toast.error(errorMsg);
            }
        });
        ws.connect();
    },

    _sendMessage(text) {
        if (!text && (!ChatWidget.attachments || ChatWidget.attachments.length === 0)) return;
        if (ChatWidget.isStreaming) return;
        if (!this.ws || !this.currentSessionId) {
            Toast.warning('No active session');
            return;
        }

        const conn = Store.get('currentDatasource');
        const attachments = ChatWidget.attachments || [];

        ChatWidget.addUserMessage(text, attachments);
        ChatWidget.startAssistantMessage();
        ChatWidget.isStreaming = true;

        this.ws.send({
            message: text,
            datasource_id: conn?.id || null,
            model_id: this.selectedModelId,
            attachments: attachments
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
                ChatWidget.addToolResult(data.tool_name, data.result, data.execution_time_ms);
                break;
            case 'done':
                ChatWidget.finishAssistantMessage();
                // Refresh session list to update title after first message
                this._loadSessions();
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
                        <h3>数据库智能卫士</h3>
                        <p>关于您的数据库，有任何问题都可以问我。我可以分析性能、诊断问题、审查配置并提出优化建议。</p>
                    </div>
                `;
                DOM.createIcons();
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
        if (!confirm(`Delete session "${session?.title || '会话 ' + this.currentSessionId}"?`)) return;
        try {
            await API.deleteChatSession(this.currentSessionId);
            this.currentSessionId = null;
            await this._loadSessions();
            Toast.success('Session deleted');
        } catch (e) {
            Toast.error('Failed to delete session: ' + e.message);
        }
    },

    async _deleteSessionById(sessionId) {
        const sessions = Store.get('chatSessions') || [];
        const session = sessions.find(s => s.id === sessionId);
        if (!confirm(`Delete session "${session?.title || '会话 ' + sessionId}"?`)) return;
        try {
            await API.deleteChatSession(sessionId);
            if (this.currentSessionId === sessionId) {
                this.currentSessionId = null;
            }
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
