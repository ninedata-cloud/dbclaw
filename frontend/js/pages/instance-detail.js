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

    validTabs: ['config', 'monitor', 'traffic', 'sessions', 'ai', 'query', 'alerts', 'inspections', 'parameters'],

    async render(routeParam = '') {
        this._rememberInstanceListScroll();
        this.cleanup();
        this.currentRoute = this._parseRoute(routeParam);
        this.sidebarListScrollTop = this._loadInstanceListScrollState();

        Header.render('实例详情');
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
                        <h3>暂无实例</h3>
                        <p>请先创建数据源，然后再进入实例详情工作台。</p>
                        <button class="btn btn-primary mt-16" onclick="Router.navigate('datasources')">前往数据源管理</button>
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
                                <div class="instance-sidebar-title">实例列表</div>
                                <div class="instance-sidebar-subtitle">单实例诊断与优化工作台</div>
                            </div>
                            <button
                                id="instance-sidebar-toggle"
                                class="instance-sidebar-toggle"
                                type="button"
                                title="${this.sidebarCollapsed ? '展开实例列表' : '收起实例列表'}"
                                aria-label="${this.sidebarCollapsed ? '展开实例列表' : '收起实例列表'}"
                            >
                                <i data-lucide="${this.sidebarCollapsed ? 'panel-left-open' : 'panel-left-close'}"></i>
                            </button>
                        </div>
                        <div class="instance-sidebar-search">
                            <input id="instance-search-input" class="filter-input" type="text" placeholder="搜索名称 / 主机 / 数据库 / 标签">
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
                    <h3>实例详情加载失败</h3>
                    <p>${Utils.escapeHtml(error.message || '未知错误')}</p>
                </div>
            `;
            Header.render('实例详情');
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
            actionRun: params.get('action_run') || null,
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
            toggleButton.title = this.sidebarCollapsed ? '展开实例列表' : '收起实例列表';
            toggleButton.setAttribute('aria-label', this.sidebarCollapsed ? '展开实例列表' : '收起实例列表');
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
            action_run: this.currentRoute.actionRun,
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
            listEl.innerHTML = '<div class="instance-list-empty">没有匹配的实例</div>';
            return;
        }

        let activeButton = null;
        Array.from(grouped.entries())
            .sort(([, left], [, right]) => left.label.localeCompare(right.label))
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
            Header.render('实例详情');
            return;
        }
        const health = this.currentSummary?.health || {};
        const metaText = `${datasource.host}:${datasource.port}${datasource.database ? ` / ${datasource.database}` : ''}${datasource.db_version ? ` · ${datasource.db_version}` : ''}`;
        const headerInfo = DOM.el('div', {
            className: 'instance-page-header-info',
            innerHTML: `
                <div class="instance-page-header-line">
                    <span class="instance-page-header-name" title="${this._escapeAttr(datasource.name)}">${this._escapeHtml(datasource.name)}</span>
                    <span class="badge badge-info">${this._escapeHtml(this._getDbTypeLabel(datasource.db_type))}</span>
                    <span class="badge badge-${this._healthBadgeClass(health.status)}">${this._escapeHtml(this._healthStatusLabel(health))}</span>
                    <span class="instance-page-header-meta" title="${this._escapeAttr(metaText)}">${this._escapeHtml(metaText)}</span>
                </div>
            `
        });
        Header.render('实例详情', headerInfo);
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
            { id: 'config', label: '实例基本信息' },
            { id: 'monitor', label: '性能监控' },
            { id: 'traffic', label: '流量拓扑' },
            { id: 'sessions', label: '实时会话查看' },
            { id: 'ai', label: 'AI 对话诊断' },
            { id: 'query', label: 'SQL 查询' },
            { id: 'alerts', label: '告警管理' },
            { id: 'inspections', label: '巡检管理' },
            { id: 'parameters', label: '实例参数配置' },
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
                initialActionRunId: this.currentRoute.actionRun ? parseInt(this.currentRoute.actionRun, 10) : null,
                initialAsk: ask,
                preferFreshSession: Boolean(
                    ask ||
                    this.currentRoute.alert ||
                    this.currentRoute.event ||
                    this.currentRoute.report ||
                    this.currentRoute.actionRun
                ),
            });
            this.currentRoute.ask = null;
            this.currentRoute.alert = null;
            this.currentRoute.event = null;
            this.currentRoute.report = null;
            this.currentRoute.actionRun = null;
            return;
        }

        if (this.currentTab === 'query') {
            this.tabCleanup = await QueryPage.renderWithOptions({
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
        }
    },

    async _renderConfigTab(container, datasourceId) {
        const summary = this.currentSummary || {};
        const datasource = summary.datasource || this.currentInstance;
        const health = summary.health || {};
        const inspection = summary.inspection || {};
        const metricTime = summary.metric_collected_at ? Format.datetime(summary.metric_collected_at) : '暂无';
        const silenceText = datasource.silence_until ? `静默至 ${Format.datetime(datasource.silence_until)}` : '未静默';
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
                                    ${datasource.db_version ? ` · ${this._escapeHtml(datasource.db_version)}` : ''}
                                </div>
                            </div>
                            <div class="instance-summary-actions">
                                <button class="btn btn-secondary btn-sm" id="instance-test-btn"><i data-lucide="plug"></i> 测试连接</button>
                                <button class="btn btn-secondary btn-sm" id="instance-refresh-btn"><i data-lucide="refresh-cw"></i> 刷新指标</button>
                                <button class="btn btn-primary btn-sm" id="instance-trigger-inspection-btn"><i data-lucide="zap"></i> 触发巡检</button>
                                <button class="btn btn-${silenced ? 'danger' : 'secondary'} btn-sm" id="instance-silence-btn"><i data-lucide="${silenced ? 'bell-ring' : 'bell-off'}"></i> ${silenced ? '取消静默' : '告警静默'}</button>
                            </div>
                        </div>
                        <div class="instance-summary-grid">
                            ${this._summaryMetric('连接状态', this._connectionStatusLabel(datasource.connection_status), datasource.connection_error || health.message || '')}
                            ${this._summaryMetric('最近指标时间', metricTime, '')}
                            ${this._summaryMetric('当前告警事件', String(summary.active_alert_event_count || 0), '点击查看告警管理', 'alerts')}
                            ${this._summaryMetric('当前告警条数', String(summary.active_alert_count || 0), '')}
                            ${this._summaryMetric('下次巡检时间', inspection.next_scheduled_at ? Format.datetime(inspection.next_scheduled_at) : '未配置', '')}
                            ${this._summaryMetric('告警静默', silenceText, datasource.silence_reason || '')}
                        </div>
                    </div>
                </section>
                <div class="instance-config-grid">
                    <section class="instance-panel">
                        <h3>接入配置</h3>
                        <div id="instance-config-overview"></div>
                    </section>
                    <section class="instance-panel">
                        <h3>监控与巡检</h3>
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
                ${this._configField('名称', datasource.name)}
                ${this._configField('数据库类型', this._getDbTypeLabel(datasource.db_type))}
                ${this._configField('主机', `${datasource.host}:${datasource.port}`)}
                ${this._configField('数据库', datasource.database || '-')}
                ${this._configField('用户名', datasource.username || '-')}
                ${this._configField('主机关联', datasource.host_id ? `Host #${datasource.host_id}` : '未配置')}
                ${this._configField('重要级别', datasource.importance_level || 'production')}
                ${this._configField('标签', (datasource.tags || []).join(', ') || '-')}
                ${this._configField('备注', datasource.remark || '-')}
                ${this._configField('连接检测时间', datasource.connection_checked_at ? Format.datetime(datasource.connection_checked_at) : '暂无')}
            `;
        }

        if (monitoring) {
            monitoring.innerHTML = `
                ${this._configField('监控源', datasource.metric_source || 'system')}
                ${this._configField('监控间隔', `${datasource.monitoring_interval || 60} 秒`)}
                ${this._configField('外部实例 ID', datasource.external_instance_id || '-')}
                ${this._configField('启用巡检', inspectionConfig?.enabled ? '是' : '否')}
                ${this._configField('巡检周期', inspectionConfig?.schedule_interval ? `${inspectionConfig.schedule_interval} 秒` : '-')}
                ${this._configField('AI 分析', inspectionConfig?.use_ai_analysis === false ? '关闭' : '开启')}
                ${this._configField('下次巡检时间', inspectionConfig?.next_scheduled_at ? Format.datetime(inspectionConfig.next_scheduled_at) : '未配置')}
                ${this._configField('阈值规则', inspectionConfig?.threshold_rules ? `<pre class="instance-inline-pre">${this._escapeHtml(JSON.stringify(inspectionConfig.threshold_rules, null, 2))}</pre>` : '未配置', true)}
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
                    <input id="instance-config-search" class="filter-input" type="text" placeholder="搜索参数名 / 参数值 / 分类">
                </div>
                <section class="instance-panel">
                    <div class="instance-panel-header">
                        <h3>实例参数配置</h3>
                        <div class="instance-panel-subtitle">只读展示数据库实例当前参数</div>
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
            container.innerHTML = '<div class="empty-state">没有匹配的参数</div>';
            return;
        }

        container.innerHTML = `
            <div class="data-table-container instance-table-compact">
                <table class="data-table instance-variables-table">
                    <thead>
                        <tr>
                            <th class="sortable" data-sort-field="key">参数名 <span class="sort-icon">${this._sortIcon('key', this.configSort)}</span></th>
                            <th class="sortable" data-sort-field="category">分类 <span class="sort-icon">${this._sortIcon('category', this.configSort)}</span></th>
                            <th class="sortable" data-sort-field="value">参数值 <span class="sort-icon">${this._sortIcon('value', this.configSort)}</span></th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${sorted.map(item => `
                            <tr>
                                <td class="instance-mono">${this._escapeHtml(item.key)}</td>
                                <td><span class="badge badge-secondary">${this._escapeHtml(item.category || 'general')}</span></td>
                                <td class="instance-variable-value">${this._escapeHtml(item.value)}</td>
                                <td>
                                    <button class="btn btn-sm btn-secondary" data-copy-value="${this._escapeAttr(item.value)}">复制</button>
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
                    Toast.success('参数值已复制');
                } catch (error) {
                    Toast.error('复制失败');
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
                    <input id="instance-session-search" class="filter-input" type="text" placeholder="搜索 SQL / 客户端">
                    <input id="instance-session-user" class="filter-input" type="text" placeholder="筛选用户">
                    <select id="instance-session-status" class="filter-select">
                        <option value="all">全部状态</option>
                        <option value="active">活跃 / 执行中</option>
                        <option value="idle">空闲</option>
                        <option value="sleep">Sleep / sleeping</option>
                    </select>
                    <button class="btn btn-secondary" id="instance-session-refresh">刷新</button>
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
                    || (this.sessionFilters.status === 'active' && /(active|running|query|execute)/.test(status))
                    || (this.sessionFilters.status === 'idle' && /idle/.test(status))
                    || (this.sessionFilters.status === 'sleep' && /(sleep|sleeping)/.test(status));
                return matchesSearch && matchesUser && matchesStatus;
            });
            const sorted = [...filtered].sort((left, right) => this._compareSessions(left, right));

            if (meta) {
                meta.textContent = `共 ${sorted.length} 个会话，最后刷新于 ${new Date().toLocaleTimeString()}`;
            }

            if (sorted.length === 0) {
                tableContainer.innerHTML = '<div class="empty-state">当前没有匹配的会话</div>';
                return;
            }

            tableContainer.innerHTML = `
                <div class="data-table-container instance-table-compact">
                    <table class="data-table instance-sessions-table">
                        <thead>
                            <tr>
                                <th class="sortable" data-session-sort="session_id">会话 ID <span class="sort-icon">${this._sortIcon('session_id', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="user">用户 <span class="sort-icon">${this._sortIcon('user', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="database">数据库 <span class="sort-icon">${this._sortIcon('database', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="client">客户端 <span class="sort-icon">${this._sortIcon('client', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="status">状态 <span class="sort-icon">${this._sortIcon('status', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="duration_seconds">持续时间 <span class="sort-icon">${this._sortIcon('duration_seconds', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="wait_event">等待事件 <span class="sort-icon">${this._sortIcon('wait_event', this.sessionSort)}</span></th>
                                <th class="sortable" data-session-sort="sql_text">SQL <span class="sort-icon">${this._sortIcon('sql_text', this.sessionSort)}</span></th>
                                <th>操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${sorted.map(item => `
                                <tr>
                                    <td class="instance-mono">${this._escapeHtml(item.session_id)}</td>
                                    <td>${this._escapeHtml(item.user || '-')}</td>
                                    <td>${this._escapeHtml(item.database || '-')}</td>
                                    <td>${this._escapeHtml(item.client || '-')}</td>
                                    <td><span class="instance-session-status-badge status-${this._escapeHtml(this._sessionStatusTone(item.status))}">${this._escapeHtml(item.status || '-')}</span></td>
                                    <td>${item.duration_seconds != null ? this._escapeHtml(Format.uptime(item.duration_seconds)) : '-'}</td>
                                    <td>${this._escapeHtml(item.wait_event || '-')}</td>
                                    <td class="instance-variable-value">${this._escapeHtml((item.sql_text || '-').slice(0, 120))}</td>
                                    <td>
                                        <div class="instance-inline-actions instance-inline-actions-compact">
                                            <button class="btn-icon instance-action-icon" type="button" title="查看 SQL" aria-label="查看 SQL" data-view-sql="${this._escapeAttr(item.sql_text || '')}">
                                                <i data-lucide="file-text"></i>
                                            </button>
                                            <button class="btn-icon instance-action-icon" type="button" title="AI 分析" aria-label="AI 分析" data-analyze-session="${this._escapeAttr(item.session_id)}">
                                                <i data-lucide="sparkles"></i>
                                            </button>
                                            ${item.can_terminate ? `<button class="btn-icon instance-action-icon danger" type="button" title="终止会话" aria-label="终止会话" data-terminate-session="${this._escapeAttr(item.session_id)}"><i data-lucide="octagon-x"></i></button>` : ''}
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
                        title: '会话 SQL',
                        content: `<pre class="instance-inline-pre">${this._escapeHtml(button.dataset.viewSql || '无 SQL 文本')}</pre>`,
                        buttons: [{ text: '关闭', variant: 'secondary', onClick: () => Modal.hide() }]
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
            tableContainer.innerHTML = `<div class="empty-state">加载会话失败：${this._escapeHtml(error.message)}</div>`;
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
        const sqlText = this._truncateSessionAnalysisBlock(sqlSourceText, 3200) || '无 SQL 文本';
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
            ? `${durationSeconds} 秒（${Format.uptime(durationSeconds)}）`
            : '-';
        const hostText = datasource.host
            ? `${datasource.host}:${datasource.port || '-'}`
            : '-';
        const versionText = this._formatSessionAnalysisValue(datasource.db_version);
        const datasourceDatabaseText = this._formatSessionAnalysisValue(datasource.database);
        const sessionDatabaseText = this._formatSessionAnalysisValue(sessionDatabase);
        const sessionSummaryParts = [
            `会话 ID ${this._formatSessionAnalysisValue(sessionId)}`,
            `用户 ${this._formatSessionAnalysisValue(sessionUser)}`,
            `客户端 ${this._formatSessionAnalysisValue(sessionClient)}`,
        ];
        const sessionStateParts = [
            `状态 ${this._formatSessionAnalysisValue(sessionStatus)}`,
            `等待事件 ${this._formatSessionAnalysisValue(waitEvent)}`,
            `持续时间 ${durationText}`,
        ];

        return [
            '请你作为资深数据库运维专家，针对下面这个数据库实例中的实时会话做诊断分析，并支持后续多轮追问。',
            '',
            '【分析目标】',
            '请判断当前会话是否异常、风险等级如何，并给出下一步排查和处置建议。',
            '',
            '【实例信息】',
            `- 实例名称：${this._formatSessionAnalysisValue(datasource.name)}`,
            `- 数据库类型：${this._formatSessionAnalysisValue(this._getDbTypeLabel(datasource.db_type) || datasource.db_type)}`,
            `- 主机：${hostText}`,
            `- 数据库：${datasourceDatabaseText}`,
            versionText !== '-' ? `- 版本：${versionText}` : null,
            '',
            '【会话信息】',
            `- ${sessionSummaryParts.join('，')}`,
            sessionDatabaseText !== '-' && sessionDatabaseText !== datasourceDatabaseText
                ? `- 会话数据库：${sessionDatabaseText}`
                : null,
            `- ${sessionStateParts.join('，')}`,
            '',
            '【SQL 文本】',
            sqlText,
            extraRawText ? '' : null,
            extraRawText ? '【补充字段】' : null,
            extraRawText || null,
            '',
            '【输出要求】',
            '1. 当前会话状态与现象判断',
            '2. 主要风险点或异常信号',
            '3. 最可能的根因分析',
            '4. 建议的排查步骤和处置建议',
            '5. 如果信息不足，请明确指出下一步建议补充哪些信息',
        ].filter(Boolean).join('\n');
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
        return `${text.slice(0, maxLength).trimEnd()}\n...（已截断）`;
    },

    async _openSessionAiAnalysis(session) {
        if (!session) {
            Toast.warning('未找到要分析的会话');
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
        const title = `会话 AI 分析 · ${datasource.name || '实例'} · Session ${session.session_id || '-'}`;

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
                initialSessionTitle: `实例会话分析 ${datasource.name || datasource.id || ''} #${session.session_id || ''}`.trim(),
                hideToolSafetyButton: true,
                hideClearSessionButton: true,
            });
            this.sessionAiDialogCleanup = dialogCleanup;
        } catch (error) {
            content.innerHTML = `
                <div class="empty-state" style="padding:40px;">
                    <i data-lucide="alert-circle"></i>
                    <h3>会话 AI 分析打开失败</h3>
                    <p>${this._escapeHtml(error.message || '未知错误')}</p>
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
        return String(left).localeCompare(String(right), 'zh-CN', { numeric: true, sensitivity: 'base' });
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
            title: '终止会话',
            content: `确认终止会话 <strong>${this._escapeHtml(sessionId)}</strong> 吗？该操作会立即中断该会话。`,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: '确认终止',
                    variant: 'danger',
                    onClick: async () => {
                        try {
                            await API.terminateInstanceSession(datasourceId, sessionId);
                            Modal.hide();
                            Toast.success(`会话 ${sessionId} 已终止`);
                            await this._loadSessionsTable(datasourceId);
                        } catch (error) {
                            Toast.error(error.message || '终止会话失败');
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
                Toast.success(`连接成功 ${result.version ? `(${result.version})` : ''}`);
            } else {
                Toast.error(result.message || '连接失败');
            }
            await this._refreshSummary();
            if (this.currentTab === 'config') {
                await this._renderCurrentTab();
            }
        } catch (error) {
            Toast.error(`测试连接失败: ${error.message}`);
        }
    },

    async _handleRefreshMetrics() {
        try {
            await API.refreshMetrics(this.currentInstance.id);
            await new Promise(resolve => setTimeout(resolve, 1000));
            Toast.success('已触发指标刷新');
            await this._refreshSummary();
            if (this.currentTab === 'monitor' || this.currentTab === 'config') {
                await this._renderCurrentTab();
            }
        } catch (error) {
            Toast.error(`刷新指标失败: ${error.message}`);
        }
    },

    _showTriggerInspectionModal() {
        const datasource = this.currentSummary?.datasource || this.currentInstance || {};
        Modal.show({
            title: '确认触发巡检',
            content: `
                <div class="form-group" style="margin-bottom:0;">
                    <div style="font-size:14px;line-height:1.8;color:var(--text-primary);">
                        将为实例 <strong>${this._escapeHtml(datasource.name || '-')}</strong> 立即创建一个人工巡检任务。
                    </div>
                    <div style="margin-top:10px;font-size:12px;line-height:1.7;color:var(--text-secondary);">
                        巡检会立刻执行，并生成一份新的巡检报告。完成后会自动跳转到“巡检管理”查看结果。
                    </div>
                </div>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: '确认触发',
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
            Toast.error('当前实例不存在，无法触发巡检');
            return;
        }

        const confirmButton = Array.from(document.querySelectorAll('#modal-container .modal-footer .btn'))
            .find((button) => button.textContent?.includes('确认触发'));
        if (confirmButton) {
            confirmButton.disabled = true;
            confirmButton.textContent = '启动中...';
        }

        try {
            const result = await API.post(`/api/inspections/trigger/${datasourceId}`);
            Modal.hide();
            Toast.success(`人工巡检任务已提交${result?.trigger_id ? ` #${result.trigger_id}` : ''}`);
            await this._refreshSummary();
            const nextUrl = this._buildUrl(datasourceId, 'inspections', {
                report: result?.report_id || null,
            });
            Router.navigate(nextUrl);
        } catch (error) {
            if (confirmButton) {
                confirmButton.disabled = false;
                confirmButton.textContent = '确认触发';
            }
            Toast.error(`触发巡检失败: ${error.message}`);
        }
    },

    _showSilenceModal() {
        Modal.show({
            title: '设置告警静默',
            content: `
                <div class="form-group">
                    <label for="instance-silence-hours">静默时长（小时）</label>
                    <input id="instance-silence-hours" class="form-input" type="number" min="0.5" max="240" step="0.5" value="1">
                </div>
                <div class="form-group">
                    <label for="instance-silence-reason">静默原因</label>
                    <textarea id="instance-silence-reason" class="form-input" rows="3" placeholder="例如：计划变更窗口"></textarea>
                </div>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: '开始静默',
                    variant: 'primary',
                    onClick: async () => {
                        const hours = parseFloat(DOM.$('#instance-silence-hours')?.value || '0');
                        const reason = DOM.$('#instance-silence-reason')?.value?.trim() || null;
                        if (!Number.isFinite(hours) || hours < 0.5 || hours > 240) {
                            Toast.error('静默时长必须在 0.5 到 240 小时之间');
                            return;
                        }
                        try {
                            await API.setDatasourceSilence(this.currentInstance.id, { hours, reason });
                            Modal.hide();
                            Toast.success('已设置告警静默');
                            await this._refreshSummary();
                            if (this.currentTab === 'config') {
                                await this._renderCurrentTab();
                            }
                        } catch (error) {
                            Toast.error(`设置静默失败: ${error.message}`);
                        }
                    }
                }
            ]
        });
    },

    async _handleCancelSilence() {
        try {
            await API.cancelDatasourceSilence(this.currentInstance.id);
            Toast.success('已取消告警静默');
            await this._refreshSummary();
            if (this.currentTab === 'config') {
                await this._renderCurrentTab();
            }
        } catch (error) {
            Toast.error(`取消静默失败: ${error.message}`);
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
        return String(health.message || '').includes('连接失败');
    },

    _healthStatusLabel(health) {
        if (this._isConnectionFailureHealth(health)) return '连接失败';
        const map = {
            healthy: '健康',
            warning: '警告',
            critical: '异常',
            unknown: '未知'
        };
        return map[health?.status] || '未知';
    },

    _connectionStatusLabel(status) {
        const map = {
            normal: '正常',
            warning: '警告',
            failed: '连接失败',
            unknown: '未知'
        };
        return map[status] || status || '未知';
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
            mongodb: 'MongoDB',
            redis: 'Redis',
            sqlserver: 'SQL Server',
            oracle: 'Oracle',
            tidb: 'TiDB',
            'tdsql-c-mysql': 'TDSQL-C MySQL',
            oceanbase: 'OceanBase',
            oceanbase_mysql: 'OceanBase MySQL',
            opengauss: 'openGauss',
            dm: 'DM',
        };
        return labels[dbType] || dbType || '-';
    },

    _escapeHtml(value) {
        return Utils.escapeHtml(String(value ?? ''));
    },

    _escapeAttr(value) {
        return this._escapeHtml(value).replace(/"/g, '&quot;');
    }
};
