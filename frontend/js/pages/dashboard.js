/* Dashboard page */
const DashboardPage = {
    async render() {
        const content = DOM.$('#page-content');
        Header.render('Dashboard');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const connections = await API.getConnections();
            Store.set('connections', connections);
            content.innerHTML = '';

            if (connections.length === 0) {
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="database"></i>
                        <h3>No Connections</h3>
                        <p>Add a database connection to get started with monitoring and diagnostics.</p>
                        <button class="btn btn-primary mt-16" onclick="Router.navigate('connections')">
                            <i data-lucide="plus"></i> Add Connection
                        </button>
                    </div>
                `;
                lucide.createIcons();
                return;
            }

            // Summary cards
            const summary = DOM.el('div', { className: 'grid-4 mb-24' });
            summary.appendChild(MetricCard.create('Total Connections', connections.length));
            summary.appendChild(MetricCard.create('MySQL', connections.filter(c => c.db_type === 'mysql').length));
            summary.appendChild(MetricCard.create('PostgreSQL', connections.filter(c => c.db_type === 'postgresql').length));
            summary.appendChild(MetricCard.create('Other', connections.filter(c => !['mysql', 'postgresql'].includes(c.db_type)).length));
            content.appendChild(summary);

            // Connection cards grid
            const heading = DOM.el('h2', { textContent: 'Connections', style: { fontSize: '16px', marginBottom: '16px', color: 'var(--text-secondary)' } });
            content.appendChild(heading);

            const grid = DOM.el('div', { className: 'dashboard-grid' });
            for (const conn of connections) {
                const card = DOM.el('div', { className: 'dashboard-conn-card', onClick: () => {
                    Store.set('currentConnection', conn);
                    Router.navigate('monitor');
                }});
                card.innerHTML = `
                    <div class="flex-between">
                        <h3>${conn.name}</h3>
                        <span class="connection-card-type type-${conn.db_type}">${conn.db_type}</span>
                    </div>
                    <div class="type">${conn.host}:${conn.port}${conn.database ? ' / ' + conn.database : ''}</div>
                    <div class="metrics" id="dash-metrics-${conn.id}">
                        <div class="metric-item"><span class="metric-label">Status</span><span class="metric-val">--</span></div>
                        <div class="metric-item"><span class="metric-label">Connections</span><span class="metric-val">--</span></div>
                    </div>
                `;
                grid.appendChild(card);

                // Load latest metrics
                this._loadConnMetrics(conn.id);
            }
            content.appendChild(grid);
            lucide.createIcons();

        } catch (err) {
            content.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${err.message}</p></div>`;
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
                <div class="metric-item"><span class="metric-label">Status</span><span class="metric-val" style="color:var(--accent-green)">Online</span></div>
                <div class="metric-item"><span class="metric-label">Active</span><span class="metric-val">${active}</span></div>
            `;
        } catch (e) {
            // Leave as --
        }
    }
};
