/* AI Diagnosis page */
const DiagnosisPage = {
    ws: null,
    datasourceSelector: null,
    datasourceClickOutsideHandler: null,
    _renderOptions: null,
    _container: null,
    currentSessionId: null,
    selectedModelId: null,
    disabledTools: [],
    highRiskTools: [],
    availableModels: [],
    sessionTokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
    _pendingResumeState: null,
    _toolCheckboxes: null,
    _modelSelectEl: null,

    _getSelectedDatasource() {
        return this.datasourceSelector?.getValue() || Store.get('currentDatasource') || null;
    },

    async render() {
        return this.renderWithOptions({});
    },

    async renderFromRoute(routeParam = '') {
        const params = new URLSearchParams(routeParam || '');
        const datasourceId = parseInt(params.get('datasource'), 10);
        return this.renderWithOptions({
            initialDatasourceId: Number.isFinite(datasourceId) ? datasourceId : null,
            initialAsk: params.get('ask') || null,
        });
    },

    async renderWithOptions(options = {}) {
        this._renderOptions = options || {};
        const content = options.container || DOM.$('#page-content');
        this._container = content;

        // Load high-risk tools list
        try {
            this.highRiskTools = await API.getHighRiskTools();
        } catch (e) { /* ignore */ }

        // Header with connection, model and tool safety toggle
        const headerActions = DOM.el('div', { className: 'flex gap-8', style: { flex: '1', minWidth: '0' } });
        try {
            const datasources = await API.getDatasources();
            Store.set('datasources', datasources);
            if (options.fixedDatasourceId) {
                const fixedDatasource = datasources.find(item => item.id === options.fixedDatasourceId) || null;
                if (fixedDatasource) {
                    Store.set('currentDatasource', fixedDatasource);
                }
            } else if (options.initialDatasourceId) {
                const initialDatasource = datasources.find(item => item.id === options.initialDatasourceId) || null;
                if (initialDatasource) {
                    Store.set('currentDatasource', initialDatasource);
                }
            }
        } catch (e) { /* ignore */ }

        this.datasourceSelector?.destroy();
        if (options.fixedDatasourceId) {
            this.datasourceSelector = {
                destroy() {},
                getValue: () => Store.get('currentDatasource') || null,
                getSelectedDatasource: () => Store.get('currentDatasource') || null,
                setValue: (datasourceId) => {
                    const allDatasources = Store.get('datasources') || [];
                    const datasource = allDatasources.find(item => item.id === datasourceId) || null;
                    Store.set('currentDatasource', datasource);
                }
            };
        } else {
            const datasourceContainer = DOM.el('div', {
                id: 'diagnosis-datasource-selector',
                style: { minWidth: '280px', maxWidth: '380px', flex: '1' }
            });
            this.datasourceSelector = new DatasourceSelector({
                container: datasourceContainer,
                allowEmpty: true,
                emptyText: '选择数据源...',
                placeholder: '选择数据源',
                showStatus: true,
                showDetails: true,
                onLoad: () => {
                    const current = Store.get('currentDatasource');
                    if (current?.id) {
                        this.datasourceSelector.setValue(current.id);
                    } else {
                        this.datasourceSelector.setValue(null);
                    }
                },
                onChange: (datasource) => {
                    Store.set('currentDatasource', datasource || null);
                }
            });
            headerActions.appendChild(datasourceContainer);
        }

        // Model selector
        const modelSelect = DOM.el('select', { className: 'form-select', style: { minWidth: '150px', maxWidth: '200px', flex: '0 1 auto' } });
        this._modelSelectEl = modelSelect;
        modelSelect.appendChild(DOM.el('option', { value: '', textContent: '默认模型' }));

        try {
            const models = await API.getAIModels();
            this.availableModels = models;
            for (const m of models) {
                const opt = DOM.el('option', { value: m.id, textContent: m.name });
                if (m.is_default) {
                    opt.selected = true;
                    this.selectedModelId = m.id;
                }
                modelSelect.appendChild(opt);
            }
        } catch (e) { /* ignore */ }

        modelSelect.addEventListener('change', () => {
            this.selectedModelId = modelSelect.value ? parseInt(modelSelect.value) : null;
            this._updateTokenUsageDisplay();
        });

        if (this.datasourceClickOutsideHandler) {
            document.removeEventListener('click', this.datasourceClickOutsideHandler);
        }
        this.datasourceClickOutsideHandler = () => {};
        document.addEventListener('click', this.datasourceClickOutsideHandler);

        // Tool safety settings button
        const toolSafetyBtn = DOM.el('button', {
            className: 'btn btn-sm btn-secondary',
            innerHTML: '<i data-lucide="shield"></i> 工具安全',
            title: 'Configure high-risk tool permissions',
            onClick: () => this._showToolSafetyModal()
        });

        const clearSessionBtn = DOM.el('button', {
            className: 'btn btn-sm btn-secondary',
            innerHTML: '<i data-lucide="eraser"></i> 清除会话',
            title: '清除当前会话',
            onClick: () => this._clearSession()
        });

        headerActions.appendChild(modelSelect);
        headerActions.appendChild(toolSafetyBtn);
        headerActions.appendChild(clearSessionBtn);

        // Two-column layout: sessions sidebar + chat area
        content.innerHTML = '';
        if (options.embedded) {
            content.style.display = 'flex';
            content.style.flexDirection = 'column';
            content.style.minHeight = '0';
            content.style.height = '100%';
            const embeddedToolbar = DOM.el('div', {
                className: 'instance-embedded-toolbar',
                style: {
                    display: 'flex',
                    gap: '12px',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: '16px',
                    flexWrap: 'wrap'
                }
            });
            embeddedToolbar.appendChild(DOM.el('div', {
                className: 'instance-embedded-title',
                textContent: 'AI 对话诊断'
            }));
            embeddedToolbar.appendChild(headerActions);
            content.appendChild(embeddedToolbar);
        } else {
            Header.render('AI 诊断', headerActions);
        }
        const layout = DOM.el('div', {
            style: options.embedded
                ? { display: 'flex', flex: '1', minHeight: '0', gap: '0', position: 'relative' }
                : { display: 'flex', height: 'calc(100vh - 56px)', gap: '0', position: 'relative' }
        });

        // Left sidebar: session list
        const sidebar = DOM.el('div', {
            id: 'session-sidebar',
            style: {
                width: '280px',
                minWidth: '280px',
                flexShrink: '0',
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
            id: 'sidebar-header',
            style: {
                padding: '12px',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex',
                gap: '8px',
                alignItems: 'center'
            }
        });

        // New session button (icon only)
        const newSessionBtn = DOM.el('button', {
            className: 'btn-icon-only',
            innerHTML: '<i data-lucide="plus"></i>',
            title: '新建会话',
            style: { flex: '1' },
            onClick: () => this._createSession()
        });

        // Toggle sidebar button
        const toggleSidebarBtn = DOM.el('button', {
            className: 'btn-icon-only',
            id: 'sidebar-toggle-btn',
            innerHTML: '<i data-lucide="panel-left-close"></i>',
            title: '隐藏会话列表',
            onClick: () => this._toggleSidebar()
        });

        sidebarHeader.appendChild(newSessionBtn);
        sidebarHeader.appendChild(toggleSidebarBtn);

        const sessionList = DOM.el('div', {
            id: 'session-list',
            style: { flex: '1', overflowY: 'auto', padding: '8px' }
        });

        sidebar.appendChild(sidebarHeader);
        sidebar.appendChild(sessionList);

        // Main chat area
        const chatContainer = DOM.el('div', {
            className: 'chat-container',
            style: { flex: '1', minWidth: '0', minHeight: '0', overflow: 'hidden', display: 'flex', flexDirection: 'row', height: '100%' }
        });

        const chatMain = DOM.el('div', {
            style: { flex: '1', display: 'flex', flexDirection: 'column', minWidth: '0', minHeight: '0', position: 'relative', height: '100%' }
        });

        const tokenUsageBar = DOM.el('div', {
            id: 'chat-token-usage',
            style: {
                display: 'none',
                margin: '0px',
                padding: '10px 12px',
                fontSize: '12px',
                color: 'var(--text-secondary)',
                flexShrink: '0'
            }
        });

        chatMain.appendChild(ChatWidget.createMessagesContainer());
        chatMain.appendChild(tokenUsageBar);
        chatMain.appendChild(ChatWidget.createInputBar(
            (text, attachments) => this._sendMessage(text, attachments),
            () => this.currentSessionId,
            { showClearButton: false }
        ));

        // AI disclaimer
        const disclaimer = DOM.el('div', {
            style: {
                paddingBottom: options.embedded ? '8px' : '20px',
                textAlign: 'center',
                fontSize: '12px',
                color: 'var(--text-muted)',
                background: 'var(--bg-secondary)',
                flexShrink: '0'

            }
        });
        disclaimer.textContent = '内容由AI生成，仅供参考';
        chatMain.appendChild(disclaimer);

        chatContainer.appendChild(chatMain);
        chatContainer.appendChild(ChatWidget.createToolPanel());

        ChatWidget.onStop = () => this._stopGeneration();
        ChatWidget.onClear = () => this._clearSession();
        ChatWidget.onApprovalRequest = (data, resolved) => {
            if (!resolved) {
                this._showApprovalRequest(data);
            } else {
                // Show resolved approval as a static card
                this._showApprovalRequest(data);
                this._removeApprovalUI(data.approval_id);
            }
        };
        layout.appendChild(sidebar);
        layout.appendChild(chatContainer);
        content.appendChild(layout);
        DOM.createIcons();

        await this._loadSessions();
        if (options.initialAsk) {
            ChatWidget.setDraft(options.initialAsk);
        }

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
        this._toolCheckboxes = document.querySelectorAll('.tool-toggle');
        this._toolCheckboxes.forEach(cb => {
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
        this.disabledTools = [];
        const checkboxes = this._toolCheckboxes || document.querySelectorAll('.tool-toggle');
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
            const sessionParams = {};
            const fixedDatasourceId = this._renderOptions?.sessionFilterDatasourceId || this._renderOptions?.fixedDatasourceId;
            if (fixedDatasourceId) {
                sessionParams.datasource_id = fixedDatasourceId;
            }
            const sessions = await API.getChatSessions(Object.keys(sessionParams).length ? sessionParams : null);
            Store.set('chatSessions', sessions);
            const list = DOM.$('#session-list');
            if (!list) return;
            list.innerHTML = '';

            if (sessions.length === 0) {
                await this._createSession();
                return;
            }

            for (const s of sessions) {
                const isActive = this.currentSessionId === s.id;
                const item = DOM.el('div', {
                    className: `session-item ${isActive ? 'active' : ''}`,
                    style: {
                        padding: '10px 12px',
                        marginBottom: '4px',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        background: isActive ? 'rgba(47, 129, 247, 0.12)' : 'transparent',
                        color: 'var(--text-primary)',
                        fontSize: '14px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        position: 'relative',
                        borderLeft: isActive ? '3px solid var(--accent-blue)' : '3px solid transparent',
                        transition: 'all 0.2s ease'
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
                    const isActive = this.currentSessionId === s.id;
                    if (!isActive) {
                        item.style.background = 'var(--bg-hover)';
                    }
                    deleteBtn.style.opacity = '1';
                });
                item.addEventListener('mouseleave', () => {
                    const isActive = this.currentSessionId === s.id;
                    if (!isActive) {
                        item.style.background = 'transparent';
                    } else {
                        item.style.background = 'rgba(47, 129, 247, 0.12)';
                    }
                    deleteBtn.style.opacity = '0';
                });
                list.appendChild(item);
            }

            if (!this.currentSessionId && sessions.length > 0) {
                // Load the most recent session (first one in the list)
                await this._switchSession(sessions[0].id);
            }
        } catch (e) {
            Toast.error('加载失败 sessions');
        }
    },

    async _createSession() {
        const conn = this._getSelectedDatasource();
        try {
            const session = await API.createChatSession({
                datasource_id: conn?.id || null,
                title: '新建会话',
                ai_model_id: this.selectedModelId,
                disabled_tools: this.disabledTools.length > 0 ? this.disabledTools : null
            });
            this.currentSessionId = session.id;
            await this._loadSessions();
            this._switchSession(session.id);
        } catch (e) {
            Toast.error('Failed to create session: ' + e.message);
        }
    },

    _getSessionTokenUsage(sessionId) {
        const sessions = Store.get('chatSessions') || [];
        const session = sessions.find(item => item.id === sessionId);
        return {
            input_tokens: session?.input_tokens || 0,
            output_tokens: session?.output_tokens || 0,
            total_tokens: session?.total_tokens || 0,
        };
    },

    _restoreSessionContext(sessionId) {
        const sessions = Store.get('chatSessions') || [];
        const session = sessions.find(s => s.id === sessionId);
        if (!session) return;

        // 恢复数据源
        if (this._renderOptions?.fixedDatasourceId != null) {
            this.datasourceSelector.setValue(this._renderOptions.fixedDatasourceId);
            Store.set('currentDatasource', this.datasourceSelector.getSelectedDatasource() || null);
        } else if (session.datasource_id != null) {
            this.datasourceSelector.setValue(session.datasource_id);
            Store.set('currentDatasource', this.datasourceSelector.getSelectedDatasource() || null);
        } else {
            this.datasourceSelector.setValue(null);
            Store.set('currentDatasource', null);
        }

        // 恢复 AI 模型
        if (session.ai_model_id != null) {
            this.selectedModelId = session.ai_model_id;
        } else {
            const defaultModel = this.availableModels.find(m => m.is_default);
            this.selectedModelId = defaultModel?.id || null;
        }
        if (this._modelSelectEl) {
            this._modelSelectEl.value = this.selectedModelId != null ? String(this.selectedModelId) : '';
        }

        // 恢复禁用工具
        this.disabledTools = session.disabled_tools || [];
    },

    async _switchSession(sessionId) {
        this.currentSessionId = sessionId;
        this._pendingResumeState = null;
        this._restoreSessionContext(sessionId);
        this._connectWebSocket(sessionId);
        ChatWidget.loadMessages([]);
        ChatWidget.showToolPanelLoading();

        // Update sidebar highlight
        const list = DOM.$('#session-list');
        if (list) {
            list.querySelectorAll('.session-item').forEach(item => {
                const isActive = item._sessionId === sessionId;
                item.style.background = isActive ? 'rgba(47, 129, 247, 0.12)' : 'transparent';
                item.style.color = 'var(--text-primary)';
                item.style.borderLeft = isActive ? '3px solid var(--accent-blue)' : '3px solid transparent';
                if (isActive) {
                    item.classList.add('active');
                } else {
                    item.classList.remove('active');
                }
            });
        }

        // Load messages and structured diagnosis insights
        try {
            const [messages, insights] = await Promise.all([
                API.getSessionMessages(sessionId),
                API.getSessionInsights(sessionId).catch(() => null)
            ]);
            const hasToolHistory = Array.isArray(messages) && messages.some((msg) =>
                ['tool_call', 'tool_result', 'approval_request', 'approval_response'].includes(msg.role)
            );
            this.sessionTokenUsage = this._getSessionTokenUsage(sessionId);
            this._updateTokenUsageDisplay();
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

            if (!hasToolHistory) {
                ChatWidget.resetToolPanel();
            }

            if (insights) {
                ChatWidget.loadDiagnosticInsights(insights);
            }
            this._applyPendingStreamResume();
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
                ChatWidget.resetToolPanel();
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
                Toast.error('Session expired. Please log in again.');
                setTimeout(() => {
                    Store.set('currentUser', null);
                    window.location.hash = 'login';
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

    async _sendMessage(text) {
        if (!text && (!ChatWidget.attachments || ChatWidget.attachments.length === 0)) return;
        if (ChatWidget.isStreaming) return;
        if (!this.ws || !this.currentSessionId) {
            Toast.warning('No active session');
            return;
        }

        const conn = this._getSelectedDatasource();
        const attachments = ChatWidget.attachments || [];

        ChatWidget.addUserMessage(text, attachments);
        ChatWidget.startAssistantMessage();
        ChatWidget.isStreaming = true;
        this._pendingResumeState = {
            content: '',
            thinking_phase: null,
            thinking_message: '',
        };

        this.ws.send({
            message: text,
            datasource_id: conn?.id || null,
            model_id: this.selectedModelId,
            attachments: attachments
        });
    },

    _getSelectedModel() {
        if (!this.availableModels || this.availableModels.length === 0) return null;
        if (this.selectedModelId) {
            return this.availableModels.find(model => model.id === this.selectedModelId) || null;
        }
        return this.availableModels.find(model => model.is_default) || this.availableModels[0] || null;
    },

    _buildTokenStatus() {
        const model = this._getSelectedModel();
        const contextWindow = model?.context_window || null;
        const totalTokens = this.sessionTokenUsage.total_tokens || 0;
        let warningLevel = 'normal';
        let warningText = '';

        if (contextWindow) {
            const usageRate = totalTokens / contextWindow;
            if (usageRate >= 0.95) {
                warningLevel = 'critical';
                warningText = '上下文已接近上限，后续对话很可能失败，建议立即新建会话';
            } else if (usageRate >= 0.85) {
                warningLevel = 'danger';
                warningText = '上下文已非常接近上限，建议缩小问题范围或新建会话';
            } else if (usageRate >= 0.7) {
                warningLevel = 'warning';
                warningText = '上下文使用量较高，建议减少追问轮次或缩小查询范围';
            }
        }

        return {
            usage: this.sessionTokenUsage,
            contextWindow,
            warningLevel,
            warningText,
        };
    },

    _updateTokenUsageDisplay() {
        ChatWidget.updateTokenUsage(this._buildTokenStatus());
    },

    _rememberResumeState(patch = {}) {
        const current = this._pendingResumeState || {
            content: '',
            thinking_phase: null,
            thinking_message: '',
        };
        this._pendingResumeState = { ...current, ...patch };
    },

    _clearResumeState() {
        this._pendingResumeState = null;
    },

    _applyPendingStreamResume() {
        if (!this._pendingResumeState) return;

        const state = this._pendingResumeState;
        ChatWidget.resumeAssistantMessage(state.content || '');

        if (state.thinking_phase || state.thinking_message) {
            ChatWidget.showThinkingIndicator(
                state.thinking_phase || 'llm_thinking',
                state.thinking_message || 'AI 正在生成中...'
            );
        } else if (!(state.content || '').trim()) {
            ChatWidget.showThinkingIndicator('llm_thinking', 'AI 正在生成中...');
        } else {
            ChatWidget.hideThinkingIndicator();
        }
    },

    _handleWSMessage(data) {
        console.log('[WS]', data.type, data);
        switch (data.type) {
            case 'thinking_start':
                console.log('[WS] calling showThinkingIndicator', data.phase, data.message);
                this._rememberResumeState({
                    thinking_phase: data.phase || 'llm_thinking',
                    thinking_message: data.message || '正在思考分析...',
                });
                ChatWidget.showThinkingIndicator(data.phase, data.message);
                break;
            case 'thinking_phase':
                console.log('[WS] calling updateThinkingIndicator', data.phase, data.message);
                this._rememberResumeState({
                    thinking_phase: data.phase || 'llm_thinking',
                    thinking_message: data.message || '正在思考分析...',
                });
                // If indicator doesn't exist yet (no thinking_start was sent), create it first
                if (!document.getElementById('thinking-indicator')) {
                    ChatWidget.showThinkingIndicator(data.phase, data.message);
                } else {
                    ChatWidget.updateThinkingIndicator(data.phase, data.message);
                }
                break;
            case 'thinking_complete':
                this._rememberResumeState({
                    thinking_phase: 'llm_thinking',
                    thinking_message: '正在思考分析...',
                });
                // Model is about to be called — show "thinking" status instead of hiding
                if (!document.getElementById('thinking-indicator')) {
                    ChatWidget.showThinkingIndicator('llm_thinking', '正在思考分析...');
                } else {
                    ChatWidget.updateThinkingIndicator('llm_thinking', '正在思考分析...');
                }
                break;
            case 'plan_step_status':
                if (data.status === 'running') {
                    // Reuse thinking indicator to show current tool execution status
                    const msg = `正在执行 ${data.tool_name}...`;
                    this._rememberResumeState({
                        thinking_phase: 'tool_execution',
                        thinking_message: msg,
                    });
                    if (!document.getElementById('thinking-indicator')) {
                        ChatWidget.showThinkingIndicator('tool_execution', msg);
                    } else {
                        ChatWidget.updateThinkingIndicator('tool_execution', msg);
                    }
                } else {
                    this._rememberResumeState({
                        thinking_phase: null,
                        thinking_message: '',
                    });
                    // Tool finished — hide indicator, next running/content event will take over
                    ChatWidget.hideThinkingIndicator();
                }
                break;
            case 'content':
                this._rememberResumeState({
                    content: `${this._pendingResumeState?.content || ''}${data.content || ''}`,
                    thinking_phase: null,
                    thinking_message: '',
                });
                ChatWidget.hideThinkingIndicator();
                ChatWidget.appendContent(data.content);
                break;
            case 'tool_call':
                ChatWidget.addToolCall(data.tool_name, data.tool_args, data.tool_call_id);
                break;
            case 'tool_result':
                ChatWidget.addToolResult(data.tool_name, data.result, data.execution_time_ms, data.tool_call_id, {
                    skill_execution_id: data.skill_execution_id,
                    action_run_id: data.action_run_id,
                    action_title: data.action_title,
                    phase: data.phase,
                    visualization: data.visualization,
                });
                break;
            case 'diagnosis_state':
                ChatWidget.updateDiagnosisState(data);
                break;
            case 'plan_created':
                ChatWidget.updateDiagnosisPlan(data);
                break;
            case 'kb_document_selected':
            case 'kb_document_read':
                ChatWidget.addKnowledgeReference(data);
                break;
            case 'diagnosis_conclusion':
                ChatWidget.updateDiagnosisConclusion(data);
                break;
            case 'approval_request':
                this._rememberResumeState({
                    thinking_phase: null,
                    thinking_message: '',
                });
                ChatWidget.hideThinkingIndicator();
                this._showApprovalRequest(data);
                break;
            case 'confirmation_resolved':
                // Approval was resolved (approved/rejected), remove the approval UI
                this._removeApprovalUI(data.approval_id);
                break;
            case 'usage':
                this.sessionTokenUsage.input_tokens += data.usage?.input_tokens || 0;
                this.sessionTokenUsage.output_tokens += data.usage?.output_tokens || 0;
                this.sessionTokenUsage.total_tokens += data.usage?.total_tokens || 0;
                this._updateTokenUsageDisplay();
                break;
            case 'done':
                ChatWidget.finishAssistantMessage();
                this._clearResumeState();
                // Refresh session list to update title after first message
                this._loadSessions();
                break;
            case 'stream_resuming':
                this._pendingResumeState = {
                    content: data.content || '',
                    thinking_phase: data.thinking_phase || null,
                    thinking_message: data.thinking_message || data.message || 'AI 正在生成中...',
                };
                this._applyPendingStreamResume();
                break;
            case 'cancel_ack':
                // Server acknowledged cancel, UI already handled in _stopGeneration
                break;
            case 'error':
                ChatWidget.showError(data.content);
                this._clearResumeState();
                break;
        }
    },

    _showApprovalRequest(data) {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;

        // Finish streaming state so user can interact
        ChatWidget.finishAssistantMessage();

        const card = DOM.el('div', {
            className: 'chat-message assistant',
            id: `approval-${data.approval_id}`,
            'data-approval-id': data.approval_id,
        });

        const riskColor = data.risk_level === 'destructive' ? 'var(--accent-red)' : '#d29922';
        const riskLabel = data.risk_level === 'destructive' ? '危险操作' : '高风险操作';

        card.innerHTML = `
            <div class="chat-avatar" style="background:${riskColor};color:#fff;">!</div>
            <div class="chat-bubble" style="border:1px solid ${riskColor};border-radius:8px;padding:12px;">
                <div style="font-weight:600;color:${riskColor};margin-bottom:8px;">${riskLabel}：需要您的确认</div>
                <div style="margin-bottom:8px;">
                    <strong>技能：</strong><code>${ChatWidget._escapeHtml(data.tool_name)}</code>
                </div>
                ${data.risk_reason ? `<div style="margin-bottom:8px;color:var(--text-secondary);">${ChatWidget._escapeHtml(data.risk_reason)}</div>` : ''}
                <div style="display:flex;gap:8px;margin-top:12px;">
                    <button class="btn btn-sm" style="background:var(--accent-green);color:#fff;border:none;padding:6px 16px;border-radius:4px;cursor:pointer;"
                        onclick="DiagnosisPage._resolveApproval('${data.approval_id}', 'approved')">
                        批准执行
                    </button>
                    <button class="btn btn-sm" style="background:var(--accent-red);color:#fff;border:none;padding:6px 16px;border-radius:4px;cursor:pointer;"
                        onclick="DiagnosisPage._resolveApproval('${data.approval_id}', 'rejected')">
                        拒绝
                    </button>
                </div>
            </div>
        `;
        messages.appendChild(card);
        ChatWidget._scrollToBottom();
    },

    _removeApprovalUI(approvalId) {
        const card = DOM.$(`#approval-${approvalId}`);
        if (card) {
            const buttons = card.querySelector('div[style*="display:flex"]');
            if (buttons) {
                buttons.innerHTML = '<span style="color:var(--text-muted);">已处理</span>';
            }
        }
    },

    async _resolveApproval(approvalId, action) {
        if (!this.currentSessionId) return;
        const card = DOM.$(`#approval-${approvalId}`);
        // Disable buttons immediately
        if (card) {
            const buttons = card.querySelectorAll('button');
            buttons.forEach(btn => { btn.disabled = true; btn.style.opacity = '0.5'; });
        }
        try {
            await API.resolveChatApproval(this.currentSessionId, approvalId, {
                action: action,
                comment: null,
            });
            if (card) {
                const statusText = action === 'approved' ? '已批准，正在执行...' : '已拒绝';
                const statusColor = action === 'approved' ? 'var(--accent-green)' : 'var(--accent-red)';
                const buttonsDiv = card.querySelector('div[style*="display:flex"]');
                if (buttonsDiv) {
                    buttonsDiv.innerHTML = `<span style="color:${statusColor};font-weight:500;">${statusText}</span>`;
                }
            }
            if (action === 'approved') {
                // The backend will continue the conversation and send events via WebSocket
                ChatWidget.startAssistantMessage();
            }
        } catch (e) {
            Toast.error('操作失败: ' + e.message);
            // Re-enable buttons on error
            if (card) {
                const buttons = card.querySelectorAll('button');
                buttons.forEach(btn => { btn.disabled = false; btn.style.opacity = '1'; });
            }
        }
    },

    async _clearSession() {
        if (!this.currentSessionId) {
            Toast.warning('No active session');
            return;
        }
        Modal.show({
            title: '清空当前会话',
            content: '将删除当前会话中的所有消息，此操作不可撤销。',
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '确认清空', variant: 'danger', onClick: async () => {
                    Modal.hide();
                    try {
                        await API.clearSessionMessages(this.currentSessionId);
                        this.sessionTokenUsage = { input_tokens: 0, output_tokens: 0, total_tokens: 0 };
                        ChatWidget.resetTokenUsage();
                        ChatWidget.resetToolPanel();
                        ChatWidget.pendingTools = new Map();
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
                        await this._loadSessions();
                        Toast.success('Session cleared');
                    } catch (e) {
                        Toast.error('Failed to clear session: ' + e.message);
                    }
                } }
            ]
        });
    },

    _stopGeneration() {
        if (this.ws) {
            this.ws.send({ type: 'cancel' });
        }
        ChatWidget.finishAssistantMessage();
        Toast.info('已停止生成');
    },

    async _deleteSession() {
        if (!this.currentSessionId) {
            Toast.warning('No active session');
            return;
        }
        const sessions = Store.get('chatSessions') || [];
        const session = sessions.find(s => s.id === this.currentSessionId);
        Modal.show({
            title: '删除会话',
            content: `确认删除会话 "${session?.title || '会话 ' + this.currentSessionId}" 吗？`,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '删除', variant: 'danger', onClick: async () => {
                    Modal.hide();
                    try {
                        await API.deleteChatSession(this.currentSessionId);
                        this.currentSessionId = null;
                        await this._loadSessions();
                        Toast.success('Session deleted');
                    } catch (e) {
                        Toast.error('Failed to delete session: ' + e.message);
                    }
                } }
            ]
        });
    },

    async _deleteSessionById(sessionId) {
        const sessions = Store.get('chatSessions') || [];
        const session = sessions.find(s => s.id === sessionId);
        Modal.show({
            title: '删除会话',
            content: `确认删除会话 "${session?.title || '会话 ' + sessionId}" 吗？`,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '删除', variant: 'danger', onClick: async () => {
                    Modal.hide();
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
                } }
            ]
        });
    },

    _toggleSidebar() {
        const sidebar = DOM.$('#session-sidebar');
        const btn = DOM.$('#sidebar-toggle-btn');
        const header = DOM.$('#sidebar-header');
        const sessionList = DOM.$('#session-list');

        if (!sidebar || !btn) return;

        const isCollapsed = sidebar.style.width === '40px';

        if (isCollapsed) {
            // Expand
            sidebar.style.width = '280px';
            sidebar.style.minWidth = '280px';
            btn.innerHTML = '<i data-lucide="panel-left-close"></i>';
            btn.title = '隐藏会话列表';
            if (header) {
                header.style.justifyContent = 'space-between';
            }
            if (sessionList) {
                sessionList.style.display = 'block';
            }
        } else {
            // Collapse
            sidebar.style.width = '40px';
            sidebar.style.minWidth = '40px';
            btn.innerHTML = '<i data-lucide="panel-left-open"></i>';
            btn.title = '显示会话列表';
            if (header) {
                header.style.justifyContent = 'center';
            }
            if (sessionList) {
                sessionList.style.display = 'none';
            }
        }

        requestAnimationFrame(() => DOM.createIcons());
    },

    _cleanup() {
        if (this.datasourceClickOutsideHandler) {
            document.removeEventListener('click', this.datasourceClickOutsideHandler);
            this.datasourceClickOutsideHandler = null;
        }
        this.datasourceSelector?.destroy();
        this.datasourceSelector = null;
        if (this.ws) {
            this.ws.disconnect();
            this.ws = null;
        }
        this.currentSessionId = null;
        this._modelSelectEl = null;
        this._renderOptions = null;
        this._container = null;
    }
};
