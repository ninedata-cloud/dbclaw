/* Real-time Monitor page */
const MonitorPage = {
    ws: null,
    datasourceSelector: null,
    _renderOptions: null,
    _container: null,
    chartIds: ['connections', 'qps', 'cache_hit', 'tps', 'network', 'latency'],
    osChartIds: ['cpu_usage', 'memory_usage', 'disk_usage', 'load_avg', 'disk_io', 'network_io'],
    // 按数据源隔离网络状态，避免多数据源切换时互相干扰
    networkStates: new Map(), // datasource_id -> { db: {...}, host: {...} }
    currentDatasourceId: null,
    // Time range state
    currentTimeRange: 60, // default 1 hour in minutes
    isRealtime: true,
    chartMaxPoints: 240,

    /**
     * 解析后端返回的 UTC 时间字符串为本地 Date 对象
     * 后端存储的是 UTC naive datetime，返回时没有时区标识
     */
    _parseUTCDateTime(dateInput) {
        const parsed = Format.parseDate(dateInput);
        if (parsed) return parsed;

        // Preserve backward-compatible UTC-naive handling for legacy values.
        if (typeof dateInput === 'string') {
            const dateStr = dateInput.trim();
            if (dateStr && !dateStr.endsWith('Z') && !dateStr.includes('+') && !dateStr.includes('T')) {
                return new Date(dateStr.replace(' ', 'T') + 'Z');
            }
            if (dateStr && !dateStr.endsWith('Z') && dateStr.includes('T') && !dateStr.includes('+')) {
                return new Date(dateStr + 'Z');
            }
        }

        return new Date(NaN);
    },

    _getSelectedDatasource() {
        return this.datasourceSelector?.getValue() || Store.get('currentConnection') || null;
    },

    _getSelectedDatasourceId() {
        return this._getSelectedDatasource()?.id || null;
    },

    _getNetworkState(datasourceId, type) {
        if (!datasourceId) return { rx: null, tx: null, time: null };
        if (!this.networkStates.has(datasourceId)) {
            this.networkStates.set(datasourceId, {
                db: { rx: null, tx: null, time: null },
                host: { rx: null, tx: null, time: null }
            });
        }
        return this.networkStates.get(datasourceId)[type];
    },

    _resetNetworkStates() {
        // 清空所有数据源的网络状态
        this.networkStates.clear();
    },

    _resetNetworkStateForDatasource(datasourceId) {
        // 重置特定数据源的网络状态
        if (datasourceId) {
            this.networkStates.delete(datasourceId);
        }
    },

    _resetChartMaxPoints() {
        this.chartMaxPoints = 240;
    },

    _setChartMaxPoints(pointCount) {
        const numericCount = typeof pointCount === 'number' ? pointCount : parseInt(pointCount, 10);
        if (!Number.isFinite(numericCount) || numericCount <= 0) {
            this._resetChartMaxPoints();
            return;
        }

        this.chartMaxPoints = Math.min(Math.max(numericCount + 120, 240), 10000);
    },

    _getChartMaxPoints() {
        return this.chartMaxPoints || 240;
    },

    _toNumeric(value) {
        if (value === null || value === undefined || value === '') return null;
        const parsed = typeof value === 'number' ? value : parseFloat(value);
        return Number.isFinite(parsed) ? parsed : null;
    },

    _formatNetworkChartValue(value) {
        if (Array.isArray(value)) {
            return value.map(item => Format.networkRate(item)).join(' / ');
        }
        return Format.networkRate(value);
    },

    _buildNetworkChartOptions() {
        return {
            valueFormatter: (value) => this._formatNetworkChartValue(value),
            options: {
                plugins: {
                    legend: {
                        display: true,
                        position: 'top',
                        labels: { color: '#e6edf3', font: { size: 11 } }
                    },
                    tooltip: {
                        callbacks: {
                            label: (context) => {
                                const datasetLabel = context.dataset?.label || '';
                                return `${datasetLabel}: ${Format.networkRate(context.parsed?.y)}`;
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        ticks: {
                            callback: (value) => Format.networkRate(value)
                        }
                    }
                }
            }
        };
    },

    _buildMultiLineDataset(label, borderColor, backgroundColor) {
        return {
            label,
            borderColor,
            backgroundColor,
            borderWidth: 1,
            data: [],
            pointRadius: 0,
            pointHoverRadius: 0,
            pointHitRadius: 10,
        };
    },

    _formatChartLabel(dateInput) {
        const date = this._parseUTCDateTime(dateInput);
        if (Number.isNaN(date.getTime())) return '';

        const now = new Date();
        const isToday =
            date.getFullYear() === now.getFullYear() &&
            date.getMonth() === now.getMonth() &&
            date.getDate() === now.getDate();

        if (isToday) {
            return date.toLocaleTimeString([], {
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        }

        const dateLabel = [
            date.getFullYear(),
            String(date.getMonth() + 1).padStart(2, '0'),
            String(date.getDate()).padStart(2, '0')
        ].join('-');
        const timeLabel = [
            String(date.getHours()).padStart(2, '0'),
            String(date.getMinutes()).padStart(2, '0')
        ].join(':');
        return `${dateLabel} ${timeLabel}`;
    },

    _calculateRateFromCounters(currentRx, currentTx, timestamp, state) {
        if (currentRx === null || currentTx === null || timestamp === null || timestamp === undefined) {
            return null;
        }

        let rxRate = null;
        let txRate = null;
        if (state.rx !== null && state.tx !== null && state.time !== null) {
            const timeDelta = (timestamp - state.time) / 1000;
            if (timeDelta > 0) {
                rxRate = Math.max(0, (currentRx - state.rx) / timeDelta);
                txRate = Math.max(0, (currentTx - state.tx) / timeDelta);
            }
        }

        state.rx = currentRx;
        state.tx = currentTx;
        state.time = timestamp;

        if (rxRate === null || txRate === null) {
            return null;
        }

        return {
            rx: Math.round(rxRate * 100) / 100,
            tx: Math.round(txRate * 100) / 100
        };
    },

    _extractDatabaseNetworkRates(data, timestamp, datasourceId) {
        const directRx = this._toNumeric(data.network_rx_rate);
        const directTx = this._toNumeric(data.network_tx_rate);
        if (directRx !== null && directTx !== null) {
            // 直接速率，重置状态
            this._resetNetworkStateForDatasource(datasourceId);
            return { rx: directRx, tx: directTx };
        }

        const cloudRx = this._toNumeric(data.network_in);
        const cloudTx = this._toNumeric(data.network_out);
        if (cloudRx !== null && cloudTx !== null) {
            this._resetNetworkStateForDatasource(datasourceId);
            return {
                rx: Math.round(cloudRx * 1024 * 100) / 100,
                tx: Math.round(cloudTx * 1024 * 100) / 100
            };
        }

        const inputRx = this._toNumeric(data.input_kbps);
        const inputTx = this._toNumeric(data.output_kbps);
        if (inputRx !== null && inputTx !== null) {
            this._resetNetworkStateForDatasource(datasourceId);
            return {
                rx: Math.round(inputRx * 1024 * 100) / 100,
                tx: Math.round(inputTx * 1024 * 100) / 100
            };
        }

        const cumulativeRx = this._toNumeric(data.bytes_received) ?? this._toNumeric(data.network_bytes_in);
        const cumulativeTx = this._toNumeric(data.bytes_sent) ?? this._toNumeric(data.network_bytes_out);
        if (cumulativeRx !== null && cumulativeTx !== null) {
            const state = this._getNetworkState(datasourceId, 'db');
            return this._calculateRateFromCounters(cumulativeRx, cumulativeTx, timestamp, state);
        }

        const aliasRx = this._toNumeric(data.network_rx_bytes);
        const aliasTx = this._toNumeric(data.network_tx_bytes);
        if (aliasRx !== null && aliasTx !== null) {
            const looksCumulative = aliasRx > 10 * 1024 * 1024 || aliasTx > 10 * 1024 * 1024;
            if (looksCumulative) {
                const state = this._getNetworkState(datasourceId, 'db');
                return this._calculateRateFromCounters(aliasRx, aliasTx, timestamp, state);
            }
            this._resetNetworkStateForDatasource(datasourceId);
            return {
                rx: Math.round(aliasRx * 1024 * 100) / 100,
                tx: Math.round(aliasTx * 1024 * 100) / 100
            };
        }

        this._resetNetworkStateForDatasource(datasourceId);
        return null;
    },

    _extractHostNetworkRates(data, timestamp, datasourceId) {
        const hostRx = this._toNumeric(data.host_network_rx_bytes);
        const hostTx = this._toNumeric(data.host_network_tx_bytes);
        if (hostRx !== null && hostTx !== null) {
            const state = this._getNetworkState(datasourceId, 'host');
            return this._calculateRateFromCounters(hostRx, hostTx, timestamp, state);
        }

        const normalizedRx = this._toNumeric(data.network_rx_rate);
        const normalizedTx = this._toNumeric(data.network_tx_rate);
        if (normalizedRx !== null && normalizedTx !== null) {
            this._resetNetworkStateForDatasource(datasourceId);
            return { rx: normalizedRx, tx: normalizedTx };
        }

        const aliasRx = this._toNumeric(data.network_rx_bytes);
        const aliasTx = this._toNumeric(data.network_tx_bytes);
        if (aliasRx !== null && aliasTx !== null) {
            const looksCumulative = aliasRx > 10 * 1024 * 1024 || aliasTx > 10 * 1024 * 1024;
            if (looksCumulative) {
                const state = this._getNetworkState(datasourceId, 'host');
                return this._calculateRateFromCounters(aliasRx, aliasTx, timestamp, state);
            }
            this._resetNetworkStateForDatasource(datasourceId);
            return {
                rx: Math.round(aliasRx * 1024 * 100) / 100,
                tx: Math.round(aliasTx * 1024 * 100) / 100
            };
        }

        this._resetNetworkStateForDatasource(datasourceId);
        return null;
    },

    async render() {
        return this.renderWithOptions({});
    },

    async renderWithOptions(options = {}) {
        this._renderOptions = options || {};
        const content = options.container || DOM.$('#page-content');
        this._container = content;

        // Load datasources first if not in store
        let connections = Store.get('datasources') || [];
        if (connections.length === 0) {
            try {
                connections = await API.getDatasources();
                Store.set('datasources', connections);
            } catch (e) {
                console.error('[Monitor] Failed to load datasources:', e);
            }
        }

        // Get or auto-select current connection
        let conn = null;
        if (options.fixedDatasourceId) {
            conn = connections.find(item => item.id === options.fixedDatasourceId) || null;
        } else {
            conn = Store.get('currentConnection');
        }
        if (!conn && connections.length > 0) {
            conn = connections[0];
        }
        if (conn) {
            Store.set('currentConnection', conn);
        }

        // Header with connection selector and time range selector
        const headerActions = DOM.el('div', { className: 'flex gap-8', style: { flex: '1', minWidth: '0' } });

        // Connection selector
        this.datasourceSelector?.destroy();
        this.datasourceSelector = null;
        if (!options.fixedDatasourceId) {
            const datasourceContainer = DOM.el('div', {
                id: 'monitor-datasource-selector',
                style: { minWidth: '280px', maxWidth: '380px', flex: '1' }
            });
            headerActions.appendChild(datasourceContainer);

            this.datasourceSelector = new DatasourceSelector({
                container: datasourceContainer,
                allowEmpty: false,
                placeholder: '选择数据源',
                showStatus: true,
                showDetails: true,
                onLoad: (loadedDatasources) => {
                    if ((!conn || !loadedDatasources.some(ds => ds.id === conn.id)) && loadedDatasources.length > 0) {
                        conn = loadedDatasources[0];
                        Store.set('currentConnection', conn);
                    }
                    if (conn?.id) {
                        this.datasourceSelector.setValue(conn.id);
                    }
                },
                onChange: (datasource) => {
                    if (!datasource) return;
                    conn = datasource;
                    Store.set('currentConnection', datasource);
                    this._reloadData(datasource.id);
                }
            });
        }

        // Time range selector
        const timeRangeSelect = DOM.el('select', {
            className: 'form-select',
            style: { minWidth: '120px', maxWidth: '180px', flex: '0 1 auto' },
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
                const selectedDatasourceId = this._getSelectedDatasourceId();
                if (selectedDatasourceId) {
                    this._reloadData(selectedDatasourceId);
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
            const selectedDatasourceId = this._getSelectedDatasourceId();
            if (this.isRealtime && selectedDatasourceId) {
                this._startMonitoring(selectedDatasourceId);
            } else {
                this._stopMonitoring();
            }
        });
        headerActions.appendChild(realtimeBtn);

        // Refresh button
        const refreshBtn = DOM.el('button', {
            className: 'btn btn-primary',
            id: 'refresh-btn',
            innerHTML: '<i data-lucide="refresh-cw"></i> 刷新'
        });
        refreshBtn.addEventListener('click', async () => {
            const selectedDatasourceId = this._getSelectedDatasourceId();
            if (!selectedDatasourceId) return;

            // Disable button and show loading state
            refreshBtn.disabled = true;
            refreshBtn.innerHTML = '<i data-lucide="loader"></i> 采集中...';

            try {
                await API.refreshMetrics(selectedDatasourceId);
                // Wait a moment for the metric to be collected and stored
                await new Promise(resolve => setTimeout(resolve, 1000));
                // Reload latest data
                await this._loadLatestData(selectedDatasourceId);
            } catch (e) {
                console.error('[Monitor] Failed to refresh metrics:', e);
                alert('刷新失败: ' + e.message);
            } finally {
                // Re-enable button
                refreshBtn.disabled = false;
                refreshBtn.innerHTML = '<i data-lucide="refresh-cw"></i> 刷新';
                DOM.createIcons();
            }
        });
        headerActions.appendChild(refreshBtn);

        content.innerHTML = '';
        if (options.embedded) {
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
                textContent: '性能监控'
            }));
            embeddedToolbar.appendChild(headerActions);
            content.appendChild(embeddedToolbar);
        } else {
            Header.render('性能监控', headerActions);
        }

        if (!conn && connections.length === 0) {
            content.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="activity"></i>
                    <h3>No Connections</h3>
                    <p>Add a database connection first to start monitoring.</p>
                    <button class="btn btn-primary mt-16" onclick="Router.navigate('datasources')">Add Connection</button>
                </div>
            `;
            DOM.createIcons();
            return;
        }

        // Health Status Banner
        const healthBanner = DOM.el('div', { className: 'health-banner mb-24', id: 'health-banner' });
        healthBanner.innerHTML = `
            <span class="health-banner-icon">⚪</span>
            <span class="health-banner-status">数据库健康状态: 检查中...</span>
            <div class="health-banner-details" id="health-details"></div>
        `;
        content.appendChild(healthBanner);

        // Database Metric cards row
        const dbMetricsRow = DOM.el('div', { className: 'grid-4 mb-24', id: 'monitor-metrics' });
        const connectionCard = DOM.el('div', { className: 'metric-card metric-card-connection-overview' });
        connectionCard.innerHTML = `
            <div class="metric-card-label">连接数（活跃/总数/最大）</div>
            <div class="connection-overview-value" data-connection-metric="summary">--/--/--</div>
        `;
        dbMetricsRow.appendChild(connectionCard);
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
        osChartsGrid.appendChild(ChartPanel.create('network_io', '网络 I/O (接收/发送)'));
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
                } else if (id === 'connections') {
                    config.data = {
                        datasets: [
                            this._buildMultiLineDataset('活跃连接数', '#10b981', 'rgba(16,185,129,0.1)'),
                            this._buildMultiLineDataset('总连接数', '#2f81f7', 'rgba(47,129,247,0.1)')
                        ]
                    };
                    config.options = {
                        plugins: {
                            legend: { display: true, position: 'top', labels: { color: '#e6edf3', font: { size: 11 } } }
                        }
                    };
                } else if (id === 'network') {
                    const networkConfig = this._buildNetworkChartOptions();
                    config.data = {
                        datasets: [
                            this._buildMultiLineDataset('接收', '#10b981', 'rgba(16,185,129,0.1)'),
                            this._buildMultiLineDataset('发送', '#8b5cf6', 'rgba(139,92,246,0.1)')
                        ]
                    };
                    config.options = networkConfig.options;
                    config.valueFormatter = networkConfig.valueFormatter;
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
                // Multi-line charts with distinct colors for better differentiation
                if (id === 'disk_io') {
                    config.data = {
                        datasets: [
                            this._buildMultiLineDataset('读', '#2f81f7', 'rgba(47,129,247,0.1)'),
                            this._buildMultiLineDataset('写', '#f97316', 'rgba(249,115,22,0.1)')
                        ]
                    };
                    config.options = {
                        plugins: {
                            legend: { display: true, position: 'top', labels: { color: '#e6edf3', font: { size: 11 } } }
                        }
                    };
                } else if (id === 'network_io') {
                    const networkConfig = this._buildNetworkChartOptions();
                    config.data = {
                        datasets: [
                            this._buildMultiLineDataset('接收', '#10b981', 'rgba(16,185,129,0.1)'),
                            this._buildMultiLineDataset('发送', '#8b5cf6', 'rgba(139,92,246,0.1)')
                        ]
                    };
                    config.options = networkConfig.options;
                    config.valueFormatter = networkConfig.valueFormatter;
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
            const selectedDatasourceId = this._getSelectedDatasourceId();
            if (selectedDatasourceId) {
                // Load health status first
                this._loadHealthStatus(selectedDatasourceId);
                // Load latest data first for immediate display, then load history
                this._loadLatestData(selectedDatasourceId).then(() => {
                    this._loadHistory(selectedDatasourceId);
                });
                if (this.isRealtime) {
                    this._startMonitoring(selectedDatasourceId);
                }
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

        // 重置当前数据源的网络状态
        this._resetNetworkStateForDatasource(connId);
        this.currentDatasourceId = connId;

        // Load health status
        this._loadHealthStatus(connId);

        // Load new data
        this._loadLatestData(connId).then(() => {
            this._loadHistory(connId);
        });

        // Start monitoring if realtime is enabled
        if (this.isRealtime) {
            this._startMonitoring(connId);
        }
    },

    async _loadHealthStatus(connId) {
        try {
            const health = await API.getDatasourceHealth(connId);
            this._updateHealthBanner(health);
        } catch (e) {
            console.error('[Monitor] Failed to load health status:', e);
            this._updateHealthBanner({
                healthy: false,
                status: 'unknown',
                message: '无法获取健康状态',
                violations: []
            });
        }
    },

    _isConnectionFailureHealth(health) {
        if (!health) return false;
        if (Array.isArray(health.violations) && health.violations.some(item => item?.type === 'connection_failure')) {
            return true;
        }
        return String(health.message || '').includes('连接失败');
    },

    _updateHealthBanner(health) {
        const banner = DOM.$('#health-banner');
        if (!banner) return;

        const isConnectionFailure = this._isConnectionFailureHealth(health);
        const statusMap = {
            'healthy': { icon: '✓', text: '健康', color: 'var(--accent-green)' },
            'warning': { icon: '⚠', text: '警告', color: 'var(--accent-yellow)' },
            'critical': { icon: '✗', text: '异常', color: 'var(--accent-red)' },
            'unknown': { icon: '?', text: '未知', color: 'var(--text-muted)' }
        };

        const statusInfo = statusMap[health.status] || statusMap.unknown;
        const statusText = isConnectionFailure ? '连接失败' : statusInfo.text;

        // Update icon with color
        const iconEl = banner.querySelector('.health-banner-icon');
        iconEl.textContent = statusInfo.icon;
        iconEl.style.color = statusInfo.color;

        // Update status text
        const statusEl = banner.querySelector('.health-banner-status');
        statusEl.innerHTML = `数据库健康状态: <span style="color:${statusInfo.color}">${statusText}</span> - ${health.message}`;

        // Update details section
        const detailsEl = DOM.$('#health-details');
        detailsEl.innerHTML = '';

        if (health.violations && health.violations.length > 0) {
            const violationsList = DOM.el('div', { className: 'health-violations' });

            for (const violation of health.violations) {
                const item = DOM.el('div', { className: 'health-violation-item' });

                if (violation.type === 'threshold') {
                    item.innerHTML = `
                        <span style="color:var(--accent-red)">✗</span>
                        <span>${violation.metric}: ${violation.value.toFixed(2)} (阈值: ${violation.threshold})</span>
                    `;
                } else if (violation.type === 'connection_failure') {
                    item.innerHTML = `
                        <span style="color:var(--accent-red)">✗</span>
                        <span>${violation.detail || health.message || '数据库连接失败'}</span>
                    `;
                } else if (violation.type === 'custom_expression') {
                    item.innerHTML = `
                        <span style="color:var(--accent-red)">✗</span>
                        <span>自定义规则触发: ${violation.expression}</span>
                    `;
                } else if (violation.type === 'ai_policy') {
                    item.innerHTML = `
                        <span style="color:var(--accent-red)">✗</span>
                        <span>AI 规则触发: ${violation.policy || 'AI 告警规则'}${violation.confidence != null ? `（置信度 ${(Number(violation.confidence) * 100).toFixed(0)}%）` : ''}</span>
                    `;
                }

                violationsList.appendChild(item);
            }

            detailsEl.appendChild(violationsList);
        }
    },

    _formatDateTimeLocal(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
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

        // Calculate default time range based on current selection
        // Use local time for datetime-local input
        const now = new Date();
        const endTime = this._formatDateTimeLocal(now);
        const startDate = new Date(now.getTime() - this.currentTimeRange * 60 * 1000);
        const startTime = this._formatDateTimeLocal(startDate);

        // Start time
        const startGroup = DOM.el('div', { className: 'form-group' });
        startGroup.appendChild(DOM.el('label', { textContent: '开始时间' }));
        const startInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'filter-input inspection-date-input',
            id: 'custom-start-time',
            value: startTime
        });
        startGroup.appendChild(startInput);
        body.appendChild(startGroup);

        // End time
        const endGroup = DOM.el('div', { className: 'form-group' });
        endGroup.appendChild(DOM.el('label', { textContent: '结束时间' }));
        const endInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'filter-input inspection-date-input',
            id: 'custom-end-time',
            value: endTime
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
            this.isRealtime = false;
            const selectedDatasourceId = this._getSelectedDatasourceId();
            if (!selectedDatasourceId) {
                alert('请先选择数据源');
                document.body.removeChild(dialog);
                DOM.$('#time-range-select').value = this.currentTimeRange;
                return;
            }
            this._loadCustomRange(selectedDatasourceId, start, end).then((hasData) => {
                if (hasData) {
                    document.body.removeChild(dialog);
                    DOM.$('#realtime-toggle').textContent = '暂停实时';
                    DOM.$('#realtime-toggle').className = 'btn btn-outline';
                } else {
                    // Keep dialog open when no data
                    DOM.$('#time-range-select').value = this.currentTimeRange;
                }
            });
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
                return false;
            }

            this._setChartMaxPoints(metrics.length);

            // Clear charts
            for (const id of [...this.chartIds, ...this.osChartIds]) {
                ChartPanel.clear(id);
            }

            this._resetNetworkStates();

            const reversed = [...metrics].reverse();

            // Update latest metric card
            if (metrics.length > 0) {
                this._updateMetricCards(metrics[0].data);
            }

            // Batch populate charts
            this._batchUpdateCharts(reversed);
            return true;
        } catch (e) {
            console.error('[Monitor] Failed to load custom range:', e);
            alert('加载数据失败: ' + e.message);
            return false;
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

            // Filter metrics to only include those within the selected time range
            // 注意：后端返回的是 UTC 时间，需要正确解析后再比较
            const now = Date.now();
            const rangeMs = this.currentTimeRange * 60 * 1000;
            const cutoffTime = now - rangeMs;
            const filtered = metrics.filter(m => {
                const timestamp = this._parseUTCDateTime(m.collected_at).getTime();
                return Number.isFinite(timestamp) && timestamp >= cutoffTime;
            });

            console.log('[Monitor] Filtered metrics:', filtered.length, 'records within range');
            if (filtered.length === 0) {
                console.warn('[Monitor] No metrics found within selected time range');
                return;
            }

            const reversed = [...filtered].reverse();
            this._setChartMaxPoints(filtered.length);

            this._resetNetworkStates();

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
                // 使用服务器采集时间而非本地时间
                const collectedAt = data.collected_at || new Date().toISOString();
                const timestamp = this._parseUTCDateTime(collectedAt).getTime();
                const time = this._formatChartLabel(collectedAt);
                this._updateMetricCards(data.data);
                this._updateCharts(data.data, time, timestamp);
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

        const active = data.connections_active ?? data.threads_running ?? data.active_connections ?? data.connected_clients ?? data.user_sessions ?? data.connections_current ?? data.active_sessions ?? 0;
        const total = data.connections_total ?? data.threads_connected ?? data.total_connections;
        const maxConnections = data.max_connections;
        const qps = data.qps ?? data.ops_per_sec ?? data.batch_requests_sec ?? 0;
        const hitRate = data.buffer_pool_hit_rate ?? data.cache_hit_rate ?? data.hit_rate;

        // Calculate uptime from boot_time if available
        let uptime = data.uptime || data.uptime_in_seconds || 0;
        if (!uptime && data.boot_time) {
            const bootTime = new Date(data.boot_time);
            const now = new Date();
            uptime = Math.floor((now - bootTime) / 1000); // Convert to seconds
        }

        const summaryEl = cards[0].querySelector('[data-connection-metric="summary"]');
        const activeText = active !== undefined && active !== null ? Number(active).toLocaleString() : '--';
        const totalText = total !== undefined && total !== null ? Number(total).toLocaleString() : '--';
        const maxText = maxConnections !== undefined && maxConnections !== null && maxConnections !== 0 ? String(Number(maxConnections)) : '--';
        if (summaryEl) summaryEl.textContent = `${activeText}/${totalText}/${maxText}`;

        MetricCard.update(cards[1], typeof qps === 'number' ? qps.toFixed(1) : qps);
        MetricCard.update(cards[2], hitRate !== undefined && hitRate !== null ? Format.percent(hitRate) : '--');
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
        const datasourceId = this.currentDatasourceId || this._getSelectedDatasourceId();
        const active = data.connections_active ?? data.threads_running ?? data.active_connections ?? data.connected_clients ?? data.user_sessions ?? data.connections_current ?? data.active_sessions ?? 0;
        const total = data.connections_total ?? data.threads_connected ?? data.total_connections;
        const qps = data.qps ?? data.ops_per_sec ?? data.batch_requests_sec ?? 0;
        const hitRate = data.buffer_pool_hit_rate ?? data.cache_hit_rate ?? data.hit_rate;
        const tps = data.tps || 0;
        const slow = data.slow_queries || data.deadlocks || 0;
        const dbNetworkRates = this._extractDatabaseNetworkRates(data, timestamp, datasourceId);
        const hostNetworkRates = this._extractHostNetworkRates(data, timestamp, datasourceId);
        const maxPoints = this._getChartMaxPoints();

        ChartPanel.update('connections', time, [parseFloat(active) || 0, parseFloat(total) || 0], maxPoints);
        ChartPanel.update('qps', time, parseFloat(qps) || 0, maxPoints);

        // 限制缓存命中率在 0-100 范围内
        const normalizedHitRate = hitRate !== undefined && hitRate !== null
            ? Math.min(Math.max(parseFloat(hitRate) || 0, 0), 100)
            : null;
        ChartPanel.update('cache_hit', time, normalizedHitRate, maxPoints);

        ChartPanel.update('tps', time, parseFloat(tps) || 0, maxPoints);
        if (dbNetworkRates) {
            ChartPanel.update('network', time, [dbNetworkRates.rx, dbNetworkRates.tx], maxPoints);
        }
        ChartPanel.update('latency', time, slow, maxPoints);

        // Update OS charts
        if (data.cpu_usage !== undefined) {
            ChartPanel.update('cpu_usage', time, parseFloat(data.cpu_usage) || 0, maxPoints);
        }
        if (data.memory_usage !== undefined) {
            ChartPanel.update('memory_usage', time, parseFloat(data.memory_usage) || 0, maxPoints);
        }
        if (data.disk_usage !== undefined) {
            ChartPanel.update('disk_usage', time, parseFloat(data.disk_usage) || 0, maxPoints);
        }
        if (data.load_avg_1min !== undefined) {
            ChartPanel.update('load_avg', time, parseFloat(data.load_avg_1min) || 0, maxPoints);
        }

        // Disk IO: Show separate read and write curves
        if (data.disk_reads_per_sec !== undefined || data.disk_writes_per_sec !== undefined) {
            const reads = parseFloat(data.disk_reads_per_sec) || 0;
            const writes = parseFloat(data.disk_writes_per_sec) || 0;
            ChartPanel.update('disk_io', time, [reads, writes], maxPoints);
        }

        if (hostNetworkRates) {
            ChartPanel.update('network_io', time, [hostNetworkRates.rx, hostNetworkRates.tx], maxPoints);
        }
    },

    _batchUpdateCharts(metrics) {
        const datasourceId = this.currentDatasourceId || this._getSelectedDatasourceId();
        const maxPoints = this._getChartMaxPoints();
        // Prepare batch data for all charts
        const batchData = {
            labels: [],
            connections_active: [],
            connections_total: [],
            qps: [],
            cache_hit: [],
            tps: [],
            network_rx: [],
            network_tx: [],
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
            const time = this._formatChartLabel(m.collected_at);
            const data = m.data;
            const timestamp = this._parseUTCDateTime(m.collected_at).getTime();

            batchData.labels.push(time);

            // Database metrics
            const active = data.connections_active ?? data.threads_running ?? data.active_connections ?? data.connected_clients ?? data.user_sessions ?? data.connections_current ?? data.active_sessions ?? 0;
            const total = data.connections_total ?? data.threads_connected ?? data.total_connections;
            batchData.connections_active.push(parseFloat(active) || 0);
            batchData.connections_total.push(parseFloat(total) || 0);
            batchData.qps.push(parseFloat(data.qps ?? data.ops_per_sec ?? data.batch_requests_sec ?? 0));

            const hitRate = data.buffer_pool_hit_rate ?? data.cache_hit_rate ?? data.hit_rate;
            // 限制缓存命中率在 0-100 范围内
            const normalizedHitRate = hitRate !== undefined && hitRate !== null
                ? Math.min(Math.max(parseFloat(hitRate) || 0, 0), 100)
                : null;
            batchData.cache_hit.push(normalizedHitRate);
            batchData.tps.push(parseFloat(data.tps || 0));
            batchData.latency.push(data.slow_queries || data.deadlocks || 0);

            const dbNetworkRates = this._extractDatabaseNetworkRates(data, timestamp, datasourceId);
            batchData.network_rx.push(dbNetworkRates ? dbNetworkRates.rx : null);
            batchData.network_tx.push(dbNetworkRates ? dbNetworkRates.tx : null);

            // OS metrics
            batchData.cpu_usage.push(data.cpu_usage !== undefined ? parseFloat(data.cpu_usage) || 0 : null);
            batchData.memory_usage.push(data.memory_usage !== undefined ? parseFloat(data.memory_usage) || 0 : null);
            batchData.disk_usage.push(data.disk_usage !== undefined ? parseFloat(data.disk_usage) || 0 : null);
            batchData.load_avg.push(data.load_avg_1min !== undefined ? parseFloat(data.load_avg_1min) || 0 : null);

            // Disk IO
            batchData.disk_io_reads.push(data.disk_reads_per_sec !== undefined ? parseFloat(data.disk_reads_per_sec) || 0 : null);
            batchData.disk_io_writes.push(data.disk_writes_per_sec !== undefined ? parseFloat(data.disk_writes_per_sec) || 0 : null);

            const hostNetworkRates = this._extractHostNetworkRates(data, timestamp, datasourceId);
            batchData.network_io_rx.push(hostNetworkRates ? hostNetworkRates.rx : null);
            batchData.network_io_tx.push(hostNetworkRates ? hostNetworkRates.tx : null);
        }

        // Batch update all charts
        ChartPanel.batchUpdateMulti('connections', batchData.labels, [batchData.connections_active, batchData.connections_total], maxPoints);
        ChartPanel.batchUpdate('qps', batchData.labels, batchData.qps, maxPoints);
        ChartPanel.batchUpdate('cache_hit', batchData.labels, batchData.cache_hit, maxPoints);
        ChartPanel.batchUpdate('tps', batchData.labels, batchData.tps, maxPoints);
        if (batchData.network_rx.some(v => v !== null) || batchData.network_tx.some(v => v !== null)) {
            const filtered = this._filterNullValuesMulti(batchData.labels, [batchData.network_rx, batchData.network_tx]);
            ChartPanel.batchUpdateMulti('network', filtered.labels, filtered.valuesArray, maxPoints);
        }
        ChartPanel.batchUpdate('latency', batchData.labels, batchData.latency, maxPoints);

        // OS charts - filter labels and data together
        if (batchData.cpu_usage.some(v => v !== null)) {
            const filtered = this._filterNullValues(batchData.labels, batchData.cpu_usage);
            ChartPanel.batchUpdate('cpu_usage', filtered.labels, filtered.values, maxPoints);
        }
        if (batchData.memory_usage.some(v => v !== null)) {
            const filtered = this._filterNullValues(batchData.labels, batchData.memory_usage);
            ChartPanel.batchUpdate('memory_usage', filtered.labels, filtered.values, maxPoints);
        }
        if (batchData.disk_usage.some(v => v !== null)) {
            const filtered = this._filterNullValues(batchData.labels, batchData.disk_usage);
            ChartPanel.batchUpdate('disk_usage', filtered.labels, filtered.values, maxPoints);
        }
        if (batchData.load_avg.some(v => v !== null)) {
            const filtered = this._filterNullValues(batchData.labels, batchData.load_avg);
            ChartPanel.batchUpdate('load_avg', filtered.labels, filtered.values, maxPoints);
        }

        // Multi-line charts - filter labels and data together
        if (batchData.disk_io_reads.some(v => v !== null) || batchData.disk_io_writes.some(v => v !== null)) {
            const filtered = this._filterNullValuesMulti(batchData.labels, [batchData.disk_io_reads, batchData.disk_io_writes]);
            ChartPanel.batchUpdateMulti('disk_io', filtered.labels, filtered.valuesArray, maxPoints);
        }
        if (batchData.network_io_rx.some(v => v !== null) || batchData.network_io_tx.some(v => v !== null)) {
            const filtered = this._filterNullValuesMulti(batchData.labels, [batchData.network_io_rx, batchData.network_io_tx]);
            ChartPanel.batchUpdateMulti('network_io', filtered.labels, filtered.valuesArray, maxPoints);
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
        this.datasourceSelector?.destroy();
        this.datasourceSelector = null;
        this._stopMonitoring();
        ChartPanel.destroyAll();
        this._resetNetworkStates();
        this._resetChartMaxPoints();
        // Reset time range state
        this.currentTimeRange = 60;
        this.isRealtime = true;
        this._renderOptions = null;
        this._container = null;
    }
};
