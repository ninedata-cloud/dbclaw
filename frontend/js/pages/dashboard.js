/* Dashboard page */
const DashboardPage = {
    _timer: null,
    _datasources: [],

    async render() {
        const content = DOM.$('#page-content');
        Header.render('资源大盘', this._buildHeaderActions());
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        this._stopTimer();

        try {
            const datasources = await API.getDatasources();
            Store.set('datasources', datasources);
            this._datasources = datasources;
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

            const grid = DOM.el('div', { className: 'dashboard-grid' });
            for (const conn of datasources) {
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
            content.appendChild(grid);
            DOM.createIcons();

            // Load metrics immediately then start auto-refresh
            await this._refreshMetrics();
            this._startTimer();

        } catch (err) {
            content.innerHTML = `<div class="empty-state"><h3>错误</h3><p>${err.message}</p></div>`;
        }
    },

    _buildHeaderActions() {
        const btn = DOM.el('button', {
            className: 'btn btn-secondary',
            title: '手工刷新',
            onClick: () => this._onManualRefresh(btn)
        });
        btn.innerHTML = '<i data-lucide="refresh-cw"></i> 刷新';
        return btn;
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

    async _refreshMetrics() {
        const ids = this._datasources.map(c => c.id);
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

                if (health.status === 'healthy') {
                    statusText = '健康';
                    statusColor = 'var(--accent-green)';
                    statusIcon = '✓';
                } else if (health.status === 'critical') {
                    statusText = '异常';
                    statusColor = 'var(--accent-red)';
                    statusIcon = '✗';
                } else if (health.status === 'warning') {
                    statusText = '警告';
                    statusColor = 'var(--accent-orange)';
                    statusIcon = '⚠';
                } else {
                    statusText = health.message || '未知';
                    statusColor = 'var(--text-muted)';
                }

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
