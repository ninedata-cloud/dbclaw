/* Alert Management Page */
const AlertsPage = {
    datasourceSelector: null,
    _renderOptions: null,
    _container: null,
    datasources: [],
    events: [],
    subscriptions: [],
    notificationIntegrations: [],
    currentUser: null,
    expandedEvents: new Set(),
    eventAlerts: {},
    filters: {
        datasource_id: null,
        status: 'all',
        severity: null,
        search: '',
        start_time: null,
        end_time: null
    },
    currentPage: {
        events: 1
    },
    pageSize: {
        events: 10
    },
    totalCount: {
        events: 0
    },

    async init(options = {}) {
        this._renderOptions = options || {};
        this._container = options.container || DOM.$('#page-content');
        this.currentUser = Store.get('currentUser');
        if (!this.currentUser) {
            Router.navigate('login');
            return;
        }

        if (options.fixedDatasourceId) {
            this.filters.datasource_id = options.fixedDatasourceId;
        }

        await this.loadDatasources();
        if (!options.hideSubscriptions) {
            await this.loadNotificationIntegrations();
        }
        await this.loadEvents();
        if (!options.hideSubscriptions) {
            await this.loadSubscriptions();
        }
        this.render();
        return () => this._cleanup();
    },

    async loadNotificationIntegrations() {
        try {
            const items = await API.get('/api/integrations');
            this.notificationIntegrations = (items || []).filter(item => item.integration_type === 'outbound_notification' && item.enabled);
        } catch (error) {
            console.error('Failed to load notification integrations:', error);
            this.notificationIntegrations = [];
        }
    },

    async loadDatasources() {
        try {
            this.datasources = await API.get('/api/datasources');
        } catch (error) {
            console.error('Failed to load datasources:', error);
            this.datasources = [];
        }
    },

    async loadEvents() {
        try {
            const offset = (this.currentPage.events - 1) * this.pageSize.events;
            const params = new URLSearchParams();

            if (this.filters.datasource_id) params.append('datasource_ids', this.filters.datasource_id);
            if (this.filters.status && this.filters.status !== 'all') params.append('status', this.filters.status);
            if (this.filters.severity) params.append('severity', this.filters.severity);
            if (this.filters.search) params.append('search', this.filters.search);
            if (this.filters.start_time) params.append('start_time', this.filters.start_time);
            if (this.filters.end_time) params.append('end_time', this.filters.end_time);
            params.append('limit', this.pageSize.events);
            params.append('offset', offset);

            const response = await API.get(`/api/alerts/events?${params.toString()}`);
            this.events = response.events || [];
            this.totalCount.events = response.total || 0;
        } catch (error) {
            console.error('Failed to load events:', error);
            this.events = [];
            this.totalCount.events = 0;
        }
    },

    async loadSubscriptions() {
        try {
            this.subscriptions = await API.get(`/api/alerts/subscriptions/list?user_id=${this.currentUser.id}`);
        } catch (error) {
            console.error('Failed to load subscriptions:', error);
            this.subscriptions = [];
        }
    },

    async loadEventAlerts(eventId) {
        if (this.eventAlerts[eventId]) return this.eventAlerts[eventId];

        try {
            const response = await API.get(`/api/alerts/events/${eventId}/alerts`);
            this.eventAlerts[eventId] = response.alerts || [];
            return this.eventAlerts[eventId];
        } catch (error) {
            console.error('Failed to load event alerts:', error);
            return [];
        }
    },

    async acknowledgeEvent(eventId) {
        try {
            await API.post(`/api/alerts/events/${eventId}/acknowledge`, { user_id: this.currentUser.id });
            await this.loadEvents();
            this.updateAlertsList();
            Toast.success('事件已确认');
        } catch (error) {
            console.error('Failed to acknowledge event:', error);
            Toast.error('确认事件失败');
        }
    },

    async resolveEvent(eventId) {
        try {
            await API.post(`/api/alerts/events/${eventId}/resolve`, {});
            await this.loadEvents();
            this.updateAlertsList();
            Toast.success('事件已解决');
        } catch (error) {
            console.error('Failed to resolve event:', error);
            Toast.error('解决事件失败');
        }
    },

    async toggleEventExpansion(eventId) {
        if (this.expandedEvents.has(eventId)) {
            this.expandedEvents.delete(eventId);
        } else {
            this.expandedEvents.add(eventId);
            await this.loadEventAlerts(eventId);
        }
        this.updateAlertsList();
    },


    _cleanup() {
        this.datasourceSelector?.destroy();
        this.datasourceSelector = null;
        this._renderOptions = null;
        this._container = null;
    },

    render() {
        const container = this._container || DOM.$('#page-content');
        DOM.clear(container);
        const headerActions = this._buildHeaderActions();
        if (this._renderOptions?.embedded) {
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
                textContent: '告警管理'
            }));
            if (Array.isArray(headerActions)) {
                headerActions.forEach(action => {
                    if (action instanceof Node) {
                        embeddedToolbar.appendChild(action);
                    }
                });
            } else if (headerActions instanceof Node) {
                embeddedToolbar.appendChild(headerActions);
            }
            container.appendChild(embeddedToolbar);
        } else {
            Header.render('告警管理', headerActions);
        }

        if (this._renderOptions?.hideSubscriptions) {
            const note = DOM.el('div', {
                className: 'instance-inline-note',
                style: {
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '12px',
                    marginBottom: '12px',
                    padding: '12px 14px',
                    borderRadius: '10px',
                    background: 'var(--bg-secondary)'
                }
            });
            note.appendChild(DOM.el('div', {
                textContent: '当前仅展示该实例的告警事件与详情，订阅管理继续保留在全局告警页。'
            }));
            note.appendChild(DOM.el('button', {
                className: 'btn btn-secondary btn-sm',
                textContent: '打开全局告警页',
                onClick: () => Router.navigate('alerts')
            }));
            container.appendChild(note);
            const alertsContent = DOM.el('div', { className: 'tab-pane active', id: 'alerts-pane' });
            alertsContent.appendChild(this.renderAlertsPane());
            container.appendChild(alertsContent);
        } else {
            const tabs = DOM.el('div', { className: 'tabs' });
            const alertsTab = DOM.el('button', {
                className: 'tab active',
                textContent: '告警列表',
                onClick: (e) => this.switchTab(e.target, 'alerts')
            });
            const subscriptionsTab = DOM.el('button', {
                className: 'tab',
                textContent: '订阅管理',
                onClick: (e) => this.switchTab(e.target, 'subscriptions')
            });
            tabs.appendChild(alertsTab);
            tabs.appendChild(subscriptionsTab);
            container.appendChild(tabs);

            const tabContent = DOM.el('div', { className: 'tab-content' });
            const alertsContent = DOM.el('div', { className: 'tab-pane active', id: 'alerts-pane' });
            alertsContent.appendChild(this.renderAlertsPane());
            const subscriptionsContent = DOM.el('div', { className: 'tab-pane', id: 'subscriptions-pane' });
            subscriptionsContent.appendChild(this.renderSubscriptionsList());
            tabContent.appendChild(alertsContent);
            tabContent.appendChild(subscriptionsContent);
            container.appendChild(tabContent);
        }

        DOM.createIcons();
    },

    _buildHeaderActions() {
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters' });

        if (!this._renderOptions?.fixedDatasourceId) {
            const datasourceContainer = DOM.el('div', {
                id: 'alerts-datasource-selector',
                style: { minWidth: '280px', maxWidth: '380px', flex: '1' }
            });
            filtersContainer.appendChild(datasourceContainer);

            setTimeout(() => {
                const container = DOM.$('#alerts-datasource-selector');
                if (!container) return;

                this.datasourceSelector?.destroy();
                this.datasourceSelector = new DatasourceSelector({
                    container,
                    allowEmpty: true,
                    emptyText: '全部数据源',
                    showStatus: true,
                    showDetails: true,
                    onLoad: () => {
                        if (this.filters.datasource_id) this.datasourceSelector.setValue(this.filters.datasource_id);
                    },
                    onChange: (datasource) => {
                        this.filters.datasource_id = datasource ? datasource.id : null;
                        this.resetPagination();
                        this.loadEvents().then(() => this.updateAlertsList());
                    }
                });
            }, 0);
        }

        const statusSelect = DOM.el('select', {
            className: 'filter-select',
            onChange: (e) => {
                this.filters.status = e.target.value;
                this.resetPagination();
                this.loadEvents().then(() => this.updateAlertsList());
            }
        });
        statusSelect.appendChild(DOM.el('option', { value: 'all', textContent: '全部状态' }));
        statusSelect.appendChild(DOM.el('option', { value: 'active', textContent: '活跃' }));
        statusSelect.appendChild(DOM.el('option', { value: 'acknowledged', textContent: '已确认' }));
        statusSelect.appendChild(DOM.el('option', { value: 'resolved', textContent: '已解决' }));
        statusSelect.value = this.filters.status;
        filtersContainer.appendChild(statusSelect);

        const severitySelect = DOM.el('select', {
            className: 'filter-select',
            onChange: (e) => {
                this.filters.severity = e.target.value || null;
                this.resetPagination();
                this.loadEvents().then(() => this.updateAlertsList());
            }
        });
        severitySelect.appendChild(DOM.el('option', { value: '', textContent: '全部严重程度' }));
        severitySelect.appendChild(DOM.el('option', { value: 'critical', textContent: '严重' }));
        severitySelect.appendChild(DOM.el('option', { value: 'high', textContent: '高' }));
        severitySelect.appendChild(DOM.el('option', { value: 'medium', textContent: '中' }));
        severitySelect.appendChild(DOM.el('option', { value: 'low', textContent: '低' }));
        severitySelect.value = this.filters.severity || '';
        filtersContainer.appendChild(severitySelect);

        const startTimeInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'filter-input',
            title: '开始时间',
            value: this.filters.start_time || '',
            onChange: (e) => {
                this.filters.start_time = e.target.value || null;
                this.resetPagination();
                this.loadEvents().then(() => this.updateAlertsList());
            }
        });
        filtersContainer.appendChild(startTimeInput);

        const endTimeInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'filter-input',
            title: '结束时间',
            value: this.filters.end_time || '',
            onChange: (e) => {
                this.filters.end_time = e.target.value || null;
                this.resetPagination();
                this.loadEvents().then(() => this.updateAlertsList());
            }
        });
        filtersContainer.appendChild(endTimeInput);

        const searchInput = DOM.el('input', {
            type: 'text',
            className: 'filter-input',
            placeholder: '搜索标题或内容',
            value: this.filters.search || '',
            onInput: (e) => {
                this.filters.search = e.target.value;
                clearTimeout(this.searchTimeout);
                this.searchTimeout = setTimeout(() => {
                    this.resetPagination();
                    this.loadEvents().then(() => this.updateAlertsList());
                }, 500);
            }
        });
        filtersContainer.appendChild(searchInput);

        return [filtersContainer];
    },

    renderAlertsPane() {
        const pane = DOM.el('div', { className: 'alerts-pane-content' });
        pane.appendChild(this.renderEventsList());
        return pane;
    },

    renderEventsList() {
        const list = DOM.el('div', { className: 'events-list', id: 'events-list' });

        if (this.events.length === 0) {
            list.appendChild(DOM.el('div', { className: 'empty-state', textContent: '暂无事件' }));
            return list;
        }

        const table = DOM.el('table', { className: 'data-table events-table' });
        const thead = DOM.el('thead');
        const headerRow = DOM.el('tr');
        headerRow.appendChild(DOM.el('th', { textContent: '', style: 'width: 40px' }));
        headerRow.appendChild(DOM.el('th', { textContent: '严重程度' }));
        headerRow.appendChild(DOM.el('th', { textContent: '数据源' }));
        headerRow.appendChild(DOM.el('th', { textContent: '类型/指标' }));
        headerRow.appendChild(DOM.el('th', { textContent: '标题' }));
        headerRow.appendChild(DOM.el('th', { textContent: '开始时间' }));
        headerRow.appendChild(DOM.el('th', { textContent: '恢复时间' }));
        headerRow.appendChild(DOM.el('th', { textContent: '数量' }));
        headerRow.appendChild(DOM.el('th', { textContent: '状态' }));
        headerRow.appendChild(DOM.el('th', { textContent: '操作' }));
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = DOM.el('tbody');
        for (const event of this.events) {
            const isExpanded = this.expandedEvents.has(event.id);
            const row = DOM.el('tr', { className: `event-row ${isExpanded ? 'expanded' : ''}` });

            const expandCell = DOM.el('td');
            const expandIcon = DOM.el('span', {
                className: `expand-icon ${isExpanded ? 'expanded' : ''}`,
                textContent: '▶',
                style: 'cursor: pointer; user-select: none;'
            });
            expandCell.appendChild(expandIcon);
            expandCell.onclick = () => this.toggleEventExpansion(event.id);
            row.appendChild(expandCell);

            const severityCell = DOM.el('td');
            severityCell.appendChild(DOM.el('span', {
                className: `severity-badge severity-${event.severity}`,
                textContent: this.getSeverityLabel(event.severity)
            }));
            row.appendChild(severityCell);

            const datasource = this.datasources.find(ds => ds.id === event.datasource_id);
            row.appendChild(DOM.el('td', { textContent: datasource ? datasource.name : `ID: ${event.datasource_id}` }));

            const typeMetric = event.metric_name || this.getAlertTypeLabel(event.alert_type);
            row.appendChild(DOM.el('td', { textContent: typeMetric || '-' }));
            row.appendChild(DOM.el('td', { textContent: event.title || '-' }));
            row.appendChild(DOM.el('td', { textContent: event.event_start_time ? new Date(event.event_start_time).toLocaleString('zh-CN') : '-' }));

            const endTime = event.status === 'resolved' && event.event_end_time
                ? new Date(event.event_end_time).toLocaleString('zh-CN')
                : '-';
            row.appendChild(DOM.el('td', { textContent: endTime }));

            const countCell = DOM.el('td');
            countCell.appendChild(DOM.el('span', {
                className: 'count-badge',
                textContent: event.alert_count ?? 0
            }));
            row.appendChild(countCell);

            const statusCell = DOM.el('td');
            statusCell.appendChild(DOM.el('span', {
                className: `status-badge status-${event.status}`,
                textContent: this.getStatusLabel(event.status)
            }));
            row.appendChild(statusCell);

            const actionsCell = DOM.el('td', { className: 'actions-cell' });
            if (event.status === 'active') {
                actionsCell.appendChild(DOM.el('button', {
                    className: 'btn btn-sm btn-secondary',
                    textContent: '✓',
                    title: '确认',
                    onClick: (e) => {
                        e.stopPropagation();
                        this.acknowledgeEvent(event.id);
                    }
                }));
            }
            if (event.status !== 'resolved') {
                actionsCell.appendChild(DOM.el('button', {
                    className: 'btn btn-sm btn-success',
                    textContent: '✓✓',
                    title: '解决',
                    onClick: (e) => {
                        e.stopPropagation();
                        this.resolveEvent(event.id);
                    }
                }));
            }
            // AI diagnosis button
            actionsCell.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-ai',
                textContent: '🤖 AI',
                title: 'AI 诊断',
                onClick: (e) => {
                    e.stopPropagation();
                    this._navigateToDiagnosis(event);
                }
            }));
            row.appendChild(actionsCell);
            tbody.appendChild(row);

            if (isExpanded) {
                const expandedRow = DOM.el('tr', { className: 'expanded-row' });
                const expandedCell = DOM.el('td', { colSpan: 11 });
                const alertsContainer = DOM.el('div', { className: 'event-alerts-container' });
                const alerts = this.eventAlerts[event.id] || [];

                // AI diagnosis summary with root cause and recommended actions
                if (event.root_cause || event.recommended_actions || event.ai_diagnosis_summary) {
                    const diagDiv = DOM.el('div', {
                        style: 'background:rgba(47,129,247,0.06);border-left:3px solid var(--accent-blue);padding:10px 12px;margin-bottom:12px;border-radius:6px;font-size:13px;'
                    });
                    let diagHTML = '<div style="font-weight:600;margin-bottom:8px;color:var(--accent-blue);">🧠 AI 诊断分析</div>';

                    if (event.root_cause) {
                        diagHTML += `<div style="margin-bottom:8px;"><div style="font-weight:500;color:var(--text-primary);margin-bottom:3px;">🔍 根本原因</div><div style="color:var(--text-secondary);line-height:1.6;">${this._escapeHtml(event.root_cause)}</div></div>`;
                    }
                    if (event.recommended_actions) {
                        diagHTML += `<div style="margin-bottom:8px;"><div style="font-weight:500;color:var(--text-primary);margin-bottom:3px;">🛠 处置建议</div><div style="color:var(--text-secondary);line-height:1.6;">${this._escapeHtml(event.recommended_actions)}</div></div>`;
                    }
                    if (event.ai_diagnosis_summary && !event.root_cause && !event.recommended_actions) {
                        diagHTML += `<div style="color:var(--text-secondary);line-height:1.6;">${this._escapeHtml(event.ai_diagnosis_summary)}</div>`;
                    }
                    diagDiv.innerHTML = diagHTML;
                    alertsContainer.appendChild(diagDiv);
                } else if (event.status === 'active' || event.diagnosis_status === 'in_progress') {
                    const diagPending = DOM.el('div', {
                        style: 'background:rgba(47,129,247,0.05);padding:10px 12px;margin-bottom:12px;border-radius:6px;font-size:12px;color:var(--text-muted);'
                    });
                    diagPending.textContent = '🤖 AI 正在诊断中...';
                    alertsContainer.appendChild(diagPending);
                } else if (event.diagnosis_status === 'pending') {
                    const diagPending = DOM.el('div', {
                        style: 'background:rgba(251,140,0,0.08);padding:10px 12px;margin-bottom:12px;border-radius:6px;font-size:12px;color:#fb8c00;'
                    });
                    diagPending.textContent = '⏳ 诊断超时，正在后台继续分析...';
                    alertsContainer.appendChild(diagPending);
                }

                if (alerts.length > 0) {
                    const alertsTable = DOM.el('table', { className: 'nested-alerts-table' });
                    const alertsThead = DOM.el('thead');
                    const alertsHeaderRow = DOM.el('tr');
                    alertsHeaderRow.appendChild(DOM.el('th', { textContent: '时间' }));
                    alertsHeaderRow.appendChild(DOM.el('th', { textContent: '指标值' }));
                    alertsHeaderRow.appendChild(DOM.el('th', { textContent: '阈值' }));
                    alertsHeaderRow.appendChild(DOM.el('th', { textContent: '状态' }));
                    alertsHeaderRow.appendChild(DOM.el('th', { textContent: '操作' }));
                    alertsThead.appendChild(alertsHeaderRow);
                    alertsTable.appendChild(alertsThead);

                    const alertsTbody = DOM.el('tbody');
                    for (const alert of alerts) {
                        const alertRow = DOM.el('tr');
                        alertRow.appendChild(DOM.el('td', { textContent: alert.created_at ? new Date(alert.created_at).toLocaleString('zh-CN') : '-' }));
                        alertRow.appendChild(DOM.el('td', { textContent: this.formatNumber(alert.metric_value) }));
                        alertRow.appendChild(DOM.el('td', { textContent: this.formatNumber(alert.threshold_value) }));

                        const alertStatusCell = DOM.el('td');
                        alertStatusCell.appendChild(DOM.el('span', {
                            className: `status-badge status-${alert.status}`,
                            textContent: this.getStatusLabel(alert.status)
                        }));
                        alertRow.appendChild(alertStatusCell);

                        const alertActionsCell = DOM.el('td');
                        alertActionsCell.appendChild(DOM.el('button', {
                            className: 'btn-icon',
                            textContent: '👁',
                            title: '查看详情',
                            onClick: () => this.showAlertDetail(alert)
                        }));
                        alertRow.appendChild(alertActionsCell);
                        alertsTbody.appendChild(alertRow);
                    }
                    alertsTable.appendChild(alertsTbody);
                    alertsContainer.appendChild(alertsTable);
                } else {
                    alertsContainer.textContent = '加载中...';
                }

                expandedCell.appendChild(alertsContainer);
                expandedRow.appendChild(expandedCell);
                tbody.appendChild(expandedRow);
            }
        }

        table.appendChild(tbody);
        list.appendChild(table);
        list.appendChild(this.renderPagination('events'));
        return list;
    },


    renderSubscriptionsList() {
        const list = DOM.el('div', { className: 'subscriptions-list', id: 'subscriptions-list' });
        const toolbar = DOM.el('div', { style: 'margin-bottom: 16px; display: flex; justify-content: flex-end;' });
        toolbar.appendChild(DOM.el('button', {
            className: 'btn btn-primary',
            textContent: '新建订阅',
            onClick: () => this.showSubscriptionModal()
        }));
        list.appendChild(toolbar);

        if (this.subscriptions.length === 0) {
            list.appendChild(DOM.el('div', { className: 'empty-state', textContent: '暂无订阅' }));
            return list;
        }

        const table = DOM.el('table', { className: 'data-table' });
        const thead = DOM.el('thead');
        const headerRow = DOM.el('tr');
        headerRow.appendChild(DOM.el('th', { textContent: '数据源' }));
        headerRow.appendChild(DOM.el('th', { textContent: '严重程度' }));
        headerRow.appendChild(DOM.el('th', { textContent: '通知目标' }));
        headerRow.appendChild(DOM.el('th', { textContent: '状态' }));
        headerRow.appendChild(DOM.el('th', { textContent: '操作' }));
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = DOM.el('tbody');
        for (const sub of this.subscriptions) {
            const row = DOM.el('tr');
            const datasourceNames = sub.datasource_ids.length === 0 ? '全部' : sub.datasource_ids.map(id => {
                const ds = this.datasources.find(d => d.id === id);
                return ds ? ds.name : `ID: ${id}`;
            }).join(', ');
            row.appendChild(DOM.el('td', { textContent: datasourceNames }));

            const severityText = sub.severity_levels.length === 0 ? '全部' : sub.severity_levels.map(s => this.getSeverityLabel(s)).join(', ');
            row.appendChild(DOM.el('td', { textContent: severityText }));

            const targetNames = (sub.integration_targets || []).length > 0
                ? sub.integration_targets.map(target => `${target.name} (${this.getIntegrationName(target.integration_id)})`).join(', ')
                : '未配置';
            row.appendChild(DOM.el('td', { textContent: targetNames }));

            const statusCell = DOM.el('td');
            statusCell.appendChild(DOM.el('span', {
                className: `status-badge ${sub.enabled ? 'status-active' : 'status-disabled'}`,
                textContent: sub.enabled ? '启用' : '禁用'
            }));
            row.appendChild(statusCell);

            const actionsCell = DOM.el('td', { className: 'actions-cell' });
            actionsCell.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: '<i data-lucide="edit"></i>',
                title: '编辑',
                onClick: () => this.showSubscriptionModal(sub)
            }));
            actionsCell.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-primary',
                innerHTML: '<i data-lucide="send"></i>',
                title: '测试通知',
                onClick: () => this.testNotification(sub.id)
            }));
            actionsCell.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-danger',
                innerHTML: '<i data-lucide="trash-2"></i>',
                title: '删除',
                onClick: () => this.deleteSubscription(sub.id)
            }));
            row.appendChild(actionsCell);
            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        list.appendChild(table);
        return list;
    },

    switchTab(tabEl, tabName) {
        DOM.$$('.tab').forEach(t => t.classList.remove('active'));
        tabEl.classList.add('active');
        DOM.$$('.tab-pane').forEach(p => p.classList.remove('active'));
        DOM.$(`#${tabName}-pane`).classList.add('active');
    },

    updateAlertsList() {
        const alertsPane = DOM.$('#alerts-pane');
        if (!alertsPane) return;

        alertsPane.replaceChildren(this.renderAlertsPane());
        DOM.createIcons();
    },

    updateEventsList() {
        this.updateAlertsList();
    },

    updateSubscriptionsList() {
        const listContainer = DOM.$('#subscriptions-list');
        if (!listContainer) return;
        const newList = this.renderSubscriptionsList();
        listContainer.parentNode.replaceChild(newList, listContainer);
        DOM.createIcons();
    },

    async showAlertDetail(alert) {
        Modal.show({
            title: '告警详情',
            content: this.renderAlertDetailContent(alert),
            size: 'large',
            buttons: [
                { text: '关闭', className: 'btn-secondary', onClick: () => Modal.hide() }
            ]
        });
    },

    renderAlertDetailContent(alert) {
        const container = DOM.el('div', { className: 'alert-detail-container' });
        const diagCtx = alert.diagnosis_context || {};
        const dsInfo = diagCtx.datasource_info || {};
        const linkedReport = diagCtx.linked_report || {};

        // ========== 1. 数据库配置信息区块 ==========
        const dsCard = DOM.el('div', { className: 'detail-card' });
        dsCard.innerHTML = `
            <div class="detail-card-header">
                <span class="detail-card-icon">📊</span>
                <span class="detail-card-title">数据库配置信息</span>
            </div>
            <div class="detail-card-body">
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">名称</span>
                        <span class="detail-value">${this._escapeHtml(dsInfo.name || '-')}</span>
                    </div>
                    <div class="detail-row-item">
                        <span class="detail-label">类型</span>
                        <span class="detail-value">${this._escapeHtml(this._getDbTypeLabel(dsInfo.db_type))}</span>
                    </div>
                </div>
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">连接</span>
                        <span class="detail-value">${this._escapeHtml(dsInfo.host || '-')}:${dsInfo.port || '-'} / ${this._escapeHtml(dsInfo.database || '-')}</span>
                    </div>
                </div>
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">等级</span>
                        <span class="detail-value">${this._getImportanceBadge(dsInfo.importance_level)}</span>
                    </div>
                    <div class="detail-row-item">
                        <span class="detail-label">监控间隔</span>
                        <span class="detail-value">${dsInfo.monitoring_interval || 60}秒</span>
                    </div>
                </div>
                ${dsInfo.remark ? `
                <div class="detail-row">
                    <div class="detail-row-item full-width">
                        <span class="detail-label">备注</span>
                        <span class="detail-value">${this._escapeHtml(dsInfo.remark)}</span>
                    </div>
                </div>` : ''}
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">状态</span>
                        <span class="detail-value ${this._getConnectionStatusClass(dsInfo.connection_status)}">${this._getConnectionStatusLabel(dsInfo.connection_status)}</span>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(dsCard);

        // ========== 2. 告警详情区块 ==========
        const alertCard = DOM.el('div', { className: 'detail-card' });
        const severityClass = `severity-${alert.severity}`;
        const severityLabel = this.getSeverityLabel(alert.severity);
        const severityIcon = alert.severity === 'critical' || alert.severity === 'high' ? '🔴' : alert.severity === 'medium' ? '🟠' : '🟡';

        alertCard.innerHTML = `
            <div class="detail-card-header">
                <span class="detail-card-icon">⚠️</span>
                <span class="detail-card-title">告警详情</span>
            </div>
            <div class="detail-card-body">
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">严重程度</span>
                        <span class="detail-value ${severityClass}">${severityIcon} ${severityLabel}</span>
                    </div>
                    <div class="detail-row-item">
                        <span class="detail-label">状态</span>
                        <span class="detail-value">${this.getStatusLabel(alert.status)}</span>
                    </div>
                </div>
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">告警类型</span>
                        <span class="detail-value">${this.getAlertTypeLabel(alert.alert_type)}</span>
                    </div>
                    <div class="detail-row-item">
                        <span class="detail-label">时间</span>
                        <span class="detail-value">${alert.created_at ? new Date(alert.created_at).toLocaleString('zh-CN') : '-'}</span>
                    </div>
                </div>
                ${alert.metric_name ? `
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">指标</span>
                        <span class="detail-value">${this._escapeHtml(alert.metric_name)}</span>
                    </div>
                    <div class="detail-row-item">
                        <span class="detail-label">当前值</span>
                        <span class="detail-value">${this.formatNumber(alert.metric_value)}</span>
                    </div>
                    ${alert.threshold_value !== null && alert.threshold_value !== undefined ? `
                    <div class="detail-row-item">
                        <span class="detail-label">阈值</span>
                        <span class="detail-value">${this.formatNumber(alert.threshold_value)}</span>
                    </div>` : ''}
                </div>` : ''}
                ${alert.trigger_reason ? `
                <div class="detail-row">
                    <div class="detail-row-item full-width">
                        <span class="detail-label">触发原因</span>
                        <span class="detail-value">${this._escapeHtml(alert.trigger_reason)}</span>
                    </div>
                </div>` : ''}
                ${alert.acknowledged_at ? `
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">确认时间</span>
                        <span class="detail-value">${new Date(alert.acknowledged_at).toLocaleString('zh-CN')}</span>
                    </div>
                </div>` : ''}
                ${alert.resolved_at ? `
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">恢复时间</span>
                        <span class="detail-value">${new Date(alert.resolved_at).toLocaleString('zh-CN')}</span>
                    </div>
                </div>` : ''}
                <div class="detail-row">
                    <div class="detail-row-item full-width">
                        <span class="detail-label">标题</span>
                        <span class="detail-value">${this._escapeHtml(alert.title || '-')}</span>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(alertCard);

        // ========== 3. AI 诊断分析区块 ==========
        const hasDiagnosis = diagCtx.case_summary || diagCtx.diagnosis_summary || diagCtx.root_cause || (diagCtx.recommended_actions_preview && diagCtx.recommended_actions_preview.length > 0);

        if (hasDiagnosis) {
            const diagCard = DOM.el('div', { className: 'detail-card diagnosis-card' });

            let diagHTML = `
                <div class="detail-card-header">
                    <span class="detail-card-icon">🧠</span>
                    <span class="detail-card-title">AI 诊断分析</span>
                </div>
                <div class="detail-card-body">
            `;

            if (diagCtx.case_summary) {
                diagHTML += `
                    <div class="diagnosis-section">
                        <div class="diagnosis-label">📋 案例摘要</div>
                        <div class="diagnosis-content">${this._escapeHtml(diagCtx.case_summary)}</div>
                    </div>
                `;
            }

            if (diagCtx.diagnosis_summary) {
                diagHTML += `
                    <div class="diagnosis-section">
                        <div class="diagnosis-label">🔬 诊断摘要</div>
                        <div class="diagnosis-content">${this._escapeHtml(diagCtx.diagnosis_summary)}</div>
                    </div>
                `;
            }

            if (diagCtx.root_cause) {
                diagHTML += `
                    <div class="diagnosis-section">
                        <div class="diagnosis-label">🔍 根本原因</div>
                        <div class="diagnosis-content">${this._escapeHtml(diagCtx.root_cause)}</div>
                    </div>
                `;
            }

            // Recommended actions with execute buttons
            if (diagCtx.recommended_actions_preview && diagCtx.recommended_actions_preview.length > 0) {
                diagHTML += `<div class="diagnosis-section"><div class="diagnosis-label">🛠 推荐操作</div>`;
                for (const action of diagCtx.recommended_actions_preview) {
                    const riskClass = action.risk_level === 'safe' || action.risk_level === 'low' ? 'risk-safe' : action.risk_level === 'medium' ? 'risk-medium' : 'risk-high';
                    const riskLabel = action.risk_level === 'safe' ? '低风险' : action.risk_level === 'low' ? '低风险' : action.risk_level === 'medium' ? '中风险' : '高风险';
                    diagHTML += `
                        <div class="action-item">
                            <div class="action-info">
                                <span class="action-title">${this._escapeHtml(action.title || action.id)}</span>
                                ${action.summary ? `<span class="action-summary">${this._escapeHtml(action.summary)}</span>` : ''}
                                <span class="action-risk ${riskClass}">${riskLabel}</span>
                            </div>
                            <button class="btn btn-sm btn-primary" onclick="AlertsPage.executeAction(${alert.id}, '${String(action.id).replace(/'/g, "\\'")}', ${linkedReport.report_id || 0})">执行</button>
                        </div>
                    `;
                }
                diagHTML += `</div>`;
            }

            diagHTML += `</div>`;
            diagCard.innerHTML = diagHTML;
            container.appendChild(diagCard);
        }

        // ========== 4. 关联报告区块 ==========
        if (linkedReport && linkedReport.report_id) {
            const reportCard = DOM.el('div', { className: 'detail-card' });
            reportCard.innerHTML = `
                <div class="detail-card-header">
                    <span class="detail-card-icon">📋</span>
                    <span class="detail-card-title">关联诊断报告</span>
                </div>
                <div class="detail-card-body">
                    <div class="report-info">
                        <div class="report-meta">
                            <span class="report-time">${linkedReport.created_at ? new Date(linkedReport.created_at).toLocaleString('zh-CN') : '-'}</span>
                            <span class="report-title">${this._escapeHtml(linkedReport.title || `报告 #${linkedReport.report_id}`)}</span>
                            <span class="report-status">${this._getReportStatusLabel(linkedReport.status)}</span>
                        </div>
                        <button class="btn btn-sm btn-secondary" onclick="AlertsPage.viewReport(${linkedReport.report_id})">查看报告</button>
                    </div>
                </div>
            `;
            container.appendChild(reportCard);
        }

        // ========== 详细内容区块 ==========
        const contentCard = DOM.el('div', { className: 'detail-card' });
        contentCard.innerHTML = `
            <div class="detail-card-header">
                <span class="detail-card-icon">📝</span>
                <span class="detail-card-title">详细内容</span>
            </div>
            <div class="detail-card-body">
                <pre class="detail-content">${this._escapeHtml(alert.content || '-')}</pre>
            </div>
        `;
        container.appendChild(contentCard);

        return container;
    },

    // Helper: Execute recommended action
    async executeAction(alertId, actionId, reportId) {
        if (!reportId) {
            Toast.show('无关联报告，无法执行操作', 'error');
            return;
        }
        try {
            const res = await API.createActionRun({ report_id: reportId, recommendation_id: actionId });
            const run = res?.run;
            if (!run?.run_id) {
                Toast.show('创建动作执行记录失败', 'error');
                return;
            }
            Toast.show('动作已提交执行', 'success');
        } catch (e) {
            Toast.show('执行失败: ' + e.message, 'error');
        }
    },

    // Helper: View report
    viewReport(reportId) {
        Modal.hide();
        if (this._renderOptions?.embedded && this.filters.datasource_id) {
            const params = new URLSearchParams();
            params.set('datasource', this.filters.datasource_id);
            params.set('tab', 'inspections');
            params.set('report', reportId);
            Router.navigate(`instance-detail?${params.toString()}`);
            return;
        }
        Router.navigate(`inspection?report=${encodeURIComponent(reportId)}`);
    },

    _navigateToDiagnosis(event) {
        const prompt = `请结合该告警事件进行根因分析，并给出处置建议。\n\n事件标题：${event.title || '-'}\n严重程度：${event.severity || '-'}\n告警类型：${event.alert_type || '-'}\n指标：${event.metric_name || '-'}\n告警数量：${event.alert_count || 0}`;
        if (this._renderOptions?.embedded) {
            const params = new URLSearchParams();
            params.set('datasource', event.datasource_id);
            params.set('tab', 'ai');
            params.set('alert', event.id);
            params.set('ask', prompt);
            Router.navigate(`instance-detail?${params.toString()}`);
            return;
        }
        const params = new URLSearchParams();
        params.set('datasource', event.datasource_id);
        params.set('alert', event.id);
        params.set('ask', prompt);
        Router.navigate(`diagnosis?${params.toString()}`);
    },

    // Helper: Get database type label
    _getDbTypeLabel(dbType) {
        const labels = {
            mysql: 'MySQL',
            postgresql: 'PostgreSQL',
            mongodb: 'MongoDB',
            redis: 'Redis',
            sqlserver: 'SQL Server',
            oracle: 'Oracle',
            tidb: 'TiDB',
            'tdsql-c-mysql': 'TDSQL-C MySQL',
            oceanbase: 'OceanBase',
            oceanbase_mysql: 'OceanBase MySQL',
            opengauss: 'openGauss',
            dm: 'DM'
        };
        return labels[dbType] || dbType || '-';
    },

    // Helper: Get importance badge
    _getImportanceBadge(level) {
        const labels = { core: '核心', production: '生产', development: '开发', temporary: '临时' };
        const label = labels[level] || level || '生产';
        const colorClass = level === 'core' ? 'importance-core' : level === 'production' ? 'importance-production' : level === 'development' ? 'importance-development' : 'importance-temporary';
        return `<span class="importance-badge ${colorClass}">● ${label}</span>`;
    },

    // Helper: Get connection status label
    _getConnectionStatusLabel(status) {
        const labels = { normal: '✅ 正常', warning: '⚠️ 警告', failed: '❌ 失败', unknown: '❓ 未知' };
        return labels[status] || status || '❓ 未知';
    },

    // Helper: Get connection status class
    _getConnectionStatusClass(status) {
        return status === 'normal' ? 'status-normal' : status === 'warning' ? 'status-warning' : status === 'failed' ? 'status-failed' : 'status-unknown';
    },

    // Helper: Get report status label
    _getReportStatusLabel(status) {
        const labels = { pending: '待处理', running: '生成中', completed: '已完成', failed: '失败' };
        return labels[status] || status || '-';
    },

    showSubscriptionModal(subscription = null) {
        const isEdit = !!subscription;
        const formData = subscription || {
            datasource_ids: [],
            severity_levels: [],
            time_ranges: [],
            integration_targets: [],
            enabled: true,
            aggregation_script: ''
        };

        Modal.show({
            title: isEdit ? '编辑订阅' : '新建订阅',
            content: this.renderSubscriptionForm(formData),
            size: 'large',
            buttons: [
                { text: '取消', className: 'btn-secondary', onClick: () => Modal.hide() },
                {
                    text: '保存',
                    className: 'btn-primary',
                    onClick: async () => {
                        const data = this.getSubscriptionFormData(subscription);
                        if (!data) return;
                        try {
                            if (isEdit) {
                                await API.put(`/api/alerts/subscriptions/${subscription.id}`, data);
                            } else {
                                data.user_id = this.currentUser.id;
                                await API.post('/api/alerts/subscriptions', data);
                            }
                            await this.loadSubscriptions();
                            this.updateSubscriptionsList();
                            Modal.hide();
                            Toast.success('保存成功');
                        } catch (error) {
                            console.error('Failed to save subscription:', error);
                            Toast.error('保存失败: ' + error.message);
                        }
                    }
                }
            ]
        });
    },

    renderSubscriptionForm(data) {
        const form = DOM.el('div', { className: 'subscription-form', id: 'subscription-form' });

        const datasourceGroup = DOM.el('div', { className: 'form-group' });
        datasourceGroup.appendChild(DOM.el('label', { textContent: '数据源（留空表示全部）' }));
        const datasourceSelect = DOM.el('select', { multiple: true, className: 'form-control', id: 'sub-datasources' });
        for (const ds of this.datasources) {
            datasourceSelect.appendChild(DOM.el('option', {
                value: ds.id,
                textContent: ds.name,
                selected: data.datasource_ids.includes(ds.id)
            }));
        }
        datasourceGroup.appendChild(datasourceSelect);
        form.appendChild(datasourceGroup);

        const severityGroup = DOM.el('div', { className: 'form-group' });
        severityGroup.appendChild(DOM.el('label', { textContent: '严重程度（留空表示全部）' }));
        const severityOptions = DOM.el('div', { className: 'checkbox-group' });
        for (const severity of ['critical', 'high', 'medium', 'low']) {
            const checkbox = DOM.el('label', { className: 'checkbox-label' });
            checkbox.appendChild(DOM.el('input', {
                type: 'checkbox',
                value: severity,
                checked: data.severity_levels.includes(severity),
                className: 'severity-checkbox'
            }));
            checkbox.appendChild(DOM.el('span', { textContent: this.getSeverityLabel(severity) }));
            severityOptions.appendChild(checkbox);
        }
        severityGroup.appendChild(severityOptions);
        form.appendChild(severityGroup);

        const targetsGroup = DOM.el('div', { className: 'form-group' });
        const targetsHeader = DOM.el('div', { className: 'subscription-targets-header' });
        targetsHeader.appendChild(DOM.el('label', { textContent: '通知目标' }));
        targetsHeader.appendChild(DOM.el('button', {
            className: 'btn btn-sm btn-secondary',
            textContent: '新增目标',
            type: 'button',
            onClick: () => this.addIntegrationTargetRow()
        }));
        targetsGroup.appendChild(targetsHeader);

        targetsGroup.appendChild(DOM.el('div', {
            className: 'integration-target-help',
            textContent: '直接选择 Integration，并在这里填写 webhook、email 等目标参数。默认同时发送告警和恢复通知。密码类字段会自动以 ENCRYPT: 形式提交。'
        }));

        const list = DOM.el('div', { id: 'integration-targets-list', className: 'integration-targets-list' });
        const targets = (data.integration_targets && data.integration_targets.length > 0) ? data.integration_targets : [this.createEmptyTarget()];
        targets.forEach(target => list.appendChild(this.renderIntegrationTargetRow(target)));
        targetsGroup.appendChild(list);
        form.appendChild(targetsGroup);

        const enabledGroup = DOM.el('div', { className: 'form-group' });
        const enabledLabel = DOM.el('label', { className: 'checkbox-label' });
        enabledLabel.appendChild(DOM.el('input', { type: 'checkbox', id: 'sub-enabled', checked: data.enabled }));
        enabledLabel.appendChild(DOM.el('span', { textContent: '启用订阅' }));
        enabledGroup.appendChild(enabledLabel);
        form.appendChild(enabledGroup);

        return form;
    },

    createEmptyTarget() {
        const integration = this.notificationIntegrations[0] || null;
        return {
            target_id: '',
            integration_id: integration ? integration.id : null,
            name: '',
            enabled: true,
            notify_on: ['alert', 'recovery'],
            params: {}
        };
    },

    renderIntegrationTargetRow(target) {
        const wrapper = DOM.el('div', { className: 'integration-target-row' });

        const integrationOptions = this.notificationIntegrations.map(item => {
            const selected = String(target.integration_id) === String(item.id) ? 'selected' : '';
            return `<option value="${item.id}" ${selected}>${item.name}</option>`;
        }).join('');

        wrapper.innerHTML = `
            <div class="integration-target-top">
                <div class="form-group">
                    <label>Integration</label>
                    <select class="target-integration">
                        <option value="">请选择</option>
                        ${integrationOptions}
                    </select>
                </div>
                <div class="integration-target-actions">
                    <label class="checkbox-label target-enabled-label"><input type="checkbox" class="target-enabled" ${target.enabled !== false ? 'checked' : ''}> <span>启用</span></label>
                    <button type="button" class="btn-icon remove-target-btn" title="删除目标" aria-label="删除目标">×</button>
                </div>
            </div>
            <div class="target-params"></div>
        `;

        const integrationSelect = wrapper.querySelector('.target-integration');
        integrationSelect.addEventListener('change', () => this.renderTargetParams(wrapper, {}));
        wrapper.querySelector('.remove-target-btn').addEventListener('click', () => {
            const list = DOM.$('#integration-targets-list');
            wrapper.remove();
            if (list && !list.children.length) list.appendChild(this.renderIntegrationTargetRow(this.createEmptyTarget()));
        });

        this.renderTargetParams(wrapper, target.params || {});
        return wrapper;
    },

    renderTargetParams(wrapper, existingParams = {}) {
        const integrationId = parseInt(wrapper.querySelector('.target-integration').value);
        const integration = this.notificationIntegrations.find(item => item.id === integrationId);
        const container = wrapper.querySelector('.target-params');
        if (!integration || !integration.config_schema?.properties) {
            container.innerHTML = '';
            return;
        }

        let html = '<div class="target-params-title">目标参数</div>';
        for (const [key, prop] of Object.entries(integration.config_schema.properties)) {
            const required = integration.config_schema.required?.includes(key) ? '<span class="target-param-required">*</span>' : '';
            const type = prop.format === 'password' ? 'password' : 'text';
            const value = prop.format === 'password' ? '' : (existingParams[key] || prop.default || '');
            html += `
                <div class="target-param-row">
                    <label class="target-param-label">${prop.title || key}${required}</label>
                    <input type="${type}" class="target-param target-param-input" data-key="${key}" data-format="${prop.format || ''}" value="${value}" placeholder="${prop.description || ''}">
                </div>
            `;
        }
        container.innerHTML = html;
    },

    addIntegrationTargetRow() {
        const list = DOM.$('#integration-targets-list');
        if (!list) return;
        list.appendChild(this.renderIntegrationTargetRow(this.createEmptyTarget()));
    },

    getSubscriptionFormData(subscription = null) {
        const datasourceIds = Array.from(DOM.$$('#sub-datasources option:checked')).map(opt => parseInt(opt.value));
        const severityLevels = Array.from(DOM.$$('.severity-checkbox:checked')).map(cb => cb.value);
        const enabled = DOM.$('#sub-enabled').checked;

        const integrationTargets = Array.from(DOM.$$('.integration-target-row')).map((row, index) => {
            const integrationId = parseInt(row.querySelector('.target-integration').value);

            const params = {};
            row.querySelectorAll('.target-param').forEach(input => {
                const key = input.dataset.key;
                const format = input.dataset.format;
                if (!key) return;
                if (format === 'password') {
                    if (input.value) params[key] = `ENCRYPT:${input.value}`;
                } else {
                    params[key] = input.value;
                }
            });

            const existingTarget = subscription?.integration_targets?.[index];
            const integrationName = this.getIntegrationName(integrationId);
            const name = (existingTarget?.name && existingTarget.name.trim()) ? existingTarget.name.trim() : `${integrationName} #${index + 1}`;

            return {
                target_id: existingTarget?.target_id || `target_${Date.now()}_${index}`,
                integration_id: integrationId,
                name,
                enabled: row.querySelector('.target-enabled').checked,
                notify_on: ['alert', 'recovery'],
                params
            };
        }).filter(target => Number.isFinite(target.integration_id));

        if (integrationTargets.length === 0) {
            Toast.error('请至少配置一个通知目标');
            return null;
        }

        return {
            datasource_ids: datasourceIds,
            severity_levels: severityLevels,
            integration_targets: integrationTargets,
            enabled
        };
    },

    getIntegrationName(integrationId) {
        const integration = this.notificationIntegrations.find(item => item.id === integrationId);
        return integration ? integration.name : `Integration #${integrationId}`;
    },

    async testNotification(subscriptionId) {
        if (!confirm('发送测试通知？')) return;
        try {
            const result = await API.post(`/api/alerts/subscriptions/${subscriptionId}/test`, {});
            alert(`测试通知已发送\n${JSON.stringify(result.deliveries, null, 2)}`);
        } catch (error) {
            console.error('Failed to test notification:', error);
            alert('测试失败: ' + error.message);
        }
    },

    async deleteSubscription(subscriptionId) {
        if (!confirm('确认删除此订阅？')) return;
        try {
            await API.delete(`/api/alerts/subscriptions/${subscriptionId}`);
            await this.loadSubscriptions();
            this.updateSubscriptionsList();
            Toast.success('订阅已删除');
        } catch (error) {
            console.error('Failed to delete subscription:', error);
            Toast.error('删除失败: ' + error.message);
        }
    },

    getSeverityLabel(severity) {
        const labels = { critical: '严重', high: '高', medium: '中', low: '低' };
        return labels[severity] || severity;
    },

    getStatusLabel(status) {
        const labels = { active: '活跃', acknowledged: '已确认', resolved: '已解决' };
        return labels[status] || status;
    },

    getAlertTypeLabel(type) {
        const labels = {
            threshold_violation: '超过阈值',
            custom_expression: '自定义表达式',
            system_error: '系统错误'
        };
        return labels[type] || type;
    },

    formatNumber(value) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
        return Number(value).toFixed(2);
    },

    _escapeHtml(text) {
        if (text == null) return '';
        const div = document.createElement('div');
        div.textContent = String(text);
        return div.innerHTML;
    },

    renderPagination(type) {
        const totalPages = Math.ceil(this.totalCount[type] / this.pageSize[type]);
        if (totalPages <= 1) return DOM.el('div');

        const container = DOM.el('div', {
            id: `pagination-${type}`,
            style: 'margin-top: 15px; display: flex; justify-content: center; gap: 10px;'
        });

        const buttons = [];
        const currentPage = this.currentPage[type];
        buttons.push(`<button class="btn btn-sm btn-secondary" style="flex: 0 0 auto;" ${currentPage === 1 ? 'disabled' : ''} onclick="AlertsPage.goToPage('${type}', ${currentPage - 1})">上一页</button>`);
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
                buttons.push(`<button class="btn btn-sm ${i === currentPage ? 'btn-primary' : 'btn-secondary'}" style="flex: 0 0 auto;" onclick="AlertsPage.goToPage('${type}', ${i})">${i}</button>`);
            } else if (i === currentPage - 3 || i === currentPage + 3) {
                buttons.push('<span style="padding:0 5px; flex: 0 0 auto;">...</span>');
            }
        }
        buttons.push(`<button class="btn btn-sm btn-secondary" style="flex: 0 0 auto;" ${currentPage === totalPages ? 'disabled' : ''} onclick="AlertsPage.goToPage('${type}', ${currentPage + 1})">下一页</button>`);
        container.innerHTML = buttons.join('');
        return container;
    },

    async goToPage(type, page) {
        this.currentPage[type] = page;
        await this.loadEvents();
        this.updateAlertsList();
    },

    resetPagination() {
        this.currentPage.events = 1;
    }
};
