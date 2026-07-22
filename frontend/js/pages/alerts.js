/* Alert Management Page */
const AlertsPage = {
    datasourceSelector: null,
    _renderOptions: null,
    _container: null,
    activeTab: 'alerts',
    _templatesMounted: false,
    datasources: [],
    events: [],
    subscriptions: [],
    notificationIntegrations: [],
    currentUser: null,
    expandedEvents: new Set(),
    eventAlerts: {},
    eventContexts: {},
    filters: {
        datasource_id: null,
        status: 'all',
        severity: null,
        search: '',
        start_time: null,
        end_time: null
    },
    sortBy: null,
    sortOrder: 'desc',
    currentPage: {
        events: 1
    },
    pageSize: {
        events: 10
    },
    totalCount: {
        events: 0
    },

    _t(key, params = {}) {
        return I18n.t(`alerts.${key}`, params);
    },

    async init(options = {}) {
        this._renderOptions = options || {};
        this._container = options.container || DOM.$('#page-content');
        this.currentUser = Store.get('currentUser');
        if (!this.currentUser) {
            Router.navigate('login');
            return;
        }

        this.activeTab = this._resolveInitialTab(options);
        this._templatesMounted = false;

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
            if (this.sortBy) params.append('sort_by', this.sortBy);
            if (this.sortOrder) params.append('sort_order', this.sortOrder);
            params.append('limit', this.pageSize.events);
            params.append('offset', offset);

            const response = await API.get(`/api/alerts/events?${params.toString()}`);
            this.events = response.events || [];
            this.totalCount.events = response.total || 0;

            // Debug: log silence info
            console.log('[Alerts] Loaded events:', this.events.length);
            const silencedEvents = this.events.filter(e => e.datasource_silence_until);
            console.log('[Alerts] Events with silence info:', silencedEvents.length);
            if (silencedEvents.length > 0) {
                console.log('[Alerts] Sample silenced event:', JSON.stringify(silencedEvents[0], null, 2));
                console.log('[Alerts] datasource_silence_until:', silencedEvents[0].datasource_silence_until);
                console.log('[Alerts] datasource_silence_reason:', silencedEvents[0].datasource_silence_reason);
            }
        } catch (error) {
            console.error('Failed to load events:', error);
            this.events = [];
            this.totalCount.events = 0;
        }
    },

    async loadSubscriptions() {
        try {
            this.subscriptions = await API.getSubscriptions();
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

    async loadEventContext(eventId) {
        if (this.eventContexts[eventId]) return this.eventContexts[eventId];
        try {
            const context = await API.getAlertEventContext(eventId);
            this.eventContexts[eventId] = context || {};
            return this.eventContexts[eventId];
        } catch (error) {
            console.error('Failed to load event context:', error);
            return {};
        }
    },

    async acknowledgeEvent(eventId) {
        try {
            await API.post(`/api/alerts/events/${eventId}/acknowledge`, {});
            await this.loadEvents();
            this.updateAlertsList();
            Toast.success(this._t('event.acknowledged'));
        } catch (error) {
            console.error('Failed to acknowledge event:', error);
            Toast.error(this._t('event.acknowledgeFailed', { message: error.message }));
        }
    },

    async resolveEvent(eventId) {
        try {
            await API.post(`/api/alerts/events/${eventId}/resolve`, {});
            await this.loadEvents();
            this.updateAlertsList();
            Toast.success(this._t('event.resolved'));
        } catch (error) {
            console.error('Failed to resolve event:', error);
            Toast.error(this._t('event.resolveFailed', { message: error.message }));
        }
    },

    async toggleEventExpansion(eventId) {
        if (this.expandedEvents.has(eventId)) {
            this.expandedEvents.delete(eventId);
        } else {
            this.expandedEvents.add(eventId);
            await Promise.all([
                this.loadEventAlerts(eventId),
                this.loadEventContext(eventId)
            ]);
        }
        this.updateAlertsList();
    },


    _cleanup() {
        this.datasourceSelector?.destroy();
        this.datasourceSelector = null;
        AlertTemplatesPage.cleanup?.();
        DOM.$('#page-header')?.classList.remove('page-header-alerts');
        this._renderOptions = null;
        this._container = null;
        this.activeTab = 'alerts';
        this._templatesMounted = false;
    },

    render() {
        const container = this._container || DOM.$('#page-content');
        DOM.clear(container);
        DOM.$('#page-header')?.classList.remove('page-header-alerts');
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
                textContent: this._t('title')
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
            Header.render(this._t('title'), headerActions);
            DOM.$('#page-header')?.classList.add('page-header-alerts');
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
                textContent: this._t('embeddedNote')
            }));
            note.appendChild(DOM.el('button', {
                className: 'btn btn-secondary btn-sm',
                textContent: this._t('openGlobal'),
                onClick: () => Router.navigate('alerts')
            }));
            container.appendChild(note);
            const alertsContent = DOM.el('div', { className: 'tab-pane active', id: 'alerts-pane' });
            alertsContent.appendChild(this.renderAlertsPane());
            container.appendChild(alertsContent);
        } else {
            const tabs = DOM.el('div', { className: 'tabs' });
            const alertsTab = DOM.el('button', {
                className: `tab ${this.activeTab === 'alerts' ? 'active' : ''}`,
                textContent: this._t('tabs.events'),
                onClick: (e) => this.switchTab(e.target, 'alerts')
            });
            const subscriptionsTab = DOM.el('button', {
                className: `tab ${this.activeTab === 'subscriptions' ? 'active' : ''}`,
                textContent: this._t('tabs.subscriptions'),
                onClick: (e) => this.switchTab(e.target, 'subscriptions')
            });
            const templatesTab = DOM.el('button', {
                className: `tab ${this.activeTab === 'templates' ? 'active' : ''}`,
                textContent: this._t('tabs.templates'),
                onClick: (e) => this.switchTab(e.target, 'templates')
            });
            tabs.appendChild(alertsTab);
            tabs.appendChild(subscriptionsTab);
            tabs.appendChild(templatesTab);
            container.appendChild(tabs);

            const tabContent = DOM.el('div', { className: 'tab-content' });
            const alertsContent = DOM.el('div', {
                className: `tab-pane ${this.activeTab === 'alerts' ? 'active' : ''}`,
                id: 'alerts-pane'
            });
            alertsContent.appendChild(this.renderAlertsPane());
            const subscriptionsContent = DOM.el('div', {
                className: `tab-pane ${this.activeTab === 'subscriptions' ? 'active' : ''}`,
                id: 'subscriptions-pane'
            });
            subscriptionsContent.appendChild(this.renderSubscriptionsList());
            const templatesContent = DOM.el('div', {
                className: `tab-pane ${this.activeTab === 'templates' ? 'active' : ''}`,
                id: 'templates-pane'
            });
            templatesContent.appendChild(DOM.el('div', {
                className: 'alert-ai-pane-placeholder text-muted text-sm',
                textContent: this._t('loadingTemplates')
            }));
            tabContent.appendChild(alertsContent);
            tabContent.appendChild(subscriptionsContent);
            tabContent.appendChild(templatesContent);
            container.appendChild(tabContent);
        }

        if (!this._renderOptions?.hideSubscriptions && this.activeTab === 'templates') {
            this.ensureTemplatesPaneRendered();
        }

        DOM.createIcons();
    },

    _buildHeaderActions() {
        if (!this._renderOptions?.hideSubscriptions && this.activeTab !== 'alerts') {
            this.datasourceSelector?.destroy();
            this.datasourceSelector = null;
            return [];
        }

        const filtersContainer = DOM.el('div', { className: 'dashboard-filters alerts-header-filters' });

        if (!this._renderOptions?.fixedDatasourceId) {
            const datasourceContainer = DOM.el('div', {
                id: 'alerts-datasource-selector',
                className: 'alerts-filter-datasource',
                style: { minWidth: '240px', maxWidth: '320px', flex: '0 1 320px' }
            });
            filtersContainer.appendChild(datasourceContainer);

            setTimeout(() => {
                const container = DOM.$('#alerts-datasource-selector');
                if (!container) return;

                this.datasourceSelector?.destroy();
                this.datasourceSelector = new DatasourceSelector({
                    container,
                    allowEmpty: true,
                    emptyText: this._t('filters.allDatasources'),
                    minWidth: '240px',
                    maxWidth: '320px',
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
            className: 'filter-select alerts-status-select',
            onChange: (e) => {
                this.filters.status = e.target.value;
                this.resetPagination();
                this.loadEvents().then(() => this.updateAlertsList());
            }
        });
        statusSelect.appendChild(DOM.el('option', { value: 'all', textContent: this._t('filters.allStatuses') }));
        statusSelect.appendChild(DOM.el('option', { value: 'active', textContent: this._t('statuses.active') }));
        statusSelect.appendChild(DOM.el('option', { value: 'acknowledged', textContent: this._t('statuses.acknowledged') }));
        statusSelect.appendChild(DOM.el('option', { value: 'resolved', textContent: this._t('statuses.resolved') }));
        statusSelect.value = this.filters.status;
        filtersContainer.appendChild(statusSelect);

        const severitySelect = DOM.el('select', {
            className: 'filter-select alerts-severity-select',
            onChange: (e) => {
                this.filters.severity = e.target.value || null;
                this.resetPagination();
                this.loadEvents().then(() => this.updateAlertsList());
            }
        });
        severitySelect.appendChild(DOM.el('option', { value: '', textContent: this._t('filters.allSeverities') }));
        for (const severity of ['critical', 'high', 'medium', 'low']) {
            severitySelect.appendChild(DOM.el('option', { value: severity, textContent: this.getSeverityLabel(severity) }));
        }
        severitySelect.value = this.filters.severity || '';
        filtersContainer.appendChild(severitySelect);

        const startTimeInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'filter-input alerts-date-input',
            dataset: { datePicker: '' },
            title: this._t('filters.startTime'),
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
            className: 'filter-input alerts-date-input',
            dataset: { datePicker: '' },
            title: this._t('filters.endTime'),
            value: this.filters.end_time || '',
            onChange: (e) => {
                this.filters.end_time = e.target.value || null;
                this.resetPagination();
                this.loadEvents().then(() => this.updateAlertsList());
            }
        });
        filtersContainer.appendChild(endTimeInput);
        DatePicker.enhance(startTimeInput);
        DatePicker.enhance(endTimeInput);

        const searchInput = DOM.el('input', {
            type: 'text',
            className: 'filter-input alerts-search-input',
            placeholder: I18n.t('placeholders.searchAlerts'),
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
        const showDatasourceColumn = !this._renderOptions?.fixedDatasourceId;

        if (this.events.length === 0) {
            list.appendChild(DOM.el('div', { className: 'empty-state', textContent: this._t('empty.events') }));
            return list;
        }

        const tableWrap = DOM.el('div', { className: 'data-table-container alerts-events-table-wrap' });
        const table = DOM.el('table', {
            className: `data-table events-table ${showDatasourceColumn ? '' : 'events-table-instance'}`.trim()
        });
        const thead = DOM.el('thead');
        const headerRow = DOM.el('tr');

        // Helper function to create sortable header
        const createSortableHeader = (text, sortKey) => {
            const th = DOM.el('th', {
                textContent: text,
                style: 'cursor: pointer; user-select: none;',
                onClick: () => this.toggleSort(sortKey)
            });

            if (this.sortBy === sortKey) {
                const arrow = this.sortOrder === 'asc' ? ' ↑' : ' ↓';
                th.textContent = text + arrow;
            }

            return th;
        };

        headerRow.appendChild(DOM.el('th', { textContent: '', style: 'width: 40px' }));
        headerRow.appendChild(createSortableHeader(this._t('columns.severity'), 'severity'));
        if (showDatasourceColumn) {
            headerRow.appendChild(createSortableHeader(this._t('columns.datasource'), 'datasource_id'));
        }
        headerRow.appendChild(createSortableHeader(this._t('columns.faultDomain'), 'fault_domain'));
        headerRow.appendChild(createSortableHeader(this._t('columns.lifecycle'), 'lifecycle_stage'));
        headerRow.appendChild(DOM.el('th', { textContent: this._t('columns.typeMetric') }));
        headerRow.appendChild(DOM.el('th', { textContent: this._t('columns.title') }));
        headerRow.appendChild(createSortableHeader(this._t('columns.startTime'), 'event_started_at'));
        headerRow.appendChild(createSortableHeader(this._t('columns.latestTime'), 'event_ended_at'));
        headerRow.appendChild(createSortableHeader(this._t('columns.duration'), 'duration'));
        headerRow.appendChild(createSortableHeader(this._t('columns.status'), 'status'));
        headerRow.appendChild(DOM.el('th', { textContent: this._t('columns.actions') }));
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

            if (showDatasourceColumn) {
                const datasource = this.datasources.find(ds => ds.id === event.datasource_id);
                const datasourceName = datasource ? datasource.name : `ID: ${event.datasource_id}`;
                const datasourceCell = DOM.el('td');

                // Add datasource name
                const nameSpan = DOM.el('span', { textContent: datasourceName });
                datasourceCell.appendChild(nameSpan);

                // Add silence badge if silenced
                const silenceState = this._getSilenceState(event);
                if (silenceState.isSilenced) {
                    const badgeDiv = DOM.el('div', { style: 'margin-top:6px;' });
                    const titleParts = [
                        this._t('silence.until', { time: Format.datetime(event.datasource_silence_until) }),
                        this._t('silence.remaining', { hours: this._formatHourValue(silenceState.remainingHours) }),
                    ];
                    if (silenceState.reason) {
                        titleParts.push(this._t('silence.reason', { reason: silenceState.reason }));
                    }
                    const badge = DOM.el('span', {
                        className: 'badge badge-warning',
                        textContent: this._t('silence.badge', { hours: this._formatHourValue(silenceState.remainingHours) }),
                        title: titleParts.join('\n')
                    });
                    badgeDiv.appendChild(badge);
                    datasourceCell.appendChild(badgeDiv);
                }

                row.appendChild(datasourceCell);
            }
            row.appendChild(DOM.el('td', {
                innerHTML: `<span class="event-pill fault-domain-${this._escapeHtml(event.fault_domain || 'general')}">${this._escapeHtml(this.getFaultDomainLabel(event.fault_domain))}</span>`
            }));
            row.appendChild(DOM.el('td', {
                innerHTML: `<span class="event-pill lifecycle-${this._escapeHtml(event.lifecycle_stage || 'active')}">${this._escapeHtml(this.getLifecycleStageLabel(event.lifecycle_stage))}</span>`
            }));

            const typeMetric = event.metric_name ? this.getMetricLabel(event.metric_name) : this.getAlertTypeLabel(event.alert_type);
            row.appendChild(DOM.el('td', { textContent: typeMetric || '-' }));
            row.appendChild(DOM.el('td', { textContent: event.title || '-' }));
            const eventStartTime = event.event_started_at || event.event_start_time || null;
            row.appendChild(DOM.el('td', {
                textContent: eventStartTime ? Format.datetime(eventStartTime) : '-'
            }));

            const eventEndTime = event.event_ended_at || event.event_end_time || null;
            const endTimeCell = DOM.el('td');
            if (event.status === 'resolved' && eventEndTime) {
                // 已解决：显示恢复时间
                endTimeCell.textContent = Format.datetime(eventEndTime);
                endTimeCell.title = this._t('event.recoveryTime');
            } else if (eventEndTime) {
                // 活跃/已确认：显示最后触发时间
                endTimeCell.textContent = Format.datetime(eventEndTime);
                endTimeCell.title = this._t('event.lastTriggeredAt');
            } else {
                endTimeCell.textContent = '-';
            }
            row.appendChild(endTimeCell);

            const durationCell = DOM.el('td');
            if (eventStartTime && eventEndTime) {
                const start = new Date(eventStartTime);
                const end = new Date(eventEndTime);
                const durationMs = end - start;
                const durationMinutes = Math.floor(durationMs / 60000);
                const durationHours = Math.floor(durationMinutes / 60);
                const durationDays = Math.floor(durationHours / 24);

                let durationText = '';
                if (durationDays > 0) {
                    durationText = this._t('event.durationDaysHours', { days: durationDays, hours: durationHours % 24 });
                } else if (durationHours > 0) {
                    durationText = this._t('event.durationHoursMinutes', { hours: durationHours, minutes: durationMinutes % 60 });
                } else if (durationMinutes > 0) {
                    durationText = this._t('event.durationMinutes', { minutes: durationMinutes });
                } else {
                    durationText = this._t('event.durationLessThanMinute');
                }
                durationCell.textContent = durationText;
                durationCell.title = this._t('event.durationRange', { start: Format.datetime(eventStartTime), end: Format.datetime(eventEndTime) });
            } else {
                durationCell.textContent = '-';
            }
            row.appendChild(durationCell);

            const statusCell = DOM.el('td');
            statusCell.appendChild(DOM.el('span', {
                className: `status-badge status-${event.status}`,
                textContent: this.getStatusLabel(event.status)
            }));
            row.appendChild(statusCell);

            const actionsCell = DOM.el('td');
            const actionsWrap = DOM.el('div', { className: 'actions-cell' });
            if (event.status === 'active') {
                actionsWrap.appendChild(DOM.el('button', {
                    className: 'btn btn-sm btn-secondary',
                    textContent: '✓',
                    title: this._t('actions.acknowledge'),
                    onClick: (e) => {
                        e.stopPropagation();
                        this.acknowledgeEvent(event.id);
                    }
                }));
            }
            if (event.status !== 'resolved') {
                actionsWrap.appendChild(DOM.el('button', {
                    className: 'btn btn-sm btn-success',
                    textContent: '✓✓',
                    title: this._t('actions.resolve'),
                    onClick: (e) => {
                        e.stopPropagation();
                        this.resolveEvent(event.id);
                    }
                }));
            }
            // Add silence button
            const datasource = this.datasources.find(ds => ds.id === event.datasource_id);
            const datasourceName = datasource ? datasource.name : `ID: ${event.datasource_id}`;
            actionsWrap.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-warning',
                textContent: '🔕',
                title: this._t('actions.silence'),
                onClick: (e) => {
                    e.stopPropagation();
                    this._showSilenceModal(event.datasource_id, datasourceName);
                }
            }));
            if (!actionsWrap.childNodes.length) {
                actionsWrap.appendChild(DOM.el('span', {
                    className: 'text-muted',
                    textContent: '-'
                }));
            }
            actionsCell.appendChild(actionsWrap);
            row.appendChild(actionsCell);
            tbody.appendChild(row);

            if (isExpanded) {
                const eventContext = this.eventContexts[event.id] || {};
                const expandedRow = DOM.el('tr', { className: 'expanded-row' });
                const expandedCell = DOM.el('td', { colSpan: showDatasourceColumn ? 12 : 11 });
                const alertsContainer = DOM.el('div', { className: 'event-alerts-container' });
                const alerts = this.eventAlerts[event.id] || [];

                // AI diagnosis summary with root cause and recommended actions
                if (event.root_cause || event.recommended_actions || event.ai_diagnosis_summary) {
                    const diagDiv = DOM.el('div', {
                        style: 'background:rgba(47,129,247,0.06);border-left:3px solid var(--accent-blue);padding:10px 12px;margin-bottom:12px;border-radius:6px;font-size:13px;'
                    });
                    let diagHTML = `<div style="font-weight:600;margin-bottom:8px;color:var(--accent-blue);">🧠 ${this._t('diagnosis.title')}</div>`;

                    if (event.root_cause) {
                        diagHTML += `<div style="margin-bottom:8px;"><div style="font-weight:500;color:var(--text-primary);margin-bottom:3px;">🔍 ${this._t('diagnosis.rootCause')}</div><div style="color:var(--text-secondary);line-height:1.6;">${this._escapeHtml(event.root_cause)}</div></div>`;
                    }
                    if (event.recommended_actions) {
                        diagHTML += `<div style="margin-bottom:8px;"><div style="font-weight:500;color:var(--text-primary);margin-bottom:3px;">🛠 ${this._t('diagnosis.recommendations')}</div><div style="color:var(--text-secondary);line-height:1.6;">${this._escapeHtml(event.recommended_actions)}</div></div>`;
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
                    diagPending.textContent = this._t('diagnosis.inProgress');
                    alertsContainer.appendChild(diagPending);
                } else if (event.diagnosis_status === 'pending') {
                    const diagPending = DOM.el('div', {
                        style: 'background:rgba(251,140,0,0.08);padding:10px 12px;margin-bottom:12px;border-radius:6px;font-size:12px;color:#fb8c00;'
                    });
                    diagPending.textContent = this._t('diagnosis.timedOut');
                    alertsContainer.appendChild(diagPending);
                }

                if (Array.isArray(eventContext.baseline_comparisons) && eventContext.baseline_comparisons.length > 0) {
                    const baselineDiv = DOM.el('div', { className: 'event-baseline-panel' });
                    baselineDiv.appendChild(DOM.el('div', {
                        className: 'event-panel-title',
                        textContent: this._t('baseline.comparison')
                    }));
                    const compareGrid = DOM.el('div', { className: 'event-baseline-grid' });
                    for (const item of eventContext.baseline_comparisons) {
                        const card = DOM.el('div', { className: `event-baseline-card status-${item.status || 'unknown'}` });
                        card.innerHTML = `
                            <div class="event-baseline-card-title">${this._escapeHtml(this.getMetricLabel(item.metric_name))}</div>
                            <div class="event-baseline-card-main">${this.formatNumber(item.current_value)}</div>
                            <div class="event-baseline-card-meta">P95: ${this.formatNumber(item.baseline_p95)} / ${this._t('baseline.upperBound')}: ${this.formatNumber(item.upper_bound)}</div>
                            <div class="event-baseline-card-meta">${this._t('baseline.average')}: ${this.formatNumber(item.baseline_avg)} / ${this._t('baseline.samples')}: ${item.sample_count || 0}</div>
                            <div class="event-baseline-card-meta">${this._t('baseline.status')}: ${this._escapeHtml(this.getBaselineStatusLabel(item.status))}${item.deviation_ratio ? ` / ${this._t('baseline.deviation')}: ${item.deviation_ratio.toFixed(2)}x` : ''}</div>
                        `;
                        compareGrid.appendChild(card);
                    }
                    baselineDiv.appendChild(compareGrid);
                    alertsContainer.appendChild(baselineDiv);
                }

                if (alerts.length > 0) {
                    const alertsTable = DOM.el('table', { className: 'nested-alerts-table' });
                    const alertsThead = DOM.el('thead');
                    const alertsHeaderRow = DOM.el('tr');
                    alertsHeaderRow.appendChild(DOM.el('th', { textContent: this._t('columns.time') }));
                    alertsHeaderRow.appendChild(DOM.el('th', { textContent: this._t('columns.metricValue') }));
                    alertsHeaderRow.appendChild(DOM.el('th', { textContent: this._t('columns.threshold') }));
                    alertsHeaderRow.appendChild(DOM.el('th', { textContent: this._t('columns.status') }));
                    alertsHeaderRow.appendChild(DOM.el('th', { textContent: this._t('columns.actions') }));
                    alertsThead.appendChild(alertsHeaderRow);
                    alertsTable.appendChild(alertsThead);

                    const alertsTbody = DOM.el('tbody');
                    for (const alert of alerts) {
                        const alertTime = this._resolveAlertTime(alert);
                        const metricValue = this._resolveAlertMetricValue(alert);
                        const thresholdValue = this._resolveAlertThresholdValue(alert);
                        const alertRow = DOM.el('tr');
                        alertRow.appendChild(DOM.el('td', {
                            textContent: alertTime ? Format.datetime(alertTime) : '-'
                        }));
                        alertRow.appendChild(DOM.el('td', { textContent: this.formatNumber(metricValue) }));
                        alertRow.appendChild(DOM.el('td', { textContent: this.formatNumber(thresholdValue) }));

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
                            title: this._t('actions.viewDetails'),
                            onClick: () => this.showAlertDetail(alert)
                        }));
                        alertRow.appendChild(alertActionsCell);
                        alertsTbody.appendChild(alertRow);
                    }
                    alertsTable.appendChild(alertsTbody);
                    alertsContainer.appendChild(alertsTable);
                } else {
                    alertsContainer.textContent = I18n.t('common.loading');
                }

                expandedCell.appendChild(alertsContainer);
                expandedRow.appendChild(expandedCell);
                tbody.appendChild(expandedRow);
            }
        }

        table.appendChild(tbody);
        tableWrap.appendChild(table);
        list.appendChild(tableWrap);
        list.appendChild(this.renderPagination('events'));
        return list;
    },


    renderSubscriptionsList() {
        const list = DOM.el('div', { className: 'subscriptions-list', id: 'subscriptions-list' });
        const toolbar = DOM.el('div', { style: 'margin-bottom: 16px; display: flex; justify-content: flex-end;' });
        toolbar.appendChild(DOM.el('button', {
            className: 'btn btn-primary',
            textContent: this._t('subscriptions.new'),
            onClick: () => this.showSubscriptionModal()
        }));
        list.appendChild(toolbar);

        if (this.subscriptions.length === 0) {
            list.appendChild(DOM.el('div', { className: 'empty-state', textContent: this._t('empty.subscriptions') }));
            return list;
        }

        const table = DOM.el('table', { className: 'data-table' });
        const thead = DOM.el('thead');
        const headerRow = DOM.el('tr');
        headerRow.appendChild(DOM.el('th', { textContent: this._t('columns.datasource') }));
        headerRow.appendChild(DOM.el('th', { textContent: this._t('columns.severity') }));
        headerRow.appendChild(DOM.el('th', { textContent: this._t('columns.notificationTargets') }));
        headerRow.appendChild(DOM.el('th', { textContent: this._t('columns.status') }));
        headerRow.appendChild(DOM.el('th', { textContent: this._t('columns.actions') }));
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = DOM.el('tbody');
        for (const sub of this.subscriptions) {
            const row = DOM.el('tr');
            const datasourceNames = sub.datasource_ids.length === 0 ? this._t('subscriptions.all') : sub.datasource_ids.map(id => {
                const ds = this.datasources.find(d => d.id === id);
                return ds ? ds.name : `ID: ${id}`;
            }).join(', ');
            row.appendChild(DOM.el('td', { textContent: datasourceNames }));

            const severityText = sub.severity_levels.length === 0 ? this._t('subscriptions.all') : sub.severity_levels.map(s => this.getSeverityLabel(s)).join(', ');
            row.appendChild(DOM.el('td', { textContent: severityText }));

            const targetNames = (sub.integration_targets || []).length > 0
                ? sub.integration_targets.map(target => `${target.name} (${this.getIntegrationName(target.integration_id)})`).join(', ')
                : this._t('subscriptions.notConfigured');
            row.appendChild(DOM.el('td', { textContent: targetNames }));

            const statusCell = DOM.el('td');
            statusCell.appendChild(DOM.el('span', {
                className: `status-badge ${sub.enabled ? 'status-active' : 'status-disabled'}`,
                textContent: sub.enabled ? this._t('subscriptions.enabled') : this._t('subscriptions.disabled')
            }));
            row.appendChild(statusCell);

            const actionsCell = DOM.el('td');
            const actionsWrap = DOM.el('div', { className: 'actions-cell' });
            actionsWrap.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: '<i data-lucide="edit"></i>',
                title: this._t('actions.edit'),
                onClick: () => this.showSubscriptionModal(sub)
            }));
            actionsWrap.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-primary',
                innerHTML: '<i data-lucide="send"></i>',
                title: this._t('actions.testNotification'),
                onClick: () => this.testNotification(sub.id)
            }));
            actionsWrap.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-danger',
                innerHTML: '<i data-lucide="trash-2"></i>',
                title: this._t('actions.delete'),
                onClick: () => this.deleteSubscription(sub.id)
            }));
            actionsCell.appendChild(actionsWrap);
            row.appendChild(actionsCell);
            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        list.appendChild(table);
        return list;
    },

    switchTab(tabEl, tabName) {
        this.activeTab = this._normalizeTab(tabName);

        const scope = this._container || document;
        scope.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tabEl.classList.add('active');
        scope.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));

        const nextPane = scope.querySelector(`#${this.activeTab}-pane`);
        nextPane?.classList.add('active');

        if (!this._renderOptions?.embedded) {
            Header.render(this._t('title'), this._buildHeaderActions());
            DOM.$('#page-header')?.classList.add('page-header-alerts');
        }

        if (this.activeTab === 'templates') {
            this.ensureTemplatesPaneRendered();
        }
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
            title: this._t('detail.title'),
            content: this.renderAlertDetailContent(alert),
            size: 'large',
            buttons: [
                { text: this._t('actions.close'), className: 'btn-secondary', onClick: () => Modal.hide() }
            ]
        });
    },

    renderAlertDetailContent(alert) {
        const container = DOM.el('div', { className: 'alert-detail-container' });
        const diagCtx = alert.diagnosis_context || {};
        const dsInfo = diagCtx.datasource_info || {};
        const linkedReport = diagCtx.linked_report || {};
        const alertTime = this._resolveAlertTime(alert);
        const metricValue = this._resolveAlertMetricValue(alert);
        const thresholdValue = this._resolveAlertThresholdValue(alert);

        // ========== 1. 数据库配置信息区块 ==========
        const dsCard = DOM.el('div', { className: 'detail-card' });
        dsCard.innerHTML = `
            <div class="detail-card-header">
                <span class="detail-card-icon">📊</span>
                <span class="detail-card-title">${this._t('detail.datasourceConfig')}</span>
            </div>
            <div class="detail-card-body">
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.name')}</span>
                        <span class="detail-value">${this._escapeHtml(dsInfo.name || '-')}</span>
                    </div>
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.type')}</span>
                        <span class="detail-value">${this._escapeHtml(this._getDbTypeLabel(dsInfo.db_type))}</span>
                    </div>
                </div>
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.connection')}</span>
                        <span class="detail-value">${this._escapeHtml(dsInfo.host || '-')}:${dsInfo.port || '-'} / ${this._escapeHtml(dsInfo.database || '-')}</span>
                    </div>
                </div>
                ${dsInfo.remark ? `
                <div class="detail-row">
                    <div class="detail-row-item full-width">
                        <span class="detail-label">${this._t('detail.remark')}</span>
                        <span class="detail-value">${this._escapeHtml(dsInfo.remark)}</span>
                    </div>
                </div>` : ''}
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.status')}</span>
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
                <span class="detail-card-title">${this._t('detail.title')}</span>
            </div>
            <div class="detail-card-body">
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.severity')}</span>
                        <span class="detail-value ${severityClass}">${severityIcon} ${severityLabel}</span>
                    </div>
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.status')}</span>
                        <span class="detail-value">${this.getStatusLabel(alert.status)}</span>
                    </div>
                </div>
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.alertType')}</span>
                        <span class="detail-value">${this.getAlertTypeLabel(alert.alert_type)}</span>
                    </div>
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.time')}</span>
                        <span class="detail-value">${alertTime ? Format.datetime(alertTime) : '-'}</span>
                    </div>
                </div>
                ${alert.metric_name ? `
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.metric')}</span>
                        <span class="detail-value">${this._escapeHtml(this.getMetricLabel(alert.metric_name))}</span>
                    </div>
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.currentValue')}</span>
                        <span class="detail-value">${this.formatNumber(metricValue)}</span>
                    </div>
                    ${thresholdValue !== null && thresholdValue !== undefined ? `
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.threshold')}</span>
                        <span class="detail-value">${this.formatNumber(thresholdValue)}</span>
                    </div>` : ''}
                </div>` : ''}
                ${alert.trigger_reason ? `
                <div class="detail-row">
                    <div class="detail-row-item full-width">
                        <span class="detail-label">${this._t('detail.triggerReason')}</span>
                        <span class="detail-value">${this._escapeHtml(alert.trigger_reason)}</span>
                    </div>
                </div>` : ''}
                ${alert.acknowledged_at ? `
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.acknowledgedAt')}</span>
                        <span class="detail-value">${I18n.formatDate(alert.acknowledged_at, { dateStyle: 'medium', timeStyle: 'medium' })}</span>
                    </div>
                </div>` : ''}
                ${alert.resolved_at ? `
                <div class="detail-row">
                    <div class="detail-row-item">
                        <span class="detail-label">${this._t('detail.recoveredAt')}</span>
                        <span class="detail-value">${I18n.formatDate(alert.resolved_at, { dateStyle: 'medium', timeStyle: 'medium' })}</span>
                    </div>
                </div>` : ''}
                <div class="detail-row">
                    <div class="detail-row-item full-width">
                        <span class="detail-label">${this._t('detail.alertTitle')}</span>
                        <span class="detail-value">${this._escapeHtml(alert.title || '-')}</span>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(alertCard);

        // ========== 3. AI 诊断分析区块 ==========
        const hasDiagnosis = diagCtx.case_summary || diagCtx.diagnosis_summary || diagCtx.root_cause || diagCtx.recommended_action;

        if (hasDiagnosis) {
            const diagCard = DOM.el('div', { className: 'detail-card diagnosis-card' });

            let diagHTML = `
                <div class="detail-card-header">
                    <span class="detail-card-icon">🧠</span>
                    <span class="detail-card-title">${this._t('diagnosis.title')}</span>
                </div>
                <div class="detail-card-body">
            `;

            if (diagCtx.case_summary) {
                diagHTML += `
                    <div class="diagnosis-section">
                        <div class="diagnosis-label">📋 ${this._t('diagnosis.caseSummary')}</div>
                        <div class="diagnosis-content">${this._escapeHtml(diagCtx.case_summary)}</div>
                    </div>
                `;
            }

            if (diagCtx.diagnosis_summary) {
                diagHTML += `
                    <div class="diagnosis-section">
                        <div class="diagnosis-label">🔬 ${this._t('diagnosis.summary')}</div>
                        <div class="diagnosis-content">${this._escapeHtml(diagCtx.diagnosis_summary)}</div>
                    </div>
                `;
            }

            if (diagCtx.root_cause) {
                diagHTML += `
                    <div class="diagnosis-section">
                        <div class="diagnosis-label">🔍 ${this._t('diagnosis.rootCause')}</div>
                        <div class="diagnosis-content">${this._escapeHtml(diagCtx.root_cause)}</div>
                    </div>
                `;
            }

            if (diagCtx.recommended_action) {
                diagHTML += `
                    <div class="diagnosis-section">
                        <div class="diagnosis-label">🛠 ${this._t('diagnosis.suggestedActions')}</div>
                        <div class="diagnosis-content">${this._escapeHtml(diagCtx.recommended_action)}</div>
                    </div>
                `;
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
                    <span class="detail-card-title">${this._t('detail.linkedReport')}</span>
                </div>
                <div class="detail-card-body">
                    <div class="report-info">
                        <div class="report-meta">
                            <span class="report-time">${linkedReport.created_at ? I18n.formatDate(linkedReport.created_at, { dateStyle: 'medium', timeStyle: 'medium' }) : '-'}</span>
                            <span class="report-title">${this._escapeHtml(linkedReport.title || this._t('detail.reportFallback', { id: linkedReport.report_id }))}</span>
                            <span class="report-status">${this._getReportStatusLabel(linkedReport.status)}</span>
                        </div>
                        <button class="btn btn-sm btn-secondary" onclick="AlertsPage.viewReport(${linkedReport.report_id})">${this._t('detail.viewReport')}</button>
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
                <span class="detail-card-title">${this._t('detail.content')}</span>
            </div>
            <div class="detail-card-body">
                <pre class="detail-content">${this._escapeHtml(alert.content || '-')}</pre>
            </div>
        `;
        container.appendChild(contentCard);

        return container;
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
        const prompt = this._t('prompt', {
            title: event.title || '-',
            severity: this.getSeverityLabel(event.severity) || '-',
            type: this.getAlertTypeLabel(event.alert_type) || '-',
            metric: this.getMetricLabel(event.metric_name) || '-',
            count: event.alert_count || 0,
        });
        if (this._renderOptions?.embedded) {
            const params = new URLSearchParams();
            params.set('datasource', event.datasource_id);
            params.set('tab', 'ai');
            params.set('event', event.id);
            params.set('ask', prompt);
            Router.navigate(`instance-detail?${params.toString()}`);
            return;
        }
        const params = new URLSearchParams();
        params.set('datasource', event.datasource_id);
        params.set('event', event.id);
        params.set('ask', prompt);
        Router.navigate(`diagnosis?${params.toString()}`);
    },

    ensureTemplatesPaneRendered(force = false) {
        const scope = this._container || document;
        const pane = scope.querySelector('#templates-pane');
        if (!pane) return;
        if (this._templatesMounted && !force) return;

        this._templatesMounted = true;
        AlertTemplatesPage.render({
            container: pane,
            embedded: true,
        }).catch((error) => {
            console.error('Failed to render alert templates pane:', error);
        });
    },

    _resolveInitialTab(options = {}) {
        if (options.hideSubscriptions) {
            return 'alerts';
        }

        const query = new URLSearchParams(options.routeParam || '');
        const requested = options.initialTab || query.get('tab');
        return this._normalizeTab(requested);
    },

    _normalizeTab(tabName) {
        return ['alerts', 'subscriptions', 'templates'].includes(tabName) ? tabName : 'alerts';
    },

    // Helper: Get database type label
    _getDbTypeLabel(dbType) {
        const labels = {
            mysql: 'MySQL',
            postgresql: 'PostgreSQL',
            sqlserver: 'SQL Server',
            oracle: 'Oracle',
            'tdsql-c-mysql': 'TDSQL-C MySQL',
            'oceanbase-mysql': 'OceanBase MySQL',
            opengauss: 'openGauss',
            hana: 'SAP HANA',
        };
        return labels[dbType] || dbType || '-';
    },

    // Helper: Get connection status label
    _getConnectionStatusLabel(status) {
        return this._t(`connectionStatus.${['normal', 'warning', 'failed'].includes(status) ? status : 'unknown'}`);
    },

    // Helper: Get connection status class
    _getConnectionStatusClass(status) {
        return status === 'normal' ? 'status-normal' : status === 'warning' ? 'status-warning' : status === 'failed' ? 'status-failed' : 'status-unknown';
    },

    // Helper: Get report status label
    _getReportStatusLabel(status) {
        return ['pending', 'running', 'completed', 'failed'].includes(status) ? this._t(`reportStatus.${status}`) : status || '-';
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
            title: isEdit ? this._t('subscriptions.edit') : this._t('subscriptions.new'),
            content: this.renderSubscriptionForm(formData),
            size: 'large',
            buttons: [
                { text: this._t('actions.cancel'), className: 'btn-secondary', onClick: () => Modal.hide() },
                {
                    text: this._t('actions.save'),
                    className: 'btn-primary',
                    onClick: async () => {
                        const data = this.getSubscriptionFormData(subscription);
                        if (!data) return;
                        try {
                            if (isEdit) {
                                await API.put(`/api/alerts/subscriptions/${subscription.id}`, data);
                            } else {
                                await API.post('/api/alerts/subscriptions', data);
                            }
                            await this.loadSubscriptions();
                            this.updateSubscriptionsList();
                            Modal.hide();
                            Toast.success(this._t('subscriptions.saved'));
                        } catch (error) {
                            console.error('Failed to save subscription:', error);
                            Toast.error(this._t('subscriptions.saveFailed', { message: error.message }));
                        }
                    }
                }
            ]
        });
    },

    renderSubscriptionForm(data) {
        const form = DOM.el('div', { className: 'subscription-form', id: 'subscription-form' });

        const datasourceGroup = DOM.el('div', { className: 'form-group' });
        datasourceGroup.appendChild(DOM.el('label', { textContent: this._t('subscriptions.datasourceHint') }));
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
        severityGroup.appendChild(DOM.el('label', { textContent: this._t('subscriptions.severityHint') }));
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
        targetsHeader.appendChild(DOM.el('label', { textContent: this._t('subscriptions.targets') }));
        targetsHeader.appendChild(DOM.el('button', {
            className: 'btn btn-sm btn-secondary',
            textContent: this._t('subscriptions.addTarget'),
            type: 'button',
            onClick: () => this.addIntegrationTargetRow()
        }));
        targetsGroup.appendChild(targetsHeader);

        targetsGroup.appendChild(DOM.el('div', {
            className: 'integration-target-help',
            textContent: this._t('subscriptions.targetHelp')
        }));

        const list = DOM.el('div', { id: 'integration-targets-list', className: 'integration-targets-list' });
        const targets = (data.integration_targets && data.integration_targets.length > 0) ? data.integration_targets : [this.createEmptyTarget()];
        targets.forEach(target => list.appendChild(this.renderIntegrationTargetRow(target)));
        targetsGroup.appendChild(list);
        form.appendChild(targetsGroup);

        const enabledGroup = DOM.el('div', { className: 'form-group' });
        const enabledLabel = DOM.el('label', { className: 'checkbox-label' });
        enabledLabel.appendChild(DOM.el('input', { type: 'checkbox', id: 'sub-enabled', checked: data.enabled }));
        enabledLabel.appendChild(DOM.el('span', { textContent: this._t('subscriptions.enable') }));
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
            return `<option value="${item.id}" ${selected}>${this._escapeHtml(this._integrationDisplayName(item))}</option>`;
        }).join('');

        wrapper.innerHTML = `
            <div class="integration-target-top">
                <div class="form-group">
                    <label>Integration</label>
                    <select class="target-integration">
                        <option value="">${this._t('subscriptions.select')}</option>
                        ${integrationOptions}
                    </select>
                </div>
                <div class="integration-target-actions">
                    <label class="checkbox-label target-enabled-label"><input type="checkbox" class="target-enabled" ${target.enabled !== false ? 'checked' : ''}> <span>${this._t('subscriptions.targetEnabled')}</span></label>
                    <button type="button" class="btn-icon remove-target-btn" title="${this._t('subscriptions.removeTarget')}" aria-label="${this._t('subscriptions.removeTarget')}">×</button>
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

        let html = `<div class="target-params-title">${this._t('subscriptions.targetParams')}</div>`;
        for (const [key, prop] of Object.entries(integration.config_schema.properties)) {
            const required = integration.config_schema.required?.includes(key) ? '<span class="target-param-required">*</span>' : '';
            const type = prop.format === 'password' ? 'password' : 'text';
            const value = prop.format === 'password' ? '' : (existingParams[key] || prop.default || '');
            const title = this._integrationSchemaPropertyText(integration, key, prop, 'title');
            const description = this._integrationSchemaPropertyText(integration, key, prop, 'description');
            html += `
                <div class="target-param-row">
                    <label class="target-param-label">${this._escapeHtml(title)}${required}</label>
                    <input type="${type}" class="target-param target-param-input" data-key="${key}" data-format="${prop.format || ''}" value="${this._escapeAttr(value)}" placeholder="${this._escapeAttr(description)}">
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
            const integrationName = this.getIntegrationName(integrationId, false);
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
            Toast.error(this._t('subscriptions.targetRequired'));
            return null;
        }

        return {
            datasource_ids: datasourceIds,
            severity_levels: severityLevels,
            integration_targets: integrationTargets,
            enabled
        };
    },

    getIntegrationName(integrationId, localized = true) {
        const integration = this.notificationIntegrations.find(item => item.id === integrationId);
        if (!integration) return `Integration #${integrationId}`;
        return localized ? this._integrationDisplayName(integration) : integration.name;
    },

    _knownIntegrationKey(integration) {
        const builtIn = {
            builtin_feishu_webhook: 'feishuWebhook',
            builtin_dingtalk_webhook: 'dingtalkWebhook',
            builtin_email: 'email',
            builtin_generic_webhook: 'genericWebhook',
            builtin_aliyun_rds: 'aliyunRds',
            builtin_huaweicloud_rds: 'huaweiRds',
            builtin_tencentcloud_rds: 'tencentRds',
            builtin_feishu_bot: 'feishuBot',
            builtin_dingtalk_bot: 'dingtalkBot',
            builtin_weixin_bot: 'weixinBot',
        }[integration?.integration_id];
        if (builtIn) return builtIn;

        const identifier = String(integration?.integration_id || integration?.code || '').toLowerCase();
        const name = String(integration?.name || '');
        if (!/(?:wecom|wechat[_-]?work|wework|qyweixin|enterprise[_-]?wechat)/.test(identifier)
            && !/\u4f01\u4e1a\u5fae\u4fe1|\u4f01\u5fae/.test(name)) return null;
        return integration?.integration_type === 'bot' || /bot|\u673a\u5668\u4eba/.test(`${identifier} ${name}`)
            ? 'enterpriseWechatBot'
            : 'enterpriseWechatWebhook';
    },

    _integrationDisplayName(integration) {
        const knownKey = this._knownIntegrationKey(integration);
        return knownKey ? I18n.t(`integrations.builtinNames.${knownKey}`) : (integration?.name || '');
    },

    _integrationSchemaPropertyText(integration, key, prop, field) {
        const metadata = {
            builtin_feishu_webhook: {
                webhook_url: { description: 'feishuWebhook' },
                secret: { title: 'secretOptional', description: 'feishuSecret' },
            },
            builtin_dingtalk_webhook: {
                webhook_url: { description: 'dingtalkWebhook' },
                secret: { title: 'secret', description: 'dingtalkSecret' },
            },
            builtin_email: {
                to: { title: 'recipient', description: 'recipientHelp' },
                cc: { title: 'ccOptional', description: 'ccHelp' },
            },
            builtin_generic_webhook: {
                webhook_url: { description: 'targetWebhook' }, method: { title: 'httpMethod' },
                auth_type: { title: 'authMethod' }, auth_token: { title: 'authTokenOptional' },
            },
        };
        const localeKey = metadata[integration?.integration_id]?.[key]?.[field];
        if (localeKey) return I18n.t(`integrations.schemaFields.${localeKey}`);
        const fallback = field === 'title' ? (prop.title || key) : (prop.description || '');
        return I18n.translateLegacyText(fallback);
    },

    async testNotification(subscriptionId) {
        if (!confirm(this._t('subscriptions.testConfirm'))) return;
        try {
            const result = await API.post(`/api/alerts/subscriptions/${subscriptionId}/test`, {});
            alert(this._t('subscriptions.testSent', { deliveries: JSON.stringify(result.deliveries, null, 2) }));
        } catch (error) {
            console.error('Failed to test notification:', error);
            alert(this._t('subscriptions.testFailed', { message: error.message }));
        }
    },

    async deleteSubscription(subscriptionId) {
        if (!confirm(this._t('subscriptions.deleteConfirm'))) return;
        try {
            await API.delete(`/api/alerts/subscriptions/${subscriptionId}`);
            await this.loadSubscriptions();
            this.updateSubscriptionsList();
            Toast.success(this._t('subscriptions.deleted'));
        } catch (error) {
            console.error('Failed to delete subscription:', error);
            Toast.error(this._t('subscriptions.deleteFailed', { message: error.message }));
        }
    },

    getSeverityLabel(severity) {
        return ['critical', 'high', 'medium', 'low'].includes(severity) ? this._t(`severity.${severity}`) : severity;
    },

    getStatusLabel(status) {
        return ['active', 'acknowledged', 'resolved'].includes(status) ? this._t(`statuses.${status}`) : status;
    },

    getAlertTypeLabel(type) {
        const labels = {
            threshold_violation: 'thresholdViolation',
            baseline_deviation: 'baselineDeviation',
            custom_expression: 'customExpression',
            system_error: 'systemError',
            ai_policy_violation: 'aiPolicyViolation'
        };
        return labels[type] ? this._t(`alertTypes.${labels[type]}`) : type;
    },

    getFaultDomainLabel(domain) {
        const labels = {
            availability: 'availability', performance: 'performance', storage: 'storage',
            replication: 'replication', general: 'general'
        };
        return labels[domain] ? this._t(`faultDomains.${labels[domain]}`) : domain || this._t('faultDomains.general');
    },

    getLifecycleStageLabel(stage) {
        const labels = {
            created: 'created', active: 'active', escalated: 'escalated',
            acknowledged: 'acknowledged', recovered: 'recovered'
        };
        return labels[stage] ? this._t(`lifecycle.${labels[stage]}`) : stage || this._t('lifecycle.active');
    },

    getMetricLabel(metric) {
        const labels = {
            cpu_usage: 'cpu',
            disk_usage: 'disk',
            connections_active: 'activeConnections',
            connection_status: 'connectionStatus',
            qps: 'QPS',
            tps: 'TPS'
        };
        if (['qps', 'tps'].includes(metric)) return labels[metric];
        return labels[metric] ? this._t(`metrics.${labels[metric]}`) : metric || '-';
    },

    getBaselineStatusLabel(status) {
        const labels = {
            above_baseline: 'above', within_baseline: 'within', no_profile: 'noProfile', unknown: 'unknown'
        };
        return labels[status] ? this._t(`baseline.${labels[status]}`) : status || this._t('baseline.unknown');
    },

    formatNumber(value) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
        return I18n.formatNumber(Number(value), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    },

    _pickFirstDefined(...values) {
        for (const value of values) {
            if (value !== null && value !== undefined && value !== '') return value;
        }
        return null;
    },

    _resolveAlertTime(alert) {
        return this._pickFirstDefined(
            alert?.created_at,
            alert?.event_time,
            alert?.alert_time,
            alert?.triggered_at,
            alert?.occurred_at
        );
    },

    _resolveAlertMetricValue(alert) {
        return this._pickFirstDefined(
            alert?.metric_value,
            alert?.current_value,
            alert?.value
        );
    },

    _resolveAlertThresholdValue(alert) {
        return this._pickFirstDefined(
            alert?.threshold_value,
            alert?.threshold,
            alert?.rule_threshold
        );
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
        buttons.push(`<button class="btn btn-sm btn-secondary" style="flex: 0 0 auto;" ${currentPage === 1 ? 'disabled' : ''} onclick="AlertsPage.goToPage('${type}', ${currentPage - 1})">${this._t('pagination.previous')}</button>`);
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= currentPage - 2 && i <= currentPage + 2)) {
                buttons.push(`<button class="btn btn-sm ${i === currentPage ? 'btn-primary' : 'btn-secondary'}" style="flex: 0 0 auto;" onclick="AlertsPage.goToPage('${type}', ${i})">${i}</button>`);
            } else if (i === currentPage - 3 || i === currentPage + 3) {
                buttons.push('<span style="padding:0 5px; flex: 0 0 auto;">...</span>');
            }
        }
        buttons.push(`<button class="btn btn-sm btn-secondary" style="flex: 0 0 auto;" ${currentPage === totalPages ? 'disabled' : ''} onclick="AlertsPage.goToPage('${type}', ${currentPage + 1})">${this._t('pagination.next')}</button>`);
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
    },

    async toggleSort(sortKey) {
        if (this.sortBy === sortKey) {
            this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortBy = sortKey;
            this.sortOrder = 'desc';
        }
        this.resetPagination();
        await this.loadEvents();
        this.updateAlertsList();
    },

    // Silence-related methods
    _getSilenceState(event) {
        if (!event?.datasource_silence_until) {
            return {
                isSilenced: false,
                remainingHours: null,
                silenceUntil: null,
                reason: event?.datasource_silence_reason || null,
            };
        }

        const silenceUntil = new Date(event.datasource_silence_until);
        if (Number.isNaN(silenceUntil.getTime())) {
            return {
                isSilenced: false,
                remainingHours: null,
                silenceUntil: null,
                reason: event?.datasource_silence_reason || null,
            };
        }

        const remainingMs = silenceUntil.getTime() - Date.now();
        if (remainingMs <= 0) {
            return {
                isSilenced: false,
                remainingHours: null,
                silenceUntil,
                reason: event?.datasource_silence_reason || null,
            };
        }

        return {
            isSilenced: true,
            remainingHours: Math.round((remainingMs / 3600000) * 100) / 100,
            silenceUntil,
            reason: event?.datasource_silence_reason || null,
        };
    },

    _formatHourValue(hours) {
        if (hours == null || !Number.isFinite(hours)) return '0';
        return hours.toFixed(1);
    },

    _escapeAttr(text) {
        if (text == null) return '';
        return this._escapeHtml(text).replace(/"/g, '&quot;').replace(/'/g, '&#39;');
    },

    async _showSilenceModal(datasourceId, datasourceName) {
        // Find the event to get current silence state
        const event = this.events.find(e => e.datasource_id === datasourceId);
        const state = event ? this._getSilenceState(event) : { isSilenced: false, remainingHours: null, reason: null };

        const defaultHours = state.isSilenced ? this._formatHourValue(state.remainingHours) : '1';
        const currentStatusHtml = state.isSilenced ? `
            <div style="margin-bottom:12px;padding:10px 12px;border-radius:8px;background:rgba(217,119,6,0.12);color:var(--text-primary);">
                <div style="font-weight:600;margin-bottom:4px;">${this._t('silence.current')}</div>
                <div style="font-size:12px;color:var(--text-secondary);">${this._t('silence.deadline', { time: this._escapeHtml(Format.datetime(event.datasource_silence_until)) })}</div>
                <div style="font-size:12px;color:var(--text-secondary);">${this._t('silence.remainingDuration', { hours: this._escapeHtml(this._formatHourValue(state.remainingHours)) })}</div>
                ${state.reason ? `<div style="font-size:12px;color:var(--text-secondary);">${this._t('silence.currentReason', { reason: this._escapeHtml(state.reason) })}</div>` : ''}
            </div>
        ` : '';

        Modal.show({
            title: this._t('silence.title'),
            content: `
                <div style="padding:6px 0;">
                    <div style="margin-bottom:12px;color:var(--text-secondary);line-height:1.6;">
                        ${this._t('silence.description', { name: `<strong>${this._escapeHtml(datasourceName)}</strong>` })}
                    </div>
                    ${currentStatusHtml}
                    <div class="form-group">
                        <label for="alert-silence-hours">${this._t('silence.durationLabel')}</label>
                        <input id="alert-silence-hours" type="number" class="form-input" min="0.5" max="240" step="0.5" value="${this._escapeAttr(defaultHours)}" placeholder="1">
                        <small class="text-muted">${this._t('silence.durationHint')}</small>
                    </div>
                    <div class="form-group" style="margin-top:12px;">
                        <label for="alert-silence-reason">${this._t('silence.reasonLabel')}</label>
                        <textarea id="alert-silence-reason" class="form-input" rows="3" maxlength="500" placeholder="${I18n.t('placeholders.silenceReason')}">${this._escapeHtml(state.reason || '')}</textarea>
                    </div>
                </div>
            `,
            buttons: [
                { text: this._t('actions.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: state.isSilenced ? this._t('silence.update') : this._t('silence.start'),
                    variant: 'primary',
                    onClick: () => this._setDatasourceSilence(datasourceId)
                }
            ]
        });
    },

    async _setDatasourceSilence(datasourceId) {
        const hoursValue = DOM.$('#alert-silence-hours')?.value;
        const reasonValue = DOM.$('#alert-silence-reason')?.value?.trim() || '';
        const hours = parseFloat(hoursValue);

        if (!Number.isFinite(hours)) {
            Toast.error(this._t('silence.invalidDuration'));
            return;
        }
        if (hours < 0.5 || hours > 240) {
            Toast.error(this._t('silence.outOfRange'));
            return;
        }

        try {
            const result = await API.setDatasourceSilence(datasourceId, {
                hours,
                reason: reasonValue || null,
            });
            Modal.hide();
            Toast.success(this._t('silence.set', { hours: this._formatHourValue(result.remaining_hours ?? hours) }));
            await this.loadEvents();
            this.updateAlertsList();
        } catch (err) {
            Toast.error(this._t('silence.setFailed', { message: err.message }));
        }
    }
};
