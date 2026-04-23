/* AI Diagnosis page */
const DiagnosisPage = {
    ws: null,
    datasourceSelector: null,
    datasourceClickOutsideHandler: null,
    _renderOptions: null,
    _container: null,
    currentSessionId: null,
    selectedModelId: null,
    skillAuthorizations: null,
    skillAuthorizationCatalog: null,
    availableModels: [],
    sessionTokenUsage: { input_tokens: 0, output_tokens: 0, total_tokens: 0 },
    _pendingResumeState: null,
    _skillAuthorizationCheckboxes: null,
    _modelSelectEl: null,
    _pendingAutoAsk: null,
    _initialAskSent: false,
    _sessionSidebarCollapsed: false,
    _streamingSessionIds: new Set(),

    _isSessionStreaming(sessionId) {
        if (!sessionId) return false;
        return this._streamingSessionIds.has(sessionId);
    },

    _markSessionStreaming(sessionId) {
        if (!sessionId) return;
        this._streamingSessionIds.add(sessionId);
        this._syncChatStreamingState();
    },

    _clearSessionStreaming(sessionId) {
        if (!sessionId) return;
        this._streamingSessionIds.delete(sessionId);
        this._syncChatStreamingState();
    },

    _syncChatStreamingState() {
        const isCurrentStreaming = this._isSessionStreaming(this.currentSessionId);
        ChatWidget.isStreaming = isCurrentStreaming;
        if (typeof ChatWidget._updateSendButton === 'function') {
            ChatWidget._updateSendButton(isCurrentStreaming);
        }
    },

    _getSelectedDatasource() {
        return this.datasourceSelector?.getValue() || Store.get('currentDatasource') || null;
    },

    _normalizeSkillAuthorizations(authorizations = null, legacyDisabledTools = []) {
        const defaults = {
            platform_operations: false,
            high_privilege_operations: false,
            knowledge_retrieval: true,
        };
        const catalogGroups = this.skillAuthorizationCatalog?.groups || [];
        catalogGroups.forEach(group => {
            defaults[group.id] = group.enabled_by_default !== false;
        });

        const normalized = { ...defaults };
        if (authorizations && typeof authorizations === 'object') {
            Object.keys(defaults).forEach(key => {
                if (authorizations[key] !== undefined) {
                    normalized[key] = Boolean(authorizations[key]);
                }
            });
        }

        const legacyGroupByTool = {
            manage_alert_settings: 'platform_operations',
            list_datasources: 'platform_operations',
            query_monitoring_history: 'platform_operations',
            query_alert_statistics: 'platform_operations',
            execute_any_sql: 'high_privilege_operations',
            execute_any_os_command: 'high_privilege_operations',
            fetch_webpage: 'knowledge_retrieval',
            web_search_bocha: 'knowledge_retrieval',
            list_documents: 'knowledge_retrieval',
            read_document: 'knowledge_retrieval',
        };
        (legacyDisabledTools || []).forEach(toolName => {
            const groupId = legacyGroupByTool[toolName];
            if (groupId) {
                normalized[groupId] = false;
            }
        });

        return normalized;
    },

    _hasPinnedInitialContext(options = this._renderOptions || {}) {
        return Boolean(
            options.preferFreshSession ||
            options.initialAsk ||
            options.initialAlertId ||
            options.initialEventId ||
            options.initialReportId
        );
    },

    _buildInitialSessionTitle(options = this._renderOptions || {}) {
        if (options.initialSessionTitle) {
            return options.initialSessionTitle;
        }
        if (options.initialReportId) {
            return `巡检报告诊断 #${options.initialReportId}`;
        }
        if (options.initialEventId) {
            return `告警事件诊断 #${options.initialEventId}`;
        }
        if (options.initialAlertId) {
            return `告警诊断 #${options.initialAlertId}`;
        }
        return '新建会话';
    },

    _stripMarkdownText(value) {
        return String(value || '')
            .replace(/```[\s\S]*?```/g, ' ')
            .replace(/`([^`]*)`/g, '$1')
            .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
            .replace(/[#>*_~\-]+/g, ' ')
            .replace(/\s+/g, ' ')
            .trim();
    },

    _compactPromptText(value, maxChars = 240) {
        const text = this._stripMarkdownText(value);
        if (!text) return '';
        if (text.length <= maxChars) return text;
        return `${text.slice(0, maxChars).trimEnd()}...`;
    },

    _buildDiagnosisContextBlock(label, context = {}) {
        const lines = [label];
        const datasourceName = context.datasource_name || context.datasource_info?.name;
        const datasourceType = context.datasource_type || context.datasource_info?.db_type;
        const triggerType = context.latest_trigger_type;
        const linkedReport = context.linked_report;

        if (datasourceName || datasourceType) {
            lines.push(`数据源：${[datasourceName, datasourceType].filter(Boolean).join(' / ')}`);
        }
        if (triggerType) {
            lines.push(`触发类型：${this._compactPromptText(triggerType, 120)}`);
        }
        if (context.case_summary) {
            lines.push(`案例摘要：${this._compactPromptText(context.case_summary, 220)}`);
        }
        if (context.diagnosis_summary) {
            lines.push(`诊断摘要：${this._compactPromptText(context.diagnosis_summary, 260)}`);
        }
        if (context.root_cause) {
            lines.push(`根因：${this._compactPromptText(context.root_cause, 260)}`);
        }
        if (context.recommended_action) {
            lines.push(`建议：${this._compactPromptText(context.recommended_action, 260)}`);
        }
        if (linkedReport?.report_id) {
            lines.push(`关联报告：#${linkedReport.report_id} ${this._compactPromptText(linkedReport.title || '', 120)}`.trim());
        }
        return lines.filter(Boolean).join('\n');
    },

    _buildReportContextBlock(reportId, report = {}) {
        const lines = [`关联巡检报告 #${reportId}`];
        if (report.title) {
            lines.push(`标题：${this._compactPromptText(report.title, 160)}`);
        }
        if (report.trigger_type) {
            lines.push(`触发类型：${this._compactPromptText(report.trigger_type, 120)}`);
        }
        if (report.status) {
            lines.push(`状态：${this._compactPromptText(report.status, 80)}`);
        }
        if (report.trigger_reason) {
            lines.push(`触发原因：${this._compactPromptText(report.trigger_reason, 220)}`);
        }
        const reportSummary = this._compactPromptText(report.content_md, 320);
        if (reportSummary) {
            lines.push(`报告摘要：${reportSummary}`);
        }
        return lines.join('\n');
    },

    async _hydrateInitialContextOptions() {
        const options = this._renderOptions || {};
        if (!this._hasPinnedInitialContext(options)) {
            return;
        }

        options.preferFreshSession = true;
        if (!options.initialSessionTitle) {
            options.initialSessionTitle = this._buildInitialSessionTitle(options);
        }

        const contextBlocks = [];

        if (Number.isFinite(options.initialEventId)) {
            try {
                const eventContext = await API.getAlertEventContext(options.initialEventId);
                const block = this._buildDiagnosisContextBlock(`关联告警事件 #${options.initialEventId}`, eventContext);
                if (block) contextBlocks.push(block);
            } catch (error) {
                console.warn('Failed to load alert event context:', error);
            }
        }

        if (Number.isFinite(options.initialAlertId)) {
            let contextBlock = '';
            try {
                const alertContext = await API.getAlertContext(options.initialAlertId);
                contextBlock = this._buildDiagnosisContextBlock(`关联告警 #${options.initialAlertId}`, alertContext);
            } catch (error) {
                try {
                    const eventContext = await API.getAlertEventContext(options.initialAlertId);
                    contextBlock = this._buildDiagnosisContextBlock(`关联告警事件 #${options.initialAlertId}`, eventContext);
                } catch (eventError) {
                    console.warn('Failed to load alert context:', error, eventError);
                }
            }
            if (contextBlock) {
                contextBlocks.push(contextBlock);
            }
        }

        if (Number.isFinite(options.initialReportId)) {
            try {
                const report = await API.getInspectionReportDetail(options.initialReportId);
                const block = this._buildReportContextBlock(options.initialReportId, report);
                if (block) contextBlocks.push(block);
            } catch (error) {
                console.warn('Failed to load inspection report detail:', error);
            }
        }

        if (contextBlocks.length === 0) {
            return;
        }

        const contextText = contextBlocks.join('\n\n');
        const contextHeading = '系统补充上下文：';
        if (options.initialAsk) {
            if (!String(options.initialAsk).includes(contextHeading)) {
                options.initialAsk = `${options.initialAsk}\n\n${contextHeading}\n${contextText}`;
            }
        } else {
            options.initialAsk = `请基于以下上下文进行诊断分析，并给出处置建议。\n\n${contextHeading}\n${contextText}`;
        }
    },

    _getSessionSidebarStorageKey(options = this._renderOptions || {}) {
        return `diagnosisSessionSidebarCollapsed:${options.embedded ? 'embedded' : 'page'}`;
    },

    _getDefaultSessionSidebarCollapsed(options = this._renderOptions || {}) {
        if (typeof options.defaultSidebarCollapsed === 'boolean') {
            return options.defaultSidebarCollapsed;
        }
        return false;
    },

    _loadSessionSidebarCollapsed(options = this._renderOptions || {}) {
        try {
            const raw = window.localStorage.getItem(this._getSessionSidebarStorageKey(options));
            if (raw === '1') return true;
            if (raw === '0') return false;
        } catch (error) {
            // Ignore storage errors and fall back to defaults.
        }
        return this._getDefaultSessionSidebarCollapsed(options);
    },

    _saveSessionSidebarCollapsed(collapsed, options = this._renderOptions || {}) {
        try {
            window.localStorage.setItem(this._getSessionSidebarStorageKey(options), collapsed ? '1' : '0');
        } catch (error) {
            // Ignore storage errors and keep runtime state only.
        }
    },

    _applySidebarCollapsed(collapsed, persist = true) {
        const sidebar = DOM.$('#session-sidebar');
        const btn = DOM.$('#sidebar-toggle-btn');
        const header = DOM.$('#sidebar-header');
        const sessionList = DOM.$('#session-list');

        if (!sidebar || !btn) return;

        this._sessionSidebarCollapsed = Boolean(collapsed);

        if (this._sessionSidebarCollapsed) {
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
        } else {
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
        }

        if (persist) {
            this._saveSessionSidebarCollapsed(this._sessionSidebarCollapsed);
        }

        requestAnimationFrame(() => DOM.createIcons());
    },

    _getWelcomeContextMeta(options = this._renderOptions || {}) {
        const isHostContext = Boolean(options.fixedHostId) && !options.fixedDatasourceId;
        const displayName = options.contextEntityName || options.hostName || options.datasourceName || '';
        return {
            isHostContext,
            displayName: String(displayName || '').trim()
        };
    },

    _getWelcomeQuickAsks() {
        const { isHostContext, displayName } = this._getWelcomeContextMeta();

        if (isHostContext) {
            const hostReference = displayName ? `主机 ${displayName}` : '当前主机';
            return [
                {
                    icon: 'activity',
                    label: '运行总览',
                    prompt: `请结合 ${hostReference} 的当前状态，给我一个主机运行健康总览，说明 CPU、内存、磁盘、网络和进程层面的整体情况、主要风险与优先排查项。`
                },
                {
                    icon: 'gauge',
                    label: '性能诊断',
                    prompt: `请从 CPU 负载、内存压力、磁盘 I/O、网络吞吐和关键进程资源占用几个角度，帮我分析 ${hostReference} 的性能风险。`
                },
                {
                    icon: 'shield-alert',
                    label: '异常排查',
                    prompt: `请帮我识别 ${hostReference} 当前最值得关注的异常信号，并按严重程度排序给出处置建议。`
                },
                {
                    icon: 'sliders-horizontal',
                    label: '配置检查',
                    prompt: `请检查 ${hostReference} 的操作系统与运行环境配置，指出明显不合理项、潜在风险和优化建议。`
                },
            ];
        }

        return [
            {
                icon: 'activity',
                label: '运行总览',
                prompt: '请结合当前数据源给我一个数据库运行健康总览，说明整体状态、主要风险和优先排查项。'
            },
            {
                icon: 'gauge',
                label: '性能诊断',
                prompt: '请从连接数、负载、慢 SQL、锁等待和缓存命中率几个角度，帮我分析当前性能风险。'
            },
            {
                icon: 'shield-alert',
                label: '异常排查',
                prompt: '请帮我识别当前实例最值得关注的异常信号，并按严重程度排序给出处置建议。'
            },
            {
                icon: 'sliders-horizontal',
                label: '参数检查',
                prompt: '请检查当前实例的关键参数配置，指出明显不合理项和优化建议。'
            },
        ];
    },

    _buildWelcomeStateHtml() {
        const options = this._renderOptions || {};
        const isCompactEmbedded = Boolean(options.embedded);
        const { isHostContext, displayName } = this._getWelcomeContextMeta(options);
        const welcomeTitle = isCompactEmbedded ? '开始 AI 诊断' : 'DBClaw AI';
        const embeddedDescription = isHostContext
            ? `可直接提问，或先使用下面的快捷入口对${displayName ? `主机 ${displayName}` : '当前主机'}进行诊断。`
            : '可直接提问，或先使用下面的快捷入口。';
        const pageDescription = isHostContext
            ? '围绕主机的 CPU、内存、磁盘、网络、进程与系统配置，快速给出可落地的诊断建议。'
            : '围绕实例状态、连接、慢 SQL、锁等待与关键参数，快速给出可落地的诊断建议。';
        const highlightPills = isHostContext
            ? `
                    <div class="diagnosis-welcome-pill"><i data-lucide="server"></i><span>主机运行概览</span></div>
                    <div class="diagnosis-welcome-pill"><i data-lucide="cpu"></i><span>CPU 与内存分析</span></div>
                    <div class="diagnosis-welcome-pill"><i data-lucide="hard-drive"></i><span>磁盘与网络排查</span></div>
                    <div class="diagnosis-welcome-pill"><i data-lucide="settings-2"></i><span>系统与进程建议</span></div>
                `
            : `
                    <div class="diagnosis-welcome-pill"><i data-lucide="database"></i><span>实例运行概览</span></div>
                    <div class="diagnosis-welcome-pill"><i data-lucide="timer"></i><span>慢查询与等待分析</span></div>
                    <div class="diagnosis-welcome-pill"><i data-lucide="network"></i><span>连接与会话画像</span></div>
                    <div class="diagnosis-welcome-pill"><i data-lucide="settings-2"></i><span>参数与容量建议</span></div>
                `;
        const quickAsks = isCompactEmbedded
            ? this._getWelcomeQuickAsks().slice(0, 3)
            : this._getWelcomeQuickAsks();
        const quickAskHtml = quickAsks.map((item) => `
            <button
                type="button"
                class="diagnosis-welcome-action"
                data-diagnosis-quickask="${Utils.escapeHtml(item.prompt)}"
            >
                <span class="diagnosis-welcome-action-icon">
                    <i data-lucide="${item.icon}"></i>
                </span>
                <span class="diagnosis-welcome-action-label">${Utils.escapeHtml(item.label)}</span>
            </button>
        `).join('');

        return `
            <div class="diagnosis-welcome${isCompactEmbedded ? ' compact-embedded' : ''}">
                <section class="diagnosis-welcome-card${isCompactEmbedded ? ' compact-embedded' : ''}">
                    <div class="diagnosis-welcome-hero">
                        <div class="diagnosis-welcome-icon">
                            <i data-lucide="sparkles"></i>
                        </div>
                        <div class="diagnosis-welcome-copy">
                            ${isCompactEmbedded ? '' : '<div class="diagnosis-welcome-eyebrow">AI Diagnosis Workspace</div>'}
                            <h3>${welcomeTitle}</h3>
                            <p>${isCompactEmbedded ? embeddedDescription : pageDescription}</p>
                        </div>
                    </div>
                    ${isCompactEmbedded ? '' : `
                    <div class="diagnosis-welcome-highlights">
                        ${highlightPills}
                    </div>
                    `}
                    <div class="diagnosis-welcome-actions">
                        ${quickAskHtml}
                    </div>
                    <div class="diagnosis-welcome-footnote">${isCompactEmbedded ? '下方输入问题即可开始。' : '从上面的快捷入口开始，或直接在下方输入你的问题。'}</div>
                </section>
            </div>
        `;
    },

    _renderWelcomeState(container) {
        if (!container) return;
        container.innerHTML = this._buildWelcomeStateHtml();
        ChatWidget.resetScrollState();
        container.querySelectorAll('[data-diagnosis-quickask]').forEach((button) => {
            button.addEventListener('click', () => {
                const prompt = button.dataset.diagnosisQuickask || '';
                ChatWidget.setDraft(prompt);
            });
        });
        DOM.createIcons();
        ChatWidget.scrollToBottomAndResume({ smooth: false });
    },

    async render() {
        return this.renderWithOptions({});
    },

    async renderFromRoute(routeParam = '') {
        const params = new URLSearchParams(routeParam || '');
        const datasourceId = parseInt(params.get('datasource'), 10);
        const alertId = parseInt(params.get('alert'), 10);
        const eventId = parseInt(params.get('event'), 10);
        const reportId = parseInt(params.get('report'), 10);
        return this.renderWithOptions({
            initialDatasourceId: Number.isFinite(datasourceId) ? datasourceId : null,
            initialAlertId: Number.isFinite(alertId) ? alertId : null,
            initialEventId: Number.isFinite(eventId) ? eventId : null,
            initialReportId: Number.isFinite(reportId) ? reportId : null,
            initialAsk: params.get('ask') || null,
            preferFreshSession: Boolean(
                params.get('ask') ||
                Number.isFinite(alertId) ||
                Number.isFinite(eventId) ||
                Number.isFinite(reportId)
            ),
        });
    },

    async renderWithOptions(options = {}) {
        this._renderOptions = options || {};
        const content = options.container || DOM.$('#page-content');
        this._container = content;
        this._pendingAutoAsk = null;
        this._initialAskSent = false;

        // Load skill authorization catalog
        try {
            this.skillAuthorizationCatalog = await API.getChatSkillAuthorizations();
        } catch (e) { /* ignore */ }
        // 每次渲染时重置为默认值，确保平台操作和高权限操作默认不授权
        this.skillAuthorizations = this._normalizeSkillAuthorizations(null);

        // Header with connection, model and tool safety toggle
        const isCompactEmbedded = Boolean(options.embedded && options.compactEmbeddedToolbar);
        const headerActions = DOM.el('div', {
            className: 'flex gap-8',
            style: {
                flex: isCompactEmbedded ? '0 1 auto' : '1',
                minWidth: '0',
                justifyContent: isCompactEmbedded ? 'flex-end' : 'flex-start'
            }
        });
        try {
            const datasources = await API.getDatasources();
            Store.set('datasources', datasources);
            if (options.fixedDatasourceId) {
                const fixedDatasource = datasources.find(item => item.id === options.fixedDatasourceId) || null;
                if (fixedDatasource) {
                    Store.set('currentDatasource', fixedDatasource);
                }
            } else if (options.fixedHostId) {
                // 主机模式：不设置固定数据源，允许用户选择
                Store.set('currentDatasource', null);
            } else if (options.initialDatasourceId) {
                const initialDatasource = datasources.find(item => item.id === options.initialDatasourceId) || null;
                if (initialDatasource) {
                    Store.set('currentDatasource', initialDatasource);
                }
            }
        } catch (e) { /* ignore */ }

        await this._hydrateInitialContextOptions();

        this.datasourceSelector?.destroy();
        if (options.fixedDatasourceId || options.fixedHostId) {
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

        // Skill authorization settings button
        headerActions.appendChild(modelSelect);
        if (!options.hideToolSafetyButton) {
            const toolSafetyBtn = DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: '<i data-lucide="shield"></i> Skill 授权',
                title: '配置 AI 可调用的 skill 分组',
                onClick: () => this._showSkillAuthorizationModal()
            });
            headerActions.appendChild(toolSafetyBtn);
        }
        if (!options.hideClearSessionButton) {
            const clearSessionBtn = DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: '<i data-lucide="eraser"></i> 清除会话',
                title: '清除当前会话',
                onClick: () => this._clearSession()
            });
            headerActions.appendChild(clearSessionBtn);
        }

        // Two-column layout: sessions sidebar + chat area
        content.innerHTML = '';
        if (options.embedded) {
            content.style.display = 'flex';
            content.style.flexDirection = 'column';
            content.style.minHeight = '0';
            content.style.height = '100%';
            const embeddedToolbar = DOM.el('div', {
                className: `instance-embedded-toolbar${isCompactEmbedded ? ' instance-embedded-toolbar-compact' : ''}`,
                style: {
                    display: 'flex',
                    gap: isCompactEmbedded ? '8px' : '12px',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: isCompactEmbedded ? '8px' : '16px',
                    flexWrap: 'wrap'
                }
            });
            if (!options.hideEmbeddedTitle) {
                embeddedToolbar.appendChild(DOM.el('div', {
                    className: 'instance-embedded-title',
                    textContent: options.embeddedTitle || 'AI 对话诊断'
                }));
            }
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
            style: { flex: '1', minWidth: '0', minHeight: '0', overflow: 'hidden', display: 'flex', flexDirection: 'column', height: '100%' }
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
        if (!options.hideSessionSidebar) {
            layout.appendChild(sidebar);
        }
        layout.appendChild(chatContainer);
        content.appendChild(layout);
        if (!options.hideSessionSidebar) {
            this._applySidebarCollapsed(this._loadSessionSidebarCollapsed(options), false);
        }
        DOM.createIcons();

        await this._loadSessions();
        if (options.initialAsk && !options.autoSendInitialAsk) {
            ChatWidget.setDraft(options.initialAsk);
        }

        return () => this._cleanup();
    },

    _showSkillAuthorizationModal() {
        const groups = this.skillAuthorizationCatalog?.groups || [];
        if (groups.length === 0) {
            Toast.info('暂无可配置的 Skill 授权分组');
            return;
        }

        const currentAuthorizations = this._normalizeSkillAuthorizations(this.skillAuthorizations);
        const borderColorByLevel = {
            low: 'var(--accent-blue)',
            medium: 'var(--accent-blue)',
            high: 'var(--accent-red)',
        };

        const renderGroup = (group) => {
            const isEnabled = currentAuthorizations[group.id] !== false;
            const itemBadges = (group.items || []).map(item => `
                <span
                    title="${Utils.escapeHtml(String(item.description || item.id || '')).replace(/"/g, '&quot;')}"
                    style="display:inline-flex;align-items:center;padding:3px 7px;border-radius:999px;background:rgba(255,255,255,0.06);border:1px solid var(--border-color);font-size:11px;color:var(--text-secondary);"
                >
                    ${item.kind === 'tool' ? '内置 ' : ''}${Utils.escapeHtml(String(item.id || ''))}
                </span>
            `).join('');

            return `
                <label style="display:flex;align-items:flex-start;gap:10px;padding:12px 14px;border-radius:10px;cursor:pointer;background:var(--bg-secondary);margin-bottom:10px;border-left:3px solid ${borderColorByLevel[group.warning_level] || 'var(--accent-blue)'};">
                    <input type="checkbox" class="skill-auth-toggle" data-group-id="${group.id}" ${isEnabled ? 'checked' : ''} style="margin-top:4px;">
                    <div style="flex:1;min-width:0;">
                        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:4px;">
                            <div style="font-weight:600;font-size:14px;color:var(--text-primary);">${Utils.escapeHtml(String(group.label || ''))}</div>
                            <span class="badge ${isEnabled ? 'badge-success' : 'badge-danger'}" id="skill-auth-badge-${group.id}">
                                ${isEnabled ? '已允许' : '已禁止'}
                            </span>
                        </div>
                        <div style="font-size:12px;line-height:1.5;color:var(--text-secondary);">${Utils.escapeHtml(String(group.description || ''))}</div>
                        <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:5px;max-height:112px;overflow:auto;">
                            ${itemBadges || '<span style="font-size:12px;color:var(--text-muted);">当前暂无可展示项</span>'}
                        </div>
                    </div>
                </label>
            `;
        };

        Modal.show({
            title: 'Skill 授权',
            width: 'min(1120px, 94vw)',
            content: `
                <p style="margin-bottom:12px;font-size:12px;color:var(--text-secondary);line-height:1.6;">
                    控制 AI 在诊断过程中是否允许调用特定分类下的 skill。修改后立即对当前会话生效，但刷新页面或切换会话后将恢复默认配置。
                </p>
                <div id="skill-authorization-list">
                    ${groups.map(group => renderGroup(group)).join('')}
                </div>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '应用授权', variant: 'primary', onClick: () => this._applySkillAuthorizations() }
            ]
        });

        this._skillAuthorizationCheckboxes = document.querySelectorAll('.skill-auth-toggle');
        this._skillAuthorizationCheckboxes.forEach(cb => {
            cb.addEventListener('change', () => {
                const badge = document.getElementById(`skill-auth-badge-${cb.dataset.groupId}`);
                if (badge) {
                    badge.className = `badge ${cb.checked ? 'badge-success' : 'badge-danger'}`;
                    badge.textContent = cb.checked ? '已允许' : '已禁止';
                }
            });
        });
    },

    _applySkillAuthorizations() {
        const nextAuthorizations = this._normalizeSkillAuthorizations();
        const checkboxes = this._skillAuthorizationCheckboxes || document.querySelectorAll('.skill-auth-toggle');
        checkboxes.forEach(cb => {
            nextAuthorizations[cb.dataset.groupId] = cb.checked;
        });
        this.skillAuthorizations = nextAuthorizations;
        Modal.hide();
        Toast.success('Skill 授权已更新，当前会话立即生效。刷新页面或切换会话后将恢复默认配置。');
    },

    async _loadSessions() {
        if (this._renderOptions?.hideSessionSidebar || this._renderOptions?.autoCreateSession) {
            if (!this.currentSessionId) {
                await this._createSession({ reloadList: false, switchSession: false });
            }
            if (this.currentSessionId) {
                await this._switchSession(this.currentSessionId);
            }
            return;
        }

        try {
            let pinnedSessionId = this.currentSessionId;
            if (this._renderOptions?.preferFreshSession && !pinnedSessionId) {
                const createdSession = await this._createSession({ reloadList: false, switchSession: false });
                pinnedSessionId = createdSession?.id || null;
            }

            const sessionParams = {};
            const fixedDatasourceId = this._renderOptions?.sessionFilterDatasourceId || this._renderOptions?.fixedDatasourceId;
            const fixedHostId = this._renderOptions?.sessionFilterHostId || this._renderOptions?.fixedHostId;
            if (fixedDatasourceId) {
                sessionParams.datasource_id = fixedDatasourceId;
            }
            if (fixedHostId) {
                sessionParams.host_id = fixedHostId;
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

            const preferredSessionId =
                (pinnedSessionId && sessions.some(s => s.id === pinnedSessionId)) ? pinnedSessionId : null;

            if (preferredSessionId) {
                await this._switchSession(preferredSessionId);
                return;
            }

            if (!this.currentSessionId && sessions.length > 0) {
                await this._switchSession(sessions[0].id);
            }
        } catch (e) {
            Toast.error('加载失败 sessions');
        }
    },

    async _createSession(options = {}) {
        const { reloadList = true, switchSession = true } = options;
        const conn = this._getSelectedDatasource();
        try {
            const session = await API.createChatSession({
                datasource_id: conn?.id || null,
                host_id: this._renderOptions?.fixedHostId || null,
                title: this._renderOptions?.initialSessionTitle || '新建会话',
                ai_model_id: this.selectedModelId,
                skill_authorizations: null  // 不保存授权配置到数据库
            });
            this.currentSessionId = session.id;
            if (reloadList && !this._renderOptions?.hideSessionSidebar) {
                await this._loadSessions();
            }
            if (switchSession) {
                await this._switchSession(session.id);
            }
            return session;
        } catch (e) {
            Toast.error('Failed to create session: ' + e.message);
            return null;
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

    _restoreSessionContext(sessionId, preserveSkillAuthorizations = false) {
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

        // 只在真正切换会话时重置 Skill 授权
        if (!preserveSkillAuthorizations) {
            this.skillAuthorizations = this._normalizeSkillAuthorizations(null);
        }
    },

    async _switchSession(sessionId) {
        const isActuallySwitching = this.currentSessionId !== sessionId;
        this.currentSessionId = sessionId;
        this._syncChatStreamingState();
        this._pendingResumeState = null;
        // 只在真正切换会话时重置授权配置为默认值
        this._restoreSessionContext(sessionId, !isActuallySwitching);
        this._connectWebSocket(sessionId);
        ChatWidget.resetScrollState();
        ChatWidget.loadMessages([]);

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
            const visibleMessages = this._filterVisibleMessages(messages);
            const hasToolHistory = Array.isArray(visibleMessages) && visibleMessages.some((msg) =>
                ['tool_call', 'tool_result', 'approval_request', 'approval_response'].includes(msg.role)
            );
            this.sessionTokenUsage = this._getSessionTokenUsage(sessionId);
            this._updateTokenUsageDisplay();
            console.log(`Loaded ${messages.length} messages for session ${sessionId}`, messages);

            if (visibleMessages && visibleMessages.length > 0) {
                ChatWidget.loadMessages(visibleMessages);
            } else {
                // Empty session - show welcome message (unless auto-sending initial ask)
                const shouldShowWelcome = !this._renderOptions?.autoSendInitialAsk;
                if (shouldShowWelcome) {
                    const container = DOM.$('#chat-messages');
                    this._renderWelcomeState(container);
                }
            }

            if (!hasToolHistory) {
                ChatWidget.resetToolPanel();
            }

            if (insights) {
                ChatWidget.loadDiagnosticInsights(insights);
            }
            this._applyPendingStreamResume();
            this._queueInitialAskIfNeeded(sessionId, messages);
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
                ChatWidget.resetScrollState();
                ChatWidget.scrollToBottomAndResume({ smooth: false });
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

        ws.on('open', () => this._flushPendingAutoAsk());
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

    async _sendMessage(text, attachments = [], messageOptions = {}) {
        const resolvedAttachments = Array.isArray(attachments) ? attachments : (ChatWidget.attachments || []);
        if (!text && (!resolvedAttachments || resolvedAttachments.length === 0)) return;
        if (this._isSessionStreaming(this.currentSessionId)) return;
        if (!this.ws || !this.currentSessionId) {
            Toast.warning('No active session');
            return;
        }

        const conn = this._getSelectedDatasource();

        if (!messageOptions.suppressUserMessage) {
            ChatWidget.addUserMessage(text, resolvedAttachments);
        } else {
            ChatWidget.setDraft('');
        }
        ChatWidget.startAssistantMessage();
        this._markSessionStreaming(this.currentSessionId);
        this._pendingResumeState = {
            content: '',
            thinking_phase: null,
            thinking_message: '',
            render_segments: [],
            run_id: null,
            status: 'partial',
        };

        this.ws.send({
            message: text,
            datasource_id: conn?.id || null,
            host_id: this._renderOptions?.fixedHostId || null,
            model_id: this.selectedModelId,
            attachments: resolvedAttachments,
            skill_authorizations: this._normalizeSkillAuthorizations(this.skillAuthorizations)
        });
    },

    _queueInitialAskIfNeeded(sessionId, messages = []) {
        const initialAsk = this._renderOptions?.initialAsk;
        if (!this._renderOptions?.autoSendInitialAsk || !initialAsk || this._initialAskSent) {
            return;
        }
        if (Array.isArray(messages) && messages.length > 0) {
            this._initialAskSent = true;
            return;
        }
        this._pendingAutoAsk = {
            sessionId,
            text: initialAsk,
        };
        this._flushPendingAutoAsk();
    },

    _flushPendingAutoAsk() {
        const pending = this._pendingAutoAsk;
        if (!pending || this._initialAskSent) return;
        if (this.currentSessionId !== pending.sessionId) return;
        if (!this.ws?.ws || this.ws.ws.readyState !== WebSocket.OPEN) return;
        this._pendingAutoAsk = null;
        this._initialAskSent = true;
        this._sendMessage(pending.text, [], {
            suppressUserMessage: Boolean(this._renderOptions?.hideInitialAskMessage)
        });
    },

    _filterVisibleMessages(messages = []) {
        if (!this._renderOptions?.hideInitialAskMessage || !Array.isArray(messages) || messages.length === 0) {
            return messages;
        }

        const expectedPrompt = String(this._renderOptions.initialAsk || '').trim();
        if (!expectedPrompt) return messages;

        let skipped = false;
        return messages.filter((msg) => {
            if (skipped || msg?.role !== 'user') return true;
            const content = String(msg?.content || '').trim();
            if (content !== expectedPrompt) return true;
            skipped = true;
            return false;
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
            render_segments: [],
            run_id: null,
            status: 'partial',
        };
        this._pendingResumeState = { ...current, ...patch };
    },

    _clearResumeState() {
        this._pendingResumeState = null;
    },

    _applyPendingStreamResume() {
        if (!this._pendingResumeState) return;

        const state = this._pendingResumeState;
        ChatWidget.resumeAssistantMessage(state.content || '', state.render_segments || []);
        const hasRenderedContent = Boolean(
            (state.content || '').trim() ||
            (Array.isArray(state.render_segments) && state.render_segments.length > 0)
        );

        if (state.thinking_phase || state.thinking_message) {
            ChatWidget.showThinkingIndicator(
                state.thinking_phase || 'llm_thinking',
                state.thinking_message || 'AI 正在生成中...'
            );
        } else if (!hasRenderedContent && state.status !== 'awaiting_approval') {
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
                    run_id: data.run_id || this._pendingResumeState?.run_id || null,
                });
                ChatWidget.showThinkingIndicator(data.phase, data.message);
                break;
            case 'thinking_phase':
                console.log('[WS] calling updateThinkingIndicator', data.phase, data.message);
                this._rememberResumeState({
                    thinking_phase: data.phase || 'llm_thinking',
                    thinking_message: data.message || '正在思考分析...',
                    run_id: data.run_id || this._pendingResumeState?.run_id || null,
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
                    thinking_phase: null,
                    thinking_message: '',
                    run_id: data.run_id || this._pendingResumeState?.run_id || null,
                });
                // Thinking phase complete, hide indicator and wait for actual content/tool calls
                ChatWidget.hideThinkingIndicator();
                break;
            case 'plan_step_status':
                if (data.status === 'running') {
                    // Reuse thinking indicator to show current tool execution status
                    const msg = `正在执行 ${data.tool_name}...`;
                    this._rememberResumeState({
                        thinking_phase: 'tool_execution',
                        thinking_message: msg,
                        run_id: data.run_id || this._pendingResumeState?.run_id || null,
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
                        run_id: data.run_id || this._pendingResumeState?.run_id || null,
                    });
                    // Tool finished — hide indicator, next running/content event will take over
                    ChatWidget.hideThinkingIndicator();
                }
                break;
            case 'content':
                ChatWidget.hideThinkingIndicator();
                ChatWidget.appendContent(data.content);
                this._rememberResumeState({
                    content: ChatWidget.currentContent || `${this._pendingResumeState?.content || ''}${data.content || ''}`,
                    render_segments: ChatWidget.getCurrentRenderSegments(),
                    thinking_phase: null,
                    thinking_message: '',
                    run_id: data.run_id || this._pendingResumeState?.run_id || null,
                    status: data.status || 'partial',
                });
                break;
            case 'tool_call':
                if (!ChatWidget.isStreaming) {
                    ChatWidget.resumeAssistantMessage(
                        this._pendingResumeState?.content || ChatWidget.currentContent || '',
                        this._pendingResumeState?.render_segments || ChatWidget.getCurrentRenderSegments()
                    );
                }
                ChatWidget.hideThinkingIndicator();
                ChatWidget.addToolCall(data.tool_name, data.tool_args, data.tool_call_id);
                this._rememberResumeState({
                    content: ChatWidget.currentContent || this._pendingResumeState?.content || '',
                    render_segments: ChatWidget.getCurrentRenderSegments(),
                    thinking_phase: null,
                    thinking_message: '',
                    run_id: data.run_id || this._pendingResumeState?.run_id || null,
                    status: 'partial',
                });
                break;
            case 'tool_result':
                if (!ChatWidget.isStreaming) {
                    ChatWidget.resumeAssistantMessage(
                        this._pendingResumeState?.content || ChatWidget.currentContent || '',
                        this._pendingResumeState?.render_segments || ChatWidget.getCurrentRenderSegments()
                    );
                }
                ChatWidget.addToolResult(data.tool_name, data.result, data.execution_time_ms, data.tool_call_id, {
                    skill_execution_id: data.skill_execution_id,
                    action_run_id: data.action_run_id,
                    action_title: data.action_title,
                    phase: data.phase,
                    visualization: data.visualization,
                });
                this._rememberResumeState({
                    content: ChatWidget.currentContent || this._pendingResumeState?.content || '',
                    render_segments: ChatWidget.getCurrentRenderSegments(),
                    thinking_phase: null,
                    thinking_message: '',
                    run_id: data.run_id || this._pendingResumeState?.run_id || null,
                    status: 'partial',
                });
                break;
            case 'diagnosis_state':
                ChatWidget.updateDiagnosisState(data);
                break;
            case 'plan_created':
                ChatWidget.updateDiagnosisPlan(data);
                break;
            case 'knowledge_plan_created':
            case 'knowledge_replanned':
                ChatWidget.updateDiagnosisPlan(data);
                break;
            case 'knowledge_unit_activated':
                ChatWidget.addKnowledgeReference(data);
                break;
            case 'kb_document_selected':
            case 'kb_document_read':
                ChatWidget.addKnowledgeReference(data);
                break;
            case 'diagnosis_conclusion':
                ChatWidget.updateDiagnosisConclusion(data);
                break;
            case 'approval_request':
                if (!ChatWidget.isStreaming) {
                    ChatWidget.resumeAssistantMessage(
                        this._pendingResumeState?.content || ChatWidget.currentContent || '',
                        this._pendingResumeState?.render_segments || ChatWidget.getCurrentRenderSegments()
                    );
                }
                ChatWidget.hideThinkingIndicator();
                ChatWidget.addToolApprovalRequest(data.tool_name, data.tool_args, data.tool_call_id, data.summary, {
                    approval_id: data.approval_id,
                    approval_status: 'pending',
                    risk_level: data.risk_level,
                    risk_reason: data.risk_reason,
                    action_run_id: data.action_run_id,
                    action_title: data.action_title,
                    phase: data.phase,
                });
                this._rememberResumeState({
                    content: ChatWidget.currentContent || this._pendingResumeState?.content || '',
                    render_segments: ChatWidget.getCurrentRenderSegments(),
                    thinking_phase: null,
                    thinking_message: '',
                    run_id: data.run_id || this._pendingResumeState?.run_id || null,
                    status: 'awaiting_approval',
                });
                this._clearSessionStreaming(this.currentSessionId);
                ChatWidget.finishAssistantMessage();
                break;
            case 'confirmation_resolved':
                ChatWidget.updateApprovalState(data.approval_id, {
                    status: data.action === 'approved' ? 'running' : 'failed',
                    summary: data.action === 'approved' ? '已批准，正在执行...' : '用户已拒绝执行',
                    metadata: {
                        approval_status: data.action === 'approved' ? 'approving' : 'rejected',
                    },
                });
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
                this._clearSessionStreaming(this.currentSessionId);
                this._clearResumeState();
                // Refresh session list to update title after first message
                if (!this._renderOptions?.hideSessionSidebar && !this._renderOptions?.autoCreateSession) {
                    this._loadSessions();
                }
                break;
            case 'stream_resuming':
                this._pendingResumeState = {
                    content: data.content || '',
                    thinking_phase: data.thinking_phase || null,
                    thinking_message: data.thinking_message || data.message || 'AI 正在生成中...',
                    render_segments: data.render_segments || [],
                    run_id: data.run_id || null,
                    status: data.status || 'partial',
                };
                if (this._pendingResumeState.status === 'awaiting_approval') {
                    this._clearSessionStreaming(this.currentSessionId);
                } else {
                    this._markSessionStreaming(this.currentSessionId);
                }
                this._applyPendingStreamResume();
                break;
            case 'cancel_ack':
                // Server acknowledged cancel, UI already handled in _stopGeneration
                this._clearSessionStreaming(this.currentSessionId);
                break;
            case 'error':
                ChatWidget.showError(data.content);
                this._clearSessionStreaming(this.currentSessionId);
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
        ChatWidget._maybeAutoScroll();
    },

    _removeApprovalUI(approvalId) {
        const card = DOM.$(`#approval-${approvalId}`);
        if (card) {
            card.remove();
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
        ChatWidget.updateApprovalState(approvalId, {
            status: action === 'approved' ? 'running' : 'failed',
            summary: action === 'approved' ? '已批准，正在执行...' : '用户已拒绝执行',
            metadata: {
                approval_status: action === 'approved' ? 'approving' : 'rejected',
            },
        });
        if (action === 'approved') {
            ChatWidget.resumeAssistantMessage(
                this._pendingResumeState?.content || ChatWidget.currentContent || '',
                ChatWidget.getCurrentRenderSegments()
            );
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
                // 后端会通过 WebSocket 继续把 tool/result/content 续写到当前 assistant 消息中
            }
        } catch (e) {
            Toast.error('操作失败: ' + e.message);
            // Re-enable buttons on error
            if (card) {
                const buttons = card.querySelectorAll('button');
                buttons.forEach(btn => { btn.disabled = false; btn.style.opacity = '1'; });
            }
            ChatWidget.updateApprovalState(approvalId, {
                status: 'waiting_approval',
                summary: '技能仍在等待确认',
                metadata: {
                    approval_status: 'pending',
                },
            });
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
                        this._renderWelcomeState(container);
                        ChatWidget.resetScrollState();
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
        this._clearSessionStreaming(this.currentSessionId);
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
        this._applySidebarCollapsed(!this._sessionSidebarCollapsed);
    },

    _cleanup() {
        if (this.datasourceClickOutsideHandler) {
            document.removeEventListener('click', this.datasourceClickOutsideHandler);
            this.datasourceClickOutsideHandler = null;
        }
        this.datasourceSelector?.destroy();
        this.datasourceSelector = null;
        if (this.ws) {
            this.ws.shouldReconnect = false;
            this.ws.disconnect();
            this.ws = null;
        }
        this.currentSessionId = null;
        this._modelSelectEl = null;
        this._pendingAutoAsk = null;
        this._initialAskSent = false;
        this._streamingSessionIds.clear();
        this._renderOptions = null;
        this._container = null;
    }
};
