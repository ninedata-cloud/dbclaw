/* Real-time Monitor page */
const MonitorPage = {
    ws: null,
    chartIds: ['connections', 'qps', 'cache_hit', 'tps', 'network', 'latency'],
    osChartIds: ['cpu_usage', 'memory_usage', 'disk_usage', 'load_avg', 'disk_io', 'network_io'],
    // Track previous network bytes for rate calculation
    prevNetworkRx: null,
    prevNetworkTx: null,
    prevNetworkTime: null,
    // Time range state
    currentTimeRange: 60, // default 1 hour in minutes
    isRealtime: true,

    render() {
        const conn = Store.get('currentConnection');

        // Header with connection selector and time range selector
        const headerActions = DOM.el('div', { className: 'flex gap-8' });

        // Connection selector
        const connSelect = DOM.el('select', { className: 'form-select', style: { minWidth: '200px' } });
        connSelect.appendChild(DOM.el('option', { value: '', textContent: '选择数据源...' }));
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
                this._reloadData(id);
            }
        });
        headerActions.appendChild(connSelect);

        // Time range selector
        const timeRangeSelect = DOM.el('select', {
            className: 'form-select',
            style: { minWidth: '150px' },
            id: 'time-range-select'
        });
        const timeRanges = [
            { value: 1, label: '最近 1 分钟' },
            { value: 10, label: '最近 10 分钟' },
            { value: 60, label: '最近 1 小时' },
            { value: 360, label: '最近 6 小时' },
            { value: 1440, label: '最近 1 天' },
            { value: 10080, label: '最近 7 天' },
            { value: 43200, label: '最近 1 个月' },
            { value: 'custom', label: '自定义时间' }
        ];
        for (const range of timeRanges) {
            const opt = DOM.el('option', {
                value: range.value,
                textContent: range.label
            });
            if (range.value === this.currentTimeRange) opt.selected = true;
            timeRangeSelect.appendChild(opt);
        }
        timeRangeSelect.addEventListener('change', () => {
            const value = timeRangeSelect.value;
            if (value === 'custom') {
                this._showCustomTimeDialog();
            } else {
                this.currentTimeRange = parseInt(value);
                this.isRealtime = true;
                if (conn) {
                    this._reloadData(conn.id);
                }
            }
        });
        headerActions.appendChild(timeRangeSelect);

        // Realtime toggle button
        const realtimeBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            id: 'realtime-toggle',
            textContent: '实时监控'
        });
        realtimeBtn.addEventListener('click', () => {
            this.isRealtime = !this.isRealtime;
            realtimeBtn.textContent = this.isRealtime ? '实时监控' : '暂停实时';
            realtimeBtn.className = this.isRealtime ? 'btn btn-secondary' : 'btn btn-outline';
            if (this.isRealtime && conn) {
                this._startMonitoring(conn.id);
            } else {
                this._stopMonitoring();
            }
        });
        headerActions.appendChild(realtimeBtn);

        Header.render('性能监控', headerActions);

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
        dbMetricsRow.appendChild(MetricCard.create('活跃连接', '--'));
        dbMetricsRow.appendChild(MetricCard.create('QPS', '--'));
        dbMetricsRow.appendChild(MetricCard.create('缓存命中率', '--'));
        dbMetricsRow.appendChild(MetricCard.create('运行时间', '--'));
        content.appendChild(dbMetricsRow);

        // OS Metric cards row
        const osMetricsRow = DOM.el('div', { className: 'grid-4 mb-24', id: 'os-metrics' });
        osMetricsRow.appendChild(MetricCard.create('CPU 使用率', '--'));
        osMetricsRow.appendChild(MetricCard.create('内存使用率', '--'));
        osMetricsRow.appendChild(MetricCard.create('磁盘使用率', '--'));
        osMetricsRow.appendChild(MetricCard.create('负载平均', '--'));
        content.appendChild(osMetricsRow);

        // Database Charts section
        const dbSection = DOM.el('h3', { textContent: '数据库指标', className: 'mb-16' });
        content.appendChild(dbSection);

        const chartsGrid = DOM.el('div', { className: 'chart-grid', id: 'monitor-charts' });
        chartsGrid.appendChild(ChartPanel.create('connections', '活跃连接'));
        chartsGrid.appendChild(ChartPanel.create('qps', '每秒查询数'));
        chartsGrid.appendChild(ChartPanel.create('cache_hit', '缓存命中率 (%)'));
        chartsGrid.appendChild(ChartPanel.create('tps', '每秒事务数'));
        chartsGrid.appendChild(ChartPanel.create('network', '网络 I/O'));
        chartsGrid.appendChild(ChartPanel.create('latency', '慢查询'));
        content.appendChild(chartsGrid);

        // OS Charts section
        const osSection = DOM.el('h3', { textContent: '操作系统指标', className: 'mb-16 mt-24' });
        content.appendChild(osSection);

        const osChartsGrid = DOM.el('div', { className: 'chart-grid', id: 'os-charts' });
        osChartsGrid.appendChild(ChartPanel.create('cpu_usage', 'CPU 使用率 (%)'));
        osChartsGrid.appendChild(ChartPanel.create('memory_usage', '内存使用率 (%)'));
        osChartsGrid.appendChild(ChartPanel.create('disk_usage', '磁盘使用率 (%)'));
        osChartsGrid.appendChild(ChartPanel.create('load_avg', '负载平均 (1分钟)'));
        osChartsGrid.appendChild(ChartPanel.create('disk_io', '磁盘 I/O (读/写 操作/秒)'));
        osChartsGrid.appendChild(ChartPanel.create('network_io', '网络 I/O (接收/发送 KB/s)'));
        content.appendChild(osChartsGrid);

        // Init charts after DOM is ready - use requestAnimationFrame to ensure canvas elements are rendered
        requestAnimationFrame(() => {
            console.log('[Monitor] Starting chart initialization');
            let successCount = 0;
            let failCount = 0;

            // Init all charts with unified blue style
            for (const id of this.chartIds) {
                const config = {};
                // Set max to 100 for percentage charts
                if (id === 'cache_hit') {
                    config.options = { scales: { y: { max: 100, min: 0 } } };
                }
                const chart = ChartPanel.init(id, 'line', config);
                if (chart) {
                    successCount++;
                } else {
                    failCount++;
                    console.error(`[Monitor] Failed to initialize chart: ${id}`);
                }
            }

            // Init OS charts with unified blue style
            for (const id of this.osChartIds) {
                const config = {};
                // Set max to 100 for percentage charts
                if (id === 'cpu_usage' || id === 'memory_usage' || id === 'disk_usage') {
                    config.options = { scales: { y: { max: 100, min: 0 } } };
                }
                // Multi-line charts keep their dual colors for clarity
                if (id === 'disk_io') {
                    config.data = {
                        datasets: [
                            { label: '读', borderColor: '#2f81f7', backgroundColor: 'rgba(47,129,247,0.1)', borderWidth: 1, data: [] },
                            { label: '写', borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,0.1)', borderWidth: 1, data: [] }
                        ]
                    };
                    config.options = {
                        plugins: {
                            legend: { display: true, position: 'top', labels: { color: '#e6edf3', font: { size: 11 } } }
                        }
                    };
                } else if (id === 'network_io') {
                    config.data = {
                        datasets: [
                            { label: '接收', borderColor: '#2f81f7', backgroundColor: 'rgba(47,129,247,0.1)', borderWidth: 1, data: [] },
                            { label: '发送', borderColor: '#58a6ff', backgroundColor: 'rgba(88,166,255,0.1)', borderWidth: 1, data: [] }
                        ]
                    };
                    config.options = {
                        plugins: {
                            legend: { display: true, position: 'top', labels: { color: '#e6edf3', font: { size: 11 } } }
                        }
                    };
                }
                const chart = ChartPanel.init(id, 'line', config);
                if (chart) {
                    successCount++;
                } else {
                    failCount++;
                    console.error(`[Monitor] Failed to initialize chart: ${id}`);
                }
            }

            console.log(`[Monitor] Chart initialization complete: ${successCount} success, ${failCount} failed`);

            // Load initial data and start WS AFTER charts are initialized
            if (conn) {
                // Load latest data first for immediate display, then load history
                this._loadLatestData(conn.id).then(() => {
                    this._loadHistory(conn.id);
                });
                if (this.isRealtime) {
                    this._startMonitoring(conn.id);
                }
            } else {
                // Auto-select first connection
                API.getDatasources().then(conns => {
                    Store.set('datasources', conns);
                    if (conns.length > 0) {
                        Store.set('currentConnection', conns[0]);
                        connSelect.value = conns[0].id;
                        this._loadLatestData(conns[0].id).then(() => {
                            this._loadHistory(conns[0].id);
                        });
                        if (this.isRealtime) {
                            this._startMonitoring(conns[0].id);
                        }
                    }
                });
            }
        });

        return () => this._cleanup();
    },

    _reloadData(connId) {
        // Stop WebSocket if running
        this._stopMonitoring();

        // Clear charts
        for (const id of [...this.chartIds, ...this.osChartIds]) {
            ChartPanel.clear(id);
        }

        // Reset network tracking
        this.prevNetworkRx = null;
        this.prevNetworkTx = null;
        this.prevNetworkTime = null;

        // Load new data
        this._loadLatestData(connId).then(() => {
            this._loadHistory(connId);
        });

        // Start monitoring if realtime is enabled
        if (this.isRealtime) {
            this._startMonitoring(connId);
        }
    },

    _showCustomTimeDialog() {
        const dialog = DOM.el('div', { className: 'modal-overlay' });
        const modal = DOM.el('div', { className: 'modal', style: { maxWidth: '500px' } });

        const header = DOM.el('div', { className: 'modal-header' });
        header.appendChild(DOM.el('h3', { textContent: '自定义时间范围' }));
        const closeBtn = DOM.el('button', { className: 'btn-icon', innerHTML: '<i data-lucide="x"></i>' });
        closeBtn.addEventListener('click', () => {
            document.body.removeChild(dialog);
            // Reset select to current range
            DOM.$('#time-range-select').value = this.currentTimeRange;
        });
        header.appendChild(closeBtn);
        modal.appendChild(header);

        const body = DOM.el('div', { className: 'modal-body' });

        // Start time
        const startGroup = DOM.el('div', { className: 'form-group' });
        startGroup.appendChild(DOM.el('label', { textContent: '开始时间' }));
        const startInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'form-input',
            id: 'custom-start-time'
        });
        startGroup.appendChild(startInput);
        body.appendChild(startGroup);

        // End time
        const endGroup = DOM.el('div', { className: 'form-group' });
        endGroup.appendChild(DOM.el('label', { textContent: '结束时间' }));
        const endInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'form-input',
            id: 'custom-end-time',
            value: new Date().toISOString().slice(0, 16)
        });
        endGroup.appendChild(endInput);
        body.appendChild(endGroup);

        modal.appendChild(body);

        const footer = DOM.el('div', { className: 'modal-footer' });
        const cancelBtn = DOM.el('button', { className: 'btn btn-secondary', textContent: '取消' });
        cancelBtn.addEventListener('click', () => {
            document.body.removeChild(dialog);
            DOM.$('#time-range-select').value = this.currentTimeRange;
        });
        const confirmBtn = DOM.el('button', { className: 'btn btn-primary', textContent: '确定' });
        confirmBtn.addEventListener('click', () => {
            const start = startInput.value;
            const end = endInput.value;
            if (!start || !end) {
                alert('请选择开始和结束时间');
                return;
            }
            if (new Date(start) >= new Date(end)) {
                alert('开始时间必须早于结束时间');
                return;
            }
            document.body.removeChild(dialog);
            this.isRealtime = false;
            this._loadCustomRange(Store.get('currentConnection').id, start, end);
            DOM.$('#realtime-toggle').textContent = '暂停实时';
            DOM.$('#realtime-toggle').className = 'btn btn-outline';
        });
        footer.appendChild(cancelBtn);
        footer.appendChild(confirmBtn);
        modal.appendChild(footer);

        dialog.appendChild(modal);
        document.body.appendChild(dialog);
        DOM.createIcons();
    },

    async _loadCustomRange(connId, startTime, endTime) {
        try {
            console.log('[Monitor] Loading custom range:', startTime, 'to', endTime);

            // Convert to ISO format for API
            const start = new Date(startTime).toISOString();
            const end = new Date(endTime).toISOString();

            const metrics = await API.getMetrics(
                connId,
                `metric_type=db_status&start_time=${encodeURIComponent(start)}&end_time=${encodeURIComponent(end)}&limit=10000`
            );

            console.log('[Monitor] Loaded custom range metrics:', metrics.length, 'records');

            if (metrics.length === 0) {
                alert('所选时间范围内没有数据');
                return;
            }

            // Clear charts
            for (const id of [...this.chartIds, ...this.osChartIds]) {
                ChartPanel.clear(id);
            }

            // Reset network tracking
            this.prevNetworkRx = null;
            this.prevNetworkTx = null;
            this.prevNetworkTime = null;

            const reversed = [...metrics].reverse();

            // Update latest metric card
            if (metrics.length > 0) {
                this._updateMetricCards(metrics[0].data);
            }

            // Batch populate charts
            this._batchUpdateCharts(reversed);
        } catch (e) {
            console.error('[Monitor] Failed to load custom range:', e);
            alert('加载数据失败: ' + e.message);
        }
    },

    async _loadLatestData(connId) {
        try {
            console.log('[Monitor] Loading latest data for connection:', connId);
            const latest = await API.getLatestMetric(connId, 'db_status');
            if (latest && latest.data) {
                console.log('[Monitor] Latest metric data:', latest.data);
                this._updateMetricCards(latest.data);
            }
        } catch (e) {
            console.error('[Monitor] Failed to load latest data:', e);
        }
    },

    async _loadHistory(connId) {
        try {
            console.log('[Monitor] Loading history for connection:', connId, 'range:', this.currentTimeRange, 'minutes');
            const metrics = await API.getMetrics(connId, `metric_type=db_status&minutes=${this.currentTimeRange}&limit=10000`);
            console.log('[Monitor] Loaded metrics:', metrics.length, 'records');
            if (metrics.length === 0) {
                console.warn('[Monitor] No metrics found');
                return;
            }

            const reversed = [...metrics].reverse();

            // Reset network tracking for history load
            this.prevNetworkRx = null;
            this.prevNetworkTx = null;
            this.prevNetworkTime = null;

            // Batch populate charts with historical data for better performance
            this._batchUpdateCharts(reversed);
            console.log('[Monitor] History loaded successfully');
        } catch (e) {
            console.error('[Monitor] Failed to load history:', e);
        }
    },

    _startMonitoring(connId) {
        // Stop existing WebSocket if any
        this._stopMonitoring();

        console.log('[Monitor] Starting WebSocket monitoring for connection:', connId);
        this.ws = new WSManager(`/ws/monitor/${connId}`);
        this.ws.on('open', () => {
            console.log('[Monitor] WebSocket connected');
        });
        this.ws.on('error', (error) => {
            console.error('[Monitor] WebSocket error:', error);
        });
        this.ws.on('close', (event) => {
            console.log('[Monitor] WebSocket closed:', event);
        });
        this.ws.on('message', (data) => {
            if (data.type === 'heartbeat') {
                console.log('[Monitor] Heartbeat received');
                return;
            }
            if (data.type === 'db_status' && data.data) {
                console.log('[Monitor] Received metric data:', data.data);
                const now = Date.now();
                const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
                this._updateMetricCards(data.data);
                this._updateCharts(data.data, time, now);
            }
        });
        this.ws.connect();
    },

    _stopMonitoring() {
        if (this.ws) {
            this.ws.disconnect();
            this.ws = null;
        }
    },

    _updateMetricCards(data) {
        const cards = DOM.$$('#monitor-metrics .metric-card');
        if (cards.length < 4) return;

        const active = data.connections_active || data.connected_clients || data.user_sessions || data.connections_current || 0;
        const qps = data.qps || data.ops_per_sec || data.batch_requests_sec || 0;
        const hitRate = data.buffer_pool_hit_rate || data.cache_hit_rate || data.hit_rate || 0;

        // Calculate uptime from boot_time if available
        let uptime = data.uptime || data.uptime_in_seconds || 0;
        if (!uptime && data.boot_time) {
            const bootTime = new Date(data.boot_time);
            const now = new Date();
            uptime = Math.floor((now - bootTime) / 1000); // Convert to seconds
        }

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

    _updateCharts(data, time, timestamp) {
        const active = data.connections_active || data.connected_clients || data.user_sessions || data.connections_current || 0;
        const qps = data.qps || data.ops_per_sec || data.batch_requests_sec || 0;
        const hitRate = data.buffer_pool_hit_rate || data.cache_hit_rate || data.hit_rate || 100;
        const tps = data.tps || 0;
        const netIn = data.bytes_received || data.network_bytes_in || data.input_kbps || 0;
        const slow = data.slow_queries || data.deadlocks || 0;

        ChartPanel.update('connections', time, active);
        ChartPanel.update('qps', time, parseFloat(qps) || 0);
        ChartPanel.update('cache_hit', time, parseFloat(hitRate) || 0);
        ChartPanel.update('tps', time, parseFloat(tps) || 0);
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

        // Disk IO: Show separate read and write curves
        if (data.disk_reads_per_sec !== undefined || data.disk_writes_per_sec !== undefined) {
            const reads = parseFloat(data.disk_reads_per_sec) || 0;
            const writes = parseFloat(data.disk_writes_per_sec) || 0;
            ChartPanel.update('disk_io', time, [reads, writes]);
        }

        // Network IO: Calculate rate from cumulative bytes
        if (data.network_rx_bytes !== undefined && data.network_tx_bytes !== undefined) {
            const currentRx = parseFloat(data.network_rx_bytes) || 0;
            const currentTx = parseFloat(data.network_tx_bytes) || 0;

            if (this.prevNetworkRx !== null && this.prevNetworkTx !== null && this.prevNetworkTime !== null) {
                // Calculate time delta in seconds
                const timeDelta = (timestamp - this.prevNetworkTime) / 1000;

                if (timeDelta > 0) {
                    // Calculate rate in KB/s
                    const rxRate = Math.max(0, (currentRx - this.prevNetworkRx) / timeDelta / 1024);
                    const txRate = Math.max(0, (currentTx - this.prevNetworkTx) / timeDelta / 1024);

                    ChartPanel.update('network_io', time, [
                        Math.round(rxRate * 100) / 100,
                        Math.round(txRate * 100) / 100
                    ]);
                }
            }

            // Update previous values
            this.prevNetworkRx = currentRx;
            this.prevNetworkTx = currentTx;
            this.prevNetworkTime = timestamp;
        }
    },

    _batchUpdateCharts(metrics) {
        // Prepare batch data for all charts
        const batchData = {
            labels: [],
            connections: [],
            qps: [],
            cache_hit: [],
            tps: [],
            network: [],
            latency: [],
            cpu_usage: [],
            memory_usage: [],
            disk_usage: [],
            load_avg: [],
            disk_io_reads: [],
            disk_io_writes: [],
            network_io_rx: [],
            network_io_tx: []
        };

        // Process all metrics
        for (const m of metrics) {
            const time = new Date(m.collected_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            const data = m.data;
            const timestamp = new Date(m.collected_at).getTime();

            batchData.labels.push(time);

            // Database metrics
            batchData.connections.push(data.connections_active || data.connected_clients || data.user_sessions || data.connections_current || 0);
            batchData.qps.push(parseFloat(data.qps || data.ops_per_sec || data.batch_requests_sec || 0));
            batchData.cache_hit.push(parseFloat(data.buffer_pool_hit_rate || data.cache_hit_rate || data.hit_rate || 100));
            batchData.tps.push(parseFloat(data.tps || 0));
            batchData.network.push(data.bytes_received || data.network_bytes_in || data.input_kbps || 0);
            batchData.latency.push(data.slow_queries || data.deadlocks || 0);

            // OS metrics
            batchData.cpu_usage.push(data.cpu_usage !== undefined ? parseFloat(data.cpu_usage) || 0 : null);
            batchData.memory_usage.push(data.memory_usage !== undefined ? parseFloat(data.memory_usage) || 0 : null);
            batchData.disk_usage.push(data.disk_usage !== undefined ? parseFloat(data.disk_usage) || 0 : null);
            batchData.load_avg.push(data.load_avg_1min !== undefined ? parseFloat(data.load_avg_1min) || 0 : null);

            // Disk IO
            batchData.disk_io_reads.push(data.disk_reads_per_sec !== undefined ? parseFloat(data.disk_reads_per_sec) || 0 : null);
            batchData.disk_io_writes.push(data.disk_writes_per_sec !== undefined ? parseFloat(data.disk_writes_per_sec) || 0 : null);

            // Network IO rate calculation
            const currentRx = data.network_rx_bytes !== undefined ? parseFloat(data.network_rx_bytes) || 0 : null;
            const currentTx = data.network_tx_bytes !== undefined ? parseFloat(data.network_tx_bytes) || 0 : null;

            if (currentRx !== null && currentTx !== null && this.prevNetworkRx !== null && this.prevNetworkTx !== null && this.prevNetworkTime !== null) {
                const timeDelta = (timestamp - this.prevNetworkTime) / 1000;
                if (timeDelta > 0) {
                    const rxRate = Math.max(0, (currentRx - this.prevNetworkRx) / timeDelta / 1024);
                    const txRate = Math.max(0, (currentTx - this.prevNetworkTx) / timeDelta / 1024);
                    batchData.network_io_rx.push(Math.round(rxRate * 100) / 100);
                    batchData.network_io_tx.push(Math.round(txRate * 100) / 100);
                } else {
                    batchData.network_io_rx.push(null);
                    batchData.network_io_tx.push(null);
                }
            } else {
                batchData.network_io_rx.push(null);
                batchData.network_io_tx.push(null);
            }

            if (currentRx !== null && currentTx !== null) {
                this.prevNetworkRx = currentRx;
                this.prevNetworkTx = currentTx;
                this.prevNetworkTime = timestamp;
            }
        }

        // Batch update all charts
        ChartPanel.batchUpdate('connections', batchData.labels, batchData.connections);
        ChartPanel.batchUpdate('qps', batchData.labels, batchData.qps);
        ChartPanel.batchUpdate('cache_hit', batchData.labels, batchData.cache_hit);
        ChartPanel.batchUpdate('tps', batchData.labels, batchData.tps);
        ChartPanel.batchUpdate('network', batchData.labels, batchData.network);
        ChartPanel.batchUpdate('latency', batchData.labels, batchData.latency);

        // OS charts - filter labels and data together
        if (batchData.cpu_usage.some(v => v !== null)) {
            const filtered = this._filterNullValues(batchData.labels, batchData.cpu_usage);
            ChartPanel.batchUpdate('cpu_usage', filtered.labels, filtered.values);
        }
        if (batchData.memory_usage.some(v => v !== null)) {
            const filtered = this._filterNullValues(batchData.labels, batchData.memory_usage);
            ChartPanel.batchUpdate('memory_usage', filtered.labels, filtered.values);
        }
        if (batchData.disk_usage.some(v => v !== null)) {
            const filtered = this._filterNullValues(batchData.labels, batchData.disk_usage);
            ChartPanel.batchUpdate('disk_usage', filtered.labels, filtered.values);
        }
        if (batchData.load_avg.some(v => v !== null)) {
            const filtered = this._filterNullValues(batchData.labels, batchData.load_avg);
            ChartPanel.batchUpdate('load_avg', filtered.labels, filtered.values);
        }

        // Multi-line charts - filter labels and data together
        if (batchData.disk_io_reads.some(v => v !== null) || batchData.disk_io_writes.some(v => v !== null)) {
            const filtered = this._filterNullValuesMulti(batchData.labels, [batchData.disk_io_reads, batchData.disk_io_writes]);
            ChartPanel.batchUpdateMulti('disk_io', filtered.labels, filtered.valuesArray);
        }
        if (batchData.network_io_rx.some(v => v !== null) || batchData.network_io_tx.some(v => v !== null)) {
            const filtered = this._filterNullValuesMulti(batchData.labels, [batchData.network_io_rx, batchData.network_io_tx]);
            ChartPanel.batchUpdateMulti('network_io', filtered.labels, filtered.valuesArray);
        }
    },

    _filterNullValues(labels, values) {
        const filtered = { labels: [], values: [] };
        for (let i = 0; i < values.length; i++) {
            if (values[i] !== null) {
                filtered.labels.push(labels[i]);
                filtered.values.push(values[i]);
            }
        }
        return filtered;
    },

    _filterNullValuesMulti(labels, valuesArray) {
        const filtered = { labels: [], valuesArray: valuesArray.map(() => []) };
        for (let i = 0; i < labels.length; i++) {
            // Include this point if any dataset has a non-null value
            const hasValue = valuesArray.some(arr => arr[i] !== null);
            if (hasValue) {
                filtered.labels.push(labels[i]);
                valuesArray.forEach((arr, idx) => {
                    filtered.valuesArray[idx].push(arr[i] !== null ? arr[i] : 0);
                });
            }
        }
        return filtered;
    },

    _cleanup() {
        this._stopMonitoring();
        ChartPanel.destroyAll();
        // Reset network tracking
        this.prevNetworkRx = null;
        this.prevNetworkTx = null;
        this.prevNetworkTime = null;
        // Reset time range state
        this.currentTimeRange = 60;
        this.isRealtime = true;
    }
};
