/* Dashboard page */
const DashboardPage = {
    async render() {
        const content = DOM.$('#page-content');
        Header.render('资源大盘');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const datasources = await API.getDatasources();
            Store.set('datasources', datasources);
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
                        <div class="metric-item"><span class="metric-label">状态</span><span class="metric-val">--</span></div>
                        <div class="metric-item"><span class="metric-label">连接数</span><span class="metric-val">--</span></div>
                    </div>
                `;
                grid.appendChild(card);

                // Load latest metrics
                this._loadConnMetrics(conn.id);
            }
            content.appendChild(grid);
            DOM.createIcons();

        } catch (err) {
            content.innerHTML = `<div class="empty-state"><h3>错误</h3><p>${err.message}</p></div>`;
        }
    },

    async _loadConnMetrics(connId) {
        try {
            const metric = await API.getLatestMetric(connId);
            const el = DOM.$(`#dash-metrics-${connId}`);
            if (!el || !metric) return;
            const data = metric.data || {};
            const active = data.connections_active || data.connected_clients || data.user_sessions || data.connections_current || 0;
            el.innerHTML = `
                <div class="metric-item"><span class="metric-label">状态</span><span class="metric-val" style="color:var(--accent-green)">在线</span></div>
                <div class="metric-item"><span class="metric-label">活跃连接</span><span class="metric-val">${active}</span></div>
            `;
        } catch (e) {
            // Leave as --
        }
    }
};
