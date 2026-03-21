/* Dashboard page */
const DashboardPage = {
    _timer: null,
    _datasources: [],
    _hosts: [],
    _healthStatuses: {},
    _filters: {
        health: '',
        dbType: '',
        hostId: '',
        search: ''
    },

    async render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        this._stopTimer();

        try {
            // Load datasources and hosts first
            const [datasources, hosts] = await Promise.all([
                API.getDatasources(),
                API.getHosts()
            ]);
            Store.set('datasources', datasources);
            this._datasources = datasources;
            this._hosts = hosts;

            // Now render header with search filters (after data is loaded)
            Header.render('资源大盘', this._buildHeaderActions());

            content.innerHTML = '';

            if (datasources.length === 0) {
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="database"></i>
                        <h3>暂无数据源</h3>
                        <p>添加数据库连接以开始监控和诊断</p>
                        <button class="btn btn-primary mt-16" onclick="Router.navigate('datasources')">
                            <i data-lucide="plus"></i> 添加数据源
                        </button>
                    </div>
                `;
                DOM.createIcons();
                return;
            }

            // Summary cards
            const summary = DOM.el('div', { className: 'grid-4 mb-24' });
            summary.appendChild(MetricCard.create('总数据源', datasources.length));
            summary.appendChild(MetricCard.create('MySQL', datasources.filter(c => c.db_type === 'mysql').length));
            summary.appendChild(MetricCard.create('PostgreSQL', datasources.filter(c => c.db_type === 'postgresql').length));
            summary.appendChild(MetricCard.create('其他', datasources.filter(c => !['mysql', 'postgresql'].includes(c.db_type)).length));
            content.appendChild(summary);

            // Connection cards grid
            const heading = DOM.el('h2', { textContent: '数据源列表', style: { fontSize: '16px', marginBottom: '16px', color: 'var(--text-secondary)' } });
            content.appendChild(heading);

            const grid = DOM.el('div', { className: 'dashboard-grid', id: 'dashboard-grid' });
            content.appendChild(grid);

            // Render filtered datasources
            this._renderDatasources();
            DOM.createIcons();

            // Load metrics immediately then start auto-refresh
            await this._refreshMetrics();
            this._startTimer();

        } catch (err) {
            content.innerHTML = `<div class="empty-state"><h3>错误</h3><p>${err.message}</p></div>`;
        }
    },

    _buildHeaderActions() {
        // Get unique db types
        const dbTypes = [...new Set(this._datasources.map(d => d.db_type))];

        // Create filters container
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters' });
        filtersContainer.innerHTML = `
            <select id="filter-health" class="filter-select">
                <option value="">全部</option>
                <option value="healthy">健康</option>
                <option value="warning">警告</option>
                <option value="critical">异常</option>
                <option value="unknown">未知</option>
            </select>
            <select id="filter-dbtype" class="filter-select">
                <option value="">全部</option>
                ${dbTypes.map(type => `<option value="${type}">${type}</option>`).join('')}
            </select>
            <select id="filter-host" class="filter-select">
                <option value="">全部</option>
                ${this._hosts.map(h => `<option value="${h.id}">${h.name}</option>`).join('')}
            </select>
            <input type="text" id="filter-search" class="filter-input" placeholder="数据源名称、主机名称、IP地址...">
            <button id="btn-search" class="btn btn-primary">
                <i data-lucide="search"></i> 检索
            </button>
        `;

        // Create refresh button
        const refreshBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            title: '手工刷新',
            id: 'btn-refresh'
        });
        refreshBtn.innerHTML = '<i data-lucide="refresh-cw"></i> 刷新';

        // Bind events after render
        setTimeout(() => {
            const btnSearch = DOM.$('#btn-search');
            const btnRefresh = DOM.$('#btn-refresh');
            const filterSearch = DOM.$('#filter-search');

            if (btnSearch) btnSearch.addEventListener('click', () => this._applyFilters());
            if (btnRefresh) btnRefresh.addEventListener('click', () => this._onManualRefresh(btnRefresh));
            if (filterSearch) {
                filterSearch.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') this._applyFilters();
                });
            }
            DOM.createIcons();
        }, 0);

        return [filtersContainer, refreshBtn];
    },

    async _onManualRefresh(btn) {
        btn.disabled = true;
        btn.innerHTML = '<i data-lucide="refresh-cw"></i> 刷新中...';
        DOM.createIcons();
        await this._refreshMetrics();
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="refresh-cw"></i> 刷新';
        DOM.createIcons();
    },

    _applyFilters() {
        this._filters.health = DOM.$('#filter-health').value;
        this._filters.dbType = DOM.$('#filter-dbtype').value;
        this._filters.hostId = DOM.$('#filter-host').value;
        this._filters.search = DOM.$('#filter-search').value.trim().toLowerCase();
        this._renderDatasources();
    },

    _filterDatasources() {
        return this._datasources.filter(conn => {
            // Health filter
            if (this._filters.health) {
                const healthStatus = this._healthStatuses[conn.id] || 'unknown';
                if (healthStatus !== this._filters.health) return false;
            }

            // DB type filter
            if (this._filters.dbType && conn.db_type !== this._filters.dbType) {
                return false;
            }

            // Host filter
            if (this._filters.hostId) {
                const hostIdNum = parseInt(this._filters.hostId);
                if (conn.host_id !== hostIdNum) return false;
            }

            // Search filter (fuzzy match on name, host, database, host name)
            if (this._filters.search) {
                const search = this._filters.search;
                const matchName = conn.name.toLowerCase().includes(search);
                const matchHost = conn.host.toLowerCase().includes(search);
                const matchDb = conn.database && conn.database.toLowerCase().includes(search);

                // Find host name if host_id exists
                let matchHostName = false;
                if (conn.host_id) {
                    const host = this._hosts.find(h => h.id === conn.host_id);
                    if (host) {
                        matchHostName = host.name.toLowerCase().includes(search) ||
                                       host.host.toLowerCase().includes(search);
                    }
                }

                if (!matchName && !matchHost && !matchDb && !matchHostName) {
                    return false;
                }
            }

            return true;
        });
    },

    _renderDatasources() {
        const grid = DOM.$('#dashboard-grid');
        if (!grid) return;

        const filtered = this._filterDatasources();
        grid.innerHTML = '';

        if (filtered.length === 0) {
            grid.innerHTML = '<div class="empty-state"><p>没有符合条件的数据源</p></div>';
            return;
        }

        for (const conn of filtered) {
            const card = DOM.el('div', { className: 'dashboard-conn-card', onClick: () => {
                Store.set('currentConnection', conn);
                Router.navigate('monitor');
            }});
            card.innerHTML = `
                <div class="flex-between">
                    <h3>${conn.name}</h3>
                    <span class="datasource-card-type type-${conn.db_type}">${conn.db_type}</span>
                </div>
                <div class="type">${conn.host}:${conn.port}${conn.database ? ' / ' + conn.database : ''}</div>
                <div class="metrics" id="dash-metrics-${conn.id}">
                    <div class="metric-item"><span class="metric-label">健康状态</span><span class="metric-val health-status" id="health-${conn.id}">--</span></div>
                    <div class="metric-item"><span class="metric-label">活跃连接</span><span class="metric-val">--</span></div>
                    <div class="metric-item"><span class="metric-label">CPU</span><span class="metric-val">--</span></div>
                    <div class="metric-item"><span class="metric-label">QPS</span><span class="metric-val">--</span></div>
                </div>
            `;
            grid.appendChild(card);
        }
        DOM.createIcons();
    },

    async _refreshMetrics() {
        const filtered = this._filterDatasources();
        const ids = filtered.map(c => c.id);
        await Promise.all(ids.map(id => this._loadConnMetrics(id)));
    },

    _startTimer() {
        this._stopTimer();
        this._timer = setInterval(() => this._refreshMetrics(), 15000);
    },

    _stopTimer() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    },

    async _loadConnMetrics(connId) {
        try {
            // Load health status
            const health = await API.getDatasourceHealth(connId);
            const healthEl = DOM.$(`#health-${connId}`);
            if (healthEl) {
                let statusText = '未知';
                let statusColor = 'var(--text-muted)';
                let statusIcon = '';
                let statusValue = 'unknown';

                if (health.status === 'healthy') {
                    statusText = '健康';
                    statusColor = 'var(--accent-green)';
                    statusIcon = '✓';
                    statusValue = 'healthy';
                } else if (health.status === 'critical') {
                    statusText = '异常';
                    statusColor = 'var(--accent-red)';
                    statusIcon = '✗';
                    statusValue = 'critical';
                } else if (health.status === 'warning') {
                    statusText = '警告';
                    statusColor = 'var(--accent-orange)';
                    statusIcon = '⚠';
                    statusValue = 'warning';
                } else {
                    statusText = health.message || '未知';
                    statusColor = 'var(--text-muted)';
                    statusValue = 'unknown';
                }

                // Store health status for filtering
                this._healthStatuses[connId] = statusValue;

                healthEl.innerHTML = `<span style="color:${statusColor}">${statusIcon} ${statusText}</span>`;
                healthEl.title = health.message || '';
            }

            // Load metrics
            const metric = await API.getLatestMetric(connId);
            const el = DOM.$(`#dash-metrics-${connId}`);
            if (!el || !metric) return;
            const data = metric.data || {};
            const active = data.connections_active || data.connected_clients || data.user_sessions || data.connections_current || 0;
            // Try cpu_usage first (database-level), fallback to os_cpu_usage (OS-level)
            const cpuValue = data.cpu_usage != null ? data.cpu_usage : data.os_cpu_usage;
            const cpu = cpuValue != null ? cpuValue.toFixed(1) + '%' : '--';
            const qps = data.qps != null ? data.qps.toFixed(1) : '--';

            // Get health status HTML
            const healthStatusHtml = healthEl ? healthEl.innerHTML : '<span style="color:var(--text-muted)">--</span>';

            el.innerHTML = `
                <div class="metric-item"><span class="metric-label">健康状态</span><span class="metric-val health-status" id="health-${connId}">${healthStatusHtml}</span></div>
                <div class="metric-item"><span class="metric-label">活跃连接</span><span class="metric-val">${active}</span></div>
                <div class="metric-item"><span class="metric-label">CPU</span><span class="metric-val">${cpu}</span></div>
                <div class="metric-item"><span class="metric-label">QPS</span><span class="metric-val">${qps}</span></div>
            `;
        } catch (e) {
            // Leave as --
        }
    }
};
