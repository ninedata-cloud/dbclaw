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
    currentTimeRange: 60, // default 1 hour in minutes

    validTabs: ['info', 'monitor', 'ai', 'processes', 'network', 'terminal'],

    /**
     * 解析后端返回的 UTC 时间字符串为本地 Date 对象
     * 后端存储的是 UTC naive datetime，返回时没有时区标识
     */
    _parseUTCDateTime(dateInput) {
        const parsed = Format.parseDate(dateInput);
        if (parsed) return parsed;

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

    _formatDateTime(dateInput, mode = 'datetime') {
        const date = this._parseUTCDateTime(dateInput);
        if (!Number.isFinite(date.getTime())) {
            if (typeof dateInput === 'string' && dateInput.trim()) return dateInput;
            return 'N/A';
        }
        if (mode === 'time') {
            return date.toLocaleTimeString();
        }
        return date.toLocaleString();
    },

    _formatPercent(value, digits = 1) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) {
            return (0).toFixed(digits);
        }
        return numericValue.toFixed(digits);
    },

    _pickFirstNumeric(data, keys = []) {
        for (const key of keys) {
            const value = Number(data?.[key]);
            if (Number.isFinite(value) && value >= 0) {
                return value;
            }
        }
        return null;
    },

    _parseSizeToBytes(value) {
        if (value === null || value === undefined) return null;
        const raw = String(value).trim();
        if (!raw) return null;

        // 支持 "20G" / "20GB" / "20GiB" / "1024" 等常见格式
        const match = raw.match(/^([\d.]+)\s*([kmgtpe]?)(i?b?)?$/i);
        if (!match) return null;

        const numeric = Number(match[1]);
        if (!Number.isFinite(numeric) || numeric < 0) return null;

        const unit = (match[2] || '').toUpperCase();
        const multipliers = {
            '': 1,
            K: 1024,
            M: 1024 ** 2,
            G: 1024 ** 3,
            T: 1024 ** 4,
            P: 1024 ** 5,
            E: 1024 ** 6
        };
        const multiplier = multipliers[unit];
        if (!multiplier) return null;

        return numeric * multiplier;
    },

    _aggregateDiskCapacityFromConfig(hostConfig) {
        const disks = Array.isArray(hostConfig?.disk) ? hostConfig.disk : [];
        if (!disks.length) return { totalBytes: null, usedBytes: null };

        let totalBytes = 0;
        let usedBytes = 0;
        let validCount = 0;

        for (const disk of disks) {
            const diskTotal = this._parseSizeToBytes(disk?.size);
            const diskUsed = this._parseSizeToBytes(disk?.used);
            if (!Number.isFinite(diskTotal) || !Number.isFinite(diskUsed) || diskTotal <= 0 || diskUsed < 0) {
                continue;
            }
            totalBytes += diskTotal;
            usedBytes += Math.min(diskUsed, diskTotal);
            validCount += 1;
        }

        if (!validCount || totalBytes <= 0) {
            return { totalBytes: null, usedBytes: null };
        }
        return { totalBytes, usedBytes };
    },

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
                                <i data-lucide="${this.sidebarCollapsed ? 'panel-right-open' : 'panel-left-close'}"></i>
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
            { key: 'critical', label: '严重', icon: 'alert-octagon', color: '#ef4444' },
            { key: 'warning', label: '警告', icon: 'alert-triangle', color: '#f59e0b' },
            { key: 'offline', label: '离线', icon: 'x-circle', color: '#6b7280' },
            { key: 'normal', label: '正常', icon: 'check-circle', color: '#10b981' }
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
                const metricTime = this._parseUTCDateTime(metric.collected_at);
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
        try {
            const config = await API.getHostConfig(this.currentHost.id);

            // 格式化运行时间
            const uptimeDays = Math.floor(config.system.uptime_seconds / 86400);
            const uptimeHours = Math.floor((config.system.uptime_seconds % 86400) / 3600);
            const uptimeMinutes = Math.floor((config.system.uptime_seconds % 3600) / 60);
            const uptimeText = `${uptimeDays}天 ${uptimeHours}小时 ${uptimeMinutes}分钟`;

            // 解析内存信息
            const parseMemory = (str) => {
                const match = str.match(/(\d+)\s*kB/);
                return match ? parseInt(match[1]) * 1024 : 0;
            };

            const memTotal = parseMemory(config.memory.MemTotal || '0');
            const memFree = parseMemory(config.memory.MemFree || '0');
            const memAvailable = parseMemory(config.memory.MemAvailable || '0');
            const memBuffers = parseMemory(config.memory.Buffers || '0');
            const memCached = parseMemory(config.memory.Cached || '0');
            const swapTotal = parseMemory(config.memory.SwapTotal || '0');
            const swapFree = parseMemory(config.memory.SwapFree || '0');

            const memUsed = memTotal - memAvailable;
            const memUsedPercent = memTotal > 0 ? ((memUsed / memTotal) * 100).toFixed(1) : 0;
            const swapUsed = swapTotal - swapFree;
            const swapUsedPercent = swapTotal > 0 ? ((swapUsed / swapTotal) * 100).toFixed(1) : 0;

            container.innerHTML = `
                <div class="host-config-page">
                    <div class="host-config-header">
                        <div class="host-config-header-info">
                            <h2>${Utils.escapeHtml(this.currentHost.name)}</h2>
                            <p>${Utils.escapeHtml(config.system.hostname)} · ${Utils.escapeHtml(config.system.os_name)} ${Utils.escapeHtml(config.system.os_version)}</p>
                        </div>
                        <div class="host-config-header-actions">
                            <button class="btn btn-secondary btn-sm" id="refresh-config-btn">
                                <i data-lucide="refresh-cw"></i> 刷新配置
                            </button>
                            <div class="host-config-collected-at">
                                <i data-lucide="clock"></i>
                                <span>采集时间: ${this._formatDateTime(config.collected_at)}</span>
                            </div>
                        </div>
                    </div>

                    <div class="host-config-grid">
                        <!-- 系统信息 -->
                        <div class="host-config-card">
                            <div class="host-config-card-header">
                                <i data-lucide="monitor"></i>
                                <h3>系统信息</h3>
                            </div>
                            <div class="host-config-card-body">
                                <div class="host-config-item">
                                    <span class="host-config-label">主机名</span>
                                    <span class="host-config-value">${Utils.escapeHtml(config.system.hostname)}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">操作系统</span>
                                    <span class="host-config-value">${Utils.escapeHtml(config.system.os_name)}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">系统版本</span>
                                    <span class="host-config-value">${Utils.escapeHtml(config.system.os_version || '-')}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">内核版本</span>
                                    <span class="host-config-value">${Utils.escapeHtml(config.system.kernel)}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">运行时间</span>
                                    <span class="host-config-value">${uptimeText}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">负载均衡</span>
                                    <span class="host-config-value">${config.system.load_avg_1} / ${config.system.load_avg_5} / ${config.system.load_avg_15}</span>
                                </div>
                            </div>
                        </div>

                        <!-- CPU 信息 -->
                        <div class="host-config-card">
                            <div class="host-config-card-header">
                                <i data-lucide="cpu"></i>
                                <h3>CPU 信息</h3>
                            </div>
                            <div class="host-config-card-body">
                                <div class="host-config-item">
                                    <span class="host-config-label">处理器型号</span>
                                    <span class="host-config-value">${Utils.escapeHtml(config.cpu.model)}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">物理 CPU 数</span>
                                    <span class="host-config-value">${config.cpu.physical_cpus}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">逻辑核心数</span>
                                    <span class="host-config-value">${config.cpu.cores}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">CPU 频率</span>
                                    <span class="host-config-value">${config.cpu.mhz} MHz</span>
                                </div>
                            </div>
                        </div>

                        <!-- 内存信息 -->
                        <div class="host-config-card">
                            <div class="host-config-card-header">
                                <i data-lucide="memory-stick"></i>
                                <h3>内存信息</h3>
                            </div>
                            <div class="host-config-card-body">
                                <div class="host-config-item">
                                    <span class="host-config-label">总内存</span>
                                    <span class="host-config-value">${this._formatBytes(memTotal)}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">已用内存</span>
                                    <span class="host-config-value">${this._formatBytes(memUsed)} (${memUsedPercent}%)</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">可用内存</span>
                                    <span class="host-config-value">${this._formatBytes(memAvailable)}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">缓冲区</span>
                                    <span class="host-config-value">${this._formatBytes(memBuffers)}</span>
                                </div>
                                <div class="host-config-item">
                                    <span class="host-config-label">缓存</span>
                                    <span class="host-config-value">${this._formatBytes(memCached)}</span>
                                </div>
                                ${swapTotal > 0 ? `
                                <div class="host-config-item">
                                    <span class="host-config-label">交换分区</span>
                                    <span class="host-config-value">${this._formatBytes(swapUsed)} / ${this._formatBytes(swapTotal)} (${swapUsedPercent}%)</span>
                                </div>
                                ` : ''}
                            </div>
                        </div>

                        <!-- 磁盘信息 -->
                        <div class="host-config-card host-config-card-wide">
                            <div class="host-config-card-header">
                                <i data-lucide="hard-drive"></i>
                                <h3>磁盘信息</h3>
                            </div>
                            <div class="host-config-card-body">
                                ${config.disk.length > 0 ? `
                                    <div class="host-config-table-container">
                                        <table class="host-config-table">
                                            <thead>
                                                <tr>
                                                    <th>文件系统</th>
                                                    <th>挂载点</th>
                                                    <th>总容量</th>
                                                    <th>已使用</th>
                                                    <th>可用</th>
                                                    <th>使用率</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                ${config.disk.map(disk => `
                                                    <tr>
                                                        <td><code>${Utils.escapeHtml(disk.filesystem)}</code></td>
                                                        <td><code>${Utils.escapeHtml(disk.mounted_on)}</code></td>
                                                        <td>${Utils.escapeHtml(disk.size)}</td>
                                                        <td>${Utils.escapeHtml(disk.used)}</td>
                                                        <td>${Utils.escapeHtml(disk.available)}</td>
                                                        <td>
                                                            <div class="host-config-progress">
                                                                <div class="host-config-progress-bar" style="width: ${disk.use_percent}"></div>
                                                                <span class="host-config-progress-text">${Utils.escapeHtml(disk.use_percent)}</span>
                                                            </div>
                                                        </td>
                                                    </tr>
                                                `).join('')}
                                            </tbody>
                                        </table>
                                    </div>
                                ` : '<p class="host-config-empty">暂无磁盘信息</p>'}
                            </div>
                        </div>

                        <!-- 网络接口 -->
                        <div class="host-config-card host-config-card-wide">
                            <div class="host-config-card-header">
                                <i data-lucide="network"></i>
                                <h3>网络接口</h3>
                            </div>
                            <div class="host-config-card-body">
                                ${config.network.length > 0 ? `
                                    <div class="host-config-table-container">
                                        <table class="host-config-table">
                                            <thead>
                                                <tr>
                                                    <th>接口名称</th>
                                                    <th>地址类型</th>
                                                    <th>IP 地址</th>
                                                </tr>
                                            </thead>
                                            <tbody>
                                                ${config.network.map(net => `
                                                    <tr>
                                                        <td><code>${Utils.escapeHtml(net.interface)}</code></td>
                                                        <td><span class="badge badge-secondary">${Utils.escapeHtml(net.family)}</span></td>
                                                        <td><code>${Utils.escapeHtml(net.address)}</code></td>
                                                    </tr>
                                                `).join('')}
                                            </tbody>
                                        </table>
                                    </div>
                                ` : '<p class="host-config-empty">暂无网络接口信息</p>'}
                            </div>
                        </div>
                    </div>

                </div>
            `;

            DOM.createIcons();

            // 绑定刷新按钮
            DOM.$('#refresh-config-btn')?.addEventListener('click', async () => {
                const btn = DOM.$('#refresh-config-btn');
                btn.disabled = true;
                btn.innerHTML = '<i data-lucide="loader" class="spin"></i> 刷新中...';
                DOM.createIcons();

                try {
                    await API.refreshHostConfig(this.currentHost.id);
                    await this._renderInfoTab(container);
                    Toast.success('配置已刷新');
                } catch (error) {
                    Toast.error('刷新失败: ' + error.message);
                    btn.disabled = false;
                    btn.innerHTML = '<i data-lucide="refresh-cw"></i> 刷新配置';
                    DOM.createIcons();
                }
            });

        } catch (error) {
            console.error('Failed to load host config:', error);
            await this._renderInfoTabDegraded(container, error);
        }
    },

    async _renderInfoTabDegraded(container, error) {
        let summary = null;
        try {
            summary = await API.getHostSummary(this.currentHost.id);
        } catch (summaryError) {
            console.warn('Failed to load host summary for degraded info tab:', summaryError);
        }

        const metric = summary?.latest_metric;
        const metricTimeText = metric?.collected_at
            ? this._formatDateTime(metric.collected_at)
            : '暂无';
        const statusText = metric ? '主机存在历史监控数据，但当前无法建立 SSH 连接' : '主机当前不可达，且暂无可用监控数据';

        container.innerHTML = `
            <div class="host-config-page">
                <div class="host-config-header">
                    <div class="host-config-header-info">
                        <h2>${Utils.escapeHtml(this.currentHost.name)}</h2>
                        <p>${Utils.escapeHtml(this.currentHost.host)}:${this.currentHost.port} · ${Utils.escapeHtml(this.currentHost.username)}</p>
                    </div>
                    <button class="btn btn-secondary btn-sm" id="retry-config-btn">
                        <i data-lucide="refresh-cw"></i> 重试连接
                    </button>
                </div>
                <div class="host-config-grid">
                    <div class="host-config-card host-config-card-wide">
                        <div class="host-config-card-header">
                            <i data-lucide="wifi-off"></i>
                            <h3>主机配置暂不可用</h3>
                        </div>
                        <div class="host-config-card-body">
                            <p class="host-config-empty">${Utils.escapeHtml(statusText)}</p>
                            <p class="host-config-empty">错误信息：${Utils.escapeHtml(error?.message || '未知错误')}</p>
                            <p class="host-config-empty">最近指标时间：${Utils.escapeHtml(metricTimeText)}</p>
                        </div>
                    </div>
                </div>
            </div>
        `;

        DOM.createIcons();

        DOM.$('#retry-config-btn')?.addEventListener('click', async () => {
            const btn = DOM.$('#retry-config-btn');
            btn.disabled = true;
            btn.innerHTML = '<i data-lucide="loader" class="spin"></i> 重试中...';
            DOM.createIcons();
            await this._renderInfoTab(container);
        });
    },

    async _renderMonitorTab(container) {
        // 获取实时状态数据
        const summary = await API.getHostSummary(this.currentHost.id);
        const metric = summary.latest_metric;
        const data = metric?.data || {};
        const cpuUsage = this._formatPercent(metric?.cpu_usage);
        const memoryUsage = this._formatPercent(metric?.memory_usage);
        const diskUsage = this._formatPercent(metric?.disk_usage);

        const memoryTotalKb = this._pickFirstNumeric(data, ['memory_total_kb']);
        const memoryUsedKb = this._pickFirstNumeric(data, ['memory_used_kb']);
        const memoryTotalBytes = this._pickFirstNumeric(data, ['memory_total_bytes']) ?? (memoryTotalKb !== null ? memoryTotalKb * 1024 : null);
        const memoryUsedBytes = this._pickFirstNumeric(data, ['memory_used_bytes']) ?? (memoryUsedKb !== null ? memoryUsedKb * 1024 : null);
        let diskTotalBytes = this._pickFirstNumeric(data, ['disk_total_bytes', 'disk_total']);
        let diskUsedBytes = this._pickFirstNumeric(data, ['disk_used_bytes', 'disk_used']);

        // 兜底：监控指标缺少磁盘容量字段时，从主机配置 disk 列表聚合
        if (!Number.isFinite(diskTotalBytes) || !Number.isFinite(diskUsedBytes)) {
            try {
                const hostConfig = await API.getHostConfig(this.currentHost.id);
                const aggregatedDisk = this._aggregateDiskCapacityFromConfig(hostConfig);
                if (!Number.isFinite(diskTotalBytes) && Number.isFinite(aggregatedDisk.totalBytes)) {
                    diskTotalBytes = aggregatedDisk.totalBytes;
                }
                if (!Number.isFinite(diskUsedBytes) && Number.isFinite(aggregatedDisk.usedBytes)) {
                    diskUsedBytes = aggregatedDisk.usedBytes;
                }
            } catch (error) {
                console.warn('Failed to load host config disk fallback:', error);
            }
        }

        const memoryTotal = Number.isFinite(memoryTotalBytes) ? this._formatBytes(memoryTotalBytes) : '未知';
        const diskTotal = Number.isFinite(diskTotalBytes) ? this._formatBytes(diskTotalBytes) : '未知';
        const memoryUsed = Number.isFinite(memoryUsedBytes) ? this._formatBytes(memoryUsedBytes) : '未知';
        const diskUsed = Number.isFinite(diskUsedBytes) ? this._formatBytes(diskUsedBytes) : '未知';

        container.innerHTML = `
            <div class="host-monitor-page">
                <!-- 工具栏 -->
                <div class="instance-embedded-toolbar">
                    <div class="instance-embedded-title">性能监控</div>
                    <div style="display: flex; gap: 12px; align-items: center;">
                        <select id="monitor-time-range" class="filter-select">
                            <option value="1" ${this.currentTimeRange === 1 ? 'selected' : ''}>最近 1 分钟</option>
                            <option value="10" ${this.currentTimeRange === 10 ? 'selected' : ''}>最近 10 分钟</option>
                            <option value="60" ${this.currentTimeRange === 60 ? 'selected' : ''}>最近 1 小时</option>
                            <option value="360" ${this.currentTimeRange === 360 ? 'selected' : ''}>最近 6 小时</option>
                            <option value="1440" ${this.currentTimeRange === 1440 ? 'selected' : ''}>最近 1 天</option>
                            <option value="10080" ${this.currentTimeRange === 10080 ? 'selected' : ''}>最近 7 天</option>
                            <option value="43200" ${this.currentTimeRange === 43200 ? 'selected' : ''}>最近 1 个月</option>
                            <option value="custom">自定义时间</option>
                        </select>
                    </div>
                </div>

                <!-- 指标卡片 -->
                ${metric ? `
                <div class="grid-4 mb-24">
                    <div class="metric-card">
                        <div class="metric-card-label">CPU 使用率</div>
                        <div class="metric-card-value">${cpuUsage}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-label">内存使用</div>
                        <div class="metric-card-value">${memoryUsage}%</div>
                        <div class="metric-card-meta">${memoryUsed} / ${memoryTotal}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-label">磁盘使用</div>
                        <div class="metric-card-value">${diskUsage}%</div>
                        <div class="metric-card-meta">${diskUsed} / ${diskTotal}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-label">运行时间</div>
                        <div class="metric-card-value" style="font-size:16px">${Number.isFinite(summary?.uptime_seconds) ? this._formatUptime(summary.uptime_seconds) : '未知'}</div>
                        <div class="metric-card-meta">最后更新: ${this._formatDateTime(metric.collected_at, 'time')}</div>
                    </div>
                </div>
                ` : ''}

                <!-- 基础指标图表 -->
                <h3 class="mb-16">基础指标</h3>
                <div class="chart-grid mb-24">
                    <div class="chart-panel">
                        <div class="chart-panel-header">
                            <span class="chart-panel-title">CPU 使用率 (%)</span>
                        </div>
                        <div class="chart-container">
                            <canvas id="cpu-chart"></canvas>
                        </div>
                    </div>
                    <div class="chart-panel">
                        <div class="chart-panel-header">
                            <span class="chart-panel-title">内存使用率 (%)</span>
                        </div>
                        <div class="chart-container">
                            <canvas id="memory-chart"></canvas>
                        </div>
                    </div>
                    <div class="chart-panel">
                        <div class="chart-panel-header">
                            <span class="chart-panel-title">磁盘使用率 (%)</span>
                        </div>
                        <div class="chart-container">
                            <canvas id="disk-chart"></canvas>
                        </div>
                    </div>
                    <div class="chart-panel">
                        <div class="chart-panel-header">
                            <span class="chart-panel-title">负载平均 (1分钟)</span>
                        </div>
                        <div class="chart-container">
                            <canvas id="load-chart"></canvas>
                        </div>
                    </div>
                </div>

                <!-- 磁盘和网络 IO 图表 -->
                <h3 class="mb-16 mt-24">磁盘与网络 I/O</h3>
                <div class="chart-grid">
                    <div class="chart-panel">
                        <div class="chart-panel-header">
                            <span class="chart-panel-title">磁盘 IOPS (读/写)</span>
                        </div>
                        <div class="chart-container">
                            <canvas id="disk-iops-chart"></canvas>
                        </div>
                    </div>
                    <div class="chart-panel">
                        <div class="chart-panel-header">
                            <span class="chart-panel-title">磁盘 I/O 流量 (读/写 KB/s)</span>
                        </div>
                        <div class="chart-container">
                            <canvas id="disk-io-chart"></canvas>
                        </div>
                    </div>
                    <div class="chart-panel">
                        <div class="chart-panel-header">
                            <span class="chart-panel-title">网络 I/O 流量 (接收/发送 KB/s)</span>
                        </div>
                        <div class="chart-container">
                            <canvas id="network-io-chart"></canvas>
                        </div>
                    </div>
                </div>
            </div>
        `;

        await this._loadMonitorData(this.currentTimeRange);

        // 时间范围切换
        DOM.$('#monitor-time-range')?.addEventListener('change', async (e) => {
            const value = e.target.value;
            if (value === 'custom') {
                this._showCustomTimeDialog();
            } else {
                this.currentTimeRange = parseInt(value);
                await this._loadMonitorData(this.currentTimeRange);
            }
        });

        this.tabCleanup = () => {
            // 清理图表实例
            if (window.hostMonitorCharts) {
                Object.values(window.hostMonitorCharts).forEach(chart => chart.destroy());
                window.hostMonitorCharts = null;
            }
        };
    },

    async _loadMonitorData(minutes) {
        try {
            const metrics = await API.getHostMetrics(this.currentHost.id, `minutes=${minutes}`);
            this._renderMonitorCharts(metrics);
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

        const labels = metrics.map(m => {
            const date = this._parseUTCDateTime(m.collected_at);
            const now = new Date();
            const isToday = date.toDateString() === now.toDateString();

            if (isToday) {
                return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            }
            return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
        });

        // 控制横轴标签密度，避免时间标签过密重叠
        const xAxisTickConfig = {
            color: '#9ca3af',
            maxRotation: 0,
            minRotation: 0,
            autoSkip: true,
            maxTicksLimit: 6
        };

        // 通用单线图表配置
        const createLineChart = (canvasId, label, data, color, yAxisConfig = {}) => {
            const canvas = DOM.$(`#${canvasId}`);
            if (!canvas) return null;

            return new Chart(canvas, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label,
                        data,
                        borderColor: color,
                        backgroundColor: color + '20',
                        borderWidth: 1,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHitRadius: 10
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            mode: 'index',
                            intersect: false
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: xAxisTickConfig
                        },
                        y: {
                            beginAtZero: true,
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#9ca3af' },
                            ...yAxisConfig
                        }
                    },
                    interaction: {
                        mode: 'nearest',
                        axis: 'x',
                        intersect: false
                    }
                }
            });
        };

        // 通用多线图表配置
        const createMultiLineChart = (canvasId, datasets, yAxisConfig = {}) => {
            const canvas = DOM.$(`#${canvasId}`);
            if (!canvas) return null;

            return new Chart(canvas, {
                type: 'line',
                data: {
                    labels,
                    datasets: datasets.map(ds => ({
                        label: ds.label,
                        data: ds.data,
                        borderColor: ds.color,
                        backgroundColor: ds.color + '20',
                        borderWidth: 1,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                        pointHitRadius: 10
                    }))
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            display: true,
                            position: 'top',
                            labels: {
                                color: '#e6edf3',
                                font: { size: 11 },
                                usePointStyle: true,
                                padding: 10
                            }
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: xAxisTickConfig
                        },
                        y: {
                            beginAtZero: true,
                            grid: { color: 'rgba(255,255,255,0.05)' },
                            ticks: { color: '#9ca3af' },
                            ...yAxisConfig
                        }
                    },
                    interaction: {
                        mode: 'nearest',
                        axis: 'x',
                        intersect: false
                    }
                }
            });
        };

        // CPU 图表
        window.hostMonitorCharts.cpu = createLineChart(
            'cpu-chart',
            'CPU 使用率',
            metrics.map(m => m.cpu_usage || 0),
            '#2f81f7',
            { max: 100, ticks: { callback: value => value + '%' } }
        );

        // 内存图表
        window.hostMonitorCharts.memory = createLineChart(
            'memory-chart',
            '内存使用率',
            metrics.map(m => m.memory_usage || 0),
            '#10b981',
            { max: 100, ticks: { callback: value => value + '%' } }
        );

        // 磁盘使用率图表
        window.hostMonitorCharts.disk = createLineChart(
            'disk-chart',
            '磁盘使用率',
            metrics.map(m => m.disk_usage || 0),
            '#f59e0b',
            { max: 100, ticks: { callback: value => value + '%' } }
        );

        // 负载平均图表
        window.hostMonitorCharts.load = createLineChart(
            'load-chart',
            '负载平均',
            metrics.map(m => m.data?.load_avg_1min || 0),
            '#8b5cf6'
        );

        // 磁盘 IOPS 图表
        window.hostMonitorCharts.diskIops = createMultiLineChart(
            'disk-iops-chart',
            [
                {
                    label: '读',
                    data: metrics.map(m => m.data?.disk_read_iops || 0),
                    color: '#2f81f7'
                },
                {
                    label: '写',
                    data: metrics.map(m => m.data?.disk_write_iops || 0),
                    color: '#f97316'
                }
            ],
            { ticks: { callback: value => value.toFixed(0) } }
        );

        // 磁盘 IO 流量图表
        window.hostMonitorCharts.diskIo = createMultiLineChart(
            'disk-io-chart',
            [
                {
                    label: '读',
                    data: metrics.map(m => m.data?.disk_read_kb_per_sec || 0),
                    color: '#2f81f7'
                },
                {
                    label: '写',
                    data: metrics.map(m => m.data?.disk_write_kb_per_sec || 0),
                    color: '#f97316'
                }
            ],
            { ticks: { callback: value => value.toFixed(0) + ' KB/s' } }
        );

        // 网络 IO 流量图表
        window.hostMonitorCharts.networkIo = createMultiLineChart(
            'network-io-chart',
            [
                {
                    label: '接收',
                    data: metrics.map(m => m.data?.network_rx_kb_per_sec || 0),
                    color: '#10b981'
                },
                {
                    label: '发送',
                    data: metrics.map(m => m.data?.network_tx_kb_per_sec || 0),
                    color: '#8b5cf6'
                }
            ],
            { ticks: { callback: value => value.toFixed(0) + ' KB/s' } }
        );
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

            <!-- 进程详情抽屉 -->
            <div id="process-detail-drawer" class="drawer">
                <div class="drawer-overlay"></div>
                <div class="drawer-content">
                    <div class="drawer-header">
                        <h3>进程详情</h3>
                        <button class="drawer-close" id="close-process-drawer">
                            <i data-lucide="x"></i>
                        </button>
                    </div>
                    <div class="drawer-body" id="process-detail-content">
                        <div class="loading-overlay"><div class="spinner"></div></div>
                    </div>
                </div>
            </div>
        `;

        this._renderProcessTable(processes);

        // 定时刷新
        this.processPollTimer = setInterval(async () => {
            const updated = await API.getHostProcesses(this.currentHost.id);
            this._renderProcessTable(updated);
        }, 5000);

        // 绑定抽屉关闭事件
        const drawer = DOM.$('#process-detail-drawer');
        const closeBtn = DOM.$('#close-process-drawer');
        const overlay = drawer?.querySelector('.drawer-overlay');

        closeBtn?.addEventListener('click', () => {
            drawer.classList.remove('open');
        });

        overlay?.addEventListener('click', () => {
            drawer.classList.remove('open');
        });

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
            <tr class="process-row" data-pid="${p.pid}" style="cursor:pointer">
                <td>${p.pid}</td>
                <td>${Utils.escapeHtml(p.user)}</td>
                <td>${this._formatPercent(p.cpu_percent)}%</td>
                <td>${this._formatPercent(p.memory_percent)}%</td>
                <td>${Utils.escapeHtml(p.state)}</td>
                <td class="host-process-command" title="${Utils.escapeHtml(p.command)}">${Utils.escapeHtml(p.command)}</td>
            </tr>
        `).join('');

        // 绑定点击事件
        tbody.querySelectorAll('.process-row').forEach(row => {
            row.addEventListener('click', async () => {
                const pid = parseInt(row.dataset.pid);
                await this._showProcessDetail(pid);
            });
        });
    },

    async _showProcessDetail(pid) {
        const drawer = DOM.$('#process-detail-drawer');
        const content = DOM.$('#process-detail-content');

        if (!drawer || !content) return;

        drawer.classList.add('open');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const detail = await API.getProcessDetail(this.currentHost.id, pid);

            // 格式化字节数
            const formatBytes = (bytes) => {
                if (!bytes || bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i];
            };

            content.innerHTML = `
                <div class="process-detail-container">
                    <!-- 基本信息 -->
                    <div class="process-detail-section">
                        <h4><i data-lucide="info"></i> 基本信息</h4>
                        <div class="process-detail-grid">
                            <div class="process-detail-item">
                                <span class="process-detail-label">PID</span>
                                <span class="process-detail-value">${detail.pid}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">用户</span>
                                <span class="process-detail-value">${Utils.escapeHtml(detail.user || '-')}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">状态</span>
                                <span class="process-detail-value">${Utils.escapeHtml(detail.state || '-')}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">启动时间</span>
                                <span class="process-detail-value">${Utils.escapeHtml(detail.start_time || '-')}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">CPU 使用率</span>
                                <span class="process-detail-value">${this._formatPercent(detail.cpu_percent)}%</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">内存使用率</span>
                                <span class="process-detail-value">${this._formatPercent(detail.memory_percent)}%</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">虚拟内存</span>
                                <span class="process-detail-value">${formatBytes(detail.vsz * 1024)}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">物理内存</span>
                                <span class="process-detail-value">${formatBytes(detail.rss * 1024)}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">CPU 时间</span>
                                <span class="process-detail-value">${Utils.escapeHtml(detail.cpu_time || '-')}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">工作目录</span>
                                <span class="process-detail-value" style="word-break:break-all">${Utils.escapeHtml(detail.cwd || '-')}</span>
                            </div>
                        </div>
                    </div>

                    <!-- 命令详情 -->
                    <div class="process-detail-section">
                        <h4><i data-lucide="terminal"></i> 命令详情</h4>
                        <div class="process-detail-code">
                            <div><strong>命令:</strong></div>
                            <pre>${Utils.escapeHtml(detail.command || '-')}</pre>
                            ${detail.cmdline ? `
                                <div style="margin-top:12px"><strong>完整命令行:</strong></div>
                                <pre>${Utils.escapeHtml(detail.cmdline)}</pre>
                            ` : ''}
                        </div>
                    </div>

                    <!-- 磁盘 IO -->
                    <div class="process-detail-section">
                        <h4><i data-lucide="hard-drive"></i> 磁盘 I/O</h4>
                        <div class="process-detail-grid">
                            <div class="process-detail-item">
                                <span class="process-detail-label">读取字节数</span>
                                <span class="process-detail-value">${formatBytes(detail.io?.read_bytes || 0)}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">写入字节数</span>
                                <span class="process-detail-value">${formatBytes(detail.io?.write_bytes || 0)}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">读取字符数</span>
                                <span class="process-detail-value">${formatBytes(detail.io?.read_chars || 0)}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">写入字符数</span>
                                <span class="process-detail-value">${formatBytes(detail.io?.write_chars || 0)}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">读取系统调用</span>
                                <span class="process-detail-value">${detail.io?.read_syscalls || 0}</span>
                            </div>
                            <div class="process-detail-item">
                                <span class="process-detail-label">写入系统调用</span>
                                <span class="process-detail-value">${detail.io?.write_syscalls || 0}</span>
                            </div>
                        </div>
                    </div>

                    <!-- 网络连接 -->
                    <div class="process-detail-section">
                        <h4><i data-lucide="network"></i> 网络连接</h4>
                        ${detail.network_connections && detail.network_connections.length > 0 ? `
                            <div class="process-network-table-container">
                                <table class="process-network-table">
                                    <thead>
                                        <tr>
                                            <th>状态</th>
                                            <th>本地地址</th>
                                            <th>本地端口</th>
                                            <th>远程地址</th>
                                            <th>远程端口</th>
                                            <th>接收队列</th>
                                            <th>发送队列</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${detail.network_connections.map(conn => `
                                            <tr>
                                                <td><span class="network-state network-state-${conn.state.toLowerCase()}">${Utils.escapeHtml(conn.state)}</span></td>
                                                <td><code>${Utils.escapeHtml(conn.local_address)}</code></td>
                                                <td><code>${Utils.escapeHtml(conn.local_port)}</code></td>
                                                <td><code>${Utils.escapeHtml(conn.remote_address)}</code></td>
                                                <td><code>${Utils.escapeHtml(conn.remote_port)}</code></td>
                                                <td>${conn.recv_bytes || 0} bytes</td>
                                                <td>${conn.send_bytes || 0} bytes</td>
                                            </tr>
                                        `).join('')}
                                    </tbody>
                                </table>
                            </div>
                        ` : '<p style="color:var(--text-secondary);padding:12px">无活动网络连接</p>'}
                    </div>

                    <!-- 环境变量 -->
                    ${detail.environment && Object.keys(detail.environment).length > 0 ? `
                        <div class="process-detail-section">
                            <h4><i data-lucide="settings"></i> 环境变量 (前20个)</h4>
                            <div class="process-detail-code">
                                <pre>${Object.entries(detail.environment).map(([k, v]) =>
                                    `${Utils.escapeHtml(k)}=${Utils.escapeHtml(v)}`
                                ).join('\n')}</pre>
                            </div>
                        </div>
                    ` : ''}
                </div>
            `;

            DOM.createIcons();
        } catch (error) {
            console.error('Failed to load process detail:', error);
            content.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="alert-circle"></i>
                    <p>加载进程详情失败: ${error.message}</p>
                </div>
            `;
            DOM.createIcons();
        }
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
            contextEntityName: this.currentHost?.name || this.currentHost?.host || '',
            sessionFilterHostId: hostId,
            defaultSidebarCollapsed: true,
            initialSessionTitle: `主机诊断 ${this.currentHost?.name || this.currentHost?.host || hostId}`.trim(),
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

    _formatDateTimeLocal(date) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${year}-${month}-${day}T${hours}:${minutes}`;
    },

    _showCustomTimeDialog() {
        const modal = Modal.show({
            title: '自定义时间范围',
            width: '480px',
            content: `
                <div class="form-group">
                    <label>开始时间</label>
                    <input type="datetime-local" class="filter-input" id="custom-start-time" />
                </div>
                <div class="form-group">
                    <label>结束时间</label>
                    <input type="datetime-local" class="filter-input" id="custom-end-time" />
                </div>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => {
                    Modal.hide();
                    DOM.$('#monitor-time-range').value = this.currentTimeRange;
                }},
                { text: '确定', variant: 'primary', onClick: () => {
                    this._applyCustomTimeRange();
                }}
            ],
            onHide: () => {
                // 如果用户直接关闭对话框，重置选择器
                const select = DOM.$('#monitor-time-range');
                if (select && select.value === 'custom') {
                    select.value = this.currentTimeRange;
                }
            }
        });

        // 设置默认时间范围
        const now = new Date();
        const endTime = this._formatDateTimeLocal(now);
        const startDate = new Date(now.getTime() - this.currentTimeRange * 60 * 1000);
        const startTime = this._formatDateTimeLocal(startDate);

        setTimeout(() => {
            const startInput = DOM.$('#custom-start-time');
            const endInput = DOM.$('#custom-end-time');
            if (startInput) startInput.value = startTime;
            if (endInput) endInput.value = endTime;
        }, 0);
    },

    async _applyCustomTimeRange() {
        const startInput = DOM.$('#custom-start-time');
        const endInput = DOM.$('#custom-end-time');

        if (!startInput || !endInput) return;

        const start = startInput.value;
        const end = endInput.value;

        if (!start || !end) {
            Toast.warning('请选择开始和结束时间');
            return;
        }

        const startDate = new Date(start);
        const endDate = new Date(end);

        if (startDate >= endDate) {
            Toast.warning('开始时间必须早于结束时间');
            return;
        }

        Modal.hide();

        try {
            await this._loadCustomRangeData(start, end);
        } catch (error) {
            console.error('Failed to load custom range data:', error);
            Toast.error('加载数据失败: ' + error.message);
            DOM.$('#monitor-time-range').value = this.currentTimeRange;
        }
    },

    async _loadCustomRangeData(startTime, endTime) {
        try {
            // 转换为 ISO 格式
            const start = new Date(startTime).toISOString();
            const end = new Date(endTime).toISOString();

            const metrics = await API.getHostMetrics(
                this.currentHost.id,
                `start_time=${encodeURIComponent(start)}&end_time=${encodeURIComponent(end)}`
            );

            if (metrics.length === 0) {
                Toast.warning('所选时间范围内没有数据');
                DOM.$('#monitor-time-range').value = this.currentTimeRange;
                return;
            }

            this._renderMonitorCharts(metrics);
            Toast.success('已加载自定义时间范围数据');
        } catch (error) {
            throw error;
        }
    },

    _bindEvents() {
        // 侧边栏折叠
        DOM.$('#host-sidebar-toggle')?.addEventListener('click', () => {
            this.sidebarCollapsed = !this.sidebarCollapsed;
            localStorage.setItem('hostDetailSidebarCollapsed', this.sidebarCollapsed);
            DOM.$('#host-detail-layout')?.classList.toggle('sidebar-collapsed');
            DOM.$('#host-sidebar-toggle i')?.setAttribute('data-lucide', this.sidebarCollapsed ? 'panel-right-open' : 'panel-left-close');
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
