/* Real-time Monitor page */
const MonitorPage = {
    ws: null,
    chartIds: ['connections', 'qps', 'cache_hit', 'threads', 'network', 'latency'],

    render() {
        const conn = Store.get('currentConnection');

        // Connection selector
        const headerActions = DOM.el('div', { className: 'flex gap-8' });
        const connSelect = DOM.el('select', { className: 'form-select', style: { minWidth: '200px' } });
        connSelect.appendChild(DOM.el('option', { value: '', textContent: 'Select a connection...' }));
        const connections = Store.get('connections') || [];
        for (const c of connections) {
            const opt = DOM.el('option', { value: c.id, textContent: `${c.name} (${c.db_type})` });
            if (conn && c.id === conn.id) opt.selected = true;
            connSelect.appendChild(opt);
        }
        connSelect.addEventListener('change', async () => {
            const id = parseInt(connSelect.value);
            if (id) {
                const conns = Store.get('connections') || [];
                const selected = conns.find(c => c.id === id);
                Store.set('currentConnection', selected);
                this._startMonitoring(id);
            }
        });
        headerActions.appendChild(connSelect);
        Header.render('Monitor', headerActions);

        const content = DOM.$('#page-content');
        content.innerHTML = '';

        if (!conn && connections.length === 0) {
            content.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="activity"></i>
                    <h3>No Connections</h3>
                    <p>Add a database connection first to start monitoring.</p>
                    <button class="btn btn-primary mt-16" onclick="Router.navigate('connections')">Add Connection</button>
                </div>
            `;
            lucide.createIcons();
            return;
        }

        // Metric cards row
        const metricsRow = DOM.el('div', { className: 'grid-4 mb-24', id: 'monitor-metrics' });
        metricsRow.appendChild(MetricCard.create('Active Connections', '--'));
        metricsRow.appendChild(MetricCard.create('QPS', '--'));
        metricsRow.appendChild(MetricCard.create('Cache Hit Rate', '--'));
        metricsRow.appendChild(MetricCard.create('Uptime', '--'));
        content.appendChild(metricsRow);

        // Charts grid
        const chartsGrid = DOM.el('div', { className: 'chart-grid', id: 'monitor-charts' });
        chartsGrid.appendChild(ChartPanel.create('connections', 'Active Connections'));
        chartsGrid.appendChild(ChartPanel.create('qps', 'Queries Per Second'));
        chartsGrid.appendChild(ChartPanel.create('cache_hit', 'Cache Hit Rate (%)', 'line', {
            data: { datasets: [{ borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,0.1)' }] }
        }));
        chartsGrid.appendChild(ChartPanel.create('threads', 'Active Threads'));
        chartsGrid.appendChild(ChartPanel.create('network', 'Network I/O'));
        chartsGrid.appendChild(ChartPanel.create('latency', 'Slow Queries'));
        content.appendChild(chartsGrid);

        // Init charts
        requestAnimationFrame(() => {
            for (const id of this.chartIds) {
                ChartPanel.init(id, 'line', id === 'cache_hit' ? {
                    data: { datasets: [{ borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,0.1)' }] },
                    options: { scales: { y: { max: 100 } } }
                } : {});
            }
        });

        // Load initial data and start WS
        if (conn) {
            this._loadHistory(conn.id);
            this._startMonitoring(conn.id);
        } else {
            // Auto-select first connection
            API.getConnections().then(conns => {
                Store.set('connections', conns);
                if (conns.length > 0) {
                    Store.set('currentConnection', conns[0]);
                    connSelect.value = conns[0].id;
                    this._loadHistory(conns[0].id);
                    this._startMonitoring(conns[0].id);
                }
            });
        }

        return () => this._cleanup();
    },

    async _loadHistory(connId) {
        try {
            const metrics = await API.getMetrics(connId, 'metric_type=db_status&limit=30');
            const reversed = [...metrics].reverse();
            for (const m of reversed) {
                const time = new Date(m.collected_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                this._updateCharts(m.data, time);
            }
        } catch (e) {
            // Ignore history load failures
        }
    },

    _startMonitoring(connId) {
        this._cleanup();
        this.ws = new WSManager(`/ws/monitor/${connId}`);
        this.ws.on('message', (data) => {
            if (data.type === 'heartbeat') return;
            if (data.type === 'db_status' && data.data) {
                const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                this._updateMetricCards(data.data);
                this._updateCharts(data.data, time);
            }
        });
        this.ws.connect();
    },

    _updateMetricCards(data) {
        const cards = DOM.$$('#monitor-metrics .metric-card');
        if (cards.length < 4) return;

        const active = data.connections_active || data.connected_clients || data.user_sessions || data.connections_current || 0;
        const qps = data.qps || data.ops_per_sec || data.batch_requests_sec || 0;
        const hitRate = data.buffer_pool_hit_rate || data.cache_hit_rate || data.hit_rate || 0;
        const uptime = data.uptime || data.uptime_in_seconds || 0;

        MetricCard.update(cards[0], active);
        MetricCard.update(cards[1], typeof qps === 'number' ? qps.toFixed(1) : qps);
        MetricCard.update(cards[2], Format.percent(hitRate));
        MetricCard.update(cards[3], Format.uptime(uptime));
    },

    _updateCharts(data, time) {
        const active = data.connections_active || data.connected_clients || data.user_sessions || data.connections_current || 0;
        const qps = data.qps || data.ops_per_sec || data.batch_requests_sec || 0;
        const hitRate = data.buffer_pool_hit_rate || data.cache_hit_rate || data.hit_rate || 100;
        const threads = data.threads_running || data.active_requests || data.connections_active || 0;
        const netIn = data.bytes_received || data.network_bytes_in || data.input_kbps || 0;
        const slow = data.slow_queries || data.deadlocks || 0;

        ChartPanel.update('connections', time, active);
        ChartPanel.update('qps', time, parseFloat(qps) || 0);
        ChartPanel.update('cache_hit', time, parseFloat(hitRate) || 0);
        ChartPanel.update('threads', time, threads);
        ChartPanel.update('network', time, netIn);
        ChartPanel.update('latency', time, slow);
    },

    _cleanup() {
        if (this.ws) {
            this.ws.disconnect();
            this.ws = null;
        }
        ChartPanel.destroyAll();
    }
};
