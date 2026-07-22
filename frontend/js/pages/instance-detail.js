/* Instance detail workspace */
const InstanceDetailPage = {
    datasources: [],
    instanceAlertSummaryMap: {},
    currentInstance: null,
    currentSummary: null,
    currentTab: 'monitor',
    currentRoute: {},
    tabCleanup: null,
    sessionsPollTimer: null,
    configSearch: '',
    configVariables: [],
    configSort: {
        field: 'key',
        direction: 'asc'
    },
    sessionFilters: {
        search: '',
        status: 'all',
        user: ''
    },
    sessionItems: [],
    sessionSort: {
        field: 'status',
        direction: 'asc'
    },
    sidebarCollapsed: false,
    sidebarListScrollTop: 0,
    instanceSearchText: '',
    collapsedInstanceGroups: {},
    sessionAiDialogCleanup: null,

    validTabs: ['config', 'monitor', 'traffic', 'sessions', 'ai', 'sqlConsole', 'alerts', 'inspections', 'parameters', 'topSql'],
    topSqlAiDialogCleanup: null,

    async render(routeParam = '') {
        this._rememberInstanceListScroll();
        this.cleanup();
        this.currentRoute = this._parseRoute(routeParam);
        this.sidebarListScrollTop = this._loadInstanceListScrollState();

        Header.render(I18n.t('pageCopy.instanceDetail.instanceDetails'));
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const [datasources, instanceAlertSummary] = await Promise.all([
                API.getDatasources(),
                API.getInstanceAlertSummary().catch(() => ({ items: [] })),
            ]);
            this.datasources = datasources;
            this.instanceAlertSummaryMap = this._buildInstanceAlertSummaryMap(instanceAlertSummary?.items);
            Store.set('datasources', this.datasources);
            this.sidebarCollapsed = this._loadSidebarState();
            this.collapsedInstanceGroups = this._loadInstanceGroupCollapseState();

            if (this.datasources.length === 0) {
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="database"></i>
                        <h3>${I18n.t('pageCopy.instanceDetail.noExamplesYet')}</h3>
                        <p>${I18n.t('pageCopy.instanceDetail.pleaseCreateADatasourceBeforeEnteringThe')}</p>
                        <button class="btn btn-primary mt-16" onclick="Router.navigate('datasources')">${I18n.t('pageCopy.instanceDetail.goToDatasourceManagement')}</button>
                    </div>
                `;
                DOM.createIcons();
                return () => this.cleanup();
            }

            const resolvedDatasourceId = this._resolveDatasourceId(this.currentRoute.datasourceId);
            this.currentInstance = this.datasources.find(item => item.id === resolvedDatasourceId) || this.datasources[0];
            this.currentTab = this.validTabs.includes(this.currentRoute.tab) ? this.currentRoute.tab : 'monitor';
            this._syncCurrentInstance(this.currentInstance);
            this._renderPageHeader();

            content.innerHTML = `
                <div id="instance-detail-layout" class="instance-detail-page ${this.sidebarCollapsed ? 'sidebar-collapsed' : ''}">
                    <aside id="instance-detail-sidebar" class="instance-detail-sidebar">
                        <div class="instance-sidebar-header">
                            <div class="instance-sidebar-header-text">
                                <div class="instance-sidebar-title">${I18n.t('pageCopy.instanceDetail.instanceList')}</div>
                                <div class="instance-sidebar-subtitle">${I18n.t('pageCopy.instanceDetail.singleInstanceDiagnosisAndOptimizationWorkbench')}</div>
                            </div>
                            <button
                                id="instance-sidebar-toggle"
                                class="instance-sidebar-toggle"
                                type="button"
                                title="${this._t(this.sidebarCollapsed ? I18n.t('pageCopy.instanceDetail.expandInstanceList') : I18n.t('pageCopy.instanceDetail.collapseInstanceList'))}"
                                aria-label="${this._t(this.sidebarCollapsed ? I18n.t('pageCopy.instanceDetail.expandInstanceList') : I18n.t('pageCopy.instanceDetail.collapseInstanceList'))}"
                            >
                                <i data-lucide="${this.sidebarCollapsed ? 'panel-left-open' : 'panel-left-close'}"></i>
                            </button>
                        </div>
                        <div class="instance-sidebar-search">
                            <input id="instance-search-input" class="filter-input" type="text" placeholder="${I18n.t('placeholders.searchInstances')}">
                        </div>
                        <div id="instance-list" class="instance-list"></div>
                    </aside>
                    <section class="instance-detail-main">
                        <div id="instance-tab-nav" class="instance-tab-nav"></div>
                        <div id="instance-tab-content" class="instance-tab-content"></div>
                    </section>
                </div>
            `;

            const searchInput = DOM.$('#instance-search-input');
            if (searchInput) {
                searchInput.addEventListener('input', () => this._renderInstanceList(searchInput.value.trim()));
            }
            DOM.$('#instance-list')?.addEventListener('scroll', () => this._rememberInstanceListScroll());
            DOM.$('#instance-sidebar-toggle')?.addEventListener('click', () => this._toggleSidebar());

            this._renderInstanceList('');
            this._applySidebarState();
            await this._refreshSummary();
            this._renderTabNav();
            await this._renderCurrentTab();
            this._syncUrlIfNeeded();
            DOM.createIcons();
        } catch (error) {
            content.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="alert-circle"></i>
                    <h3>${I18n.t('pageCopy.instanceDetail.failedToLoadInstanceDetails')}</h3>
                    <p>${Utils.escapeHtml(error.message || I18n.t('pageCopy.instanceDetail.unknownError'))}</p>
                </div>
            `;
            Header.render(I18n.t('pageCopy.instanceDetail.instanceDetails'));
            DOM.createIcons();
        }

        return () => this.cleanup();
    },

    cleanup() {
        if (this.sessionAiDialogCleanup) {
            const overlay = DOM.$('#modal-overlay');
            if (overlay && !overlay.classList.contains('hidden')) {
                Modal.hide();
            } else {
                try {
                    this.sessionAiDialogCleanup();
                } catch (error) {
                    console.error('Instance session AI dialog cleanup failed:', error);
                }
                this.sessionAiDialogCleanup = null;
            }
        }
        if (typeof this.tabCleanup === 'function') {
            try {
                this.tabCleanup();
            } catch (error) {
                console.error('Instance detail tab cleanup failed:', error);
            }
        }
        this.tabCleanup = null;
        if (this.sessionsPollTimer) {
            clearInterval(this.sessionsPollTimer);
            this.sessionsPollTimer = null;
        }
    },

    _parseRoute(routeParam = '') {
        const params = new URLSearchParams(routeParam || '');
        const datasourceId = parseInt(params.get('datasource'), 10);
        const tab = params.get('tab') || 'monitor';
        return {
            datasourceId: Number.isFinite(datasourceId) ? datasourceId : null,
            tab,
            alert: params.get('alert') || null,
            event: params.get('event') || null,
            report: params.get('report') || null,
            ask: params.get('ask') || null,
        };
    },

    _resolveDatasourceId(routeDatasourceId) {
        const candidateIds = [
            routeDatasourceId,
            Store.get('currentInstanceId'),
            Store.get('currentInstance')?.id,
            Store.get('currentDatasource')?.id,
            Store.get('currentConnection')?.id,
            this.datasources[0]?.id,
        ].filter(Boolean);

        for (const candidateId of candidateIds) {
            const matched = this.datasources.find(item => item.id === candidateId);
            if (matched) return matched.id;
        }
        return this.datasources[0].id;
    },

    _syncCurrentInstance(instance) {
        if (!instance) return;
        Store.set('currentInstance', instance);
        Store.set('currentInstanceId', instance.id);
        Store.set('currentConnection', instance);
        Store.set('currentDatasource', instance);
    },

    _loadSidebarState() {
        try {
            return window.localStorage.getItem('instanceDetailSidebarCollapsed') === '1';
        } catch (error) {
            return false;
        }
    },

    _saveSidebarState() {
        try {
            window.localStorage.setItem('instanceDetailSidebarCollapsed', this.sidebarCollapsed ? '1' : '0');
        } catch (error) {
            // Ignore storage errors and keep runtime state only.
        }
    },

    _loadInstanceListScrollState() {
        try {
            const raw = window.sessionStorage.getItem('instanceDetailListScrollTop');
            const value = Number.parseFloat(raw || '');
            return Number.isFinite(value) && value >= 0 ? value : 0;
        } catch (error) {
            return 0;
        }
    },

    _saveInstanceListScrollState(scrollTop) {
        const nextScrollTop = Number.isFinite(scrollTop) && scrollTop >= 0 ? scrollTop : 0;
        this.sidebarListScrollTop = nextScrollTop;
        try {
            window.sessionStorage.setItem('instanceDetailListScrollTop', String(nextScrollTop));
        } catch (error) {
            // Ignore storage errors and keep runtime state only.
        }
    },

    _rememberInstanceListScroll() {
        const listEl = DOM.$('#instance-list');
        if (!listEl) return;
        this._saveInstanceListScrollState(listEl.scrollTop || 0);
    },

    _loadInstanceGroupCollapseState() {
        try {
            const raw = window.localStorage.getItem('instanceDetailCollapsedGroups');
            const parsed = raw ? JSON.parse(raw) : {};
            return parsed && typeof parsed === 'object' ? parsed : {};
        } catch (error) {
            return {};
        }
    },

    _saveInstanceGroupCollapseState() {
        try {
            window.localStorage.setItem('instanceDetailCollapsedGroups', JSON.stringify(this.collapsedInstanceGroups || {}));
        } catch (error) {
            // Ignore storage errors and keep runtime state only.
        }
    },

    _isInstanceGroupCollapsed(groupKey) {
        return Boolean(this.collapsedInstanceGroups?.[groupKey]);
    },

    _toggleInstanceGroupCollapse(groupKey) {
        this._rememberInstanceListScroll();
        this.collapsedInstanceGroups = {
            ...(this.collapsedInstanceGroups || {}),
            [groupKey]: !this._isInstanceGroupCollapsed(groupKey),
        };
        this._saveInstanceGroupCollapseState();
        this._renderInstanceList(this.instanceSearchText);
    },

    _isElementVisibleInContainer(element, container) {
        if (!element || !container) return false;
        const elementTop = element.offsetTop;
        const elementBottom = elementTop + element.offsetHeight;
        const viewTop = container.scrollTop;
        const viewBottom = viewTop + container.clientHeight;
        return elementTop >= viewTop && elementBottom <= viewBottom;
    },

    _restoreInstanceListScroll(listEl, activeItem, fallbackScrollTop = 0) {
        if (!listEl) return;

        const targetScrollTop = Number.isFinite(fallbackScrollTop) && fallbackScrollTop > 0
            ? fallbackScrollTop
            : this.sidebarListScrollTop;

        if (Number.isFinite(targetScrollTop) && targetScrollTop > 0) {
            listEl.scrollTop = targetScrollTop;
        }

        if (activeItem && !this._isElementVisibleInContainer(activeItem, listEl)) {
            activeItem.scrollIntoView({ block: 'nearest' });
        }

        this._saveInstanceListScrollState(listEl.scrollTop || 0);
    },

    _applySidebarState() {
        const layout = DOM.$('#instance-detail-layout');
        const toggleButton = DOM.$('#instance-sidebar-toggle');
        if (layout) {
            layout.classList.toggle('sidebar-collapsed', this.sidebarCollapsed);
        }
        if (toggleButton) {
            toggleButton.title = this._t(this.sidebarCollapsed ? I18n.t('pageCopy.instanceDetail.expandInstanceList') : I18n.t('pageCopy.instanceDetail.collapseInstanceList'));
            toggleButton.setAttribute('aria-label', this._t(this.sidebarCollapsed ? I18n.t('pageCopy.instanceDetail.expandInstanceList') : I18n.t('pageCopy.instanceDetail.collapseInstanceList')));
            toggleButton.innerHTML = `<i data-lucide="${this.sidebarCollapsed ? 'panel-left-open' : 'panel-left-close'}"></i>`;
        }
        DOM.createIcons();
    },

    _toggleSidebar() {
        this.sidebarCollapsed = !this.sidebarCollapsed;
        this._saveSidebarState();
        this._applySidebarState();
    },

    _buildUrl(datasourceId, tab, extraParams = {}) {
        const params = new URLSearchParams();
        params.set('datasource', datasourceId);
        params.set('tab', tab || this.currentTab || 'monitor');
        Object.entries(extraParams).forEach(([key, value]) => {
            if (value !== null && value !== undefined && value !== '') {
                params.set(key, value);
            }
        });
        return `instance-detail?${params.toString()}`;
    },

    _syncUrlIfNeeded() {
        const extraParams = {
            alert: this.currentRoute.alert,
            event: this.currentRoute.event,
            report: this.currentRoute.report,
            ask: this.currentRoute.ask,
        };
        const expectedHash = `#${this._buildUrl(this.currentInstance.id, this.currentTab, extraParams)}`;
        if (window.location.hash !== expectedHash) {
            window.location.hash = expectedHash;
        }
    },

    _renderInstanceList(searchText = '') {
        const listEl = DOM.$('#instance-list');
        if (!listEl) return;

        const keyword = (searchText || '').trim().toLowerCase();
        const searchChanged = keyword !== this.instanceSearchText;
        this.instanceSearchText = keyword;
        const currentScrollTop = searchChanged ? 0 : (listEl.scrollTop || this.sidebarListScrollTop || 0);
        const grouped = new Map();
        const filtered = this.datasources.filter(item => {
            if (!keyword) return true;
            const haystack = [
                item.name,
                item.host,
                item.database,
                item.db_type,
                ...(item.tags || []),
            ].filter(Boolean).join(' ').toLowerCase();
            return haystack.includes(keyword);
        });

        filtered.forEach(item => {
            const groupKey = String(item.db_type || 'unknown');
            if (!grouped.has(groupKey)) {
                grouped.set(groupKey, {
                    label: this._getDbTypeLabel(item.db_type),
                    items: [],
                });
            }
            grouped.get(groupKey).items.push(item);
        });

        listEl.innerHTML = '';
        if (filtered.length === 0) {
            this._saveInstanceListScrollState(0);
            listEl.innerHTML = `<div class="instance-list-empty">${I18n.t('pageCopy.instanceDetail.noMatchingInstance')}</div>`;
            return;
        }

        let activeButton = null;
        Array.from(grouped.entries())
            .sort(([, left], [, right]) => left.label.localeCompare(right.label, I18n.getLocale()))
            .forEach(([groupKey, group]) => {
            const { label: typeLabel, items } = group;
            const collapsed = this._isInstanceGroupCollapsed(groupKey);
            const section = DOM.el('div', { className: 'instance-list-group' });
            if (collapsed) {
                section.classList.add('collapsed');
            }

            const groupHeader = DOM.el('button', {
                className: 'instance-list-group-title',
                type: 'button',
                onClick: () => this._toggleInstanceGroupCollapse(groupKey),
            });
            groupHeader.innerHTML = `
                <span class="instance-list-group-title-main">
                    <i data-lucide="${collapsed ? 'chevron-right' : 'chevron-down'}"></i>
                    <span>${this._escapeHtml(typeLabel)}</span>
                </span>
                <span class="instance-list-group-count">${items.length}</span>
            `;
            section.appendChild(groupHeader);

            const itemsWrap = DOM.el('div', { className: 'instance-list-group-items' });

            items.forEach(item => {
                const active = this.currentInstance?.id === item.id;
                const statusTone = this._instanceListStatusTone(item);
                const button = DOM.el('button', {
                    className: `instance-list-item ${active ? 'active' : ''}`,
                    onClick: () => {
                        if (this.currentInstance?.id === item.id) return;
                        this._rememberInstanceListScroll();
                        Router.navigate(this._buildUrl(item.id, this.currentTab));
                    }
                });
                button.innerHTML = `
                    <div class="instance-list-item-main">
                        <div class="instance-list-item-title">${this._escapeHtml(item.name)}</div>
                        <div class="instance-list-item-meta">${this._escapeHtml(item.host)}:${item.port}${item.database ? ` / ${this._escapeHtml(item.database)}` : ''}</div>
                    </div>
                    <div class="instance-list-item-side">
                        <span class="instance-status-dot status-${this._escapeHtml(statusTone)}"></span>
                    </div>
                `;
                if (active && !collapsed) {
                    activeButton = button;
                }
                itemsWrap.appendChild(button);
            });

            section.appendChild(itemsWrap);
            listEl.appendChild(section);
        });

        this._restoreInstanceListScroll(listEl, activeButton, currentScrollTop);
        DOM.createIcons();
    },

    async _refreshSummary() {
        this.currentSummary = await API.getInstanceSummary(this.currentInstance.id);
        if (this.currentSummary?.datasource) {
            const mergedDatasource = this._mergeDatasourceHealth(this.currentSummary.datasource, this.currentSummary.health);
            this.currentSummary.datasource = mergedDatasource;
            this.currentInstance = mergedDatasource;
            this._setInstanceAlertSummary(
                this.currentInstance.id,
                this.currentSummary.active_alert_event_count,
                this.currentSummary.active_alert_count
            );
            this.datasources = this.datasources.map(item => item.id === this.currentInstance.id ? this._mergeDatasourceHealth({
                ...item,
                ...mergedDatasource,
            }, this.currentSummary.health) : item);
            this._syncCurrentInstance(this.currentInstance);
            const searchInput = DOM.$('#instance-search-input');
            this._renderInstanceList(searchInput?.value?.trim() || '');
        }
        this._renderPageHeader();
    },

    _renderPageHeader() {
        const datasource = this.currentSummary?.datasource || this.currentInstance;
        if (!datasource) {
            Header.render(I18n.t('pageCopy.instanceDetail.instanceDetails'));
            return;
        }
        const health = this.currentSummary?.health || {};

        // 精简版本信息
        const versionInfo = datasource.db_version ? this._simplifyVersion(datasource.db_version, datasource.db_type) : null;
        const versionDisplay = versionInfo ? versionInfo.short : '';
        const versionTooltip = versionInfo ? versionInfo.full : '';

        const metaText = `${datasource.host}:${datasource.port}${datasource.database ? ` / ${datasource.database}` : ''}${versionDisplay ? ` · ${versionDisplay}` : ''}`;
        const metaTooltip = `${datasource.host}:${datasource.port}${datasource.database ? ` / ${datasource.database}` : ''}${versionTooltip ? ` · ${versionTooltip}` : ''}`;

        const headerInfo = DOM.el('div', {
            className: 'instance-page-header-info',
            innerHTML: `
                <div class="instance-page-header-line">
                    <span class="instance-page-header-name" title="${this._escapeAttr(datasource.name)}">${this._escapeHtml(datasource.name)}</span>
                    <span class="badge badge-info">${this._escapeHtml(this._getDbTypeLabel(datasource.db_type))}</span>
                    <span class="badge badge-${this._healthBadgeClass(health.status)}">${this._escapeHtml(this._healthStatusLabel(health))}</span>
                    <span class="instance-page-header-meta" title="${this._escapeAttr(metaTooltip)}">${this._escapeHtml(metaText)}</span>
                </div>
            `
        });
        Header.render(I18n.t('pageCopy.instanceDetail.instanceDetails'), headerInfo);
        DOM.createIcons();
    },

    _summaryMetric(label, value, hint = '', jumpTab = '') {
        return `
            <button class="instance-summary-metric ${jumpTab ? 'clickable' : ''}" ${jumpTab ? `data-jump-tab="${jumpTab}"` : 'type="button"'} title="${this._escapeAttr(hint || '')}">
                <span class="instance-summary-metric-label">${this._escapeHtml(label)}</span>
                <span class="instance-summary-metric-value">${this._escapeHtml(value || '-')}</span>
            </button>
        `;
    },

    _renderTabNav() {
        const nav = DOM.$('#instance-tab-nav');
        if (!nav) return;

        const tabs = [
            { id: 'config', label: I18n.t('pageCopy.instanceDetail.basicInformation') },
            { id: 'monitor', label: I18n.t('pageCopy.instanceDetail.performanceMonitoring') },
            { id: 'traffic', label: I18n.t('pageCopy.instanceDetail.trafficTopology') },
            { id: 'sessions', label: I18n.t('pageCopy.instanceDetail.realTimeSessions') },
            { id: 'ai', label: I18n.t('pageCopy.instanceDetail.aiDiagnosis') },
            { id: 'sqlConsole', label: I18n.t('pageCopy.instanceDetail.sqlWindow') },
            { id: 'topSql', label: 'TOP SQL' },
            { id: 'alerts', label: I18n.t('pageCopy.instanceDetail.alertManagement') },
            { id: 'inspections', label: I18n.t('pageCopy.instanceDetail.inspectionManagement') },
            { id: 'parameters', label: I18n.t('pageCopy.instanceDetail.instanceParameters') },
        ];

        nav.innerHTML = tabs.map(tab => `
            <button class="instance-tab ${this.currentTab === tab.id ? 'active' : ''}" data-tab="${tab.id}">
                ${this._escapeHtml(tab.label)}
            </button>
        `).join('');

        nav.querySelectorAll('.instance-tab').forEach(button => {
            button.addEventListener('click', () => {
                const nextTab = button.dataset.tab;
                if (!nextTab || nextTab === this.currentTab) return;
                Router.navigate(this._buildUrl(this.currentInstance.id, nextTab));
            });
        });
    },

    async _renderCurrentTab() {
        const container = DOM.$('#instance-tab-content');
        if (!container) return;

        this.cleanup();
        container.className = 'instance-tab-content';
        container.style.cssText = '';
        if (this.currentTab === 'ai' || this.currentTab === 'traffic') {
            container.classList.add('instance-tab-content-no-scroll');
        } else {
            container.classList.add('instance-tab-content-scroll');
        }
        container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        const datasourceId = this.currentInstance.id;

        if (this.currentTab === 'config') {
            await this._renderConfigTab(container, datasourceId);
            return;
        }

        if (this.currentTab === 'parameters') {
            await this._renderParametersTab(container, datasourceId);
            return;
        }

        if (this.currentTab === 'sessions') {
            await this._renderSessionsTab(container, datasourceId);
            return;
        }

        if (this.currentTab === 'monitor') {
            this.tabCleanup = await MonitorPage.renderWithOptions({
                container,
                embedded: true,
                fixedDatasourceId: datasourceId,
            });
            return;
        }

        if (this.currentTab === 'traffic') {
            this.tabCleanup = await InstanceTrafficPage.render({
                container,
                datasourceId,
                datasource: this.currentInstance,
            });
            return;
        }

        if (this.currentTab === 'ai') {
            const ask = this.currentRoute.ask;
            this.tabCleanup = await DiagnosisPage.renderWithOptions({
                container,
                embedded: true,
                fixedDatasourceId: datasourceId,
                sessionFilterDatasourceId: datasourceId,
                defaultSidebarCollapsed: true,
                initialAlertId: this.currentRoute.alert ? parseInt(this.currentRoute.alert, 10) : null,
                initialEventId: this.currentRoute.event ? parseInt(this.currentRoute.event, 10) : null,
                initialReportId: this.currentRoute.report ? parseInt(this.currentRoute.report, 10) : null,
                initialAsk: ask,
                preferFreshSession: Boolean(
                    ask ||
                    this.currentRoute.alert ||
                    this.currentRoute.event ||
                    this.currentRoute.report
                ),
            });
            this.currentRoute.ask = null;
            this.currentRoute.alert = null;
            this.currentRoute.event = null;
            this.currentRoute.report = null;
            return;
        }

        if (this.currentTab === 'sqlConsole') {
            this.tabCleanup = await SqlConsolePage.renderWithOptions({
                container,
                embedded: true,
                fixedDatasourceId: datasourceId,
                filterHistoryDatasourceId: datasourceId,
            });
            return;
        }

        if (this.currentTab === 'alerts') {
            this.tabCleanup = await AlertsPage.init({
                container,
                embedded: true,
                fixedDatasourceId: datasourceId,
                hideSubscriptions: true,
            });
            return;
        }

        if (this.currentTab === 'inspections') {
            this.tabCleanup = await InspectionPage.renderWithOptions({
                container,
                embedded: true,
                fixedDatasourceId: datasourceId,
                initialReportId: this.currentRoute.report ? parseInt(this.currentRoute.report, 10) : null,
            });
            this.currentRoute.report = null;
            return;
        }

        if (this.currentTab === 'topSql') {
            await this._renderTopSqlTab(container, datasourceId);
            return;
        }
    },

    async _renderConfigTab(container, datasourceId) {
        const summary = this.currentSummary || {};
        const datasource = summary.datasource || this.currentInstance;
        const health = summary.health || {};
        const inspection = summary.inspection || {};
        const metricTime = summary.metric_collected_at ? Format.datetime(summary.metric_collected_at) : I18n.t('pageCopy.instanceDetail.noneYet');
        const silenceText = datasource.silence_until
            ? `${I18n.t('pageCopy.instanceDetail.silencedUntil')} ${Format.datetime(datasource.silence_until)}`
            : I18n.t('pageCopy.instanceDetail.notSilenced');
        const silenced = Boolean(datasource.silence_until);

        container.innerHTML = `
            <div class="instance-config-page">
                <section class="instance-summary-card instance-summary-card-inline">
                    <div class="instance-summary-main">
                        <div class="instance-summary-heading">
                            <div>
                                <div class="instance-summary-title-row">
                                    <h2>${this._escapeHtml(datasource.name)}</h2>
                                    <span class="badge badge-info">${this._escapeHtml(this._getDbTypeLabel(datasource.db_type))}</span>
                                    <span class="badge badge-${this._healthBadgeClass(health.status)}">${this._escapeHtml(this._healthStatusLabel(health))}</span>
                                </div>
                                <div class="instance-summary-meta">
                                    ${this._escapeHtml(datasource.host)}:${datasource.port}${datasource.database ? ` / ${this._escapeHtml(datasource.database)}` : ''}
                                    ${datasource.db_version ? ` · ${this._escapeHtml(this._simplifyVersion(datasource.db_version, datasource.db_type).short)}` : ''}
                                </div>
                            </div>
                            <div class="instance-summary-actions">
                                <button class="btn btn-secondary btn-sm" id="instance-test-btn"><i data-lucide="plug"></i> ${I18n.t('pageCopy.instanceDetail.testConnection')}</button>
                                <button class="btn btn-secondary btn-sm" id="instance-refresh-btn"><i data-lucide="refresh-cw"></i> ${I18n.t('pageCopy.instanceDetail.refreshMetrics')}</button>
                                <button class="btn btn-primary btn-sm" id="instance-trigger-inspection-btn"><i data-lucide="zap"></i> ${I18n.t('pageCopy.instanceDetail.triggerInspection')}</button>
                                <button class="btn btn-${silenced ? 'danger' : 'secondary'} btn-sm" id="instance-silence-btn"><i data-lucide="${silenced ? 'bell-ring' : 'bell-off'}"></i> ${this._t(silenced ? I18n.t('pageCopy.instanceDetail.cancelsilence') : I18n.t('pageCopy.instanceDetail.alertSilence'))}</button>
                            </div>
                        </div>
                        <div class="instance-summary-grid">
                            ${this._summaryMetric(I18n.t('pageCopy.instanceDetail.connectionStatus'), this._connectionStatusLabel(datasource.connection_status), datasource.connection_error || health.message || '')}
                            ${this._summaryMetric(I18n.t('pageCopy.instanceDetail.latestMetric'), metricTime, '')}
                            ${this._summaryMetric(I18n.t('pageCopy.instanceDetail.activeAlertEvents'), String(summary.active_alert_event_count || 0), I18n.t('pageCopy.instanceDetail.viewAlertManagement'), 'alerts')}
                            ${this._summaryMetric(I18n.t('pageCopy.instanceDetail.activeAlerts'), String(summary.active_alert_count || 0), '')}
                            ${this._summaryMetric(I18n.t('pageCopy.instanceDetail.nextInspection'), inspection.next_scheduled_at ? Format.datetime(inspection.next_scheduled_at) : I18n.t('pageCopy.instanceDetail.notConfigured'), '')}
                            ${this._summaryMetric(I18n.t('pageCopy.instanceDetail.alertSilence'), silenceText, datasource.silence_reason || '')}
                        </div>
                    </div>
                </section>
                <div class="instance-config-grid">
                    <section class="instance-panel">
                        <h3>${I18n.t('pageCopy.instanceDetail.connectionSettings')}</h3>
                        <div id="instance-config-overview"></div>
                    </section>
                    <section class="instance-panel">
                        <h3>${I18n.t('pageCopy.instanceDetail.monitoringAndInspection')}</h3>
                        <div id="instance-config-monitoring"></div>
                    </section>
                </div>
            </div>
        `;

        const inspectionConfig = await API.get(`/api/inspections/config/${datasourceId}`).catch(() => null);
        const overview = DOM.$('#instance-config-overview');
        const monitoring = DOM.$('#instance-config-monitoring');

        if (overview) {
            overview.innerHTML = `
                ${this._configField(I18n.t('pageCopy.instanceDetail.name'), datasource.name)}
                ${this._configField(I18n.t('pageCopy.instanceDetail.databaseType'), this._getDbTypeLabel(datasource.db_type))}
                ${this._configField(I18n.t('pageCopy.instanceDetail.host'), `${datasource.host}:${datasource.port}`)}
                ${this._configField(I18n.t('pageCopy.instanceDetail.database'), datasource.database || '-')}
                ${this._configField(I18n.t('pageCopy.instanceDetail.username'), datasource.username || '-')}
                ${this._configField(I18n.t('pageCopy.instanceDetail.hostAssociation'), datasource.host_id ? `Host #${datasource.host_id}` : I18n.t('pageCopy.instanceDetail.notConfigured'))}
                ${this._configField(I18n.t('pageCopy.instanceDetail.tags'), (datasource.tags || []).join(', ') || '-')}
                ${this._configField(I18n.t('pageCopy.instanceDetail.notes'), datasource.remark || '-')}
                ${this._configField(I18n.t('pageCopy.instanceDetail.connectionCheckTime'), datasource.connection_checked_at ? Format.datetime(datasource.connection_checked_at) : I18n.t('pageCopy.instanceDetail.noneYet'))}
            `;
        }

        if (monitoring) {
            monitoring.innerHTML = `
                ${this._configField(I18n.t('pageCopy.instanceDetail.metricSource'), datasource.metric_source || 'system')}
                ${this._configField(I18n.t('pageCopy.instanceDetail.externalInstanceId'), datasource.external_instance_id || '-')}
                ${this._configField(I18n.t('pageCopy.instanceDetail.inspectionEnabled'), I18n.t(inspectionConfig?.enabled ? 'common.yes' : 'common.no'))}
                ${this._configField(I18n.t('pageCopy.instanceDetail.inspectionCycle'), inspectionConfig?.schedule_interval ? `${inspectionConfig.schedule_interval} ${I18n.t('pageCopy.instanceDetail.seconds')}` : '-')}
                ${this._configField(I18n.t('pageCopy.instanceDetail.aiAnalysis'), this._t(inspectionConfig?.use_ai_analysis === false ? I18n.t('pageCopy.instanceDetail.close') : I18n.t('pageCopy.instanceDetail.enabled')))}
                ${this._configField(I18n.t('pageCopy.instanceDetail.nextInspection'), inspectionConfig?.next_scheduled_at ? Format.datetime(inspectionConfig.next_scheduled_at) : I18n.t('pageCopy.instanceDetail.notConfigured'))}
                ${this._configField(I18n.t('pageCopy.instanceDetail.thresholdRules'), inspectionConfig?.threshold_rules ? `<pre class="instance-inline-pre">${this._escapeHtml(JSON.stringify(inspectionConfig.threshold_rules, null, 2))}</pre>` : I18n.t('pageCopy.instanceDetail.notConfigured'), true)}
            `;
        }

        container.querySelector('#instance-test-btn')?.addEventListener('click', () => this._handleTestConnection());
        container.querySelector('#instance-refresh-btn')?.addEventListener('click', () => this._handleRefreshMetrics());
        container.querySelector('#instance-trigger-inspection-btn')?.addEventListener('click', () => this._showTriggerInspectionModal());
        container.querySelector('#instance-silence-btn')?.addEventListener('click', () => {
            if (silenced) {
                this._handleCancelSilence();
            } else {
                this._showSilenceModal();
            }
        });
        container.querySelectorAll('[data-jump-tab]').forEach(node => {
            node.addEventListener('click', () => Router.navigate(this._buildUrl(this.currentInstance.id, node.dataset.jumpTab)));
        });
        DOM.createIcons();
    },

    async _renderParametersTab(container, datasourceId) {
        container.innerHTML = `
            <div class="instance-config-page">
                <div class="instance-config-toolbar">
                    <input id="instance-config-search" class="filter-input" type="text" placeholder="${I18n.t('placeholders.searchInstanceConfig')}">
                </div>
                <section class="instance-panel">
                    <div class="instance-panel-header">
                        <h3>${I18n.t('pageCopy.instanceDetail.instanceParameters')}</h3>
                        <div class="instance-panel-subtitle">${I18n.t('pageCopy.instanceDetail.readOnlyDisplayOfTheCurrentParameters')}</div>
                    </div>
                    <div id="instance-config-variables"></div>
                </section>
            </div>
        `;

        this.configVariables = await API.getInstanceVariables(datasourceId).catch(() => []);
        this.configSearch = '';
        this.configSort = {
            field: 'key',
            direction: 'asc'
        };

        const variablesContainer = DOM.$('#instance-config-variables');
        const searchInput = DOM.$('#instance-config-search');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                this.configSearch = searchInput.value.trim().toLowerCase();
                this._renderVariablesTable(variablesContainer);
            });
        }

        this._renderVariablesTable(variablesContainer);
    },

    _renderVariablesTable(container) {
        if (!container) return;
        const filtered = this.configVariables.filter(item => {
            if (!this.configSearch) return true;
            const haystack = `${item.key} ${item.value} ${item.category}`.toLowerCase();
            return haystack.includes(this.configSearch);
        });
        const sorted = [...filtered].sort((left, right) => this._compareVariables(left, right));

        if (sorted.length === 0) {
            container.innerHTML = `<div class="empty-state">${I18n.t('pageCopy.instanceDetail.noMatchingParameters')}</div>`;
            return;
        }

        container.innerHTML = `
            <div class="data-table-container instance-table-compact">
                <table class="data-table instance-variables-table">
                    <thead>
                        <tr>
                            <th class="sortable" data-sort-field="key">${I18n.t('pageCopy.instanceDetail.key')} <span class="sort-icon">${this._sortIcon('key', this.configSort)}</span></th>
                            <th class="sortable" data-sort-field="category">${I18n.t('pageCopy.instanceDetail.category')} <span class="sort-icon">${this._sortIcon('category', this.configSort)}</span></th>
                            <th class="sortable" data-sort-field="value">${I18n.t('pageCopy.instanceDetail.parameterValueColumn')} <span class="sort-icon">${this._sortIcon('value', this.configSort)}</span></th>
                            <th>${I18n.t('pageCopy.instanceDetail.actions')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${sorted.map(item => `
                            <tr>
                                <td class="instance-mono">${this._escapeHtml(item.key)}</td>
                                <td><span class="badge badge-secondary">${this._escapeHtml(item.category || 'general')}</span></td>
                                <td class="instance-variable-value">${this._escapeHtml(item.value)}</td>
                                <td>
                                    <button class="btn btn-sm btn-secondary" data-copy-value="${this._escapeAttr(item.value)}">${I18n.t('pageCopy.instanceDetail.copy')}</button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;

        container.querySelectorAll('[data-sort-field]').forEach(button => {
            button.addEventListener('click', () => {
                this._toggleTableSort('configSort', button.dataset.sortField);
                this._renderVariablesTable(container);
            });
        });

        container.querySelectorAll('[data-copy-value]').forEach(button => {
            button.addEventListener('click', async () => {
                try {
                    await navigator.clipboard.writeText(button.dataset.copyValue || '');
                    Toast.success(I18n.t('pageCopy.instanceDetail.parameterValueCopied'));
                } catch (error) {
                    Toast.error(this._t(I18n.t('pageCopy.instanceDetail.copyFailed')));
                }
            });
        });
    },

    async _renderSessionsTab(container, datasourceId) {
        this.sessionFilters = {
            search: '',
            status: 'all',
            user: ''
        };
        this.sessionSort = {
            field: 'status',
            direction: 'asc'
        };
        container.innerHTML = `
            <div class="instance-sessions-page">
                <div class="instance-sessions-toolbar">
                    <input id="instance-session-search" class="filter-input" type="text" placeholder="${I18n.t('placeholders.searchSessions')}">
                    <input id="instance-session-user" class="filter-input" type="text" placeholder="${I18n.t('placeholders.filterUser')}">
                    <select id="instance-session-status" class="filter-select">
                        <option value="all">${I18n.t('pageCopy.instanceDetail.allStatuses')}</option>
                        <option value="active">${I18n.t('pageCopy.instanceDetail.activeExecuting')}</option>
                        <option value="idle">${I18n.t('pageCopy.instanceDetail.free')}</option>
                        <option value="sleep">Sleep / sleeping</option>
                    </select>
                    <button class="btn btn-secondary" id="instance-session-refresh">${I18n.t('pageCopy.instanceDetail.refresh')}</button>
                </div>
                <div id="instance-session-meta" class="instance-session-meta"></div>
                <div id="instance-session-table"></div>
            </div>
        `;

        const bindReload = () => this._loadSessionsTable(datasourceId);
        DOM.$('#instance-session-search')?.addEventListener('input', (event) => {
            this.sessionFilters.search = event.target.value.trim().toLowerCase();
            bindReload();
        });
        DOM.$('#instance-session-user')?.addEventListener('input', (event) => {
            this.sessionFilters.user = event.target.value.trim().toLowerCase();
            bindReload();
        });
        DOM.$('#instance-session-status')?.addEventListener('change', (event) => {
            this.sessionFilters.status = event.target.value;
            bindReload();
        });
        DOM.$('#instance-session-refresh')?.addEventListener('click', bindReload);

        await this._loadSessionsTable(datasourceId);
    },

    async _loadSessionsTable(datasourceId) {
        const tableContainer = DOM.$('#instance-session-table');
        const meta = DOM.$('#instance-session-meta');
        if (!tableContainer) return;

        try {
            const sessions = await API.getInstanceSessions(datasourceId);
            this.sessionItems = sessions || [];
            const filtered = this.sessionItems.filter(item => {
                const haystack = `${item.sql_text || ''} ${item.client || ''}`.toLowerCase();
                const user = (item.user || '').toLowerCase();
                const status = (item.status || '').toLowerCase();
                const matchesSearch = !this.sessionFilters.search || haystack.includes(this.sessionFilters.search);
                const matchesUser = !this.sessionFilters.user || user.includes(this.sessionFilters.user);
                const matchesStatus = this.sessionFilters.status === 'all'
                    || (this.sessionFilters.status === 'active' && /^(active|running|query|execute)$/i.test(status))
                    || (this.sessionFilters.status === 'idle' && /^(idle|inactive)$/i.test(status))
                    || (this.sessionFilters.status === 'sleep' && /^(sleep|sleeping)$/i.test(status));
                return matchesSearch && matchesUser && matchesStatus;
            });
            const sorted = [...filtered].sort((left, right) => this._compareSessions(left, right));

            if (meta) {
                meta.textContent = I18n.t('instanceDetail.sessionMeta', {
                    count: I18n.formatNumber(sorted.length),
                    time: I18n.formatTime(new Date()),
                });
            }

            if (sorted.length === 0) {
                tableContainer.innerHTML = `<div class="empty-state">${I18n.t('pageCopy.instanceDetail.thereAreCurrentlyNoMatchingSessions')}</div>`;
                return;
            }

            tableContainer.innerHTML = `
                <div class="data-table-container instance-table-compact">
                    <table class="data-table instance-sessions-table">
                        <thead>
                            <tr>
                                <th class="sortable" data-session-sort="session_id">${I18n.t('pageCopy.instanceDetail.sessionId')} <span class="sort-icon">${this._sortIcon('session_id', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="user">${I18n.t('pageCopy.instanceDetail.user')} <span class="sort-icon">${this._sortIcon('user', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="database">${I18n.t('pageCopy.instanceDetail.database')} <span class="sort-icon">${this._sortIcon('database', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="client">${I18n.t('pageCopy.instanceDetail.client')} <span class="sort-icon">${this._sortIcon('client', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="status">${I18n.t('pageCopy.instanceDetail.status')} <span class="sort-icon">${this._sortIcon('status', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="duration_seconds">${I18n.t('pageCopy.instanceDetail.duration')} <span class="sort-icon">${this._sortIcon('duration_seconds', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="wait_event">${I18n.t('pageCopy.instanceDetail.waitEvent')} <span class="sort-icon">${this._sortIcon('wait_event', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="sql_text">SQL <span class="sort-icon">${this._sortIcon('sql_text', this.sessionSort)}</span></th>
                                <th>${I18n.t('pageCopy.instanceDetail.actions')}</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${sorted.map(item => `
                                <tr>
                                    <td class="instance-mono">${this._escapeHtml(item.session_id)}</td>
                                    <td>${this._escapeHtml(item.user || '-')}</td>
                                    <td>${this._escapeHtml(item.database || '-')}</td>
                                    <td>${this._escapeHtml(item.client || '-')}</td>
                                    <td><span class="instance-session-status-badge status-${this._escapeHtml(this._sessionStatusTone(item.status))}">${this._escapeHtml(this._t(item.status || '-'))}</span></td>
                                    <td>${item.duration_seconds != null ? this._escapeHtml(Format.uptime(item.duration_seconds)) : '-'}</td>
                                    <td>${this._escapeHtml(item.wait_event || '-')}</td>
                                    <td class="instance-variable-value">${this._escapeHtml((item.sql_text || '-').slice(0, 120))}</td>
                                    <td>
                                        <div class="instance-inline-actions instance-inline-actions-compact">
                                            <button class="btn-icon instance-action-icon" type="button" title="${I18n.t('pageCopy.instanceDetail.viewSql')}" aria-label="${I18n.t('pageCopy.instanceDetail.viewSql')}" data-view-sql="${this._escapeAttr(item.sql_text || '')}">
                                                <i data-lucide="file-text"></i>
                                            </button>
                                            <button class="btn-icon instance-action-icon" type="button" title="${I18n.t('pageCopy.instanceDetail.aiAnalysis')}" aria-label="${I18n.t('pageCopy.instanceDetail.aiAnalysis')}" data-analyze-session="${this._escapeAttr(item.session_id)}">
                                                <i data-lucide="sparkles"></i>
                                            </button>
                                            ${item.can_terminate ? `<button class="btn-icon instance-action-icon danger" type="button" title="${I18n.t('pageCopy.instanceDetail.terminateSession')}" aria-label="${I18n.t('pageCopy.instanceDetail.terminateSession')}" data-terminate-session="${this._escapeAttr(item.session_id)}"><i data-lucide="octagon-x"></i></button>` : ''}
                                        </div>
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;

            tableContainer.querySelectorAll('[data-session-sort]').forEach(button => {
                button.addEventListener('click', () => {
                    this._toggleTableSort('sessionSort', button.dataset.sessionSort);
                    this._loadSessionsTable(datasourceId);
                });
            });

            tableContainer.querySelectorAll('[data-view-sql]').forEach(button => {
                button.addEventListener('click', () => {
                    Modal.show({
                        title: I18n.t('pageCopy.instanceDetail.sessionSql'),
                        content: `<pre class="instance-inline-pre">${this._escapeHtml(button.dataset.viewSql || I18n.t('pageCopy.instanceDetail.noSqlText'))}</pre>`,
                        buttons: [{ text: I18n.t('pageCopy.instanceDetail.close'), variant: 'secondary', onClick: () => Modal.hide() }]
                    });
                });
            });

            tableContainer.querySelectorAll('[data-analyze-session]').forEach(button => {
                button.addEventListener('click', () => {
                    const session = this.sessionItems.find(item => String(item.session_id) === String(button.dataset.analyzeSession));
                    this._openSessionAiAnalysis(session);
                });
            });

            tableContainer.querySelectorAll('[data-terminate-session]').forEach(button => {
                button.addEventListener('click', () => this._terminateSession(datasourceId, button.dataset.terminateSession));
            });
            DOM.createIcons();
        } catch (error) {
            tableContainer.innerHTML = `<div class="empty-state">${this._escapeHtml(I18n.t('instanceDetail.loadSessionsFailed', { message: error.message }))}</div>`;
        }
    },

    _buildSessionAnalysisPrompt(session) {
        const datasource = this.currentSummary?.datasource || this.currentInstance || {};
        const raw = session?.raw && typeof session.raw === 'object' ? session.raw : {};
        const sessionId = this._resolveSessionAnalysisValue(session?.session_id, raw.ID);
        const sessionUser = this._resolveSessionAnalysisValue(session?.user, raw.USER);
        const sessionDatabase = this._resolveSessionAnalysisValue(session?.database, raw.DB);
        const sessionClient = this._resolveSessionAnalysisValue(session?.client, raw.HOST);
        const sessionStatus = this._resolveSessionAnalysisValue(session?.status, raw.COMMAND);
        const durationSeconds = this._resolveSessionAnalysisNumber(session?.duration_seconds, raw.TIME);
        const waitEvent = this._resolveSessionAnalysisValue(session?.wait_event, raw.STATE);
        const sqlSourceText = this._resolveSessionAnalysisValue(session?.sql_text, raw.INFO);
        const sqlText = this._truncateSessionAnalysisBlock(sqlSourceText, 3200) || I18n.t('pageCopy.instanceDetail.noSqlText');
        const extraRawText = this._buildSessionAnalysisRawExtra(raw, {
            ID: sessionId,
            USER: sessionUser,
            DB: sessionDatabase,
            HOST: sessionClient,
            COMMAND: sessionStatus,
            TIME: durationSeconds,
            STATE: waitEvent,
            INFO: sqlSourceText,
        });
        const durationText = durationSeconds != null
            ? I18n.t('pageCopy.instanceDetail.durationWithUptime', { value0: durationSeconds, value1: Format.uptime(durationSeconds) })
            : '-';
        const hostText = datasource.host
            ? `${datasource.host}:${datasource.port || '-'}`
            : '-';
        const versionText = datasource.db_version
            ? this._simplifyVersion(datasource.db_version, datasource.db_type).short
            : '-';
        const datasourceDatabaseText = this._formatSessionAnalysisValue(datasource.database);
        const sessionDatabaseText = this._formatSessionAnalysisValue(sessionDatabase);
        const sessionSummaryParts = [
            I18n.t('pageCopy.instanceDetail.sessionIdValue', { value0: this._formatSessionAnalysisValue(sessionId) }),
            I18n.t('pageCopy.instanceDetail.userValue', { value0: this._formatSessionAnalysisValue(sessionUser) }),
            I18n.t('pageCopy.instanceDetail.clientValue', { value0: this._formatSessionAnalysisValue(sessionClient) }),
        ];
        const sessionStateParts = [
            I18n.t('pageCopy.instanceDetail.statusValue', { value0: this._formatSessionAnalysisValue(sessionStatus) }),
            I18n.t('pageCopy.instanceDetail.waitEventValue', { value0: this._formatSessionAnalysisValue(waitEvent) }),
            I18n.t('pageCopy.instanceDetail.durationValue', { value0: durationText }),
        ];

        return this._t([
            I18n.t('pageCopy.instanceDetail.asASeniorDatabaseOperationAndMaintenance'),
            '',
            I18n.t('pageCopy.instanceDetail.analysisTarget'),
            I18n.t('pageCopy.instanceDetail.pleaseDetermineWhetherTheCurrentSessionIs'),
            '',
            I18n.t('pageCopy.instanceDetail.instanceInformation'),
            I18n.t('pageCopy.instanceDetail.instanceNameValue', { value0: this._formatSessionAnalysisValue(datasource.name) }),
            I18n.t('pageCopy.instanceDetail.databaseTypeValue', { value0: this._formatSessionAnalysisValue(this._getDbTypeLabel(datasource.db_type) || datasource.db_type) }),
            I18n.t('pageCopy.instanceDetail.hostValue', { value0: hostText }),
            I18n.t('pageCopy.instanceDetail.databaseValue', { value0: datasourceDatabaseText }),
            versionText !== '-' ? I18n.t('pageCopy.instanceDetail.versionValue', { value0: versionText }) : null,
            '',
            I18n.t('pageCopy.instanceDetail.sessionInformation'),
            `- ${sessionSummaryParts.join('，')}`,
            sessionDatabaseText !== '-' && sessionDatabaseText !== datasourceDatabaseText
                ? I18n.t('pageCopy.instanceDetail.sessionDatabaseValue', { value0: sessionDatabaseText })
                : null,
            `- ${sessionStateParts.join('，')}`,
            '',
            I18n.t('pageCopy.instanceDetail.sqlText'),
            sqlText,
            extraRawText ? '' : null,
            extraRawText ? I18n.t('pageCopy.instanceDetail.supplementaryFields') : null,
            extraRawText || null,
            '',
            I18n.t('pageCopy.instanceDetail.outputRequirements'),
            I18n.t('pageCopy.instanceDetail.sessionAssessmentRequirement'),
            I18n.t('pageCopy.instanceDetail.sessionRiskRequirement'),
            I18n.t('pageCopy.instanceDetail.sessionRootCauseRequirement'),
            I18n.t('pageCopy.instanceDetail.sessionResolutionRequirement'),
            I18n.t('pageCopy.instanceDetail.sessionMissingInfoRequirement'),
        ].filter(Boolean).join('\n'));
    },

    _formatSessionAnalysisValue(value) {
        if (value == null) return '-';
        const text = String(value).trim();
        return text || '-';
    },

    _resolveSessionAnalysisValue(...values) {
        for (const value of values) {
            if (value == null) continue;
            const text = String(value).trim();
            if (text) return text;
        }
        return null;
    },

    _resolveSessionAnalysisNumber(...values) {
        for (const value of values) {
            if (value == null || value === '') continue;
            const parsed = Number(value);
            if (Number.isFinite(parsed)) return parsed;
        }
        return null;
    },

    _buildSessionAnalysisRawExtra(raw, normalizedValues = {}) {
        if (!raw || typeof raw !== 'object') return '';

        const extras = Object.entries(raw).filter(([key, value]) => {
            if (value == null) return false;
            if (typeof value === 'string' && !value.trim()) return false;

            const normalizedKey = String(key).toUpperCase();
            if (!(normalizedKey in normalizedValues)) {
                return true;
            }

            return this._normalizeSessionAnalysisCompareValue(value)
                !== this._normalizeSessionAnalysisCompareValue(normalizedValues[normalizedKey]);
        });

        if (extras.length === 0) return '';

        const compactExtra = Object.fromEntries(extras);
        return this._truncateSessionAnalysisBlock(JSON.stringify(compactExtra, null, 2), 1600);
    },

    _normalizeSessionAnalysisCompareValue(value) {
        if (value == null) return '';
        if (typeof value === 'number') return String(value);
        return String(value).trim();
    },

    _truncateSessionAnalysisBlock(value, maxLength = 2400) {
        const text = String(value ?? '').trim();
        if (!text) return '';
        if (text.length <= maxLength) return text;
        return `${text.slice(0, maxLength).trimEnd()}\n${I18n.t('pageCopy.instanceDetail.truncated')}`;
    },

    async _openSessionAiAnalysis(session) {
        if (!session) {
            Toast.warning(I18n.t('pageCopy.instanceDetail.noSessionFoundToAnalyze'));
            return;
        }

        if (this.sessionAiDialogCleanup) {
            try {
                this.sessionAiDialogCleanup();
            } catch (error) {
                console.error('Previous session AI dialog cleanup failed:', error);
            }
            this.sessionAiDialogCleanup = null;
        }

        const datasource = this.currentSummary?.datasource || this.currentInstance || {};
        const content = DOM.el('div', { className: 'instance-session-ai-shell' });
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        let dialogCleanup = null;
        const title = I18n.t('instanceDetail.sessionAiTitle', {
            name: datasource.name || I18n.t('pageCopy.instanceDetail.instance'),
            sessionId: session.session_id || '-',
        });

        Modal.show({
            title,
            content,
            width: '1280px',
            maxHeight: '92vh',
            containerClassName: 'instance-session-ai-modal',
            bodyClassName: 'instance-session-ai-modal-body',
            onHide: () => {
                if (typeof dialogCleanup === 'function') {
                    try {
                        dialogCleanup();
                    } catch (error) {
                        console.error('Session AI dialog cleanup failed:', error);
                    }
                }
                if (this.sessionAiDialogCleanup === dialogCleanup) {
                    this.sessionAiDialogCleanup = null;
                }
            }
        });

        try {
            dialogCleanup = await DiagnosisPage.renderWithOptions({
                container: content,
                embedded: true,
                hideEmbeddedTitle: true,
                compactEmbeddedToolbar: true,
                fixedDatasourceId: datasource.id,
                hideSessionSidebar: true,
                autoCreateSession: true,
                autoSendInitialAsk: true,
                hideInitialAskMessage: true,
                initialAsk: this._buildSessionAnalysisPrompt(session),
                initialSessionTitle: I18n.t('instanceDetail.sessionAnalysisTitle', {
                    name: datasource.name || datasource.id || '',
                    sessionId: session.session_id || '',
                }).trim(),
                hideToolSafetyButton: true,
                hideClearSessionButton: true,
            });
            this.sessionAiDialogCleanup = dialogCleanup;
        } catch (error) {
            content.innerHTML = `
                <div class="empty-state" style="padding:40px;">
                    <i data-lucide="alert-circle"></i>
                    <h3>${I18n.t('pageCopy.instanceDetail.conversationalAiAnalysisFailedToOpen')}</h3>
                    <p>${this._escapeHtml(error.message || I18n.t('pageCopy.instanceDetail.unknownError'))}</p>
                </div>
            `;
            DOM.createIcons();
        }
    },

    _toggleTableSort(stateKey, field) {
        const current = this[stateKey] || {};
        if (current.field === field) {
            this[stateKey] = {
                field,
                direction: current.direction === 'asc' ? 'desc' : 'asc'
            };
            return;
        }
        this[stateKey] = {
            field,
            direction: 'asc'
        };
    },

    _sortIcon(field, state) {
        if (!state || state.field !== field) return '↕';
        return state.direction === 'asc' ? '↑' : '↓';
    },

    _compareVariables(left, right) {
        const state = this.configSort || { field: 'key', direction: 'asc' };
        const direction = state.direction === 'desc' ? -1 : 1;
        const leftValue = this._normalizeSortValue(left?.[state.field]);
        const rightValue = this._normalizeSortValue(right?.[state.field]);
        return this._compareSortValues(leftValue, rightValue) * direction;
    },

    _compareSessions(left, right) {
        const state = this.sessionSort || { field: 'status', direction: 'asc' };
        const direction = state.direction === 'desc' ? -1 : 1;
        let result = 0;

        if (state.field === 'status') {
            result = this._sessionStatusRank(left?.status) - this._sessionStatusRank(right?.status);
            if (result === 0) {
                result = (right?.duration_seconds || 0) - (left?.duration_seconds || 0);
            }
        } else if (state.field === 'duration_seconds') {
            result = (left?.duration_seconds ?? -1) - (right?.duration_seconds ?? -1);
        } else {
            const leftValue = this._normalizeSortValue(left?.[state.field]);
            const rightValue = this._normalizeSortValue(right?.[state.field]);
            result = this._compareSortValues(leftValue, rightValue);
        }

        if (result === 0) {
            result = this._sessionStatusRank(left?.status) - this._sessionStatusRank(right?.status);
        }
        if (result === 0) {
            result = (right?.duration_seconds || 0) - (left?.duration_seconds || 0);
        }
        return result * direction;
    },

    _normalizeSortValue(value) {
        if (value == null) return '';
        if (typeof value === 'number') return value;
        return String(value).toLowerCase();
    },

    _compareSortValues(left, right) {
        if (typeof left === 'number' && typeof right === 'number') {
            return left - right;
        }
        return String(left).localeCompare(String(right), I18n.getLocale(), { numeric: true, sensitivity: 'base' });
    },

    _sessionStatusRank(status) {
        const normalized = String(status || '').toLowerCase();
        if (/\binactive\b/.test(normalized)) return 2;
        if (/\bidle in transaction\b|\bidle\b/.test(normalized)) return 1;
        if (/\bsleep\b|\bsleeping\b/.test(normalized)) return 2;
        if (/\bactive\b|\brunning\b|\bquery\b|\bexecute(?:d|ing)?\b|\blocked\b|lock wait/.test(normalized)) return 0;
        return 3;
    },

    _sessionStatusTone(status) {
        const rank = this._sessionStatusRank(status);
        if (rank === 0) return 'active';
        if (rank === 1) return 'idle';
        if (rank === 2) return 'sleep';
        return 'other';
    },

    async _terminateSession(datasourceId, sessionId) {
        Modal.show({
            title: I18n.t('pageCopy.instanceDetail.terminateSession'),
            content: I18n.t('instanceDetail.terminateConfirm', {
                sessionId: `<strong>${this._escapeHtml(sessionId)}</strong>`,
            }),
            buttons: [
                { text: I18n.t('pageCopy.instanceDetail.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: I18n.t('pageCopy.instanceDetail.confirmTermination'),
                    variant: 'danger',
                    onClick: async () => {
                        try {
                            await API.terminateInstanceSession(datasourceId, sessionId);
                            Modal.hide();
                            Toast.success(I18n.t('instanceDetail.terminated', { sessionId }));
                            await this._loadSessionsTable(datasourceId);
                        } catch (error) {
                            Toast.error(I18n.t('instanceDetail.terminateFailed', {
                                message: error.message || I18n.t('pageCopy.instanceDetail.unknownError'),
                            }));
                        }
                    }
                }
            ]
        });
    },

    async _handleTestConnection() {
        try {
            const result = await API.testDatasource(this.currentInstance.id);
            if (result.success) {
                const versionDisplay = result.version
                    ? `(${this._simplifyVersion(result.version, this.currentInstance.db_type).short})`
                    : '';
                Toast.success(I18n.t('instanceDetail.connectionSucceeded', { version: versionDisplay }).trim());
            } else {
                Toast.error(result.message || this._t(I18n.t('pageCopy.instanceDetail.connectionFailed')));
            }
            await this._refreshSummary();
            if (this.currentTab === 'config') {
                await this._renderCurrentTab();
            }
        } catch (error) {
            Toast.error(I18n.t('instanceDetail.testConnectionFailed', { message: error.message }));
        }
    },

    async _handleRefreshMetrics() {
        const refreshBtn = DOM.$('#instance-refresh-btn');
        const originalHtml = refreshBtn ? refreshBtn.innerHTML : '';

        if (refreshBtn) {
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = `<span class="spinner" style="display:inline-block;width:14px;height:14px;margin-right:8px;vertical-align:-2px;"></span>${I18n.t('pageCopy.instanceDetail.collecting')}`;
        }
        Toast.info(I18n.t('instanceDetail.refreshStarted'));

        try {
            await API.refreshMetrics(this.currentInstance.id);
            await new Promise(resolve => setTimeout(resolve, 1000));
            await this._refreshSummary();
            if (this.currentTab === 'monitor' || this.currentTab === 'config') {
                await this._renderCurrentTab();
            }
            Toast.success(I18n.t('pageCopy.instanceDetail.indicatorRefreshCompleted'));
        } catch (error) {
            Toast.error(I18n.t('instanceDetail.refreshFailed', { message: error.message }));
        } finally {
            if (refreshBtn) {
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = originalHtml || `<i data-lucide="refresh-cw"></i> ${I18n.t('pageCopy.instanceDetail.refreshMetrics')}`;
                DOM.createIcons();
            }
        }
    },

    _showTriggerInspectionModal() {
        const datasource = this.currentSummary?.datasource || this.currentInstance || {};
        Modal.show({
            title: I18n.t('pageCopy.instanceDetail.confirmTriggerInspection'),
            content: `
                <div class="form-group" style="margin-bottom:0;">
                    <div style="font-size:14px;line-height:1.8;color:var(--text-primary);">
                        ${I18n.t('instanceDetail.triggerPrompt', { name: `<strong>${this._escapeHtml(datasource.name || '-')}</strong>` })}
                    </div>
                    <div style="margin-top:10px;font-size:12px;line-height:1.7;color:var(--text-secondary);">
                        ${I18n.t('instanceDetail.triggerHelp')}
                    </div>
                </div>
            `,
            buttons: [
                { text: I18n.t('pageCopy.instanceDetail.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: I18n.t('pageCopy.instanceDetail.confirmTrigger'),
                    variant: 'primary',
                    onClick: async () => {
                        await this._handleTriggerInspection();
                    }
                },
            ],
        });
    },

    async _handleTriggerInspection() {
        const datasourceId = this.currentInstance?.id;
        if (!datasourceId) {
            Toast.error(this._t(I18n.t('pageCopy.instanceDetail.theCurrentInstanceDoesNotExistAnd')));
            return;
        }

        const confirmButton = Array.from(document.querySelectorAll('#modal-container .modal-footer .btn'))
            .find((button) => button.textContent?.includes(I18n.t('pageCopy.instanceDetail.confirmTrigger')));
        if (confirmButton) {
            confirmButton.disabled = true;
            confirmButton.textContent = I18n.t('pageCopy.instanceDetail.starting');
        }

        try {
            const result = await API.post(`/api/inspections/trigger/${datasourceId}`);
            Modal.hide();
            Toast.success(I18n.t('instanceDetail.inspectionSubmitted', {
                triggerId: result?.trigger_id ? ` #${result.trigger_id}` : '',
            }));
            await this._refreshSummary();
            const nextUrl = this._buildUrl(datasourceId, 'inspections', {
                report: result?.report_id || null,
            });
            Router.navigate(nextUrl);
        } catch (error) {
            if (confirmButton) {
                confirmButton.disabled = false;
                confirmButton.textContent = I18n.t('pageCopy.instanceDetail.confirmTrigger');
            }
            Toast.error(I18n.t('instanceDetail.triggerFailed', { message: error.message }));
        }
    },

    _showSilenceModal() {
        Modal.show({
            title: I18n.t('pageCopy.instanceDetail.silenceAlerts'),
            content: `
                <div class="form-group">
                    <label for="instance-silence-hours">${I18n.t('alerts.silence.durationLabel')}</label>
                    <input id="instance-silence-hours" class="form-input" type="number" min="0.5" max="240" step="0.5" value="1">
                </div>
                <div class="form-group">
                    <label for="instance-silence-reason">${I18n.t('alerts.silence.reasonLabel')}</label>
                    <textarea id="instance-silence-reason" class="form-input" rows="3" placeholder="${I18n.t('placeholders.instanceSilenceReason')}"></textarea>
                </div>
            `,
            buttons: [
                { text: I18n.t('pageCopy.instanceDetail.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: I18n.t('pageCopy.instanceDetail.startSilence'),
                    variant: 'primary',
                    onClick: async () => {
                        const hours = parseFloat(DOM.$('#instance-silence-hours')?.value || '0');
                        const reason = DOM.$('#instance-silence-reason')?.value?.trim() || null;
                        if (!Number.isFinite(hours) || hours < 0.5 || hours > 240) {
                            Toast.error(this._t(I18n.t('pageCopy.instanceDetail.quietDurationMustBeBetween05')));
                            return;
                        }
                        try {
                            await API.setDatasourceSilence(this.currentInstance.id, { hours, reason });
                            Modal.hide();
                            Toast.success(I18n.t('pageCopy.instanceDetail.alertSilenceEnabled'));
                            await this._refreshSummary();
                            if (this.currentTab === 'config') {
                                await this._renderCurrentTab();
                            }
                        } catch (error) {
                            Toast.error(I18n.t('instanceDetail.silenceSetFailed', { message: error.message }));
                        }
                    }
                }
            ]
        });
    },

    async _handleCancelSilence() {
        try {
            await API.cancelDatasourceSilence(this.currentInstance.id);
            Toast.success(I18n.t('pageCopy.instanceDetail.alarmSilenceHasBeenCanceled'));
            await this._refreshSummary();
            if (this.currentTab === 'config') {
                await this._renderCurrentTab();
            }
        } catch (error) {
            Toast.error(I18n.t('instanceDetail.silenceCancelFailed', { message: error.message }));
        }
    },

    _configField(label, value, allowHtml = false) {
        return `
            <div class="instance-config-field ${allowHtml ? 'full' : ''}">
                <div class="instance-config-label">${this._escapeHtml(label)}</div>
                <div class="instance-config-value">${allowHtml ? value : this._escapeHtml(value || '-')}</div>
            </div>
        `;
    },

    _healthBadgeClass(status) {
        if (status === 'healthy') return 'success';
        if (status === 'warning') return 'warning';
        if (status === 'critical') return 'danger';
        return 'secondary';
    },

    _isConnectionFailureHealth(health) {
        if (!health) return false;
        if (Array.isArray(health.violations) && health.violations.some(item => item?.type === 'connection_failure')) {
            return true;
        }
        return String(health.message || '').includes(I18n.t('pageCopy.instanceDetail.connectionFailed'));
    },

    _healthStatusLabel(health) {
        if (this._isConnectionFailureHealth(health)) return I18n.t('pageCopy.instanceDetail.connectionFailed');
        const map = {
            healthy: I18n.t('pageCopy.instanceDetail.healthy'),
            warning: I18n.t('pageCopy.instanceDetail.warning'),
            critical: I18n.t('pageCopy.instanceDetail.abnormal'),
            unknown: I18n.t('pageCopy.instanceDetail.unknown')
        };
        return map[health?.status] || I18n.t('pageCopy.instanceDetail.unknown');
    },

    _connectionStatusLabel(status) {
        const map = {
            normal: I18n.t('pageCopy.instanceDetail.healthy2'),
            warning: I18n.t('pageCopy.instanceDetail.warning'),
            failed: I18n.t('pageCopy.instanceDetail.connectionFailed'),
            unknown: I18n.t('pageCopy.instanceDetail.unknown')
        };
        return map[status] || this._t(status || I18n.t('pageCopy.instanceDetail.unknown'));
    },

    _mergeDatasourceHealth(datasource, health) {
        if (!datasource) return datasource;
        return {
            ...datasource,
            health_summary: health ? {
                healthy: health.healthy,
                status: health.status || 'unknown',
                message: health.message || '',
                violations: Array.isArray(health.violations) ? health.violations : [],
            } : datasource.health_summary || null,
        };
    },

    _healthStatusTone(status) {
        if (status === 'healthy') return 'normal';
        if (status === 'warning') return 'warning';
        if (status === 'critical') return 'failed';
        return 'unknown';
    },

    _instanceListStatusTone(datasource) {
        const alertSummary = this._getInstanceAlertSummary(datasource?.id);
        const hasActiveAlert = (alertSummary.active_alert_event_count || 0) > 0 || (alertSummary.active_alert_count || 0) > 0;
        if (hasActiveAlert) {
            return 'failed';
        }
        const health = datasource?.health_summary
            || (datasource?.id === this.currentInstance?.id ? this.currentSummary?.health : null);
        const healthTone = this._healthStatusTone(health?.status);
        if (healthTone === 'normal') {
            return 'normal';
        }
        if (healthTone === 'warning' || healthTone === 'failed') {
            return 'failed';
        }
        if (datasource?.connection_status === 'normal') {
            return 'normal';
        }
        return 'failed';
    },

    _buildInstanceAlertSummaryMap(items = []) {
        return (Array.isArray(items) ? items : []).reduce((acc, item) => {
            const datasourceId = Number.parseInt(item?.datasource_id, 10);
            if (!Number.isFinite(datasourceId)) return acc;
            acc[datasourceId] = {
                active_alert_event_count: Number(item?.active_alert_event_count) || 0,
                active_alert_count: Number(item?.active_alert_count) || 0,
            };
            return acc;
        }, {});
    },

    _getInstanceAlertSummary(datasourceId) {
        if (!Number.isFinite(Number(datasourceId))) {
            return {
                active_alert_event_count: 0,
                active_alert_count: 0,
            };
        }
        return this.instanceAlertSummaryMap?.[datasourceId] || {
            active_alert_event_count: 0,
            active_alert_count: 0,
        };
    },

    _setInstanceAlertSummary(datasourceId, activeAlertEventCount, activeAlertCount) {
        const normalizedId = Number.parseInt(datasourceId, 10);
        if (!Number.isFinite(normalizedId)) return;
        this.instanceAlertSummaryMap = {
            ...(this.instanceAlertSummaryMap || {}),
            [normalizedId]: {
                active_alert_event_count: Number(activeAlertEventCount) || 0,
                active_alert_count: Number(activeAlertCount) || 0,
            },
        };
    },

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

    _t(value) {
        return String(value ?? '');
    },

    _escapeHtml(value) {
        return Utils.escapeHtml(String(value ?? ''));
    },

    _escapeAttr(value) {
        return this._escapeHtml(value).replace(/"/g, '&quot;');
    },

    async _renderTopSqlTab(container, datasourceId) {
        try {
            const response = await API.get(`/api/datasources/${datasourceId}/top-sql?limit=100`);
            const topSqlList = response.data || [];

            if (topSqlList.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="database"></i>
                        <h3>${I18n.t('pageCopy.instanceDetail.noTopSqlDataYet')}</h3>
                        <p>${I18n.t('pageCopy.instanceDetail.theCurrentDatabaseMayNotHaveThe')}</p>
                        <p class="text-muted mt-8">${I18n.t('pageCopy.instanceDetail.mysqlPerformanceSchemaNeedsToBeEnabled')}</p>
                    </div>
                `;
                DOM.createIcons();
                return;
            }

            // 存储原始数据和当前状态
            this.topSqlData = {
                datasourceId,
                allData: topSqlList,
                filteredData: topSqlList,
                sortColumn: 'total_time_sec',
                sortDirection: 'desc',
                filterText: ''
            };

            this._renderTopSqlContent(container);
        } catch (error) {
            console.error('Failed to load TOP SQL:', error);
            container.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="alert-circle"></i>
                    <h3>${I18n.t('pageCopy.instanceDetail.loadFailed')}</h3>
                    <p>${this._escapeHtml(I18n.t('instanceDetail.loadTopSqlFailed', { message: error.message || I18n.t('pageCopy.instanceDetail.unknownError') }))}</p>
                </div>
            `;
            DOM.createIcons();
        }
    },

    _renderTopSqlContent(container) {
        const { filteredData, sortColumn, sortDirection, filterText } = this.topSqlData;

        container.innerHTML = `
            <div class="top-sql-container">
                <div class="top-sql-header">
                    <h3>${I18n.t('pageCopy.instanceDetail.topSqlAnalysis')}</h3>
                    <div class="top-sql-controls">
                        <div class="search-box">
                            <i data-lucide="search"></i>
                            <input type="text"
                                   id="topSqlFilter"
                                   placeholder="${I18n.t('placeholders.searchSql')}"
                                   value="${this._escapeAttr(filterText)}">
                        </div>
                        <div class="top-sql-stats">
                            <span class="badge badge-info">${I18n.t('instanceDetail.topSqlCount', { count: I18n.formatNumber(filteredData.length) })}</span>
                        </div>
                    </div>
                </div>
                <div class="table-container">
                    <table class="data-table top-sql-table">
                        <thead>
                            <tr>
                                <th style="width: 60px;">${I18n.t('pageCopy.instanceDetail.serialNumber')}</th>
                                <th style="width: 140px;" data-sort="sql_id" data-label="SQL ID">
                                    SQL ID ${this._getSortIcon('sql_id')}
                                </th>
                                <th style="min-width: 300px;" data-sort="sql_text" data-label="${I18n.t('pageCopy.instanceDetail.sqlText2')}">
                                    ${I18n.t('pageCopy.instanceDetail.sqlText2')} ${this._getSortIcon('sql_text')}
                                </th>
                                <th style="width: 100px;" data-sort="exec_count" data-label="${I18n.t('pageCopy.instanceDetail.executionCount')}">
                                    ${I18n.t('pageCopy.instanceDetail.executionCount')} ${this._getSortIcon('exec_count')}
                                </th>
                                <th style="width: 130px;" data-sort="total_time_sec" data-label="${I18n.t('pageCopy.instanceDetail.totalExecutionTimeS')}">
                                    ${I18n.t('pageCopy.instanceDetail.totalExecutionTimeS')} ${this._getSortIcon('total_time_sec')}
                                </th>
                                <th style="width: 120px;" data-sort="total_rows_scanned" data-label="${I18n.t('pageCopy.instanceDetail.totalRowsScanned')}">
                                    ${I18n.t('pageCopy.instanceDetail.totalRowsScanned')} ${this._getSortIcon('total_rows_scanned')}
                                </th>
                                <th style="width: 130px;" data-sort="total_wait_time_sec" data-label="${I18n.t('pageCopy.instanceDetail.totalWaitingTimeS')}">
                                    ${I18n.t('pageCopy.instanceDetail.totalWaitingTimeS')} ${this._getSortIcon('total_wait_time_sec')}
                                </th>
                                <th style="width: 130px;" data-sort="avg_time_sec" data-label="${I18n.t('pageCopy.instanceDetail.averageExecutionTimeS')}">
                                    ${I18n.t('pageCopy.instanceDetail.averageExecutionTimeS')} ${this._getSortIcon('avg_time_sec')}
                                </th>
                                <th style="width: 120px;" data-sort="avg_rows_scanned" data-label="${I18n.t('pageCopy.instanceDetail.averageRowsScanned')}">
                                    ${I18n.t('pageCopy.instanceDetail.averageRowsScanned')} ${this._getSortIcon('avg_rows_scanned')}
                                </th>
                                <th style="width: 130px;" data-sort="avg_wait_time_sec" data-label="${I18n.t('pageCopy.instanceDetail.averageWaitingTimeS')}">
                                    ${I18n.t('pageCopy.instanceDetail.averageWaitingTimeS')} ${this._getSortIcon('avg_wait_time_sec')}
                                </th>
                                <th style="width: 160px;" data-sort="last_exec_time" data-label="${I18n.t('pageCopy.instanceDetail.lastRun')}">
                                    ${I18n.t('pageCopy.instanceDetail.lastRun')} ${this._getSortIcon('last_exec_time')}
                                </th>
                            </tr>
                        </thead>
                        <tbody>
                            ${filteredData.map((sql, index) => `
                                <tr class="top-sql-row" data-sql-index="${index}">
                                    <td>${index + 1}</td>
                                    <td class="text-monospace" title="${this._escapeAttr(sql.sql_id || '-')}">${this._escapeHtml(this._truncate(sql.sql_id, 20))}</td>
                                    <td class="sql-text-cell">
                                        <div class="sql-text-wrapper" title="${this._escapeAttr(sql.sql_text || '-')}">
                                            ${this._escapeHtml(sql.sql_text || '-')}
                                        </div>
                                    </td>
                                    <td class="text-right">${Format.number(sql.exec_count || 0)}</td>
                                    <td class="text-right">${Format.number(sql.total_time_sec || 0, 6)}</td>
                                    <td class="text-right">${Format.number(sql.total_rows_scanned || 0)}</td>
                                    <td class="text-right">${Format.number(sql.total_wait_time_sec || 0, 6)}</td>
                                    <td class="text-right">${Format.number(sql.avg_time_sec || 0, 6)}</td>
                                    <td class="text-right">${Format.number(sql.avg_rows_scanned || 0, 2)}</td>
                                    <td class="text-right">${Format.number(sql.avg_wait_time_sec || 0, 6)}</td>
                                    <td>${sql.last_exec_time ? Format.datetime(sql.last_exec_time) : '-'}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            </div>
        `;

        // 确保抽屉在body级别
        if (!document.getElementById('topSqlDrawer')) {
            const drawer = document.createElement('div');
            drawer.id = 'topSqlDrawer';
            drawer.className = 'drawer';
            drawer.style.visibility = 'visible';
            document.body.appendChild(drawer);
        }

        DOM.createIcons();
        this._attachTopSqlEventListeners(container);

        // 恢复输入框焦点
        const filterInput = container.querySelector('#topSqlFilter');
        if (filterInput && document.activeElement?.id === 'topSqlFilter') {
            filterInput.focus();
            filterInput.setSelectionRange(filterInput.value.length, filterInput.value.length);
        }
    },

    _getSortIcon(column) {
        const { sortColumn, sortDirection } = this.topSqlData;
        if (sortColumn !== column) {
            return '<i data-lucide="chevrons-up-down" class="sort-icon"></i>';
        }
        return sortDirection === 'asc'
            ? '<i data-lucide="chevron-up" class="sort-icon active"></i>'
            : '<i data-lucide="chevron-down" class="sort-icon active"></i>';
    },

    _attachTopSqlEventListeners(container) {
        // 搜索过滤
        const filterInput = container.querySelector('#topSqlFilter');
        if (filterInput) {
            filterInput.addEventListener('input', (e) => {
                this.topSqlData.filterText = e.target.value.toLowerCase();
                this._applyTopSqlFilter();
                this._updateTopSqlTable(container);
            });
        }

        // 表头排序
        const headers = container.querySelectorAll('th[data-sort]');
        headers.forEach(th => {
            th.style.cursor = 'pointer';
            th.addEventListener('click', () => {
                const column = th.dataset.sort;
                if (this.topSqlData.sortColumn === column) {
                    this.topSqlData.sortDirection = this.topSqlData.sortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    this.topSqlData.sortColumn = column;
                    this.topSqlData.sortDirection = 'desc';
                }
                this._sortTopSqlData();
                this._updateTopSqlTable(container);
            });
        });

        // 行点击显示详情
        const rows = container.querySelectorAll('.top-sql-row');
        rows.forEach(row => {
            row.style.cursor = 'pointer';
            row.addEventListener('click', () => {
                const index = parseInt(row.dataset.sqlIndex);
                const sql = this.topSqlData.filteredData[index];
                this._showTopSqlDrawer(sql);
            });
        });
    },

    _updateTopSqlTable(container) {
        const { filteredData } = this.topSqlData;

        // 更新统计信息
        const statsDiv = container.querySelector('.top-sql-stats');
        if (statsDiv) {
            statsDiv.innerHTML = `<span class="badge badge-info">${I18n.t('instanceDetail.topSqlCount', { count: I18n.formatNumber(filteredData.length) })}</span>`;
        }

        // 更新表格内容
        const tbody = container.querySelector('.top-sql-table tbody');
        if (tbody) {
            tbody.innerHTML = filteredData.map((sql, index) => `
                <tr class="top-sql-row" data-sql-index="${index}">
                    <td>${index + 1}</td>
                    <td class="text-monospace" title="${this._escapeAttr(sql.sql_id || '-')}">${this._escapeHtml(this._truncate(sql.sql_id, 20))}</td>
                    <td class="sql-text-cell">
                        <div class="sql-text-wrapper" title="${this._escapeAttr(sql.sql_text || '-')}">
                            ${this._escapeHtml(sql.sql_text || '-')}
                        </div>
                    </td>
                    <td class="text-right">${Format.number(sql.exec_count || 0)}</td>
                    <td class="text-right">${Format.number(sql.total_time_sec || 0, 6)}</td>
                    <td class="text-right">${Format.number(sql.total_rows_scanned || 0)}</td>
                    <td class="text-right">${Format.number(sql.total_wait_time_sec || 0, 6)}</td>
                    <td class="text-right">${Format.number(sql.avg_time_sec || 0, 6)}</td>
                    <td class="text-right">${Format.number(sql.avg_rows_scanned || 0, 2)}</td>
                    <td class="text-right">${Format.number(sql.avg_wait_time_sec || 0, 6)}</td>
                    <td>${sql.last_exec_time ? Format.datetime(sql.last_exec_time) : '-'}</td>
                </tr>
            `).join('');

            // 重新绑定行点击事件
            const rows = tbody.querySelectorAll('.top-sql-row');
            rows.forEach(row => {
                row.style.cursor = 'pointer';
                row.addEventListener('click', () => {
                    const index = parseInt(row.dataset.sqlIndex);
                    const sql = this.topSqlData.filteredData[index];
                    this._showTopSqlDrawer(sql);
                });
            });
        }

        // 更新表头排序图标
        const headers = container.querySelectorAll('th[data-sort]');
        headers.forEach(th => {
            const column = th.dataset.sort;
            const iconHtml = this._getSortIcon(column);
            const label = th.dataset.label || th.textContent.replace(/\s+/g, ' ').trim();
            th.innerHTML = `${this._escapeHtml(label)} ${iconHtml}`;
        });

        DOM.createIcons();
    },

    _applyTopSqlFilter() {
        const { allData, filterText } = this.topSqlData;
        if (!filterText) {
            this.topSqlData.filteredData = [...allData];
        } else {
            this.topSqlData.filteredData = allData.filter(sql => {
                const sqlId = (sql.sql_id || '').toLowerCase();
                const sqlText = (sql.sql_text || '').toLowerCase();
                return sqlId.includes(filterText) || sqlText.includes(filterText);
            });
        }
        this._sortTopSqlData();
    },

    _sortTopSqlData() {
        const { filteredData, sortColumn, sortDirection } = this.topSqlData;
        filteredData.sort((a, b) => {
            let aVal = a[sortColumn];
            let bVal = b[sortColumn];

            // 处理 null/undefined
            if (aVal == null) aVal = sortDirection === 'asc' ? Infinity : -Infinity;
            if (bVal == null) bVal = sortDirection === 'asc' ? Infinity : -Infinity;

            // 字符串比较
            if (typeof aVal === 'string') {
                return sortDirection === 'asc'
                    ? aVal.localeCompare(bVal, I18n.getLocale())
                    : bVal.localeCompare(aVal, I18n.getLocale());
            }

            // 数值比较
            return sortDirection === 'asc' ? aVal - bVal : bVal - aVal;
        });
    },

    _showTopSqlDrawer(sql) {
        const drawer = document.getElementById('topSqlDrawer');
        if (!drawer) return;

        drawer.style.visibility = 'visible';
        drawer.innerHTML = `
            <div class="drawer-overlay"></div>
            <div class="drawer-content">
                <div class="drawer-header">
                    <h3>${I18n.t('pageCopy.instanceDetail.sqlDetails')}</h3>
                    <button class="btn-icon" id="closeTopSqlDrawer" title="${I18n.t('pageCopy.instanceDetail.close')}" aria-label="${I18n.t('pageCopy.instanceDetail.close')}">
                        <i data-lucide="x"></i>
                    </button>
                </div>
                <div class="drawer-body">
                    <div class="sql-detail-section">
                        <h4>${I18n.t('pageCopy.instanceDetail.sqlText2')}</h4>
                        <pre class="sql-code">${this._escapeHtml(sql.sql_text || '-')}</pre>
                    </div>
                    <div class="sql-detail-section">
                        <h4>${I18n.t('pageCopy.instanceDetail.executionStatistics')}</h4>
                        <div class="sql-stats-grid">
                            <div class="stat-item">
                                <label>SQL ID</label>
                                <span class="text-monospace">${this._escapeHtml(sql.sql_id || '-')}</span>
                            </div>
                            <div class="stat-item">
                                <label>${I18n.t('pageCopy.instanceDetail.executionCount')}</label>
                                <span>${Format.number(sql.exec_count || 0)}</span>
                            </div>
                            <div class="stat-item">
                                <label>${I18n.t('pageCopy.instanceDetail.totalExecutionTime')}</label>
                                <span>${Format.number(sql.total_time_sec || 0, 6)} ${I18n.t('pageCopy.instanceDetail.seconds')}</span>
                            </div>
                            <div class="stat-item">
                                <label>${I18n.t('pageCopy.instanceDetail.averageExecutionTime')}</label>
                                <span>${Format.number(sql.avg_time_sec || 0, 6)} ${I18n.t('pageCopy.instanceDetail.seconds')}</span>
                            </div>
                            <div class="stat-item">
                                <label>${I18n.t('pageCopy.instanceDetail.totalRowsScanned')}</label>
                                <span>${Format.number(sql.total_rows_scanned || 0)}</span>
                            </div>
                            <div class="stat-item">
                                <label>${I18n.t('pageCopy.instanceDetail.averageRowsScanned')}</label>
                                <span>${Format.number(sql.avg_rows_scanned || 0, 2)}</span>
                            </div>
                            <div class="stat-item">
                                <label>${I18n.t('pageCopy.instanceDetail.totalWaitingTime')}</label>
                                <span>${Format.number(sql.total_wait_time_sec || 0, 6)} ${I18n.t('pageCopy.instanceDetail.seconds')}</span>
                            </div>
                            <div class="stat-item">
                                <label>${I18n.t('pageCopy.instanceDetail.averageWaitingTime')}</label>
                                <span>${Format.number(sql.avg_wait_time_sec || 0, 6)} ${I18n.t('pageCopy.instanceDetail.seconds')}</span>
                            </div>
                            <div class="stat-item">
                                <label>${I18n.t('pageCopy.instanceDetail.lastRun')}</label>
                                <span>${sql.last_exec_time ? Format.datetime(sql.last_exec_time) : '-'}</span>
                            </div>
                        </div>
                    </div>
                    <div class="sql-detail-actions">
                        <button class="btn btn-secondary" id="viewExplainPlan">
                            <i data-lucide="git-branch"></i>
                            ${I18n.t('pageCopy.instanceDetail.viewExecutionPlan')}
                        </button>
                        <button class="btn btn-primary" id="aiDiagnoseTopSql">
                            <i data-lucide="sparkles"></i>
                            ${I18n.t('pageCopy.instanceDetail.aiDiagnosisAnalysis')}
                        </button>
                    </div>
                    <div id="explainPlanResult" class="sql-detail-section" style="display: none;">
                        <h4>${I18n.t('pageCopy.instanceDetail.executionPlan')}</h4>
                        <div id="explainPlanContent"></div>
                    </div>
                    <div id="aiDiagnosisResult" class="sql-detail-section" style="display: none;">
                        <h4>${I18n.t('pageCopy.instanceDetail.aiDiagnosisResults')}</h4>
                        <div id="aiDiagnosisContent"></div>
                    </div>
                </div>
            </div>
        `;

        drawer.classList.add('active');
        DOM.createIcons();

        // 关闭抽屉
        const closeBtn = drawer.querySelector('#closeTopSqlDrawer');
        const overlay = drawer.querySelector('.drawer-overlay');
        const closeDrawer = () => drawer.classList.remove('active');
        closeBtn?.addEventListener('click', closeDrawer);
        overlay?.addEventListener('click', closeDrawer);

        // 查看执行计划
        const explainBtn = drawer.querySelector('#viewExplainPlan');
        explainBtn?.addEventListener('click', () => this._viewExplainPlan(sql));

        // AI 诊断分析
        const aiBtn = drawer.querySelector('#aiDiagnoseTopSql');
        aiBtn?.addEventListener('click', () => this._aiDiagnoseTopSql(sql));
    },

    async _viewExplainPlan(sql) {
        const resultDiv = document.getElementById('explainPlanResult');
        const contentDiv = document.getElementById('explainPlanContent');
        if (!resultDiv || !contentDiv) return;

        resultDiv.style.display = 'block';
        contentDiv.innerHTML = `<div class="loading-spinner"><i data-lucide="loader"></i> ${I18n.t('pageCopy.instanceDetail.gettingExecutionPlan')}</div>`;
        DOM.createIcons();

        try {
            const response = await API.explainSql(this.topSqlData.datasourceId, sql.sql_text);

            if (response.explain_result) {
                const plan = response.explain_result;
                if (plan.format === 'json') {
                    contentDiv.innerHTML = `<pre class="explain-plan">${this._escapeHtml(JSON.stringify(plan.plan, null, 2))}</pre>`;
                } else if (plan.format === 'table') {
                    contentDiv.innerHTML = this._renderExplainTable(plan.plan);
                } else {
                    contentDiv.innerHTML = `<pre class="explain-plan">${this._escapeHtml(JSON.stringify(plan, null, 2))}</pre>`;
                }
            } else {
                contentDiv.innerHTML = `<div class="error-message">${I18n.t('pageCopy.instanceDetail.unableToObtainExecutionPlan')}</div>`;
            }
        } catch (error) {
            console.error('Failed to get explain plan:', error);
            contentDiv.innerHTML = `<div class="error-message">${this._escapeHtml(I18n.t('instanceDetail.explainFailed', { message: error.message }))}</div>`;
        }
    },

    _renderExplainTable(planRows) {
        if (!planRows || planRows.length === 0) {
            return `<div class="empty-state">${I18n.t('pageCopy.instanceDetail.noExecutionPlanData')}</div>`;
        }

        // 过滤掉不需要展示的字段
        const excludeColumns = ['OPERATOR_ID', 'PARENT_OPERATOR_ID', 'id', 'parent_id'];
        const allColumns = Object.keys(planRows[0]);
        const columns = allColumns.filter(col => !excludeColumns.includes(col));

        return `
            <div class="table-container">
                <table class="data-table explain-plan-table">
                    <thead>
                        <tr>
                            ${columns.map(col => `<th>${this._escapeHtml(col)}</th>`).join('')}
                        </tr>
                    </thead>
                    <tbody>
                        ${planRows.map(row => `
                            <tr>
                                ${columns.map(col => {
                                    const value = String(row[col] ?? '-');
                                    // OPERATOR_NAME (HANA) 或 operation (Oracle) 列使用 pre 标签保留空格
                                    if (col === 'OPERATOR_NAME' || col === 'operation') {
                                        return `<td class="operator-name-cell"><pre class="operator-name">${this._escapeHtml(value)}</pre></td>`;
                                    }
                                    return `<td>${this._escapeHtml(value)}</td>`;
                                }).join('')}
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    },

    async _aiDiagnoseTopSql(sql) {
        if (!sql) {
            Toast.warning(I18n.t('pageCopy.instanceDetail.sqlToParseNotFound'));
            return;
        }

        if (this.topSqlAiDialogCleanup) {
            try {
                this.topSqlAiDialogCleanup();
            } catch (error) {
                console.error('Previous TopSQL AI dialog cleanup failed:', error);
            }
            this.topSqlAiDialogCleanup = null;
        }

        const datasource = this.currentInstance;
        if (!datasource) {
            Toast.error(this._t(I18n.t('pageCopy.instanceDetail.unableToObtainDatasourceInformation')));
            return;
        }

        const content = DOM.el('div', { className: 'instance-topsql-ai-shell' });
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        let dialogCleanup = null;
        const sqlPreview = sql.sql_text?.substring(0, 50) || 'SQL';
        const title = I18n.t('instanceDetail.sqlAiTitle', {
            name: datasource.name || I18n.t('pageCopy.instanceDetail.instance'),
            sql: `${sqlPreview}${sql.sql_text?.length > 50 ? '...' : ''}`,
        });

        Modal.show({
            title,
            content,
            width: '1280px',
            maxHeight: '92vh',
            containerClassName: 'instance-topsql-ai-modal',
            bodyClassName: 'instance-topsql-ai-modal-body',
            onHide: () => {
                if (typeof dialogCleanup === 'function') {
                    try {
                        dialogCleanup();
                    } catch (error) {
                        console.error('TopSQL AI dialog cleanup failed:', error);
                    }
                }
                if (this.topSqlAiDialogCleanup === dialogCleanup) {
                    this.topSqlAiDialogCleanup = null;
                }
            }
        });

        try {
            dialogCleanup = await DiagnosisPage.renderWithOptions({
                container: content,
                embedded: true,
                hideEmbeddedTitle: true,
                compactEmbeddedToolbar: true,
                fixedDatasourceId: datasource.id,
                hideSessionSidebar: true,
                autoCreateSession: true,
                autoSendInitialAsk: true,
                hideInitialAskMessage: true,
                initialAsk: this._buildTopSqlDiagnosisPrompt(sql),
                initialSessionTitle: I18n.t('instanceDetail.sqlAnalysisTitle', {
                    name: datasource.name || datasource.id || '',
                    sql: sqlPreview,
                }).trim(),
                hideToolSafetyButton: true,
                hideClearSessionButton: true,
            });
            this.topSqlAiDialogCleanup = dialogCleanup;
        } catch (error) {
            content.innerHTML = `
                <div class="empty-state" style="padding:40px;">
                    <i data-lucide="alert-circle"></i>
                    <h3>${I18n.t('pageCopy.instanceDetail.sqlAiCouldNotOpenDiagnosis')}</h3>
                    <p>${this._escapeHtml(error.message || I18n.t('pageCopy.instanceDetail.unknownError'))}</p>
                </div>
            `;
            DOM.createIcons();
        }
    },

    _buildTopSqlDiagnosisPrompt(sql) {
        const datasource = this.currentInstance || {};
        const hostText = datasource.host
            ? `${datasource.host}:${datasource.port || '-'}`
            : '-';
        const versionText = datasource.db_version
            ? this._simplifyVersion(datasource.db_version, datasource.db_type).short
            : '-';
        const datasourceDatabaseText = this._formatSessionAnalysisValue(datasource.database);

        const sqlText = this._truncateSessionAnalysisBlock(sql.sql_text || '', 2400);

        const statsParts = [];
        if (sql.exec_count != null) statsParts.push(I18n.t('pageCopy.instanceDetail.executionCountValue', { value0: sql.exec_count }));
        if (sql.avg_time_sec != null) statsParts.push(I18n.t('pageCopy.instanceDetail.elapsedValue', { value0: sql.avg_time_sec }));
        if (sql.total_time_sec != null) statsParts.push(I18n.t('pageCopy.instanceDetail.elapsedValue2', { value0: sql.total_time_sec }));

        const scanParts = [];
        if (sql.avg_rows_scanned != null) scanParts.push(I18n.t('pageCopy.instanceDetail.averageRowsScannedValue', { value0: sql.avg_rows_scanned }));
        if (sql.total_rows_scanned != null) scanParts.push(I18n.t('pageCopy.instanceDetail.totalRowsScannedValue', { value0: sql.total_rows_scanned }));

        const waitParts = [];
        if (sql.total_wait_time_sec != null) waitParts.push(I18n.t('pageCopy.instanceDetail.totalWaitingTimeValue', { value0: sql.total_wait_time_sec }));

        return this._t([
            I18n.t('pageCopy.instanceDetail.asASeniorDatabaseOperationAndMaintenance2'),
            '',
            I18n.t('pageCopy.instanceDetail.analysisTarget'),
            I18n.t('pageCopy.instanceDetail.pleaseDetermineWhetherThereArePerformanceProblems'),
            '',
            I18n.t('pageCopy.instanceDetail.instanceInformation'),
            I18n.t('pageCopy.instanceDetail.instanceNameValue', { value0: this._formatSessionAnalysisValue(datasource.name) }),
            I18n.t('pageCopy.instanceDetail.databaseTypeValue', { value0: this._formatSessionAnalysisValue(this._getDbTypeLabel(datasource.db_type) || datasource.db_type) }),
            I18n.t('pageCopy.instanceDetail.hostValue', { value0: hostText }),
            I18n.t('pageCopy.instanceDetail.databaseValue', { value0: datasourceDatabaseText }),
            versionText !== '-' ? I18n.t('pageCopy.instanceDetail.versionValue', { value0: versionText }) : null,
            '',
            I18n.t('pageCopy.instanceDetail.sqlStatistics'),
            statsParts.length > 0 ? `- ${statsParts.join('，')}` : null,
            scanParts.length > 0 ? `- ${scanParts.join('，')}` : null,
            waitParts.length > 0 ? `- ${waitParts.join('，')}` : null,
            '',
            I18n.t('pageCopy.instanceDetail.sqlText'),
            sqlText,
            '',
            I18n.t('pageCopy.instanceDetail.outputRequirements'),
            I18n.t('pageCopy.instanceDetail.sqlAssessmentRequirement'),
            I18n.t('pageCopy.instanceDetail.sqlBottleneckRequirement'),
            I18n.t('pageCopy.instanceDetail.sqlRootCauseRequirement'),
            I18n.t('pageCopy.instanceDetail.sqlOptimizationRequirement'),
            I18n.t('pageCopy.instanceDetail.sqlMissingInfoRequirement'),
        ].filter(Boolean).join('\n'));
    },

    _formatAiResponse(text) {
        // 简单的 Markdown 格式化
        return this._escapeHtml(text)
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/\n/g, '<br>');
    },

    _truncate(text, maxLength) {
        if (!text) return '-';
        return text.length > maxLength ? text.substring(0, maxLength) + '...' : text;
    },

    _simplifyVersion(fullVersion, dbType) {
        if (!fullVersion) return { short: I18n.t('pageCopy.instanceDetail.unknownVersion'), full: '', details: '' };

        const patterns = {
            'postgresql': /PostgreSQL\s+([\d.]+)/i,
            'mysql': /([\d.]+)/,
            'oracle': /Oracle Database ([\d.]+)/i,
            'sqlserver': /Microsoft SQL Server\s+([\d.]+)/i,
            'opengauss': /openGauss\s+([\d.]+)/i,
            'hana': /HDB\s+([\d.]+)/i,
            'tdsql': /([\d.]+)/,
            'oceanbasemysql': /([\d.]+)/
        };

        const dbTypeNormalized = (dbType || '').toLowerCase().replace(/[_-]/g, '');
        const pattern = patterns[dbTypeNormalized];

        if (pattern) {
            const match = fullVersion.match(pattern);
            if (match) {
                const versionNum = match[1];
                const dbDisplayNames = {
                    'postgresql': 'PostgreSQL',
                    'mysql': 'MySQL',
                    'oracle': 'Oracle',
                    'sqlserver': 'SQL Server',
                    'opengauss': 'openGauss',
                    'hana': 'SAP HANA',
                    'tdsql': 'TDSQL-C',
                    'oceanbasemysql': 'OceanBase MySQL'
                };
                const displayName = dbDisplayNames[dbTypeNormalized] || dbType.toUpperCase();
                const short = `${displayName} ${versionNum}`;
                const details = fullVersion.substring(match.index + match[0].length).trim().replace(/^[,\s]+/, '');

                return { short, full: fullVersion, details };
            }
        }

        // 兜底：截断到50字符
        if (fullVersion.length > 50) {
            return {
                short: fullVersion.substring(0, 50) + '...',
                full: fullVersion,
                details: fullVersion.substring(50)
            };
        }

        return { short: fullVersion, full: fullVersion, details: '' };
    }
};
