/* Real-time instance traffic topology */
const InstanceTrafficPage = {
    container: null,
    datasourceId: null,
    datasource: null,
    refs: {},
    data: null,
    historyPoints: [],
    visibleClients: [],
    clientLayout: [],
    particles: [],
    hoveredClientId: null,
    historyChart: null,
    pollTimer: null,
    animationFrame: null,
    resizeObserver: null,
    refreshInFlight: false,
    requestSerial: 0,
    lastFrameAt: 0,
    pollIntervalSeconds: 5,

    async render({ container, datasourceId, datasource }) {
        this.cleanup();

        this.container = container;
        this.datasourceId = datasourceId;
        this.datasource = datasource || null;
        this.historyPoints = [];
        this._renderShell();
        this._cacheRefs();
        this._bindStaticEvents();
        this._observeResize();

        await this._refresh({ showLoading: true, silent: false });
        this._startAnimation();

        return () => this.cleanup();
    },

    cleanup() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
            this.animationFrame = null;
        }
        if (this.resizeObserver) {
            this.resizeObserver.disconnect();
            this.resizeObserver = null;
        }
        if (this.historyChart) {
            this.historyChart.destroy();
            this.historyChart = null;
        }
        this.container = null;
        this.refs = {};
        this.data = null;
        this.visibleClients = [];
        this.clientLayout = [];
        this.particles = [];
        this.hoveredClientId = null;
        this.refreshInFlight = false;
        this.lastFrameAt = 0;
    },

    _renderShell() {
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="instance-traffic-page">
                <section class="instance-traffic-hero">
                    <div class="instance-traffic-hero-bg"></div>
                    <div class="instance-traffic-hero-header">
                        <div id="instance-traffic-status" class="instance-traffic-status">正在加载流量数据...</div>
                        <div class="instance-traffic-actions">
                            <button class="btn btn-secondary" id="instance-traffic-refresh" type="button">
                                <i data-lucide="refresh-cw"></i> 立即刷新
                            </button>
                        </div>
                    </div>
                    <div id="instance-traffic-stats" class="instance-traffic-stats"></div>
                    <div id="instance-traffic-topology" class="instance-traffic-topology">
                        <canvas id="instance-traffic-canvas" class="instance-traffic-canvas"></canvas>
                        <div class="instance-traffic-grid"></div>
                        <div class="instance-traffic-orbit orbit-1"></div>
                        <div class="instance-traffic-orbit orbit-2"></div>
                        <div class="instance-traffic-orbit orbit-3"></div>
                        <div class="instance-traffic-server" id="instance-traffic-server">
                            <div class="instance-traffic-server-rings"></div>
                            <div class="instance-traffic-server-core">
                                <div class="instance-traffic-server-icon">
                                    <i data-lucide="database"></i>
                                </div>
                                <div class="instance-traffic-server-title" id="instance-traffic-server-title">数据库实例</div>
                                <div class="instance-traffic-server-meta" id="instance-traffic-server-meta">等待数据...</div>
                            </div>
                        </div>
                        <div id="instance-traffic-client-layer" class="instance-traffic-client-layer"></div>
                        <div id="instance-traffic-empty" class="instance-traffic-empty hidden">
                            <div class="instance-traffic-empty-icon"><i data-lucide="scan-search"></i></div>
                            <div class="instance-traffic-empty-title">当前没有观测到客户端链路</div>
                            <div class="instance-traffic-empty-text">实例仍会继续轮询，一旦有会话接入会自动生成流量拓扑。</div>
                        </div>
                    </div>
                    <div class="instance-traffic-footer">
                        <div id="instance-traffic-mode-pill" class="instance-traffic-mode-pill">等待数据</div>
                        <div id="instance-traffic-legend" class="instance-traffic-legend"></div>
                    </div>
                </section>
                <section class="instance-traffic-side">
                    <div class="instance-panel instance-traffic-panel">
                        <div class="instance-traffic-panel-header">
                            <div>
                                <h3>总流量趋势</h3>
                            </div>
                        </div>
                        <div class="instance-traffic-chart-wrap">
                            <canvas id="instance-traffic-history-chart"></canvas>
                            <div id="instance-traffic-chart-empty" class="instance-traffic-chart-empty hidden">等待趋势数据...</div>
                        </div>
                    </div>
                    <div class="instance-panel instance-traffic-panel instance-traffic-list-panel">
                        <div class="instance-traffic-panel-header">
                            <div>
                                <h3>热点客户端</h3>
                            </div>
                        </div>
                        <div id="instance-traffic-client-list" class="instance-traffic-client-list"></div>
                    </div>
                </section>
            </div>
        `;
        DOM.createIcons();
    },

    _cacheRefs() {
        this.refs = {
            status: DOM.$('#instance-traffic-status', this.container),
            stats: DOM.$('#instance-traffic-stats', this.container),
            topology: DOM.$('#instance-traffic-topology', this.container),
            canvas: DOM.$('#instance-traffic-canvas', this.container),
            serverTitle: DOM.$('#instance-traffic-server-title', this.container),
            serverMeta: DOM.$('#instance-traffic-server-meta', this.container),
            clientLayer: DOM.$('#instance-traffic-client-layer', this.container),
            empty: DOM.$('#instance-traffic-empty', this.container),
            legend: DOM.$('#instance-traffic-legend', this.container),
            modePill: DOM.$('#instance-traffic-mode-pill', this.container),
            list: DOM.$('#instance-traffic-client-list', this.container),
            listSubtitle: DOM.$('#instance-traffic-list-subtitle', this.container),
            chartCanvas: DOM.$('#instance-traffic-history-chart', this.container),
            chartEmpty: DOM.$('#instance-traffic-chart-empty', this.container),
            refreshButton: DOM.$('#instance-traffic-refresh', this.container),
        };

        if (this.refs.canvas) {
            this.refs.ctx = this.refs.canvas.getContext('2d');
        }
    },

    _bindStaticEvents() {
        this.refs.refreshButton?.addEventListener('click', () => this._refresh({ silent: false }));
    },

    _observeResize() {
        if (!this.refs.topology || typeof ResizeObserver === 'undefined') {
            return;
        }

        this.resizeObserver = new ResizeObserver(() => {
            this._resizeCanvas();
            this._positionClientNodes();
            this._rebuildParticles();
        });
        this.resizeObserver.observe(this.refs.topology);
    },

    async _refresh({ showLoading = false, silent = true } = {}) {
        if (!this.datasourceId || this.refreshInFlight) {
            return;
        }

        const requestId = ++this.requestSerial;
        this.refreshInFlight = true;

        if (showLoading && this.refs.status) {
            this.refs.status.textContent = '正在加载流量数据...';
        }

        try {
            const data = await API.getInstanceTraffic(this.datasourceId);
            if (!this.container || requestId !== this.requestSerial) {
                return;
            }

            this.data = data || null;
            this.datasource = data?.datasource || this.datasource;
            this.pollIntervalSeconds = Math.max(3, parseInt(data?.poll_interval_seconds || 5, 10));
            this._applyData();
            this._schedulePolling();
        } catch (error) {
            if (!silent) {
                Toast.error(error.message || '加载流量监控失败');
            }
            if (this.refs.status) {
                this.refs.status.textContent = `流量数据加载失败：${error.message || '未知错误'}`;
            }
            if (this.refs.list) {
                this.refs.list.innerHTML = `
                    <div class="instance-traffic-list-empty">
                        <i data-lucide="triangle-alert"></i>
                        <span>${this._escapeHtml(error.message || '加载失败')}</span>
                    </div>
                `;
                DOM.createIcons();
            }
        } finally {
            if (requestId === this.requestSerial) {
                this.refreshInFlight = false;
            }
        }
    },

    _applyData() {
        if (!this.data) return;

        this.visibleClients = (this.data.clients || []).slice(0, 12);
        this._renderStatus();
        this._renderStats();
        this._renderServer();
        this._renderLegend();
        this._renderClientNodes();
        this._renderClientList();
        this._updateHistory();
        this._renderHistoryChart();
        this._resizeCanvas();
        this._positionClientNodes();
        this._rebuildParticles();

        const hasClients = (this.data.clients || []).length > 0;
        if (this.refs.empty) {
            this.refs.empty.classList.toggle('hidden', hasClients);
        }
        DOM.createIcons();
    },

    _renderStatus() {
        if (!this.refs.status || !this.data) return;
        const modeLabel = this._rateModeLabel(this.data.rate_mode);
        const updatedAt = this.data.captured_at ? new Date(this.data.captured_at).toLocaleTimeString() : '--';
        this.refs.status.textContent = `${this.data.rate_label} · ${modeLabel} · 上次刷新 ${updatedAt} · ${this.pollIntervalSeconds}s 自动轮询`;
    },

    _renderStats() {
        if (!this.refs.stats || !this.data) return;

        // 处理最大连接数：null、undefined、"null" 都显示为 --
        let maxSessionCount = '--';
        if (this.data.max_session_count != null && String(this.data.max_session_count).toLowerCase() !== 'null') {
            const parsed = Number(this.data.max_session_count);
            if (Number.isFinite(parsed) && parsed > 0) {
                maxSessionCount = String(parsed);
            }
        }

        const activeSessionCount = String(this.data.active_session_count || 0);
        const totalSessionCount = String(this.data.total_session_count || 0);
        const totalClientCount = String(this.data.total_client_count || 0);

        const hasTrafficData = this.data.rate_mode === 'measured';
        const txRate = hasTrafficData && this.data.total_tx_rate != null ? Format.networkRate(this.data.total_tx_rate) : '--';
        const rxRate = hasTrafficData && this.data.total_rx_rate != null ? Format.networkRate(this.data.total_rx_rate) : '--';

        let statsHtml = `
            <div class="instance-traffic-stat-card compact">
                <div class="instance-traffic-stat-label">客户端数量</div>
                <div class="instance-traffic-stat-value">${this._escapeHtml(totalClientCount)}</div>
            </div>
            <div class="instance-traffic-stat-card compact">
                <div class="instance-traffic-stat-label">会话数量</div>
                <div class="instance-traffic-stat-triple">
                    <span><strong>${this._escapeHtml(activeSessionCount)}</strong><em>活跃</em></span>
                    <span><strong>${this._escapeHtml(totalSessionCount)}</strong><em>总数</em></span>
                    <span><strong>${this._escapeHtml(maxSessionCount)}</strong><em>最大</em></span>
                </div>
            </div>
        `;

        // 只有在有实测流量数据时才显示网络流量卡片
        if (hasTrafficData) {
            statsHtml += `
                <div class="instance-traffic-stat-card compact">
                    <div class="instance-traffic-stat-label">网络流量</div>
                    <div class="instance-traffic-stat-pairs">
                        <span>发送 <strong>${this._escapeHtml(txRate)}</strong></span>
                        <span>接收 <strong>${this._escapeHtml(rxRate)}</strong></span>
                    </div>
                </div>
            `;
        }

        this.refs.stats.innerHTML = statsHtml;

        if (this.refs.modePill) {
            this.refs.modePill.className = `instance-traffic-mode-pill mode-${this._escapeHtml(this.data.rate_mode || 'unavailable')}`;
            const modeText = this.data.rate_mode === 'measured' ? '链路实测' : '无流量数据';
            this.refs.modePill.textContent = `${this._rateModeLabel(this.data.rate_mode)} · ${modeText}`;
        }
    },

    _renderServer() {
        if (!this.data) return;
        const datasource = this.data.datasource || this.datasource || {};
        if (this.refs.serverTitle) {
            this.refs.serverTitle.textContent = datasource.name || '数据库实例';
        }
        if (this.refs.serverMeta) {
            const metaParts = [
                datasource.db_type ? this._getDbTypeLabel(datasource.db_type) : null,
                datasource.host ? `${datasource.host}:${datasource.port}` : null,
                datasource.database || null,
            ].filter(Boolean);
            this.refs.serverMeta.textContent = metaParts.join(' / ') || '等待流量数据';
        }
    },

    _renderLegend() {
        if (!this.refs.legend || !this.data) return;

        const visibleCount = this.visibleClients.length;
        const hiddenCount = Math.max(0, (this.data.clients || []).length - visibleCount);
        const parts = [
            '<span class="legend-chip status-active">活跃 SQL</span>',
            '<span class="legend-chip status-waiting">等待 / 堵塞</span>',
            '<span class="legend-chip status-idle">空闲连接</span>',
        ];
        if (hiddenCount > 0) {
            parts.push(`<span class="legend-chip neutral">拓扑图显示前 ${visibleCount} 个热点，其余 ${hiddenCount} 个在右侧列表</span>`);
        }
        this.refs.legend.innerHTML = parts.join('');
    },

    _renderClientNodes() {
        if (!this.refs.clientLayer || !this.data) return;

        if (!this.visibleClients.length) {
            this.refs.clientLayer.innerHTML = '';
            this.clientLayout = [];
            return;
        }

        this.refs.clientLayer.innerHTML = this.visibleClients.map(client => `
            <button
                class="instance-traffic-client-node status-${this._escapeHtml(client.status || 'idle')}"
                type="button"
                data-client-id="${this._escapeAttr(client.client_id)}"
            >
                <span class="instance-traffic-client-glow"></span>
                <span class="instance-traffic-client-title">${this._escapeHtml(client.client_label)}</span>
                <span class="instance-traffic-client-meta">${this._escapeHtml(this._clientNodeMeta(client))}</span>
                <span class="instance-traffic-client-rate">${this._escapeHtml(this._clientRateLabel(client))}</span>
            </button>
        `).join('');

        DOM.$$('.instance-traffic-client-node', this.refs.clientLayer).forEach(node => {
            const clientId = node.dataset.clientId;
            node.addEventListener('mouseenter', () => this._setHoveredClient(clientId));
            node.addEventListener('mouseleave', () => this._setHoveredClient(null));
            node.addEventListener('click', () => {
                const client = (this.data.clients || []).find(item => item.client_id === clientId);
                if (client) {
                    this._showClientDetails(client);
                }
            });
        });
    },

    _renderClientList() {
        if (!this.refs.list || !this.data) return;

        const clients = this.data.clients || [];
        if (!clients.length) {
            this.refs.list.innerHTML = `
                <div class="instance-traffic-list-empty">
                    <i data-lucide="orbit"></i>
                    <span>等待客户端接入后生成链路榜单</span>
                </div>
            `;
            DOM.createIcons();
            return;
        }

        const visibleHint = this.data.rate_mode === 'measured' ? '按实时链路带宽排序' : '按会话活跃度热度排序';
        if (this.refs.listSubtitle) {
            this.refs.listSubtitle.textContent = visibleHint;
        }

        const maxRate = Math.max(...clients.map(item => item.estimated_total_rate || 0), 1);
        this.refs.list.innerHTML = clients.map((client, index) => {
            const barWidth = Math.max(8, Math.round(((client.estimated_total_rate || 0) / maxRate) * 100));
            return `
                <button
                    class="instance-traffic-list-item status-${this._escapeHtml(client.status || 'idle')}"
                    type="button"
                    data-client-id="${this._escapeAttr(client.client_id)}"
                >
                    <span class="instance-traffic-list-rank">${index + 1}</span>
                    <span class="instance-traffic-list-main">
                        <span class="instance-traffic-list-top">
                            <span class="instance-traffic-list-title">${this._escapeHtml(client.client_label)}</span>
                            <span class="instance-traffic-list-rate">${this._escapeHtml(this._clientRateLabel(client))}</span>
                        </span>
                        <span class="instance-traffic-list-meta">${this._escapeHtml(this._clientListMeta(client))}</span>
                        <span class="instance-traffic-list-bar"><span style="width:${barWidth}%"></span></span>
                    </span>
                </button>
            `;
        }).join('');

        DOM.$$('.instance-traffic-list-item', this.refs.list).forEach(item => {
            const clientId = item.dataset.clientId;
            item.addEventListener('mouseenter', () => this._setHoveredClient(clientId));
            item.addEventListener('mouseleave', () => this._setHoveredClient(null));
            item.addEventListener('click', () => {
                const client = clients.find(entry => entry.client_id === clientId);
                if (client) {
                    this._showClientDetails(client);
                }
            });
        });
    },

    _updateHistory() {
        if (!this.data) return;

        const backendHistory = Array.isArray(this.data.history) ? this.data.history : [];
        if (backendHistory.length) {
            this.historyPoints = backendHistory.map(item => ({
                timestamp: item.timestamp,
                rxRate: item.rx_rate,
                txRate: item.tx_rate,
                totalRate: item.total_rate,
                mode: item.mode || 'measured',
            }));
        }

        this._upsertHistoryPoint({
            timestamp: this.data.captured_at || new Date().toISOString(),
            rxRate: this.data.total_rx_rate,
            txRate: this.data.total_tx_rate,
            totalRate: this.data.total_rate,
            mode: this.data.rate_mode || 'unavailable',
        });
        this.historyPoints = this.historyPoints.slice(-36);
    },

    _upsertHistoryPoint(point) {
        if (!point || point.totalRate == null) return;
        const timestamp = new Date(point.timestamp).toISOString();
        const existingIndex = this.historyPoints.findIndex(item => new Date(item.timestamp).toISOString() === timestamp);
        const normalizedPoint = {
            timestamp,
            rxRate: point.rxRate,
            txRate: point.txRate,
            totalRate: point.totalRate,
            mode: point.mode || 'measured',
        };

        if (existingIndex >= 0) {
            this.historyPoints.splice(existingIndex, 1, normalizedPoint);
        } else {
            this.historyPoints.push(normalizedPoint);
        }
    },

    _renderHistoryChart() {
        if (!this.refs.chartCanvas) return;

        // 判断是否支持流量采集
        const supportsTraffic = this.data && this.data.rate_mode === 'measured';
        const validPoints = supportsTraffic ? this.historyPoints.filter(point => point.totalRate != null && point.mode === 'measured') : [];

        if (!validPoints.length) {
            if (this.refs.chartEmpty) {
                this.refs.chartEmpty.classList.remove('hidden');
                // 根据数据源类型显示不同提示
                if (this.data && this.data.rate_mode === 'unavailable') {
                    this.refs.chartEmpty.textContent = '当前数据库类型不支持网络流量采集';
                } else if (supportsTraffic) {
                    this.refs.chartEmpty.textContent = '等待趋势数据...';
                } else {
                    this.refs.chartEmpty.textContent = '等待趋势数据...';
                }
            }
            if (this.historyChart) {
                this.historyChart.data.labels = [];
                this.historyChart.data.datasets.forEach(dataset => {
                    dataset.data = [];
                });
                this.historyChart.update('none');
            }
            return;
        }

        if (this.refs.chartEmpty) {
            this.refs.chartEmpty.classList.add('hidden');
        }

        const labels = validPoints.map(point => this._formatChartLabel(point.timestamp));
        const rxData = validPoints.map(point => point.rxRate ?? null);
        const txData = validPoints.map(point => point.txRate ?? null);
        const totalData = validPoints.map(point => point.totalRate ?? null);

        if (!this.historyChart && typeof Chart !== 'undefined') {
            this.historyChart = new Chart(this.refs.chartCanvas, {
                type: 'line',
                data: {
                    labels,
                    datasets: [
                        {
                            label: '总带宽',
                            data: totalData,
                            borderColor: '#7dd3fc',
                            backgroundColor: 'rgba(125, 211, 252, 0.18)',
                            fill: true,
                            tension: 0.32,
                            borderWidth: 2,
                            pointRadius: 0,
                        },
                        {
                            label: '入站',
                            data: rxData,
                            borderColor: '#22c55e',
                            backgroundColor: 'rgba(34, 197, 94, 0.12)',
                            fill: false,
                            tension: 0.28,
                            borderWidth: 1.4,
                            pointRadius: 0,
                        },
                        {
                            label: '出站',
                            data: txData,
                            borderColor: '#f59e0b',
                            backgroundColor: 'rgba(245, 158, 11, 0.12)',
                            fill: false,
                            tension: 0.28,
                            borderWidth: 1.4,
                            pointRadius: 0,
                        },
                    ],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    layout: {
                        padding: {
                            top: 4,
                            bottom: 12,
                            left: 6,
                            right: 6,
                        },
                    },
                    interaction: {
                        mode: 'index',
                        intersect: false,
                    },
                    plugins: {
                        legend: {
                            labels: {
                                color: '#dbe6f4',
                                boxWidth: 10,
                                usePointStyle: true,
                                pointStyle: 'circle',
                                padding: 10,
                            },
                        },
                        tooltip: {
                            callbacks: {
                                label: (context) => `${context.dataset.label}: ${Format.networkRate(context.parsed?.y)}`,
                            },
                        },
                    },
                    scales: {
                        x: {
                            grid: {
                                color: 'rgba(148, 163, 184, 0.14)',
                            },
                            ticks: {
                                color: '#94a3b8',
                                maxTicksLimit: 6,
                                maxRotation: 0,
                                minRotation: 0,
                                autoSkip: true,
                                padding: 14,
                            },
                        },
                        y: {
                            grid: {
                                color: 'rgba(148, 163, 184, 0.14)',
                            },
                            ticks: {
                                color: '#94a3b8',
                                padding: 10,
                                callback: (value) => Format.networkRate(value),
                            },
                        },
                    },
                },
            });
        }

        if (!this.historyChart) return;

        this.historyChart.data.labels = labels;
        this.historyChart.data.datasets[0].data = totalData;
        this.historyChart.data.datasets[1].data = rxData;
        this.historyChart.data.datasets[2].data = txData;
        this.historyChart.update('none');
    },

    _resizeCanvas() {
        if (!this.refs.canvas || !this.refs.ctx || !this.refs.topology) return;

        const rect = this.refs.topology.getBoundingClientRect();
        if (!rect.width || !rect.height) return;

        const ratio = window.devicePixelRatio || 1;
        this.refs.canvas.width = Math.round(rect.width * ratio);
        this.refs.canvas.height = Math.round(rect.height * ratio);
        this.refs.canvas.style.width = `${rect.width}px`;
        this.refs.canvas.style.height = `${rect.height}px`;
        this.refs.ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    },

    _positionClientNodes() {
        if (!this.refs.topology || !this.refs.clientLayer) return;

        const topologyRect = this.refs.topology.getBoundingClientRect();
        const nodes = DOM.$$('.instance-traffic-client-node', this.refs.clientLayer);
        if (!nodes.length) {
            this.clientLayout = [];
            return;
        }

        const centerX = topologyRect.width / 2;
        const centerY = topologyRect.height / 2;
        const innerCount = nodes.length <= 8 ? nodes.length : Math.ceil(nodes.length * 0.52);
        const outerCount = Math.max(0, nodes.length - innerCount);
        const rings = [
            { count: innerCount, radiusX: topologyRect.width * 0.28, radiusY: topologyRect.height * 0.28, angleOffset: -Math.PI / 2 },
            { count: outerCount, radiusX: topologyRect.width * 0.39, radiusY: topologyRect.height * 0.36, angleOffset: -Math.PI / 2 + 0.18 },
        ];

        this.clientLayout = [];
        let index = 0;
        rings.forEach(ring => {
            for (let ringIndex = 0; ringIndex < ring.count; ringIndex += 1) {
                const node = nodes[index];
                const client = this.visibleClients[index];
                if (!node || !client) break;

                const angle = ring.angleOffset + (Math.PI * 2 * ringIndex) / Math.max(ring.count, 1);
                const nodeRect = node.getBoundingClientRect();
                const x = centerX + Math.cos(angle) * ring.radiusX - nodeRect.width / 2;
                const y = centerY + Math.sin(angle) * ring.radiusY - nodeRect.height / 2;

                node.style.left = `${Math.max(12, Math.min(topologyRect.width - nodeRect.width - 12, x))}px`;
                node.style.top = `${Math.max(12, Math.min(topologyRect.height - nodeRect.height - 12, y))}px`;

                const finalLeft = parseFloat(node.style.left || '0');
                const finalTop = parseFloat(node.style.top || '0');
                this.clientLayout.push({
                    clientId: client.client_id,
                    client,
                    x: finalLeft + nodeRect.width / 2,
                    y: finalTop + nodeRect.height / 2,
                });
                index += 1;
            }
        });
    },

    _rebuildParticles() {
        this.particles = this.clientLayout.flatMap(layout => {
            const count = Math.max(2, Math.min(8, Math.round((layout.client.heat_score || 0) / 18) + 2));
            return Array.from({ length: count }, (_, index) => ({
                clientId: layout.clientId,
                progress: Math.random(),
                speed: 0.08 + ((layout.client.heat_score || 0) / 100) * 0.22 + index * 0.01,
                direction: index % 2 === 0 ? 1 : -1,
                size: 1.8 + ((layout.client.heat_score || 0) / 100) * 2.4,
                alpha: 0.35 + Math.random() * 0.45,
            }));
        });
    },

    _startAnimation() {
        const tick = (timestamp) => {
            if (!this.container) return;
            if (!this.lastFrameAt) {
                this.lastFrameAt = timestamp;
            }
            const deltaSeconds = Math.min(0.08, (timestamp - this.lastFrameAt) / 1000);
            this.lastFrameAt = timestamp;
            this._drawTopology(deltaSeconds);
            this.animationFrame = requestAnimationFrame(tick);
        };
        this.animationFrame = requestAnimationFrame(tick);
    },

    _drawTopology(deltaSeconds) {
        const ctx = this.refs.ctx;
        const canvas = this.refs.canvas;
        const topology = this.refs.topology;
        if (!ctx || !canvas || !topology) return;

        const width = topology.clientWidth;
        const height = topology.clientHeight;
        if (!width || !height) return;

        ctx.clearRect(0, 0, width, height);
        const centerX = width / 2;
        const centerY = height / 2;
        ctx.save();
        ctx.globalCompositeOperation = 'screen';

        this.clientLayout.forEach(layout => {
            const color = this._statusColor(layout.client.status);
            const hovered = this.hoveredClientId === layout.clientId;
            const gradient = ctx.createLinearGradient(layout.x, layout.y, centerX, centerY);
            gradient.addColorStop(0, this._rgba(color, hovered ? 0.68 : 0.32));
            gradient.addColorStop(1, 'rgba(34, 211, 238, 0.12)');

            ctx.beginPath();
            ctx.setLineDash(hovered ? [] : [8, 11]);
            ctx.moveTo(layout.x, layout.y);
            ctx.lineTo(centerX, centerY);
            ctx.strokeStyle = gradient;
            ctx.lineWidth = 1.4 + ((layout.client.heat_score || 0) / 100) * 4 + (hovered ? 1.2 : 0);
            ctx.shadowColor = this._rgba(color, hovered ? 0.45 : 0.22);
            ctx.shadowBlur = hovered ? 18 : 8;
            ctx.stroke();

            ctx.setLineDash([]);
            ctx.beginPath();
            ctx.arc(layout.x, layout.y, hovered ? 5.5 : 3.2, 0, Math.PI * 2);
            ctx.fillStyle = this._rgba(color, hovered ? 0.95 : 0.66);
            ctx.fill();
        });

        this.particles.forEach(particle => {
            const layout = this.clientLayout.find(item => item.clientId === particle.clientId);
            if (!layout) return;

            particle.progress += particle.direction * particle.speed * deltaSeconds;
            if (particle.progress > 1) particle.progress = 0;
            if (particle.progress < 0) particle.progress = 1;

            const px = layout.x + (centerX - layout.x) * particle.progress;
            const py = layout.y + (centerY - layout.y) * particle.progress;
            const color = this._statusColor(layout.client.status);

            ctx.beginPath();
            ctx.arc(px, py, particle.size, 0, Math.PI * 2);
            ctx.fillStyle = this._rgba(color, particle.alpha);
            ctx.shadowColor = this._rgba(color, 0.72);
            ctx.shadowBlur = 12;
            ctx.fill();
        });

        ctx.restore();
    },

    _schedulePolling() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
        }
        this.pollTimer = setInterval(() => {
            this._refresh({ silent: true });
        }, this.pollIntervalSeconds * 1000);
    },

    _setHoveredClient(clientId) {
        this.hoveredClientId = clientId;
        DOM.$$('.instance-traffic-client-node', this.refs.clientLayer).forEach(node => {
            node.classList.toggle('is-hovered', !!clientId && node.dataset.clientId === clientId);
        });
        DOM.$$('.instance-traffic-list-item', this.refs.list).forEach(item => {
            item.classList.toggle('is-hovered', !!clientId && item.dataset.clientId === clientId);
        });
    },

    _showClientDetails(client) {
        const sqlHtml = (client.sql_samples || []).length
            ? client.sql_samples.map(sql => `<pre class="instance-inline-pre">${this._escapeHtml(sql)}</pre>`).join('')
            : '<div class="instance-inline-pre">暂无可展示 SQL</div>';

        Modal.show({
            title: `客户端链路详情 · ${client.client_label}`,
            content: `
                <div class="instance-traffic-modal">
                    <div class="instance-traffic-modal-grid">
                        <div class="instance-config-field">
                            <div class="instance-config-label">链路强度</div>
                            <div class="instance-config-value">${this._escapeHtml(this._clientRateLabel(client))}</div>
                        </div>
                        <div class="instance-config-field">
                            <div class="instance-config-label">会话概况</div>
                            <div class="instance-config-value">${this._escapeHtml(this._clientListMeta(client))}</div>
                        </div>
                        <div class="instance-config-field">
                            <div class="instance-config-label">用户</div>
                            <div class="instance-config-value">${this._escapeHtml((client.users || []).join(', ') || '-')}</div>
                        </div>
                        <div class="instance-config-field">
                            <div class="instance-config-label">数据库</div>
                            <div class="instance-config-value">${this._escapeHtml((client.databases || []).join(', ') || '-')}</div>
                        </div>
                    </div>
                    <div class="instance-config-field full">
                        <div class="instance-config-label">采样 SQL</div>
                        <div class="instance-config-value">${sqlHtml}</div>
                    </div>
                </div>
            `,
            buttons: [
                { text: '关闭', variant: 'secondary', onClick: () => Modal.hide() },
            ],
        });
    },

    _clientNodeMeta(client) {
        const parts = [`${client.session_count || 0} 会话`];
        if (client.active_session_count) {
            parts.push(`${client.active_session_count} 活跃`);
        }
        if (client.waiting_session_count) {
            parts.push(`${client.waiting_session_count} 等待`);
        }
        return parts.join(' / ');
    },

    _clientListMeta(client) {
        const parts = [
            `${client.session_count || 0} 会话`,
            `${client.active_session_count || 0} 活跃`,
            `${client.waiting_session_count || 0} 等待`,
        ];
        if (client.max_duration_seconds != null) {
            parts.push(`最长 ${Format.uptime(client.max_duration_seconds)}`);
        }
        return parts.join(' · ');
    },

    _clientRateLabel(client) {
        // 只有在有实测流量时才显示流量值，否则显示热度
        if (client.estimated_total_rate != null) {
            return Format.networkRate(client.estimated_total_rate);
        }
        return `热度 ${Math.round(client.heat_score || 0)}`;
    },

    _rateModeLabel(mode) {
        if (mode === 'measured') return '实测流量';
        return '暂无流量';
    },

    _getDbTypeLabel(dbType) {
        if (typeof InstanceDetailPage !== 'undefined' && typeof InstanceDetailPage._getDbTypeLabel === 'function') {
            return InstanceDetailPage._getDbTypeLabel(dbType);
        }
        return dbType || '-';
    },

    _statusColor(status) {
        if (status === 'active') return [34, 211, 238];
        if (status === 'waiting') return [245, 158, 11];
        if (status === 'idle') return [129, 140, 248];
        return [148, 163, 184];
    },

    _rgba(color, alpha) {
        return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`;
    },

    _formatChartLabel(dateInput) {
        const date = new Date(dateInput);
        if (Number.isNaN(date.getTime())) return '';
        return date.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    },

    _escapeHtml(value) {
        return Utils.escapeHtml(String(value ?? ''));
    },

    _escapeAttr(value) {
        return this._escapeHtml(value).replace(/"/g, '&quot;');
    },
};
