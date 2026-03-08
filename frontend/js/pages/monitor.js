/* Real-time Monitor page */
const MonitorPage = {
    ws: null,
    chartIds: ['connections', 'qps', 'cache_hit', 'threads', 'network', 'latency'],
    osChartIds: ['cpu_usage', 'memory_usage', 'disk_usage', 'load_avg', 'disk_io', 'network_io'],

    render() {
        const conn = Store.get('currentConnection');

        // Connection selector
        const headerActions = DOM.el('div', { className: 'flex gap-8' });
        const connSelect = DOM.el('select', { className: 'form-select', style: { minWidth: '200px' } });
        connSelect.appendChild(DOM.el('option', { value: '', textContent: 'Select a connection...' }));
        const connections = Store.get('datasources') || [];
        for (const c of connections) {
            const opt = DOM.el('option', { value: c.id, textContent: `${c.name} (${c.db_type})` });
            if (conn && c.id === conn.id) opt.selected = true;
            connSelect.appendChild(opt);
        }
        connSelect.addEventListener('change', async () => {
            const id = parseInt(connSelect.value);
            if (id) {
                const conns = Store.get('datasources') || [];
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
            DOM.createIcons();
            return;
        }

        // Database Metric cards row
        const dbMetricsRow = DOM.el('div', { className: 'grid-4 mb-24', id: 'monitor-metrics' });
        dbMetricsRow.appendChild(MetricCard.create('Active Connections', '--'));
        dbMetricsRow.appendChild(MetricCard.create('QPS', '--'));
        dbMetricsRow.appendChild(MetricCard.create('Cache Hit Rate', '--'));
        dbMetricsRow.appendChild(MetricCard.create('Uptime', '--'));
        content.appendChild(dbMetricsRow);

        // OS Metric cards row
        const osMetricsRow = DOM.el('div', { className: 'grid-4 mb-24', id: 'os-metrics' });
        osMetricsRow.appendChild(MetricCard.create('CPU Usage', '--'));
        osMetricsRow.appendChild(MetricCard.create('Memory Usage', '--'));
        osMetricsRow.appendChild(MetricCard.create('Disk Usage', '--'));
        osMetricsRow.appendChild(MetricCard.create('Load Average', '--'));
        content.appendChild(osMetricsRow);

        // Database Charts section
        const dbSection = DOM.el('h3', { textContent: 'Database Metrics', className: 'mb-16' });
        content.appendChild(dbSection);

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

        // OS Charts section
        const osSection = DOM.el('h3', { textContent: 'Operating System Metrics', className: 'mb-16 mt-24' });
        content.appendChild(osSection);

        const osChartsGrid = DOM.el('div', { className: 'chart-grid', id: 'os-charts' });
        osChartsGrid.appendChild(ChartPanel.create('cpu_usage', 'CPU Usage (%)', 'line', {
            data: { datasets: [{ borderColor: '#f85149', backgroundColor: 'rgba(248,81,73,0.1)' }] }
        }));
        osChartsGrid.appendChild(ChartPanel.create('memory_usage', 'Memory Usage (%)', 'line', {
            data: { datasets: [{ borderColor: '#d29922', backgroundColor: 'rgba(210,153,34,0.1)' }] }
        }));
        osChartsGrid.appendChild(ChartPanel.create('disk_usage', 'Disk Usage (%)', 'line', {
            data: { datasets: [{ borderColor: '#a371f7', backgroundColor: 'rgba(163,113,247,0.1)' }] }
        }));
        osChartsGrid.appendChild(ChartPanel.create('load_avg', 'Load Average (1min)', 'line', {
            data: { datasets: [{ borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,0.1)' }] }
        }));
        osChartsGrid.appendChild(ChartPanel.create('disk_io', 'Disk I/O (ops/sec)'));
        osChartsGrid.appendChild(ChartPanel.create('network_io', 'Network I/O (KB/s)'));
        content.appendChild(osChartsGrid);

        // Init charts
        requestAnimationFrame(() => {
            for (const id of this.chartIds) {
                ChartPanel.init(id, 'line', id === 'cache_hit' ? {
                    data: { datasets: [{ borderColor: '#3fb950', backgroundColor: 'rgba(63,185,80,0.1)' }] },
                    options: { scales: { y: { max: 100 } } }
                } : {});
            }
            // Init OS charts
            for (const id of this.osChartIds) {
                const config = {};
                if (id === 'cpu_usage' || id === 'memory_usage' || id === 'disk_usage') {
                    config.options = { scales: { y: { max: 100, min: 0 } } };
                }
                if (id === 'cpu_usage') {
                    config.data = { datasets: [{ borderColor: '#f85149', backgroundColor: 'rgba(248,81,73,0.1)' }] };
                } else if (id === 'memory_usage') {
                    config.data = { datasets: [{ borderColor: '#d29922', backgroundColor: 'rgba(210,153,34,0.1)' }] };
                } else if (id === 'disk_usage') {
                    config.data = { datasets: [{ borderColor: '#a371f7', backgroundColor: 'rgba(163,113,247,0.1)' }] };
                } else if (id === 'load_avg') {
                    config.data = { datasets: [{ borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,0.1)' }] };
                }
                ChartPanel.init(id, 'line', config);
            }
        });

        // Load initial data and start WS
        if (conn) {
            this._loadHistory(conn.id);
            this._startMonitoring(conn.id);
        } else {
            // Auto-select first connection
            API.getDatasources().then(conns => {
                Store.set('datasources', conns);
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

        // Update OS metric cards
        const osCards = DOM.$$('#os-metrics .metric-card');
        if (osCards.length >= 4) {
            const cpuUsage = data.cpu_usage;
            const memUsage = data.memory_usage;
            const diskUsage = data.disk_usage;
            const loadAvg = data.load_avg_1min;

            MetricCard.update(osCards[0], cpuUsage !== undefined ? Format.percent(cpuUsage) : '--');
            MetricCard.update(osCards[1], memUsage !== undefined ? Format.percent(memUsage) : '--');
            MetricCard.update(osCards[2], diskUsage !== undefined ? Format.percent(diskUsage) : '--');
            MetricCard.update(osCards[3], loadAvg !== undefined ? loadAvg.toFixed(2) : '--');
        }
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

        // Update OS charts
        if (data.cpu_usage !== undefined) {
            ChartPanel.update('cpu_usage', time, parseFloat(data.cpu_usage) || 0);
        }
        if (data.memory_usage !== undefined) {
            ChartPanel.update('memory_usage', time, parseFloat(data.memory_usage) || 0);
        }
        if (data.disk_usage !== undefined) {
            ChartPanel.update('disk_usage', time, parseFloat(data.disk_usage) || 0);
        }
        if (data.load_avg_1min !== undefined) {
            ChartPanel.update('load_avg', time, parseFloat(data.load_avg_1min) || 0);
        }
        if (data.disk_reads_per_sec !== undefined || data.disk_writes_per_sec !== undefined) {
            const diskIO = (parseFloat(data.disk_reads_per_sec) || 0) + (parseFloat(data.disk_writes_per_sec) || 0);
            ChartPanel.update('disk_io', time, diskIO);
        }
        if (data.network_rx_bytes !== undefined || data.network_tx_bytes !== undefined) {
            // Convert bytes to KB/s (approximate rate)
            const networkIO = ((parseFloat(data.network_rx_bytes) || 0) + (parseFloat(data.network_tx_bytes) || 0)) / 1024;
            ChartPanel.update('network_io', time, networkIO);
        }
    },

    _cleanup() {
        if (this.ws) {
            this.ws.disconnect();
            this.ws = null;
        }
        ChartPanel.destroyAll();
    }
};
