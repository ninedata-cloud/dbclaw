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
            return I18n.t('pageCopy.diagnosis.inspectionReportDiagnosisValue', { value0: options.initialReportId });
        }
        if (options.initialEventId) {
            return I18n.t('pageCopy.diagnosis.alarmEventDiagnosisValue', { value0: options.initialEventId });
        }
        if (options.initialAlertId) {
            return I18n.t('pageCopy.diagnosis.alarmDiagnosisValue', { value0: options.initialAlertId });
        }
        return I18n.t('pageCopy.diagnosis.newSession');
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
            lines.push(I18n.t('pageCopy.diagnosis.datasourceValue', { value0: [datasourceName, datasourceType].filter(Boolean).join(' / ') }));
        }
        if (triggerType) {
            lines.push(I18n.t('pageCopy.diagnosis.triggerTypeValue', { value0: this._compactPromptText(triggerType, 120) }));
        }
        if (context.case_summary) {
            lines.push(I18n.t('pageCopy.diagnosis.caseSummaryValue', { value0: this._compactPromptText(context.case_summary, 220) }));
        }
        if (context.diagnosis_summary) {
            lines.push(I18n.t('pageCopy.diagnosis.diagnosisSummaryValue', { value0: this._compactPromptText(context.diagnosis_summary, 260) }));
        }
        if (context.root_cause) {
            lines.push(I18n.t('pageCopy.diagnosis.rootCauseLabel', { value0: this._compactPromptText(context.root_cause, 260) }));
        }
        if (context.recommended_action) {
            lines.push(I18n.t('pageCopy.diagnosis.recommendationsLabel', { value0: this._compactPromptText(context.recommended_action, 260) }));
        }
        if (linkedReport?.report_id) {
            lines.push(I18n.t('pageCopy.diagnosis.linkedReportLabel', { value0: linkedReport.report_id, value1: this._compactPromptText(linkedReport.title || '', 120) }).trim());
        }
        return lines.filter(Boolean).join('\n');
    },

    _buildReportContextBlock(reportId, report = {}) {
        const lines = [I18n.t('pageCopy.diagnosis.inspectionReportValue', { value0: reportId })];
        if (report.title) {
            lines.push(I18n.t('pageCopy.diagnosis.titleValue', { value0: this._compactPromptText(report.title, 160) }));
        }
        if (report.trigger_type) {
            lines.push(I18n.t('pageCopy.diagnosis.triggerTypeValue', { value0: this._compactPromptText(report.trigger_type, 120) }));
        }
        if (report.status) {
            lines.push(I18n.t('pageCopy.diagnosis.statusValue', { value0: this._compactPromptText(report.status, 80) }));
        }
        if (report.trigger_reason) {
            lines.push(I18n.t('pageCopy.diagnosis.triggerReasonValue', { value0: this._compactPromptText(report.trigger_reason, 220) }));
        }
        const reportSummary = this._compactPromptText(report.content_md, 320);
        if (reportSummary) {
            lines.push(I18n.t('pageCopy.diagnosis.reportSummaryLabel', { value0: reportSummary }));
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
                const block = this._buildDiagnosisContextBlock(I18n.t('pageCopy.diagnosis.alarmValue', { value0: options.initialEventId }), eventContext);
                if (block) contextBlocks.push(block);
            } catch (error) {
                console.warn('Failed to load alert event context:', error);
            }
        }

        if (Number.isFinite(options.initialAlertId)) {
            let contextBlock = '';
            try {
                const alertContext = await API.getAlertContext(options.initialAlertId);
                contextBlock = this._buildDiagnosisContextBlock(I18n.t('pageCopy.diagnosis.alarmValue2', { value0: options.initialAlertId }), alertContext);
            } catch (error) {
                try {
                    const eventContext = await API.getAlertEventContext(options.initialAlertId);
                    contextBlock = this._buildDiagnosisContextBlock(I18n.t('pageCopy.diagnosis.alarmValue', { value0: options.initialAlertId }), eventContext);
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
        const contextHeading = I18n.t('pageCopy.diagnosis.systemSupplementaryContext');
        if (options.initialAsk) {
            if (!String(options.initialAsk).includes(contextHeading)) {
                options.initialAsk = `${options.initialAsk}\n\n${contextHeading}\n${contextText}`;
            }
        } else {
            options.initialAsk = I18n.t('pageCopy.diagnosis.contextDiagnosisAnalysisDisposalRecommendationsValueValue', { value0: contextHeading, value1: contextText });
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
            btn.title = I18n.t('pageCopy.diagnosis.showConversationList');
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
            btn.title = I18n.t('pageCopy.diagnosis.hideSessionList');
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
            const hostReference = displayName ? I18n.t('pageCopy.diagnosis.hostValue', { value0: displayName }) : I18n.t('pageCopy.diagnosis.currentHost');
            return [
                {
                    icon: 'activity',
                    label: I18n.t('pageCopy.diagnosis.runOverview'),
                    prompt: I18n.t('pageCopy.diagnosis.hostHealthPrompt', { value0: hostReference })
                },
                {
                    icon: 'gauge',
                    label: I18n.t('pageCopy.diagnosis.performanceDiagnostics'),
                    prompt: I18n.t('pageCopy.diagnosis.cpuMemoryDiskIONetworkAnalysis', { value0: hostReference })
                },
                {
                    icon: 'shield-alert',
                    label: I18n.t('pageCopy.diagnosis.anomalyTroubleshooting'),
                    prompt: I18n.t('pageCopy.diagnosis.anomalyTriagePrompt', { value0: hostReference })
                },
                {
                    icon: 'sliders-horizontal',
                    label: I18n.t('pageCopy.diagnosis.configurationCheck'),
                    prompt: I18n.t('pageCopy.diagnosis.environmentReviewPrompt', { value0: hostReference })
                },
            ];
        }

        return [
            {
                icon: 'activity',
                label: I18n.t('pageCopy.diagnosis.runOverview'),
                prompt: I18n.t('pageCopy.diagnosis.pleaseGiveMeAnOverviewOfThe')
            },
            {
                icon: 'gauge',
                label: I18n.t('pageCopy.diagnosis.performanceDiagnostics'),
                prompt: I18n.t('pageCopy.diagnosis.pleaseHelpMeAnalyzeTheCurrentPerformance')
            },
            {
                icon: 'shield-alert',
                label: I18n.t('pageCopy.diagnosis.anomalyTroubleshooting'),
                prompt: I18n.t('pageCopy.diagnosis.pleaseHelpMeIdentifyTheMostNoteworthy')
            },
            {
                icon: 'sliders-horizontal',
                label: I18n.t('pageCopy.diagnosis.parameterCheck'),
                prompt: I18n.t('pageCopy.diagnosis.pleaseCheckTheKeyParameterConfigurationOf')
            },
        ];
    },

    _buildWelcomeStateHtml() {
        const options = this._renderOptions || {};
        const isCompactEmbedded = Boolean(options.embedded);
        const { isHostContext, displayName } = this._getWelcomeContextMeta(options);
        const welcomeTitle = isCompactEmbedded ? I18n.t('pageCopy.diagnosis.startAiDiagnosis') : 'DBClaw AI';
        const embeddedDescription = isHostContext
            ? I18n.t('pageCopy.diagnosis.youCanAskQuestionsDirectlyOrUse', { value0: displayName ? I18n.t('pageCopy.diagnosis.hostValue', { value0: displayName }) : I18n.t('pageCopy.diagnosis.currentHost') })
            : I18n.t('pageCopy.diagnosis.youCanAskQuestionsDirectlyOrUse2');
        const pageDescription = isHostContext
            ? I18n.t('pageCopy.diagnosis.quicklyProvidePracticalDiagnosticSuggestionsAroundThe')
            : I18n.t('pageCopy.diagnosis.quicklyProvidePracticalDiagnosticSuggestionsAroundInstance');
        const highlightPills = isHostContext
            ? I18n.t('pageCopy.diagnosis.hostCpuMemoryanalysisDiskNetworkSystem')
            : I18n.t('pageCopy.diagnosis.instanceSlowQueryWaitinganalysisConnectionSession');
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
                    <div class="diagnosis-welcome-footnote">${isCompactEmbedded ? I18n.t('pageCopy.diagnosis.enterYourQuestionBelowToGetStarted') : I18n.t('pageCopy.diagnosis.getStartedWithTheQuickEntryAbove')}</div>
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
                emptyText: I18n.t('pageCopy.diagnosis.selectDatasource'),
                placeholder: I18n.t('placeholders.selectDatasource'),
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
        modelSelect.appendChild(DOM.el('option', { value: '', textContent: I18n.t('pageCopy.diagnosis.defaultModel') }));

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
                innerHTML: I18n.t('pageCopy.diagnosis.skillAuthorize'),
                title: I18n.t('pageCopy.diagnosis.configureSkillGroupsThatCanBeCalled'),
                onClick: () => this._showSkillAuthorizationModal()
            });
            headerActions.appendChild(toolSafetyBtn);
        }
        if (!options.hideClearSessionButton) {
            const clearSessionBtn = DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: I18n.t('pageCopy.diagnosis.clearSession'),
                title: I18n.t('pageCopy.diagnosis.clearCurrentSession'),
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
                    textContent: options.embeddedTitle || I18n.t('pageCopy.diagnosis.aiDiagnosis')
                }));
            }
            embeddedToolbar.appendChild(headerActions);
            content.appendChild(embeddedToolbar);
        } else {
            Header.render(I18n.t('pageCopy.diagnosis.aiDiagnosis2'), headerActions);
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
            title: I18n.t('pageCopy.diagnosis.newSession'),
            style: { flex: '1' },
            onClick: () => this._createSession()
        });

        // Toggle sidebar button
        const toggleSidebarBtn = DOM.el('button', {
            className: 'btn-icon-only',
            id: 'sidebar-toggle-btn',
            innerHTML: '<i data-lucide="panel-left-close"></i>',
            title: I18n.t('pageCopy.diagnosis.hideSessionList'),
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
        disclaimer.textContent = I18n.t('pageCopy.diagnosis.contentIsGeneratedByAiAndIs');
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
            Toast.info(I18n.t('skillAuthorization.emptyGroups'));
            return;
        }

        const currentAuthorizations = this._normalizeSkillAuthorizations(this.skillAuthorizations);
        const borderColorByLevel = {
            low: 'var(--accent-blue)',
            medium: 'var(--accent-blue)',
            high: 'var(--accent-red)',
        };
        const localizedGroupIds = new Set(['platform_operations', 'high_privilege_operations', 'knowledge_retrieval']);
        const localizedItemIds = new Set(['list_documents', 'read_document']);

        const renderGroup = (group) => {
            const isEnabled = currentAuthorizations[group.id] !== false;
            const groupLabel = localizedGroupIds.has(group.id)
                ? I18n.t(`skillAuthorization.groups.${group.id}.label`)
                : String(group.label || group.id || '');
            const groupDescription = localizedGroupIds.has(group.id)
                ? I18n.t(`skillAuthorization.groups.${group.id}.description`)
                : String(group.description || '');
            const itemBadges = (group.items || []).map(item => {
                const description = localizedItemIds.has(item.id)
                    ? I18n.t(`skillAuthorization.items.${item.id}.description`)
                    : String(item.description || item.id || '');
                return `
                <span
                    title="${Utils.escapeHtml(description).replace(/"/g, '&quot;')}"
                    style="display:inline-flex;align-items:center;padding:3px 7px;border-radius:999px;background:rgba(255,255,255,0.06);border:1px solid var(--border-color);font-size:11px;color:var(--text-secondary);"
                >
                    ${item.kind === 'tool' ? `${I18n.t('skillAuthorization.builtIn')} ` : ''}${Utils.escapeHtml(String(item.id || ''))}
                </span>
            `;
            }).join('');

            return `
                <label style="display:flex;align-items:flex-start;gap:10px;padding:12px 14px;border-radius:10px;cursor:pointer;background:var(--bg-secondary);margin-bottom:10px;border-left:3px solid ${borderColorByLevel[group.warning_level] || 'var(--accent-blue)'};">
                    <input type="checkbox" class="skill-auth-toggle" data-group-id="${group.id}" ${isEnabled ? 'checked' : ''} style="margin-top:4px;">
                    <div style="flex:1;min-width:0;">
                        <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:4px;">
                            <div style="font-weight:600;font-size:14px;color:var(--text-primary);">${Utils.escapeHtml(groupLabel)}</div>
                            <span class="badge ${isEnabled ? 'badge-success' : 'badge-danger'}" id="skill-auth-badge-${group.id}">
                                ${I18n.t(isEnabled ? 'skillAuthorization.allowed' : 'skillAuthorization.denied')}
                            </span>
                        </div>
                        <div style="font-size:12px;line-height:1.5;color:var(--text-secondary);">${Utils.escapeHtml(groupDescription)}</div>
                        <div style="margin-top:8px;display:flex;flex-wrap:wrap;gap:5px;max-height:112px;overflow:auto;">
                            ${itemBadges || `<span style="font-size:12px;color:var(--text-muted);">${I18n.t('skillAuthorization.emptyItems')}</span>`}
                        </div>
                    </div>
                </label>
            `;
        };

        Modal.show({
            title: I18n.t('skillAuthorization.title'),
            width: 'min(1120px, 94vw)',
            content: `
                <p style="margin-bottom:12px;font-size:12px;color:var(--text-secondary);line-height:1.6;">
                    ${I18n.t('skillAuthorization.help')}
                </p>
                <div id="skill-authorization-list">
                    ${groups.map(group => renderGroup(group)).join('')}
                </div>
            `,
            buttons: [
                { text: I18n.t('common.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('skillAuthorization.apply'), variant: 'primary', onClick: () => this._applySkillAuthorizations() }
            ]
        });

        this._skillAuthorizationCheckboxes = document.querySelectorAll('.skill-auth-toggle');
        this._skillAuthorizationCheckboxes.forEach(cb => {
            cb.addEventListener('change', () => {
                const badge = document.getElementById(`skill-auth-badge-${cb.dataset.groupId}`);
                if (badge) {
                    badge.className = `badge ${cb.checked ? 'badge-success' : 'badge-danger'}`;
                    badge.textContent = I18n.t(cb.checked ? 'skillAuthorization.allowed' : 'skillAuthorization.denied');
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
        Toast.success(I18n.t('skillAuthorization.updated'));
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
                    textContent: s.title.substring(0, 40) || I18n.t('pageCopy.diagnosis.session') + s.id
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
            Toast.error(e.message || I18n.t('common.requestFailed'));
        }
    },

    async _createSession(options = {}) {
        const { reloadList = true, switchSession = true } = options;
        const conn = this._getSelectedDatasource();
        try {
            const session = await API.createChatSession({
                datasource_id: conn?.id || null,
                host_id: this._renderOptions?.fixedHostId || null,
                title: this._renderOptions?.initialSessionTitle || I18n.t('pageCopy.diagnosis.newSession'),
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
            Toast.error(I18n.t('chat.createSessionFailed', { message: e.message }));
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
            console.error('Failed to load messages:', e);
            Toast.error(e.message || I18n.t('common.requestFailed'));
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
                Toast.error(I18n.t('auth.sessionExpired'));
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
            Toast.warning(I18n.t('chat.noActiveSession'));
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
                warningText = I18n.t('pageCopy.diagnosis.theContextIsCloseToTheUpper');
            } else if (usageRate >= 0.85) {
                warningLevel = 'danger';
                warningText = I18n.t('pageCopy.diagnosis.theContextIsVeryCloseToThe');
            } else if (usageRate >= 0.7) {
                warningLevel = 'warning';
                warningText = I18n.t('pageCopy.diagnosis.theUsageOfContextIsHighIt');
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
                state.thinking_message || I18n.t('pageCopy.diagnosis.aiGenerating')
            );
        } else if (!hasRenderedContent && state.status !== 'awaiting_approval') {
            ChatWidget.showThinkingIndicator('llm_thinking', I18n.t('pageCopy.diagnosis.aiGenerating'));
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
                    thinking_message: data.message || I18n.t('pageCopy.diagnosis.thinkingAndAnalyzing'),
                    run_id: data.run_id || this._pendingResumeState?.run_id || null,
                });
                ChatWidget.showThinkingIndicator(data.phase, data.message);
                break;
            case 'thinking_phase':
                console.log('[WS] calling updateThinkingIndicator', data.phase, data.message);
                this._rememberResumeState({
                    thinking_phase: data.phase || 'llm_thinking',
                    thinking_message: data.message || I18n.t('pageCopy.diagnosis.thinkingAndAnalyzing'),
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
                    const msg = `${I18n.t('pageCopy.diagnosis.executing')} ${data.tool_name}...`;
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
                    summary: data.action === 'approved' ? I18n.t('pageCopy.diagnosis.approvedExecuting') : I18n.t('pageCopy.diagnosis.userHasRefusedExecution'),
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
                    thinking_message: data.thinking_message || data.message || I18n.t('pageCopy.diagnosis.aiGenerating'),
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
        const riskLabel = data.risk_level === 'destructive' ? I18n.t('pageCopy.diagnosis.dangerousOperation') : I18n.t('pageCopy.diagnosis.highRiskOperations');

        card.innerHTML = I18n.t('pageCopy.diagnosis.skillApprovalPrompt', { value0: riskColor, value1: riskColor, value2: riskColor, value3: riskLabel, value4: ChatWidget._escapeHtml(data.tool_name), value5: data.risk_reason ? `<div style="margin-bottom:8px;color:var(--text-secondary);">${ChatWidget._escapeHtml(data.risk_reason)}</div>` : '', value6: data.approval_id, value7: data.approval_id });
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
            summary: action === 'approved' ? I18n.t('pageCopy.diagnosis.approvedExecuting') : I18n.t('pageCopy.diagnosis.userHasRefusedExecution'),
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
                const statusText = action === 'approved' ? I18n.t('pageCopy.diagnosis.approvedExecuting') : I18n.t('pageCopy.diagnosis.rejected');
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
            Toast.error(e.message || I18n.t('common.requestFailed'));
            // Re-enable buttons on error
            if (card) {
                const buttons = card.querySelectorAll('button');
                buttons.forEach(btn => { btn.disabled = false; btn.style.opacity = '1'; });
            }
            ChatWidget.updateApprovalState(approvalId, {
                status: 'waiting_approval',
                summary: I18n.t('pageCopy.diagnosis.skillStillAwaitingConfirmation'),
                metadata: {
                    approval_status: 'pending',
                },
            });
        }
    },

    async _clearSession() {
        if (!this.currentSessionId) {
            Toast.warning(I18n.t('chat.noActiveSession'));
            return;
        }
        Modal.show({
            title: I18n.t('pageCopy.diagnosis.clearCurrentSession2'),
            content: I18n.t("pageCopy.diagnosis._clearSessionContent"),
            buttons: [
                { text: I18n.t('pageCopy.diagnosis.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('pageCopy.diagnosis.confirmClearing'), variant: 'danger', onClick: async () => {
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
                        Toast.success(I18n.t('chat.sessionCleared'));
                    } catch (e) {
                        Toast.error(I18n.t('chat.clearSessionFailed', { message: e.message }));
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
        Toast.info(I18n.t('chat.generationStopped'));
    },

    async _deleteSession() {
        if (!this.currentSessionId) {
            Toast.warning(I18n.t('chat.noActiveSession'));
            return;
        }
        const sessions = Store.get('chatSessions') || [];
        const session = sessions.find(s => s.id === this.currentSessionId);
        Modal.show({
            title: I18n.t('pageCopy.diagnosis.deleteSession'),
            content: I18n.t('pageCopy.diagnosis._deleteSessionContent', {
                value0: session?.title || I18n.t('pageCopy.diagnosis._deleteSessionContent2') + this.currentSessionId
            }),
            buttons: [
                { text: I18n.t('pageCopy.diagnosis.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('pageCopy.diagnosis.delete'), variant: 'danger', onClick: async () => {
                    Modal.hide();
                    try {
                        await API.deleteChatSession(this.currentSessionId);
                        this.currentSessionId = null;
                        await this._loadSessions();
                        Toast.success(I18n.t('chat.sessionDeleted'));
                    } catch (e) {
                        Toast.error(I18n.t('chat.deleteSessionFailed', { message: e.message }));
                    }
                } }
            ]
        });
    },

    async _deleteSessionById(sessionId) {
        const sessions = Store.get('chatSessions') || [];
        const session = sessions.find(s => s.id === sessionId);
        Modal.show({
            title: I18n.t('pageCopy.diagnosis.deleteSession'),
            content: I18n.t('pageCopy.diagnosis._deleteSessionByIdContent', {
                value0: session?.title || I18n.t('pageCopy.diagnosis._deleteSessionByIdContent2') + sessionId
            }),
            buttons: [
                { text: I18n.t('pageCopy.diagnosis.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('pageCopy.diagnosis.delete'), variant: 'danger', onClick: async () => {
                    Modal.hide();
                    try {
                        await API.deleteChatSession(sessionId);
                        if (this.currentSessionId === sessionId) {
                            this.currentSessionId = null;
                        }
                        await this._loadSessions();
                        Toast.success(I18n.t('chat.sessionDeleted'));
                    } catch (e) {
                        Toast.error(I18n.t('chat.deleteSessionFailed', { message: e.message }));
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
