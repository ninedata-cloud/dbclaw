/* Host Network Topology Page - 参考实例流量拓扑样式 */
const HostNetworkPage = {
    container: null,
    hostId: null,
    host: null,
    refs: {},
    data: null,
    visibleNodes: [],
    nodeLayout: [],
    particles: [],
    hoveredNodeId: null,
    pollTimer: null,
    animationFrame: null,
    resizeObserver: null,
    refreshInFlight: false,
    requestSerial: 0,
    lastFrameAt: 0,
    pollIntervalSeconds: 10,

    async render({ container, hostId, host }) {
        this.cleanup();

        this.container = container;
        this.hostId = hostId;
        this.host = host || null;
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
        this.container = null;
        this.refs = {};
        this.data = null;
        this.visibleNodes = [];
        this.nodeLayout = [];
        this.particles = [];
        this.hoveredNodeId = null;
        this.refreshInFlight = false;
        this.lastFrameAt = 0;
    },

    _renderShell() {
        if (!this.container) return;

        this.container.innerHTML = `
            <div class="host-network-page">
                <section class="host-network-hero">
                    <div class="host-network-hero-bg"></div>
                    <div class="host-network-hero-header">
                        <div id="host-network-status" class="host-network-status">正在加载网络拓扑...</div>
                        <div class="host-network-actions">
                            <button class="btn btn-secondary" id="host-network-refresh" type="button">
                                <i data-lucide="refresh-cw"></i> 立即刷新
                            </button>
                        </div>
                    </div>
                    <div id="host-network-stats" class="host-network-stats"></div>
                    <div id="host-network-topology" class="host-network-topology">
                        <canvas id="host-network-canvas" class="host-network-canvas"></canvas>
                        <div class="host-network-grid"></div>
                        <div class="host-network-orbit orbit-1"></div>
                        <div class="host-network-orbit orbit-2"></div>
                        <div class="host-network-orbit orbit-3"></div>
                        <div class="host-network-server" id="host-network-server">
                            <div class="host-network-server-rings"></div>
                            <div class="host-network-server-core">
                                <div class="host-network-server-icon">
                                    <i data-lucide="server"></i>
                                </div>
                                <div class="host-network-server-title" id="host-network-server-title">主机</div>
                                <div class="host-network-server-meta" id="host-network-server-meta">等待数据...</div>
                            </div>
                        </div>
                        <div id="host-network-node-layer" class="host-network-node-layer"></div>
                        <div id="host-network-empty" class="host-network-empty hidden">
                            <div class="host-network-empty-icon"><i data-lucide="scan-search"></i></div>
                            <div class="host-network-empty-title">当前没有观测到网络连接</div>
                            <div class="host-network-empty-text">主机仍会继续轮询，一旦有连接建立会自动生成网络拓扑。</div>
                        </div>
                    </div>
                    <div class="host-network-footer">
                        <div id="host-network-legend" class="host-network-legend"></div>
                    </div>
                </section>
                <section class="host-network-side">
                    <div class="instance-panel host-network-panel host-network-list-panel">
                        <div class="host-network-panel-header">
                            <div>
                                <h3>热点连接</h3>
                                <div class="host-network-panel-subtitle">按连接数排序</div>
                            </div>
                        </div>
                        <div id="host-network-node-list" class="host-network-node-list"></div>
                    </div>
                </section>
            </div>
        `;
        DOM.createIcons();
    },

    _cacheRefs() {
        this.refs = {
            status: DOM.$('#host-network-status', this.container),
            stats: DOM.$('#host-network-stats', this.container),
            topology: DOM.$('#host-network-topology', this.container),
            canvas: DOM.$('#host-network-canvas', this.container),
            serverTitle: DOM.$('#host-network-server-title', this.container),
            serverMeta: DOM.$('#host-network-server-meta', this.container),
            nodeLayer: DOM.$('#host-network-node-layer', this.container),
            empty: DOM.$('#host-network-empty', this.container),
            legend: DOM.$('#host-network-legend', this.container),
            list: DOM.$('#host-network-node-list', this.container),
            refreshButton: DOM.$('#host-network-refresh', this.container),
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
            this._positionNodes();
            this._rebuildParticles();
        });
        this.resizeObserver.observe(this.refs.topology);
    },

    async _refresh({ showLoading = false, silent = true } = {}) {
        if (!this.hostId || this.refreshInFlight) {
            return;
        }

        const requestId = ++this.requestSerial;
        this.refreshInFlight = true;

        if (showLoading && this.refs.status) {
            this.refs.status.textContent = '正在加载网络拓扑...';
        }

        try {
            const data = await API.getHostNetworkTopology(this.hostId);
            if (!this.container || requestId !== this.requestSerial) {
                return;
            }

            this.data = data || null;
            this.host = data?.host || this.host;
            this._applyData();
            this._schedulePolling();
        } catch (error) {
            if (!silent) {
                Toast.error(error.message || '加载网络拓扑失败');
            }
            if (this.refs.status) {
                this.refs.status.textContent = `网络拓扑加载失败：${error.message || '未知错误'}`;
            }
            if (this.refs.list) {
                this.refs.list.innerHTML = `
                    <div class="host-network-list-empty">
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

        this.visibleNodes = (this.data.connections || []).slice(0, 16);
        this._renderStatus();
        this._renderStats();
        this._renderServer();
        this._renderLegend();
        this._renderNodes();
        this._renderNodeList();
        this._resizeCanvas();
        this._positionNodes();
        this._rebuildParticles();

        const hasNodes = (this.data.connections || []).length > 0;
        if (this.refs.empty) {
            this.refs.empty.classList.toggle('hidden', hasNodes);
        }
        DOM.createIcons();
    },

    _renderStatus() {
        if (!this.refs.status || !this.data) return;
        const updatedAt = new Date().toLocaleTimeString();
        this.refs.status.textContent = `网络拓扑 · 上次刷新 ${updatedAt} · ${this.pollIntervalSeconds}s 自动轮询`;
    },

    _renderStats() {
        if (!this.refs.stats || !this.data) return;

        const stats = this.data.stats || {};
        const totalConnections = String(stats.total_connections || 0);
        const established = String(stats.established || 0);
        const timeWait = String(stats.time_wait || 0);
        const listen = String(stats.listen || 0);
        const uniqueIps = String((this.data.connections || []).length);

        this.refs.stats.innerHTML = `
            <div class="host-network-stat-card compact">
                <div class="host-network-stat-label">总连接数</div>
                <div class="host-network-stat-value">${this._escapeHtml(totalConnections)}</div>
            </div>
            <div class="host-network-stat-card compact">
                <div class="host-network-stat-label">连接状态</div>
                <div class="host-network-stat-triple">
                    <span><strong>${this._escapeHtml(established)}</strong><em>已建立</em></span>
                    <span><strong>${this._escapeHtml(timeWait)}</strong><em>等待</em></span>
                    <span><strong>${this._escapeHtml(listen)}</strong><em>监听</em></span>
                </div>
            </div>
            <div class="host-network-stat-card compact">
                <div class="host-network-stat-label">远程节点</div>
                <div class="host-network-stat-value">${this._escapeHtml(uniqueIps)}</div>
            </div>
        `;
    },

    _renderServer() {
        if (!this.data) return;
        const host = this.data.host || this.host || {};
        if (this.refs.serverTitle) {
            this.refs.serverTitle.textContent = host.name || '主机';
        }
        if (this.refs.serverMeta) {
            const metaParts = [
                host.host ? `${host.host}:${host.port}` : null,
            ].filter(Boolean);
            this.refs.serverMeta.textContent = metaParts.join(' / ') || '等待网络数据';
        }
    },

    _renderLegend() {
        if (!this.refs.legend || !this.data) return;

        const visibleCount = this.visibleNodes.length;
        const hiddenCount = Math.max(0, (this.data.connections || []).length - visibleCount);
        const parts = [
            '<span class="legend-chip status-established">已建立连接</span>',
            '<span class="legend-chip status-time-wait">TIME_WAIT</span>',
            '<span class="legend-chip status-listen">监听端口</span>',
        ];
        if (hiddenCount > 0) {
            parts.push(`<span class="legend-chip neutral">拓扑图显示前 ${visibleCount} 个热点，其余 ${hiddenCount} 个在右侧列表</span>`);
        }
        this.refs.legend.innerHTML = parts.join('');
    },

    _renderNodes() {
        if (!this.refs.nodeLayer || !this.data) return;

        if (!this.visibleNodes.length) {
            this.refs.nodeLayer.innerHTML = '';
            this.nodeLayout = [];
            return;
        }

        this.refs.nodeLayer.innerHTML = this.visibleNodes.map(node => `
            <button
                class="host-network-node status-${this._escapeHtml(this._getNodeStatus(node))}"
                type="button"
                data-node-id="${this._escapeAttr(node.remote_ip)}"
            >
                <span class="host-network-node-glow"></span>
                <span class="host-network-node-title">${this._escapeHtml(node.remote_ip)}</span>
                <span class="host-network-node-meta">${this._escapeHtml(this._nodeMetaText(node))}</span>
                <span class="host-network-node-count">${this._escapeHtml(String(node.connection_count))}</span>
            </button>
        `).join('');

        DOM.$$('.host-network-node', this.refs.nodeLayer).forEach(nodeEl => {
            const nodeId = nodeEl.dataset.nodeId;
            nodeEl.addEventListener('mouseenter', () => this._setHoveredNode(nodeId));
            nodeEl.addEventListener('mouseleave', () => this._setHoveredNode(null));
            nodeEl.addEventListener('click', () => {
                const node = (this.data.connections || []).find(item => item.remote_ip === nodeId);
                if (node) {
                    this._showNodeDetails(node);
                }
            });
        });
    },

    _renderNodeList() {
        if (!this.refs.list || !this.data) return;

        const nodes = this.data.connections || [];
        if (!nodes.length) {
            this.refs.list.innerHTML = `
                <div class="host-network-list-empty">
                    <i data-lucide="orbit"></i>
                    <span>等待网络连接后生成拓扑榜单</span>
                </div>
            `;
            DOM.createIcons();
            return;
        }

        const maxCount = Math.max(...nodes.map(item => item.connection_count || 0), 1);
        this.refs.list.innerHTML = nodes.map((node, index) => {
            const barWidth = Math.max(8, Math.round(((node.connection_count || 0) / maxCount) * 100));
            return `
                <button
                    class="host-network-list-item status-${this._escapeHtml(this._getNodeStatus(node))}"
                    type="button"
                    data-node-id="${this._escapeAttr(node.remote_ip)}"
                >
                    <span class="host-network-list-rank">${index + 1}</span>
                    <span class="host-network-list-main">
                        <span class="host-network-list-top">
                            <span class="host-network-list-title">${this._escapeHtml(node.remote_ip)}</span>
                            <span class="host-network-list-count">${this._escapeHtml(String(node.connection_count))} 连接</span>
                        </span>
                        <span class="host-network-list-meta">${this._escapeHtml(this._nodeListMetaText(node))}</span>
                        <span class="host-network-list-bar"><span style="width:${barWidth}%"></span></span>
                    </span>
                </button>
            `;
        }).join('');

        DOM.$$('.host-network-list-item', this.refs.list).forEach(item => {
            const nodeId = item.dataset.nodeId;
            item.addEventListener('mouseenter', () => this._setHoveredNode(nodeId));
            item.addEventListener('mouseleave', () => this._setHoveredNode(null));
            item.addEventListener('click', () => {
                const node = nodes.find(entry => entry.remote_ip === nodeId);
                if (node) {
                    this._showNodeDetails(node);
                }
            });
        });
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

    _positionNodes() {
        if (!this.refs.topology || !this.refs.nodeLayer) return;

        const topologyRect = this.refs.topology.getBoundingClientRect();
        const nodeEls = DOM.$$('.host-network-node', this.refs.nodeLayer);
        if (!nodeEls.length) {
            this.nodeLayout = [];
            return;
        }

        const centerX = topologyRect.width / 2;
        const centerY = topologyRect.height / 2;
        const innerCount = nodeEls.length <= 8 ? nodeEls.length : Math.ceil(nodeEls.length * 0.52);
        const outerCount = Math.max(0, nodeEls.length - innerCount);
        const rings = [
            { count: innerCount, radiusX: topologyRect.width * 0.28, radiusY: topologyRect.height * 0.28, angleOffset: -Math.PI / 2 },
            { count: outerCount, radiusX: topologyRect.width * 0.39, radiusY: topologyRect.height * 0.36, angleOffset: -Math.PI / 2 + 0.18 },
        ];

        this.nodeLayout = [];
        let index = 0;
        rings.forEach(ring => {
            for (let ringIndex = 0; ringIndex < ring.count; ringIndex += 1) {
                const nodeEl = nodeEls[index];
                const node = this.visibleNodes[index];
                if (!nodeEl || !node) break;

                const angle = ring.angleOffset + (Math.PI * 2 * ringIndex) / Math.max(ring.count, 1);
                const nodeRect = nodeEl.getBoundingClientRect();
                const x = centerX + Math.cos(angle) * ring.radiusX - nodeRect.width / 2;
                const y = centerY + Math.sin(angle) * ring.radiusY - nodeRect.height / 2;

                nodeEl.style.left = `${Math.max(12, Math.min(topologyRect.width - nodeRect.width - 12, x))}px`;
                nodeEl.style.top = `${Math.max(12, Math.min(topologyRect.height - nodeRect.height - 12, y))}px`;

                const finalLeft = parseFloat(nodeEl.style.left || '0');
                const finalTop = parseFloat(nodeEl.style.top || '0');
                this.nodeLayout.push({
                    nodeId: node.remote_ip,
                    node,
                    x: finalLeft + nodeRect.width / 2,
                    y: finalTop + nodeRect.height / 2,
                });
                index += 1;
            }
        });
    },

    _rebuildParticles() {
        this.particles = this.nodeLayout.flatMap(layout => {
            const count = Math.max(2, Math.min(8, Math.round((layout.node.connection_count || 0) / 5) + 2));
            return Array.from({ length: count }, (_, index) => ({
                nodeId: layout.nodeId,
                progress: Math.random(),
                speed: 0.08 + ((layout.node.connection_count || 0) / 50) * 0.22 + index * 0.01,
                direction: index % 2 === 0 ? 1 : -1,
                size: 1.8 + ((layout.node.connection_count || 0) / 50) * 2.4,
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

        this.nodeLayout.forEach(layout => {
            const color = this._statusColor(this._getNodeStatus(layout.node));
            const hovered = this.hoveredNodeId === layout.nodeId;
            const gradient = ctx.createLinearGradient(layout.x, layout.y, centerX, centerY);
            gradient.addColorStop(0, this._rgba(color, hovered ? 0.68 : 0.32));
            gradient.addColorStop(1, 'rgba(34, 211, 238, 0.12)');

            ctx.beginPath();
            ctx.setLineDash(hovered ? [] : [8, 11]);
            ctx.moveTo(layout.x, layout.y);
            ctx.lineTo(centerX, centerY);
            ctx.strokeStyle = gradient;
            ctx.lineWidth = 1.4 + ((layout.node.connection_count || 0) / 20) * 4 + (hovered ? 1.2 : 0);
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
            const layout = this.nodeLayout.find(item => item.nodeId === particle.nodeId);
            if (!layout) return;

            particle.progress += particle.direction * particle.speed * deltaSeconds;
            if (particle.progress > 1) particle.progress = 0;
            if (particle.progress < 0) particle.progress = 1;

            const px = layout.x + (centerX - layout.x) * particle.progress;
            const py = layout.y + (centerY - layout.y) * particle.progress;
            const color = this._statusColor(this._getNodeStatus(layout.node));

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

    _setHoveredNode(nodeId) {
        this.hoveredNodeId = nodeId;
        DOM.$$('.host-network-node', this.refs.nodeLayer).forEach(nodeEl => {
            nodeEl.classList.toggle('is-hovered', !!nodeId && nodeEl.dataset.nodeId === nodeId);
        });
        DOM.$$('.host-network-list-item', this.refs.list).forEach(item => {
            item.classList.toggle('is-hovered', !!nodeId && item.dataset.nodeId === nodeId);
        });
    },

    _showNodeDetails(node) {
        const statesHtml = Object.entries(node.states || {})
            .filter(([_, count]) => count > 0)
            .map(([state, count]) => `<div class="host-network-state-item"><span class="host-network-state-badge status-${this._escapeHtml(state.toLowerCase())}">${this._escapeHtml(state)}</span><span>${count}</span></div>`)
            .join('');

        Modal.show({
            title: `网络节点详情 · ${node.remote_ip}`,
            content: `
                <div class="host-network-modal">
                    <div class="host-network-modal-grid">
                        <div class="instance-config-field">
                            <div class="instance-config-label">远程 IP</div>
                            <div class="instance-config-value"><code>${this._escapeHtml(node.remote_ip)}</code></div>
                        </div>
                        <div class="instance-config-field">
                            <div class="instance-config-label">连接数</div>
                            <div class="instance-config-value">${this._escapeHtml(String(node.connection_count))}</div>
                        </div>
                    </div>
                    <div class="instance-config-field full">
                        <div class="instance-config-label">连接状态分布</div>
                        <div class="host-network-states">${statesHtml || '<div style="color:var(--text-secondary)">无状态数据</div>'}</div>
                    </div>
                </div>
            `,
            buttons: [
                { text: '关闭', variant: 'secondary', onClick: () => Modal.hide() },
            ],
        });
    },

    _getNodeStatus(node) {
        const states = node.states || {};
        if (states.ESTABLISHED || states.ESTAB) return 'established';
        if (states.TIME_WAIT) return 'time-wait';
        if (states.LISTEN) return 'listen';
        return 'other';
    },

    _nodeMetaText(node) {
        const states = node.states || {};
        const parts = [];
        if (states.ESTABLISHED || states.ESTAB) parts.push(`${states.ESTABLISHED || states.ESTAB} 已建立`);
        if (states.TIME_WAIT) parts.push(`${states.TIME_WAIT} 等待`);
        if (states.LISTEN) parts.push(`${states.LISTEN} 监听`);
        return parts.join(' / ') || `${node.connection_count} 连接`;
    },

    _nodeListMetaText(node) {
        const states = node.states || {};
        const parts = [];
        if (states.ESTABLISHED || states.ESTAB) parts.push(`${states.ESTABLISHED || states.ESTAB} 已建立`);
        if (states.TIME_WAIT) parts.push(`${states.TIME_WAIT} 等待`);
        if (states.LISTEN) parts.push(`${states.LISTEN} 监听`);
        const otherCount = node.connection_count - (states.ESTABLISHED || 0) - (states.ESTAB || 0) - (states.TIME_WAIT || 0) - (states.LISTEN || 0);
        if (otherCount > 0) parts.push(`${otherCount} 其他`);
        return parts.join(' · ') || '无状态数据';
    },

    _statusColor(status) {
        if (status === 'established') return [16, 185, 129];
        if (status === 'time-wait') return [245, 158, 11];
        if (status === 'listen') return [59, 130, 246];
        return [148, 163, 184];
    },

    _rgba(color, alpha) {
        return `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${alpha})`;
    },

    _escapeHtml(value) {
        return Utils.escapeHtml(String(value ?? ''));
    },

    _escapeAttr(value) {
        return this._escapeHtml(value).replace(/"/g, '&quot;');
    },
};
