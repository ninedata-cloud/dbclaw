/* Host Detail Page */
const HostDetailPage = {
    hosts: [],
    currentHost: null,
    currentTab: 'info',
    currentRoute: {},
    tabCleanup: null,
    sidebarCollapsed: false,
    hostSearchText: '',
    processFilters: { search: '', user: '' },
    processSort: { field: 'cpu_percent', direction: 'desc' },
    processPollTimer: null,

    validTabs: ['info', 'monitor', 'ai', 'processes', 'network', 'terminal'],

    async render(routeParam = '') {
        this.cleanup();
        this.currentRoute = this._parseRoute(routeParam);
        this.sidebarCollapsed = localStorage.getItem('hostDetailSidebarCollapsed') === 'true';

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            // 加载主机列表
            this.hosts = await API.getHosts();

            if (this.hosts.length === 0) {
                Header.render('主机详情');
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="server"></i>
                        <h3>暂无主机</h3>
                        <p>请先添加主机，然后再进入主机详情工作台。</p>
                        <button class="btn btn-primary mt-16" onclick="Router.navigate('hosts')">前往主机管理</button>
                    </div>
                `;
                DOM.createIcons();
                return () => this.cleanup();
            }

            // 解析当前主机
            const resolvedHostId = this._resolveHostId(this.currentRoute.hostId);
            this.currentHost = this.hosts.find(h => h.id === resolvedHostId) || this.hosts[0];
            this.currentTab = this.validTabs.includes(this.currentRoute.tab) ? this.currentRoute.tab : 'info';

            // 渲染 Header 带主机信息
            this._renderHeader();

            // 渲染页面
            content.innerHTML = `
                <div id="host-detail-layout" class="host-detail-page ${this.sidebarCollapsed ? 'sidebar-collapsed' : ''}">
                    <aside id="host-detail-sidebar" class="host-detail-sidebar">
                        <div class="host-sidebar-header">
                            <div>
                                <div class="host-sidebar-title">主机列表</div>
                                <div class="host-sidebar-subtitle">主机运维工作台</div>
                            </div>
                            <button id="host-sidebar-toggle" class="host-sidebar-toggle" type="button">
                                <i data-lucide="${this.sidebarCollapsed ? 'panel-left-open' : 'panel-left-close'}"></i>
                            </button>
                        </div>
                        <div class="host-sidebar-search">
                            <input id="host-search-input" class="filter-input" type="text" placeholder="搜索主机名称或地址">
                        </div>
                        <div id="host-list" class="host-list"></div>
                    </aside>
                    <section class="host-detail-main">
                        <div id="host-tab-nav" class="host-tab-nav"></div>
                        <div id="host-tab-content" class="host-tab-content"></div>
                    </section>
                </div>
            `;

            this._renderHostList();
            this._renderTabNav();
            await this._renderCurrentTab();
            this._bindEvents();

            DOM.createIcons();
            return () => this.cleanup();
        } catch (error) {
            console.error('Failed to render host detail page:', error);
            content.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="alert-circle"></i>
                    <h3>加载失败</h3>
                    <p>${error.message}</p>
                </div>
            `;
            DOM.createIcons();
        }
    },

    _parseRoute(routeParam) {
        const params = new URLSearchParams(routeParam);
        return {
            hostId: params.get('host') ? parseInt(params.get('host')) : null,
            tab: params.get('tab') || 'info'
        };
    },

    _resolveHostId(hostId) {
        if (hostId && this.hosts.find(h => h.id === hostId)) {
            return hostId;
        }
        const lastHostId = localStorage.getItem('lastViewedHostId');
        if (lastHostId && this.hosts.find(h => h.id === parseInt(lastHostId))) {
            return parseInt(lastHostId);
        }
        return this.hosts[0]?.id;
    },

    _renderHeader() {
        const host = this.currentHost;
        const headerActions = `
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="text-align: right;">
                    <div style="font-size: 16px; font-weight: 600; color: var(--text-primary);">${Utils.escapeHtml(host.name)}</div>
                    <div style="font-size: 13px; color: var(--text-secondary); margin-top: 2px;">
                        ${Utils.escapeHtml(host.host)}:${host.port} · ${Utils.escapeHtml(host.username)}
                    </div>
                </div>
            </div>
        `;
        Header.render('主机详情', headerActions);
    },

    _renderHostList() {
        const container = DOM.$('#host-list');
        if (!container) return;

        const searchText = this.hostSearchText.toLowerCase();
        const filteredHosts = this.hosts.filter(h => 
            h.name.toLowerCase().includes(searchText) || 
            h.host.toLowerCase().includes(searchText)
        );

        // 按状态分组
        const groups = {
            normal: filteredHosts.filter(h => h.status === 'normal'),
            warning: filteredHosts.filter(h => h.status === 'warning'),
            critical: filteredHosts.filter(h => h.status === 'critical'),
            offline: filteredHosts.filter(h => h.status === 'offline' || h.status === 'unknown')
        };

        let html = '';
        const groupConfigs = [
            { key: 'normal', label: '正常', icon: 'check-circle', color: '#10b981' },
            { key: 'warning', label: '警告', icon: 'alert-triangle', color: '#f59e0b' },
            { key: 'critical', label: '严重', icon: 'alert-octagon', color: '#ef4444' },
            { key: 'offline', label: '离线', icon: 'x-circle', color: '#6b7280' }
        ];

        groupConfigs.forEach(({ key, label, icon, color }) => {
            if (groups[key].length > 0) {
                html += `<div class="host-list-group">`;
                html += `<div class="host-list-group-header">
                    <i data-lucide="${icon}" style="width:14px;height:14px;color:${color}"></i>
                    <span>${label} (${groups[key].length})</span>
                </div>`;
                groups[key].forEach(host => {
                    const isActive = host.id === this.currentHost?.id;
                    html += `
                        <div class="host-list-item ${isActive ? 'active' : ''}" data-host-id="${host.id}">
                            <div class="host-list-item-icon" style="background:${color}22">
                                <i data-lucide="server" style="width:16px;height:16px;color:${color}"></i>
                            </div>
                            <div class="host-list-item-info">
                                <div class="host-list-item-name">${Utils.escapeHtml(host.name)}</div>
                                <div class="host-list-item-meta">${Utils.escapeHtml(host.host)}:${host.port}</div>
                            </div>
                        </div>
                    `;
                });
                html += `</div>`;
            }
        });

        container.innerHTML = html || '<div style="padding:20px;text-align:center;color:var(--text-secondary)">无匹配主机</div>';
        DOM.createIcons();
    },

    async _renderHostHeader() {
        const container = DOM.$('#host-header-card');
        if (!container) return;

        try {
            const summary = await API.getHostSummary(this.currentHost.id);
            const host = summary.host;
            const metric = summary.latest_metric;

            // 状态判断
            let statusClass = 'unknown';
            let statusText = '未知';
            if (metric) {
                const now = new Date();
                const metricTime = new Date(metric.collected_at);
                const ageSeconds = (now - metricTime) / 1000;

                if (ageSeconds > 300) {
                    statusClass = 'offline';
                    statusText = '离线';
                } else if (metric.cpu_usage > 80 || metric.memory_usage > 80 || metric.disk_usage > 80) {
                    statusClass = 'critical';
                    statusText = '严重';
                } else if (metric.cpu_usage > 60 || metric.memory_usage > 60 || metric.disk_usage > 60) {
                    statusClass = 'warning';
                    statusText = '警告';
                } else {
                    statusClass = 'normal';
                    statusText = '正常';
                }
            }

            container.innerHTML = `
                <div class="host-header-content">
                    <div class="host-header-left">
                        <div class="host-header-status host-status-${statusClass}">
                            <i data-lucide="${statusClass === 'normal' ? 'check-circle' : statusClass === 'warning' ? 'alert-triangle' : statusClass === 'critical' ? 'alert-octagon' : 'x-circle'}"></i>
                            ${statusText}
                        </div>
                    </div>
                    <div class="host-header-right">
                        <div class="host-header-icon">
                            <i data-lucide="server"></i>
                        </div>
                        <div class="host-header-info">
                            <div class="host-header-title">${Utils.escapeHtml(host.name)}</div>
                            <div class="host-header-meta">
                                <span>${Utils.escapeHtml(host.host)}:${host.port}</span>
                                <span class="host-header-separator">•</span>
                                <span>${Utils.escapeHtml(host.username)}</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            DOM.createIcons();
        } catch (error) {
            console.error('Failed to render host header:', error);
        }
    },

    _renderTabNav() {
        const container = DOM.$('#host-tab-nav');
        if (!container) return;

        const tabs = [
            { id: 'info', label: '基本信息', icon: 'info' },
            { id: 'monitor', label: '性能监控', icon: 'activity' },
            { id: 'processes', label: '实时进程', icon: 'cpu' },
            { id: 'terminal', label: 'Terminal', icon: 'terminal' },
            { id: 'network', label: '网络拓扑', icon: 'network' },
            { id: 'ai', label: 'AI诊断', icon: 'sparkles' }
        ];

        container.innerHTML = tabs.map(tab => `
            <button class="host-tab-button ${tab.id === this.currentTab ? 'active' : ''}" data-tab="${tab.id}">
                <i data-lucide="${tab.icon}"></i>
                ${tab.label}
            </button>
        `).join('');

        DOM.createIcons();
    },

    async _renderCurrentTab() {
        if (this.tabCleanup) {
            this.tabCleanup();
            this.tabCleanup = null;
        }

        const container = DOM.$('#host-tab-content');
        if (!container) return;

        container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            switch (this.currentTab) {
                case 'info':
                    await this._renderInfoTab(container);
                    break;
                case 'monitor':
                    await this._renderMonitorTab(container);
                    break;
                case 'processes':
                    await this._renderProcessesTab(container);
                    break;
                case 'terminal':
                    await this._renderTerminalTab(container);
                    break;
                case 'network':
                    await this._renderNetworkTab(container);
                    break;
                case 'ai':
                    await this._renderAiTab(container);
                    break;
            }
        } catch (error) {
            console.error('Failed to render tab:', error);
            container.innerHTML = `<div class="empty-state"><i data-lucide="alert-circle"></i><p>加载失败: ${error.message}</p></div>`;
            DOM.createIcons();
        }
    },

    async _renderInfoTab(container) {
        const summary = await API.getHostSummary(this.currentHost.id);
        const host = summary.host;
        const metric = summary.latest_metric;
        const data = metric?.data || {};

        // 解析硬件配置
        const cpuCores = data.cpu_count || '未知';
        const memoryTotal = data.memory_total ? this._formatBytes(data.memory_total) : '未知';
        const diskTotal = data.disk_total ? this._formatBytes(data.disk_total) : '未知';
        const memoryUsed = data.memory_used ? this._formatBytes(data.memory_used) : '未知';
        const diskUsed = data.disk_used ? this._formatBytes(data.disk_used) : '未知';

        container.innerHTML = `
            <div class="host-info-section">
                <h3 class="host-info-section-title">硬件配置</h3>
                <div class="host-info-grid">
                    <div class="host-info-card">
                        <div class="host-info-card-title">CPU 核心数</div>
                        <div class="host-info-card-value">${cpuCores}</div>
                    </div>
                    <div class="host-info-card">
                        <div class="host-info-card-title">内存总量</div>
                        <div class="host-info-card-value">${memoryTotal}</div>
                    </div>
                    <div class="host-info-card">
                        <div class="host-info-card-title">磁盘总量</div>
                        <div class="host-info-card-value">${diskTotal}</div>
                    </div>
                    <div class="host-info-card">
                        <div class="host-info-card-title">操作系统</div>
                        <div class="host-info-card-value" style="font-size:14px">${Utils.escapeHtml(host.os_version || '未知')}</div>
                    </div>
                </div>
            </div>

            ${metric ? `
            <div class="host-info-section">
                <h3 class="host-info-section-title">实时状态</h3>
                <div class="host-info-grid">
                    <div class="host-info-card">
                        <div class="host-info-card-title">CPU 使用率</div>
                        <div class="host-info-card-value">${metric.cpu_usage?.toFixed(1) || 0}%</div>
                        <div class="host-info-card-meta">最后更新: ${new Date(metric.collected_at).toLocaleString()}</div>
                    </div>
                    <div class="host-info-card">
                        <div class="host-info-card-title">内存使用</div>
                        <div class="host-info-card-value">${metric.memory_usage?.toFixed(1) || 0}%</div>
                        <div class="host-info-card-meta">${memoryUsed} / ${memoryTotal}</div>
                    </div>
                    <div class="host-info-card">
                        <div class="host-info-card-title">磁盘使用</div>
                        <div class="host-info-card-value">${metric.disk_usage?.toFixed(1) || 0}%</div>
                        <div class="host-info-card-meta">${diskUsed} / ${diskTotal}</div>
                    </div>
                    <div class="host-info-card">
                        <div class="host-info-card-title">运行时间</div>
                        <div class="host-info-card-value" style="font-size:16px">${summary.uptime_seconds ? this._formatUptime(summary.uptime_seconds) : '未知'}</div>
                    </div>
                </div>
            </div>

            <div class="host-info-section">
                <h3 class="host-info-section-title">连接信息</h3>
                <div class="host-info-grid">
                    <div class="host-info-card">
                        <div class="host-info-card-title">主机地址</div>
                        <div class="host-info-card-value" style="font-size:16px">${Utils.escapeHtml(host.host)}:${host.port}</div>
                    </div>
                    <div class="host-info-card">
                        <div class="host-info-card-title">用户名</div>
                        <div class="host-info-card-value" style="font-size:16px">${Utils.escapeHtml(host.username)}</div>
                    </div>
                    <div class="host-info-card">
                        <div class="host-info-card-title">认证方式</div>
                        <div class="host-info-card-value" style="font-size:16px">${host.auth_type === 'password' ? '密码' : host.auth_type === 'key' ? '密钥' : 'Agent'}</div>
                    </div>
                    <div class="host-info-card">
                        <div class="host-info-card-title">进程数</div>
                        <div class="host-info-card-value">${summary.process_count || '未知'}</div>
                    </div>
                </div>
            </div>
            ` : '<p style="padding:20px;color:var(--text-secondary)">暂无指标数据</p>'}
        `;
    },

    async _renderMonitorTab(container) {
        container.innerHTML = `
            <div class="host-monitor-container">
                <div class="host-monitor-controls">
                    <select id="monitor-time-range" class="filter-input" style="width:150px">
                        <option value="1">最近 1 小时</option>
                        <option value="6">最近 6 小时</option>
                        <option value="24" selected>最近 24 小时</option>
                        <option value="72">最近 3 天</option>
                        <option value="168">最近 7 天</option>
                    </select>
                </div>
                <div class="host-monitor-charts">
                    <div class="host-monitor-chart">
                        <h3>CPU 使用率</h3>
                        <canvas id="cpu-chart"></canvas>
                    </div>
                    <div class="host-monitor-chart">
                        <h3>内存使用率</h3>
                        <canvas id="memory-chart"></canvas>
                    </div>
                    <div class="host-monitor-chart">
                        <h3>磁盘使用率</h3>
                        <canvas id="disk-chart"></canvas>
                    </div>
                </div>
            </div>
        `;

        await this._loadMonitorData(24);

        // 时间范围切换
        DOM.$('#monitor-time-range')?.addEventListener('change', async (e) => {
            await this._loadMonitorData(parseInt(e.target.value));
        });

        this.tabCleanup = () => {
            // 清理图表实例
            if (window.hostMonitorCharts) {
                Object.values(window.hostMonitorCharts).forEach(chart => chart.destroy());
                window.hostMonitorCharts = null;
            }
        };
    },

    async _loadMonitorData(hours) {
        try {
            const data = await API.getHostMetrics(this.currentHost.id, `hours=${hours}`);
            this._renderMonitorCharts(data.metrics);
        } catch (error) {
            console.error('Failed to load monitor data:', error);
        }
    },

    _renderMonitorCharts(metrics) {
        if (!window.Chart) {
            console.error('Chart.js not loaded');
            return;
        }

        // 清理旧图表
        if (window.hostMonitorCharts) {
            Object.values(window.hostMonitorCharts).forEach(chart => chart.destroy());
        }

        window.hostMonitorCharts = {};

        const labels = metrics.map(m => new Date(m.collected_at).toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit'
        }));

        const chartConfig = (label, data, color) => ({
            type: 'line',
            data: {
                labels,
                datasets: [{
                    label,
                    data,
                    borderColor: color,
                    backgroundColor: color + '20',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        max: 100,
                        ticks: {
                            callback: value => value + '%'
                        }
                    }
                }
            }
        });

        // CPU 图表
        const cpuCanvas = DOM.$('#cpu-chart');
        if (cpuCanvas) {
            window.hostMonitorCharts.cpu = new Chart(cpuCanvas, chartConfig(
                'CPU 使用率',
                metrics.map(m => m.cpu_usage || 0),
                '#3b82f6'
            ));
        }

        // 内存图表
        const memoryCanvas = DOM.$('#memory-chart');
        if (memoryCanvas) {
            window.hostMonitorCharts.memory = new Chart(memoryCanvas, chartConfig(
                '内存使用率',
                metrics.map(m => m.memory_usage || 0),
                '#10b981'
            ));
        }

        // 磁盘图表
        const diskCanvas = DOM.$('#disk-chart');
        if (diskCanvas) {
            window.hostMonitorCharts.disk = new Chart(diskCanvas, chartConfig(
                '磁盘使用率',
                metrics.map(m => m.disk_usage || 0),
                '#f59e0b'
            ));
        }
    },

    async _renderProcessesTab(container) {
        const processes = await API.getHostProcesses(this.currentHost.id);
        
        container.innerHTML = `
            <div style="margin-bottom:16px">
                <input type="text" class="filter-input" id="process-search" placeholder="搜索进程..." style="max-width:300px">
            </div>
            <table class="host-process-table">
                <thead>
                    <tr>
                        <th data-sort="pid">PID</th>
                        <th data-sort="user">用户</th>
                        <th data-sort="cpu_percent">CPU %</th>
                        <th data-sort="memory_percent">内存 %</th>
                        <th data-sort="state">状态</th>
                        <th>命令</th>
                    </tr>
                </thead>
                <tbody id="process-table-body"></tbody>
            </table>
        `;

        this._renderProcessTable(processes);
        
        // 定时刷新
        this.processPollTimer = setInterval(async () => {
            const updated = await API.getHostProcesses(this.currentHost.id);
            this._renderProcessTable(updated);
        }, 5000);

        this.tabCleanup = () => {
            if (this.processPollTimer) {
                clearInterval(this.processPollTimer);
                this.processPollTimer = null;
            }
        };
    },

    _renderProcessTable(processes) {
        const tbody = DOM.$('#process-table-body');
        if (!tbody) return;

        // 保存原始数据供搜索和排序使用
        tbody.dataset.processes = JSON.stringify(processes);

        const searchText = this.processFilters.search.toLowerCase();
        const filtered = processes.filter(p =>
            p.command.toLowerCase().includes(searchText) ||
            p.user.toLowerCase().includes(searchText)
        );

        // 排序
        filtered.sort((a, b) => {
            const field = this.processSort.field;
            const dir = this.processSort.direction === 'asc' ? 1 : -1;
            return (a[field] > b[field] ? 1 : -1) * dir;
        });

        tbody.innerHTML = filtered.map(p => `
            <tr>
                <td>${p.pid}</td>
                <td>${Utils.escapeHtml(p.user)}</td>
                <td>${p.cpu_percent.toFixed(1)}%</td>
                <td>${p.memory_percent.toFixed(1)}%</td>
                <td>${Utils.escapeHtml(p.state)}</td>
                <td class="host-process-command" title="${Utils.escapeHtml(p.command)}">${Utils.escapeHtml(p.command)}</td>
            </tr>
        `).join('');
    },

    async _renderTerminalTab(container) {
        this.tabCleanup = await HostTerminal.render(container, this.currentHost.id);
    },

    async _renderNetworkTab(container) {
        this.tabCleanup = await HostNetworkPage.render({
            container,
            hostId: this.currentHost.id,
            host: this.currentHost
        });
    },

    async _renderAiTab(container) {
        const hostId = this.currentHost.id;

        // 调用 DiagnosisPage 嵌入式渲染
        this.tabCleanup = await DiagnosisPage.renderWithOptions({
            container,
            embedded: true,
            fixedHostId: hostId,
            sessionFilterHostId: hostId,
            defaultSidebarCollapsed: true,
            initialAsk: null,
            preferFreshSession: false,
        });
    },

    _formatUptime(seconds) {
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${days}天 ${hours}小时 ${minutes}分钟`;
    },

    _formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i];
    },

    _bindEvents() {
        // 侧边栏折叠
        DOM.$('#host-sidebar-toggle')?.addEventListener('click', () => {
            this.sidebarCollapsed = !this.sidebarCollapsed;
            localStorage.setItem('hostDetailSidebarCollapsed', this.sidebarCollapsed);
            DOM.$('#host-detail-layout')?.classList.toggle('sidebar-collapsed');
            DOM.$('#host-sidebar-toggle i')?.setAttribute('data-lucide', this.sidebarCollapsed ? 'panel-left-open' : 'panel-left-close');
            DOM.createIcons();
        });

        // 主机搜索
        DOM.$('#host-search-input')?.addEventListener('input', (e) => {
            this.hostSearchText = e.target.value;
            this._renderHostList();
        });

        // 主机列表点击
        DOM.$('#host-list')?.addEventListener('click', async (e) => {
            const item = e.target.closest('.host-list-item');
            if (item) {
                const hostId = parseInt(item.dataset.hostId);
                const host = this.hosts.find(h => h.id === hostId);
                if (host) {
                    this.currentHost = host;
                    localStorage.setItem('lastViewedHostId', hostId);
                    this._renderHeader();
                    Router.navigate(`host-detail?host=${hostId}&tab=${this.currentTab}`);
                }
            }
        });

        // Tab 切换
        DOM.$('#host-tab-nav')?.addEventListener('click', (e) => {
            const btn = e.target.closest('.host-tab-button');
            if (btn) {
                const tab = btn.dataset.tab;
                if (tab && this.validTabs.includes(tab)) {
                    this.currentTab = tab;
                    Router.navigate(`host-detail?host=${this.currentHost.id}&tab=${tab}`);
                }
            }
        });

        // 进程搜索
        DOM.$('#process-search')?.addEventListener('input', (e) => {
            this.processFilters.search = e.target.value;
            // 立即重新渲染进程表格
            if (this.currentTab === 'processes') {
                const tbody = DOM.$('#process-table-body');
                if (tbody && tbody.dataset.processes) {
                    this._renderProcessTable(JSON.parse(tbody.dataset.processes));
                }
            }
        });

        // 进程表头排序
        DOM.$('.host-process-table thead')?.addEventListener('click', (e) => {
            const th = e.target.closest('th[data-sort]');
            if (th) {
                const field = th.dataset.sort;
                if (this.processSort.field === field) {
                    this.processSort.direction = this.processSort.direction === 'asc' ? 'desc' : 'asc';
                } else {
                    this.processSort.field = field;
                    this.processSort.direction = 'desc';
                }
                // 重新渲染进程表格
                const tbody = DOM.$('#process-table-body');
                if (tbody && tbody.dataset.processes) {
                    this._renderProcessTable(JSON.parse(tbody.dataset.processes));
                }
            }
        });
    },

    cleanup() {
        if (this.tabCleanup) {
            this.tabCleanup();
            this.tabCleanup = null;
        }
        if (this.processPollTimer) {
            clearInterval(this.processPollTimer);
            this.processPollTimer = null;
        }
    }
};
