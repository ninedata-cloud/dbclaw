/* Alert Management Page */
const AlertsPage = {
    datasources: [],
    alerts: [],
    events: [],
    subscriptions: [],
    alertChannels: [],  // Integration Alert Channels
    currentUser: null,
    viewMode: 'events',  // 'events' or 'alerts'
    expandedEvents: new Set(),
    eventAlerts: {},  // Cache: {eventId: [alerts]}
    filters: {
        datasource_id: null,
        status: 'all',
        severity: null,
        search: '',
        start_time: null,
        end_time: null
    },
    currentPage: {
        events: 1,
        alerts: 1
    },
    pageSize: {
        events: 10,
        alerts: 10
    },
    totalCount: {
        events: 0,
        alerts: 0
    },

    async init() {
        this.currentUser = Store.get('currentUser');
        if (!this.currentUser) {
            Router.navigate('login');
            return;
        }

        await this.loadDatasources();
        await this.loadAlertChannels();  // 加载告警通道
        await this.loadEvents();
        await this.loadAlerts();
        await this.loadSubscriptions();
        this.render();
    },

    async loadAlertChannels() {
        try {
            console.log('Loading alert channels...');
            this.alertChannels = await API.get('/api/alert-channels');
            console.log('Alert channels loaded:', this.alertChannels);
            console.log('Alert channels count:', this.alertChannels ? this.alertChannels.length : 0);
        } catch (error) {
            console.error('Failed to load alert channels:', error);
            console.error('Error details:', error.message);
            this.alertChannels = [];
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

            if (this.filters.datasource_id) {
                params.append('datasource_ids', this.filters.datasource_id);
            }
            if (this.filters.status && this.filters.status !== 'all') {
                params.append('status', this.filters.status);
            }
            if (this.filters.severity) {
                params.append('severity', this.filters.severity);
            }
            if (this.filters.search) {
                params.append('search', this.filters.search);
            }
            if (this.filters.start_time) {
                params.append('start_time', this.filters.start_time);
            }
            if (this.filters.end_time) {
                params.append('end_time', this.filters.end_time);
            }
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

    async loadAlerts() {
        try {
            const offset = (this.currentPage.alerts - 1) * this.pageSize.alerts;
            const params = new URLSearchParams();

            if (this.filters.datasource_id) {
                params.append('datasource_ids', this.filters.datasource_id);
            }
            if (this.filters.status && this.filters.status !== 'all') {
                params.append('status', this.filters.status);
            }
            if (this.filters.severity) {
                params.append('severity', this.filters.severity);
            }
            if (this.filters.search) {
                params.append('search', this.filters.search);
            }
            if (this.filters.start_time) {
                params.append('start_time', this.filters.start_time);
            }
            if (this.filters.end_time) {
                params.append('end_time', this.filters.end_time);
            }
            params.append('limit', this.pageSize.alerts);
            params.append('offset', offset);

            const response = await API.get(`/api/alerts?${params.toString()}`);
            this.alerts = response.alerts || [];
            this.totalCount.alerts = response.total || 0;
        } catch (error) {
            console.error('Failed to load alerts:', error);
            this.alerts = [];
            this.totalCount.alerts = 0;
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
        if (this.eventAlerts[eventId]) {
            return this.eventAlerts[eventId];
        }

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
            await API.post(`/api/alerts/events/${eventId}/acknowledge`, {
                user_id: this.currentUser.id
            });
            await this.loadEvents();
            this.updateEventsList();
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
            this.updateEventsList();
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
        this.updateEventsList();
    },

    switchViewMode(mode) {
        this.viewMode = mode;
        this.updateAlertsList();
    },

    render() {
        Header.render('告警管理', this._buildHeaderActions());

        const container = DOM.$('#page-content');
        DOM.clear(container);

        // View toggle (for alerts tab)
        const viewToggle = DOM.el('div', { className: 'view-toggle' });
        const eventsViewBtn = DOM.el('button', {
            className: `btn ${this.viewMode === 'events' ? 'btn-primary' : 'btn-secondary'}`,
            textContent: '事件视图',
            onClick: () => this.switchViewMode('events')
        });
        const alertsViewBtn = DOM.el('button', {
            className: `btn ${this.viewMode === 'alerts' ? 'btn-primary' : 'btn-secondary'}`,
            textContent: '告警视图',
            onClick: () => this.switchViewMode('alerts')
        });
        viewToggle.appendChild(eventsViewBtn);
        viewToggle.appendChild(alertsViewBtn);
        //container.appendChild(viewToggle);

        // Tabs
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

        // Tab content
        const tabContent = DOM.el('div', { className: 'tab-content' });
        const alertsContent = DOM.el('div', { className: 'tab-pane active', id: 'alerts-pane' });
        alertsContent.appendChild(this.viewMode === 'events' ? this.renderEventsList() : this.renderAlertsList());
        const subscriptionsContent = DOM.el('div', { className: 'tab-pane', id: 'subscriptions-pane' });
        subscriptionsContent.appendChild(this.renderSubscriptionsList());
        tabContent.appendChild(alertsContent);
        tabContent.appendChild(subscriptionsContent);
        container.appendChild(tabContent);

        DOM.createIcons();
    },

    _buildHeaderActions() {
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters' });

        // Datasource select
        const datasourceSelect = DOM.el('select', {
            className: 'filter-select',
            onChange: (e) => {
                this.filters.datasource_id = e.target.value ? parseInt(e.target.value) : null;
                this.resetPagination();
                Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
            }
        });
        datasourceSelect.appendChild(DOM.el('option', { value: '', textContent: '全部数据源' }));
        for (const ds of this.datasources) {
            datasourceSelect.appendChild(DOM.el('option', {
                value: ds.id,
                textContent: ds.name,
                selected: this.filters.datasource_id === ds.id
            }));
        }
        filtersContainer.appendChild(datasourceSelect);

        // Status select
        const statusSelect = DOM.el('select', {
            className: 'filter-select',
            onChange: (e) => {
                this.filters.status = e.target.value;
                this.resetPagination();
                Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
            }
        });
        statusSelect.appendChild(DOM.el('option', { value: 'all', textContent: '全部状态' }));
        statusSelect.appendChild(DOM.el('option', { value: 'active', textContent: '活跃' }));
        statusSelect.appendChild(DOM.el('option', { value: 'acknowledged', textContent: '已确认' }));
        statusSelect.appendChild(DOM.el('option', { value: 'resolved', textContent: '已解决' }));
        filtersContainer.appendChild(statusSelect);

        // Severity select
        const severitySelect = DOM.el('select', {
            className: 'filter-select',
            onChange: (e) => {
                this.filters.severity = e.target.value || null;
                this.resetPagination();
                Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
            }
        });
        severitySelect.appendChild(DOM.el('option', { value: '', textContent: '全部严重程度' }));
        severitySelect.appendChild(DOM.el('option', { value: 'critical', textContent: '严重' }));
        severitySelect.appendChild(DOM.el('option', { value: 'high', textContent: '高' }));
        severitySelect.appendChild(DOM.el('option', { value: 'medium', textContent: '中' }));
        severitySelect.appendChild(DOM.el('option', { value: 'low', textContent: '低' }));
        filtersContainer.appendChild(severitySelect);

        // Start time input
        const startTimeInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'filter-input',
            title: '开始时间',
            value: this.filters.start_time || '',
            onChange: (e) => {
                this.filters.start_time = e.target.value || null;
                this.resetPagination();
                Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
            }
        });
        filtersContainer.appendChild(startTimeInput);

        // End time input
        const endTimeInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'filter-input',
            title: '结束时间',
            value: this.filters.end_time || '',
            onChange: (e) => {
                this.filters.end_time = e.target.value || null;
                this.resetPagination();
                Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
            }
        });
        filtersContainer.appendChild(endTimeInput);

        // Search input
        const searchInput = DOM.el('input', {
            type: 'text',
            className: 'filter-input',
            placeholder: '搜索标题或内容',
            onInput: (e) => {
                this.filters.search = e.target.value;
                clearTimeout(this.searchTimeout);
                this.searchTimeout = setTimeout(() => {
                    this.resetPagination();
                    Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
                }, 500);
            }
        });
        filtersContainer.appendChild(searchInput);

        const addSubBtn = DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i>新建订阅',
            onClick: () => this.showSubscriptionModal()
        });

        return [filtersContainer, addSubBtn];
    },

    renderFilters() {
        const filters = DOM.el('div', { className: 'alert-filters' });

        // Datasource filter (single select)
        const datasourceFilter = DOM.el('div', { className: 'filter-group' });
        datasourceFilter.appendChild(DOM.el('label', { textContent: '数据源' }));
        const datasourceSelect = DOM.el('select', {
            className: 'form-control',
            value: this.filters.datasource_id || '',
            onChange: (e) => {
                this.filters.datasource_id = e.target.value ? parseInt(e.target.value) : null;
                this.resetPagination();
                Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
            }
        });
        datasourceSelect.appendChild(DOM.el('option', { value: '', textContent: '全部' }));
        for (const ds of this.datasources) {
            datasourceSelect.appendChild(DOM.el('option', {
                value: ds.id,
                textContent: ds.name,
                selected: this.filters.datasource_id === ds.id
            }));
        }
        datasourceFilter.appendChild(datasourceSelect);
        filters.appendChild(datasourceFilter);

        // Status filter
        const statusFilter = DOM.el('div', { className: 'filter-group' });
        statusFilter.appendChild(DOM.el('label', { textContent: '状态' }));
        const statusSelect = DOM.el('select', {
            className: 'form-control',
            value: this.filters.status,
            onChange: (e) => {
                this.filters.status = e.target.value;
                this.resetPagination();
                Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
            }
        });
        statusSelect.appendChild(DOM.el('option', { value: 'all', textContent: '全部' }));
        statusSelect.appendChild(DOM.el('option', { value: 'active', textContent: '活跃' }));
        statusSelect.appendChild(DOM.el('option', { value: 'acknowledged', textContent: '已确认' }));
        statusSelect.appendChild(DOM.el('option', { value: 'resolved', textContent: '已解决' }));
        statusFilter.appendChild(statusSelect);
        filters.appendChild(statusFilter);

        // Severity filter
        const severityFilter = DOM.el('div', { className: 'filter-group' });
        severityFilter.appendChild(DOM.el('label', { textContent: '严重程度' }));
        const severitySelect = DOM.el('select', {
            className: 'form-control',
            onChange: (e) => {
                this.filters.severity = e.target.value || null;
                this.resetPagination();
                Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
            }
        });
        severitySelect.appendChild(DOM.el('option', { value: '', textContent: '全部' }));
        severitySelect.appendChild(DOM.el('option', { value: 'critical', textContent: '严重' }));
        severitySelect.appendChild(DOM.el('option', { value: 'high', textContent: '高' }));
        severitySelect.appendChild(DOM.el('option', { value: 'medium', textContent: '中' }));
        severitySelect.appendChild(DOM.el('option', { value: 'low', textContent: '低' }));
        severityFilter.appendChild(severitySelect);
        filters.appendChild(severityFilter);

        // Start time filter
        const startTimeFilter = DOM.el('div', { className: 'filter-group' });
        startTimeFilter.appendChild(DOM.el('label', { textContent: '开始时间' }));
        const startTimeInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'form-control',
            value: this.filters.start_time || '',
            onChange: (e) => {
                this.filters.start_time = e.target.value || null;
                this.resetPagination();
                Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
            }
        });
        startTimeFilter.appendChild(startTimeInput);
        filters.appendChild(startTimeFilter);

        // End time filter
        const endTimeFilter = DOM.el('div', { className: 'filter-group' });
        endTimeFilter.appendChild(DOM.el('label', { textContent: '结束时间' }));
        const endTimeInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'form-control',
            value: this.filters.end_time || '',
            onChange: (e) => {
                this.filters.end_time = e.target.value || null;
                this.resetPagination();
                Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
            }
        });
        endTimeFilter.appendChild(endTimeInput);
        filters.appendChild(endTimeFilter);

        // Search filter
        const searchFilter = DOM.el('div', { className: 'filter-group' });
        searchFilter.appendChild(DOM.el('label', { textContent: '搜索' }));
        const searchInput = DOM.el('input', {
            type: 'text',
            className: 'form-control',
            placeholder: '搜索标题或内容',
            onInput: (e) => {
                this.filters.search = e.target.value;
                clearTimeout(this.searchTimeout);
                this.searchTimeout = setTimeout(() => {
                    this.resetPagination();
                    Promise.all([this.loadEvents(), this.loadAlerts()]).then(() => this.updateAlertsList());
                }, 500);
            }
        });
        searchFilter.appendChild(searchInput);
        filters.appendChild(searchFilter);

        return filters;
    },

    renderEventsList() {
        const list = DOM.el('div', { className: 'events-list', id: 'events-list' });

        if (this.events.length === 0) {
            list.appendChild(DOM.el('div', {
                className: 'empty-state',
                textContent: '暂无事件'
            }));
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

            // Main event row
            const row = DOM.el('tr', { className: `event-row ${isExpanded ? 'expanded' : ''}` });

            // Expand icon
            const expandCell = DOM.el('td');
            const expandIcon = DOM.el('span', {
                className: `expand-icon ${isExpanded ? 'expanded' : ''}`,
                textContent: '▶',
                style: 'cursor: pointer; user-select: none;'
            });
            expandCell.appendChild(expandIcon);
            expandCell.onclick = () => this.toggleEventExpansion(event.id);
            row.appendChild(expandCell);

            // Severity badge
            const severityCell = DOM.el('td');
            const severityBadge = DOM.el('span', {
                className: `severity-badge severity-${event.severity}`,
                textContent: this.getSeverityLabel(event.severity)
            });
            severityCell.appendChild(severityBadge);
            row.appendChild(severityCell);

            // Datasource
            const datasource = this.datasources.find(ds => ds.id === event.datasource_id);
            row.appendChild(DOM.el('td', { textContent: datasource ? datasource.name : `ID: ${event.datasource_id}` }));

            // Type/Metric
            const typeMetric = event.metric_name || this.getAlertTypeLabel(event.alert_type);
            row.appendChild(DOM.el('td', { textContent: typeMetric }));

            // Title
            row.appendChild(DOM.el('td', { textContent: event.title }));

            // Start time
            row.appendChild(DOM.el('td', { textContent: new Date(event.event_start_time).toLocaleString('zh-CN') }));

            // End time
            // End time (recovery time)
            const endTime = event.status === 'resolved' && event.event_end_time
                ? new Date(event.event_end_time).toLocaleString('zh-CN')
                : '-';
            row.appendChild(DOM.el('td', { textContent: endTime }));

            // Count
            const countCell = DOM.el('td');
            const countBadge = DOM.el('span', {
                className: 'count-badge',
                textContent: event.alert_count
            });
            countCell.appendChild(countBadge);
            row.appendChild(countCell);

            // Status
            const statusCell = DOM.el('td');
            const statusBadge = DOM.el('span', {
                className: `status-badge status-${event.status}`,
                textContent: this.getStatusLabel(event.status)
            });
            statusCell.appendChild(statusBadge);
            row.appendChild(statusCell);

            // Actions
            const actionsCell = DOM.el('td', { className: 'actions-cell' });
            if (event.status === 'active') {
                const ackBtn = DOM.el('button', {
                    className: 'btn btn-sm btn-secondary',
                    textContent: '✓',
                    title: '确认',
                    onClick: (e) => {
                        e.stopPropagation();
                        this.acknowledgeEvent(event.id);
                    }
                });
                actionsCell.appendChild(ackBtn);
            }
            if (event.status !== 'resolved') {
                const resolveBtn = DOM.el('button', {
                    className: 'btn btn-sm btn-success',
                    textContent: '✓✓',
                    title: '解决',
                    onClick: (e) => {
                        e.stopPropagation();
                        this.resolveEvent(event.id);
                    }
                });
                actionsCell.appendChild(resolveBtn);
            }
            row.appendChild(actionsCell);

            tbody.appendChild(row);

            // Expanded alerts row
            if (isExpanded) {
                const expandedRow = DOM.el('tr', { className: 'expanded-row' });
                const expandedCell = DOM.el('td', { colSpan: 10 });
                const alertsContainer = DOM.el('div', { className: 'event-alerts-container' });

                const alerts = this.eventAlerts[event.id] || [];
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
                        alertRow.appendChild(DOM.el('td', { textContent: new Date(alert.created_at).toLocaleString('zh-CN') }));
                        alertRow.appendChild(DOM.el('td', { textContent: alert.metric_value !== null ? alert.metric_value.toFixed(2) : '-' }));
                        alertRow.appendChild(DOM.el('td', { textContent: alert.threshold_value !== null ? alert.threshold_value.toFixed(2) : '-' }));

                        const alertStatusCell = DOM.el('td');
                        const alertStatusBadge = DOM.el('span', {
                            className: `status-badge status-${alert.status}`,
                            textContent: this.getStatusLabel(alert.status)
                        });
                        alertStatusCell.appendChild(alertStatusBadge);
                        alertRow.appendChild(alertStatusCell);

                        const alertActionsCell = DOM.el('td');
                        const viewBtn = DOM.el('button', {
                            className: 'btn-icon',
                            textContent: '👁',
                            title: '查看详情',
                            onClick: () => this.showAlertDetail(alert)
                        });
                        alertActionsCell.appendChild(viewBtn);
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

        // Add pagination
        list.appendChild(this.renderPagination('events'));

        return list;
    },

    renderAlertsList() {
        const list = DOM.el('div', { className: 'alerts-list', id: 'alerts-list' });

        if (this.alerts.length === 0) {
            list.appendChild(DOM.el('div', {
                className: 'empty-state',
                textContent: '暂无告警'
            }));
            return list;
        }

        const table = DOM.el('table', { className: 'data-table' });
        const thead = DOM.el('thead');
        const headerRow = DOM.el('tr');
        headerRow.appendChild(DOM.el('th', { textContent: '严重程度' }));
        headerRow.appendChild(DOM.el('th', { textContent: '数据源' }));
        headerRow.appendChild(DOM.el('th', { textContent: '类型' }));
        headerRow.appendChild(DOM.el('th', { textContent: '标题' }));
        headerRow.appendChild(DOM.el('th', { textContent: '创建时间' }));
        headerRow.appendChild(DOM.el('th', { textContent: '状态' }));
        headerRow.appendChild(DOM.el('th', { textContent: '操作' }));
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = DOM.el('tbody');
        for (const alert of this.alerts) {
            const row = DOM.el('tr');

            // Severity badge
            const severityCell = DOM.el('td');
            const severityBadge = DOM.el('span', {
                className: `severity-badge severity-${alert.severity}`,
                textContent: this.getSeverityLabel(alert.severity)
            });
            severityCell.appendChild(severityBadge);
            row.appendChild(severityCell);

            // Datasource
            const datasource = this.datasources.find(ds => ds.id === alert.datasource_id);
            row.appendChild(DOM.el('td', { textContent: datasource ? datasource.name : `ID: ${alert.datasource_id}` }));

            // Type
            row.appendChild(DOM.el('td', { textContent: this.getAlertTypeLabel(alert.alert_type) }));

            // Title
            row.appendChild(DOM.el('td', { textContent: alert.title }));

            // Created time
            row.appendChild(DOM.el('td', { textContent: new Date(alert.created_at).toLocaleString('zh-CN') }));

            // Status
            const statusCell = DOM.el('td');
            const statusBadge = DOM.el('span', {
                className: `status-badge status-${alert.status}`,
                textContent: this.getStatusLabel(alert.status)
            });
            statusCell.appendChild(statusBadge);
            row.appendChild(statusCell);

            // Actions
            const actionsCell = DOM.el('td', { className: 'actions-cell' });
            const viewBtn = DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: '<i data-lucide="eye"></i>',
                title: '查看详情',
                onClick: () => this.showAlertDetail(alert)
            });
            actionsCell.appendChild(viewBtn);

            if (alert.status === 'active') {
                const ackBtn = DOM.el('button', {
                    className: 'btn btn-sm btn-primary',
                    innerHTML: '<i data-lucide="check"></i>',
                    title: '确认',
                    onClick: () => this.acknowledgeAlert(alert.id)
                });
                actionsCell.appendChild(ackBtn);
            }

            if (alert.status !== 'resolved') {
                const resolveBtn = DOM.el('button', {
                    className: 'btn btn-sm btn-success',
                    innerHTML: '<i data-lucide="check-check"></i>',
                    title: '解决',
                    onClick: () => this.resolveAlert(alert.id)
                });
                actionsCell.appendChild(resolveBtn);
            }

            row.appendChild(actionsCell);
            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        list.appendChild(table);

        // Add pagination
        list.appendChild(this.renderPagination('alerts'));

        return list;
    },

    renderSubscriptionsList() {
        const list = DOM.el('div', { className: 'subscriptions-list', id: 'subscriptions-list' });

        if (this.subscriptions.length === 0) {
            list.appendChild(DOM.el('div', {
                className: 'empty-state',
                textContent: '暂无订阅'
            }));
            return list;
        }

        const table = DOM.el('table', { className: 'data-table' });
        const thead = DOM.el('thead');
        const headerRow = DOM.el('tr');
        headerRow.appendChild(DOM.el('th', { textContent: '数据源' }));
        headerRow.appendChild(DOM.el('th', { textContent: '严重程度' }));
        headerRow.appendChild(DOM.el('th', { textContent: '通知渠道' }));
        headerRow.appendChild(DOM.el('th', { textContent: '状态' }));
        headerRow.appendChild(DOM.el('th', { textContent: '操作' }));
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = DOM.el('tbody');
        for (const sub of this.subscriptions) {
            const row = DOM.el('tr');

            // Datasources
            const datasourceNames = sub.datasource_ids.length === 0
                ? '全部'
                : sub.datasource_ids.map(id => {
                    const ds = this.datasources.find(d => d.id === id);
                    return ds ? ds.name : `ID: ${id}`;
                }).join(', ');
            row.appendChild(DOM.el('td', { textContent: datasourceNames }));

            // Severity levels
            const severityText = sub.severity_levels.length === 0
                ? '全部'
                : sub.severity_levels.map(s => this.getSeverityLabel(s)).join(', ');
            row.appendChild(DOM.el('td', { textContent: severityText }));

            // Channels - 显示 Integration Channel 名称
            const channelNames = sub.channel_ids && sub.channel_ids.length > 0
                ? sub.channel_ids.map(id => {
                    const channel = this.alertChannels.find(c => c.id === id);
                    return channel ? channel.name : `ID: ${id}`;
                }).join(', ')
                : '未配置';
            row.appendChild(DOM.el('td', { textContent: channelNames }));

            // Status
            const statusCell = DOM.el('td');
            const statusBadge = DOM.el('span', {
                className: `status-badge ${sub.enabled ? 'status-active' : 'status-disabled'}`,
                textContent: sub.enabled ? '启用' : '禁用'
            });
            statusCell.appendChild(statusBadge);
            row.appendChild(statusCell);

            // Actions
            const actionsCell = DOM.el('td', { className: 'actions-cell' });
            const editBtn = DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: '<i data-lucide="edit"></i>',
                title: '编辑',
                onClick: () => this.showSubscriptionModal(sub)
            });
            const testBtn = DOM.el('button', {
                className: 'btn btn-sm btn-primary',
                innerHTML: '<i data-lucide="send"></i>',
                title: '测试通知',
                onClick: () => this.testNotification(sub.id)
            });
            const deleteBtn = DOM.el('button', {
                className: 'btn btn-sm btn-danger',
                innerHTML: '<i data-lucide="trash-2"></i>',
                title: '删除',
                onClick: () => this.deleteSubscription(sub.id)
            });
            actionsCell.appendChild(editBtn);
            actionsCell.appendChild(testBtn);
            actionsCell.appendChild(deleteBtn);
            row.appendChild(actionsCell);

            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        list.appendChild(table);

        return list;
    },

    switchTab(tabEl, tabName) {
        // Update tab buttons
        DOM.$$('.tab').forEach(t => t.classList.remove('active'));
        tabEl.classList.add('active');

        // Update tab panes
        DOM.$$('.tab-pane').forEach(p => p.classList.remove('active'));
        DOM.$(`#${tabName}-pane`).classList.add('active');
    },

    updateAlertsList() {
        const listContainer = this.viewMode === 'events' ? DOM.$('#events-list') : DOM.$('#alerts-list');
        if (listContainer) {
            DOM.clear(listContainer);
            const newList = this.viewMode === 'events' ? this.renderEventsList() : this.renderAlertsList();
            listContainer.parentNode.replaceChild(newList, listContainer);
            DOM.createIcons();
        }
    },

    updateEventsList() {
        this.updateAlertsList();
    },

    updateSubscriptionsList() {
        const listContainer = DOM.$('#subscriptions-list');
        if (listContainer) {
            DOM.clear(listContainer);
            const newList = this.renderSubscriptionsList();
            listContainer.parentNode.replaceChild(newList, listContainer);
            DOM.createIcons();
        }
    },

    async showAlertDetail(alert) {
        Modal.show({
            title: '告警详情',
            content: this.renderAlertDetailContent(alert),
            size: 'large',
            buttons: [
                {
                    text: '关闭',
                    className: 'btn-secondary',
                    onClick: () => Modal.hide()
                }
            ]
        });
    },

    renderAlertDetailContent(alert) {
        const content = DOM.el('div', { className: 'alert-detail' });

        const datasource = this.datasources.find(ds => ds.id === alert.datasource_id);

        const fields = [
            { label: '严重程度', value: this.getSeverityLabel(alert.severity), className: `severity-${alert.severity}` },
            { label: '数据源', value: datasource ? datasource.name : `ID: ${alert.datasource_id}` },
            { label: '告警类型', value: this.getAlertTypeLabel(alert.alert_type) },
            { label: '状态', value: this.getStatusLabel(alert.status) },
            { label: '标题', value: alert.title },
            { label: '创建时间', value: new Date(alert.created_at).toLocaleString('zh-CN') },
        ];

        if (alert.metric_name) {
            fields.push({ label: '指标名称', value: alert.metric_name });
        }
        if (alert.metric_value !== null) {
            fields.push({ label: '当前值', value: alert.metric_value.toFixed(2) });
        }
        if (alert.threshold_value !== null) {
            fields.push({ label: '阈值', value: alert.threshold_value.toFixed(2) });
        }
        if (alert.trigger_reason) {
            fields.push({ label: '触发原因', value: alert.trigger_reason });
        }
        if (alert.acknowledged_at) {
            fields.push({ label: '确认时间', value: new Date(alert.acknowledged_at).toLocaleString('zh-CN') });
        }
        if (alert.resolved_at) {
            fields.push({ label: '解决时间', value: new Date(alert.resolved_at).toLocaleString('zh-CN') });
        }

        for (const field of fields) {
            const fieldEl = DOM.el('div', { className: 'detail-field' });
            fieldEl.appendChild(DOM.el('label', { textContent: field.label }));
            const valueEl = DOM.el('div', {
                className: field.className ? `detail-value ${field.className}` : 'detail-value',
                textContent: field.value
            });
            fieldEl.appendChild(valueEl);
            content.appendChild(fieldEl);
        }

        // Content
        const contentField = DOM.el('div', { className: 'detail-field' });
        contentField.appendChild(DOM.el('label', { textContent: '详细内容' }));
        const contentValue = DOM.el('pre', {
            className: 'detail-content',
            textContent: alert.content
        });
        contentField.appendChild(contentValue);
        content.appendChild(contentField);

        return content;
    },

    async acknowledgeAlert(alertId) {
        if (!confirm('确认此告警？')) return;

        try {
            await API.post(`/api/alerts/${alertId}/acknowledge`, {
                user_id: this.currentUser.id
            });
            await this.loadAlerts();
            this.updateAlertsList();
            alert('告警已确认');
        } catch (error) {
            console.error('Failed to acknowledge alert:', error);
            alert('确认失败: ' + error.message);
        }
    },

    async resolveAlert(alertId) {
        if (!confirm('解决此告警？')) return;

        try {
            await API.post(`/api/alerts/${alertId}/resolve`, {});
            await this.loadAlerts();
            this.updateAlertsList();
            alert('告警已解决');
        } catch (error) {
            console.error('Failed to resolve alert:', error);
            alert('解决失败: ' + error.message);
        }
    },

    showSubscriptionModal(subscription = null) {
        const isEdit = !!subscription;
        const formData = subscription || {
            datasource_ids: [],
            severity_levels: [],
            time_ranges: [],
            channel_ids: [],  // 使用 channel_ids 而不是 channels
            enabled: true,
            aggregation_script: ''
        };

        const content = this.renderSubscriptionForm(formData);

        Modal.show({
            title: isEdit ? '编辑订阅' : '新建订阅',
            content,
            size: 'large',
            buttons: [
                {
                    text: '取消',
                    className: 'btn-secondary',
                    onClick: () => Modal.hide()
                },
                {
                    text: '保存',
                    className: 'btn-primary',
                    onClick: async () => {
                        const data = this.getSubscriptionFormData();
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
                            alert('保存成功');
                        } catch (error) {
                            console.error('Failed to save subscription:', error);
                            alert('保存失败: ' + error.message);
                        }
                    }
                }
            ]
        });
    },

    renderSubscriptionForm(data) {
        const form = DOM.el('div', { className: 'subscription-form', id: 'subscription-form' });

        // Datasource multi-select
        const datasourceGroup = DOM.el('div', { className: 'form-group' });
        datasourceGroup.appendChild(DOM.el('label', { textContent: '数据源（留空表示全部）' }));
        const datasourceSelect = DOM.el('select', {
            multiple: true,
            className: 'form-control',
            id: 'sub-datasources'
        });
        for (const ds of this.datasources) {
            const option = DOM.el('option', {
                value: ds.id,
                textContent: ds.name,
                selected: data.datasource_ids.includes(ds.id)
            });
            datasourceSelect.appendChild(option);
        }
        datasourceGroup.appendChild(datasourceSelect);
        form.appendChild(datasourceGroup);

        // Severity checkboxes
        const severityGroup = DOM.el('div', { className: 'form-group' });
        severityGroup.appendChild(DOM.el('label', { textContent: '严重程度（留空表示全部）' }));
        const severityOptions = DOM.el('div', { className: 'checkbox-group' });
        for (const severity of ['critical', 'high', 'medium', 'low']) {
            const checkbox = DOM.el('label', { className: 'checkbox-label' });
            const input = DOM.el('input', {
                type: 'checkbox',
                value: severity,
                checked: data.severity_levels.includes(severity),
                className: 'severity-checkbox'
            });
            checkbox.appendChild(input);
            checkbox.appendChild(DOM.el('span', { textContent: this.getSeverityLabel(severity) }));
            severityOptions.appendChild(checkbox);
        }
        severityGroup.appendChild(severityOptions);
        form.appendChild(severityGroup);

        // Alert Channels (Integration system)
        const channelsGroup = DOM.el('div', { className: 'form-group' });
        const channelsLabel = DOM.el('label', { textContent: '通知渠道' });
        const manageLink = DOM.el('a', {
            href: '#',
            textContent: '（管理通知渠道）',
            style: 'margin-left: 10px; font-size: 0.9em;',
            onClick: (e) => {
                e.preventDefault();
                Router.navigate('integrations');
            }
        });
        channelsLabel.appendChild(manageLink);
        channelsGroup.appendChild(channelsLabel);

        if (!this.alertChannels || this.alertChannels.length === 0) {
            const noChannelsMsg = DOM.el('div', {
                className: 'alert alert-warning',
                innerHTML: '暂无可用的通知渠道。请先在<a href="#integrations">集成管理</a>中配置通知渠道。'
            });
            channelsGroup.appendChild(noChannelsMsg);
        } else {
            const channelsOptions = DOM.el('div', { className: 'checkbox-group' });
            for (const channel of this.alertChannels) {
                if (!channel.enabled) continue;  // 只显示启用的通道

                const checkbox = DOM.el('label', { className: 'checkbox-label' });
                const input = DOM.el('input', {
                    type: 'checkbox',
                    value: channel.id,
                    checked: data.channel_ids.includes(channel.id),
                    className: 'channel-checkbox'
                });
                const channelInfo = DOM.el('span', {
                    innerHTML: `<strong>${channel.name}</strong> <small style="color: #666;">(${channel.integration_name})</small>`
                });
                checkbox.appendChild(input);
                checkbox.appendChild(channelInfo);
                channelsOptions.appendChild(checkbox);
            }
            channelsGroup.appendChild(channelsOptions);
        }
        form.appendChild(channelsGroup);

        // Enabled toggle
        const enabledGroup = DOM.el('div', { className: 'form-group' });
        const enabledLabel = DOM.el('label', { className: 'checkbox-label' });
        const enabledInput = DOM.el('input', {
            type: 'checkbox',
            id: 'sub-enabled',
            checked: data.enabled
        });
        enabledLabel.appendChild(enabledInput);
        enabledLabel.appendChild(DOM.el('span', { textContent: '启用订阅' }));
        enabledGroup.appendChild(enabledLabel);
        form.appendChild(enabledGroup);

        return form;
    },

    getSubscriptionFormData() {
        const datasourceIds = Array.from(DOM.$$('#sub-datasources option:checked')).map(opt => parseInt(opt.value));
        const severityLevels = Array.from(DOM.$$('.severity-checkbox:checked')).map(cb => cb.value);
        const channelIds = Array.from(DOM.$$('.channel-checkbox:checked')).map(cb => parseInt(cb.value));
        const enabled = DOM.$('#sub-enabled').checked;

        if (channelIds.length === 0) {
            alert('请至少选择一个通知渠道');
            return null;
        }

        return {
            datasource_ids: datasourceIds,
            severity_levels: severityLevels,
            channel_ids: channelIds,
            enabled
        };
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
            alert('订阅已删除');
        } catch (error) {
            console.error('Failed to delete subscription:', error);
            alert('删除失败: ' + error.message);
        }
    },

    getSeverityLabel(severity) {
        const labels = {
            critical: '严重',
            high: '高',
            medium: '中',
            low: '低'
        };
        return labels[severity] || severity;
    },

    getStatusLabel(status) {
        const labels = {
            active: '活跃',
            acknowledged: '已确认',
            resolved: '已解决'
        };
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

    renderPagination(type) {
        const totalPages = Math.ceil(this.totalCount[type] / this.pageSize[type]);
        if (totalPages <= 1) {
            return DOM.el('div');
        }

        const container = DOM.el('div', {
            id: `pagination-${type}`,
            style: 'margin-top: 15px; display: flex; justify-content: center; gap: 10px;'
        });

        const buttons = [];
        const currentPage = this.currentPage[type];

        // Previous button
        buttons.push(`<button class="btn btn-sm btn-secondary" style="flex: 0 0 auto;" ${currentPage === 1 ? 'disabled' : ''} onclick="AlertsPage.goToPage('${type}', ${currentPage - 1})">上一页</button>`);

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
                buttons.push(`<button class="btn btn-sm ${i === currentPage ? 'btn-primary' : 'btn-secondary'}" style="flex: 0 0 auto;" onclick="AlertsPage.goToPage('${type}', ${i})">${i}</button>`);
            } else if (i === currentPage - 3 || i === currentPage + 3) {
                buttons.push(`<span style="padding:0 5px; flex: 0 0 auto;">...</span>`);
            }
        }

        // Next button
        buttons.push(`<button class="btn btn-sm btn-secondary" style="flex: 0 0 auto;" ${currentPage === totalPages ? 'disabled' : ''} onclick="AlertsPage.goToPage('${type}', ${currentPage + 1})">下一页</button>`);

        container.innerHTML = buttons.join('');
        return container;
    },

    async goToPage(type, page) {
        this.currentPage[type] = page;

        if (type === 'events') {
            await this.loadEvents();
            this.updateEventsList();
        } else {
            await this.loadAlerts();
            this.updateAlertsList();
        }
    },

    resetPagination() {
        this.currentPage.events = 1;
        this.currentPage.alerts = 1;
    }
};
