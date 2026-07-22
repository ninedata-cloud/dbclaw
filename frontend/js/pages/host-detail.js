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
            return I18n.formatTime(date);
        }
        return I18n.formatDate(date, { dateStyle: 'medium', timeStyle: 'medium' });
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
                Header.render(I18n.t('hostDetail.title'));
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="server"></i>
                        <h3>${I18n.t('hostDetail.noHosts')}</h3>
                        <p>${I18n.t('hostDetail.noHostsHint')}</p>
                        <button class="btn btn-primary mt-16" onclick="Router.navigate('hosts')">${I18n.t('hostDetail.goToHosts')}</button>
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
                                <div class="host-sidebar-title">${I18n.t('hostDetail.hostList')}</div>
                                <div class="host-sidebar-subtitle">${I18n.t('hostDetail.workbench')}</div>
                            </div>
                            <button id="host-sidebar-toggle" class="host-sidebar-toggle" type="button" aria-label="${I18n.t('hostDetail.toggleSidebar')}">
                                <i data-lucide="${this.sidebarCollapsed ? 'panel-right-open' : 'panel-left-close'}"></i>
                            </button>
                        </div>
                        <div class="host-sidebar-search">
                            <input id="host-search-input" class="filter-input" type="text" placeholder="${I18n.t('hostDetail.searchHosts')}">
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
                    <h3>${I18n.t('common.failed')}</h3>
                    <p>${Utils.escapeHtml(error.message)}</p>
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
        Header.render(I18n.t('hostDetail.title'), headerActions);
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
            { key: 'critical', label: I18n.t('hostDetail.status.critical'), icon: 'alert-octagon', color: '#ef4444' },
            { key: 'warning', label: I18n.t('hostDetail.status.warning'), icon: 'alert-triangle', color: '#f59e0b' },
            { key: 'offline', label: I18n.t('hostDetail.status.offline'), icon: 'x-circle', color: '#6b7280' },
            { key: 'normal', label: I18n.t('hostDetail.status.normal'), icon: 'check-circle', color: '#10b981' }
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

        container.innerHTML = html || `<div style="padding:20px;text-align:center;color:var(--text-secondary)">${I18n.t('hostDetail.noMatchingHosts')}</div>`;
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
            let statusText = I18n.t('hostDetail.status.unknown');
            if (metric) {
                const now = new Date();
                const metricTime = this._parseUTCDateTime(metric.collected_at);
                const ageSeconds = (now - metricTime) / 1000;

                if (ageSeconds > 300) {
                    statusClass = 'offline';
                    statusText = I18n.t('hostDetail.status.offline');
                } else if (metric.cpu_usage > 80 || metric.memory_usage > 80 || metric.disk_usage > 80) {
                    statusClass = 'critical';
                    statusText = I18n.t('hostDetail.status.critical');
                } else if (metric.cpu_usage > 60 || metric.memory_usage > 60 || metric.disk_usage > 60) {
                    statusClass = 'warning';
                    statusText = I18n.t('hostDetail.status.warning');
                } else {
                    statusClass = 'normal';
                    statusText = I18n.t('hostDetail.status.normal');
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
            { id: 'info', label: I18n.t('hostDetail.tabs.info'), icon: 'info' },
            { id: 'monitor', label: I18n.t('hostDetail.tabs.monitor'), icon: 'activity' },
            { id: 'processes', label: I18n.t('hostDetail.tabs.processes'), icon: 'cpu' },
            { id: 'terminal', label: I18n.t('hostDetail.tabs.terminal'), icon: 'terminal' },
            { id: 'network', label: I18n.t('hostDetail.tabs.network'), icon: 'network' },
            { id: 'ai', label: I18n.t('hostDetail.tabs.ai'), icon: 'sparkles' }
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
            container.innerHTML = `<div class="empty-state"><i data-lucide="alert-circle"></i><p>${I18n.t('hostDetail.loadFailed', { message: Utils.escapeHtml(error.message) })}</p></div>`;
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
            const uptimeText = I18n.t('hostDetail.uptime', {
                days: uptimeDays, hours: uptimeHours, minutes: uptimeMinutes
            });

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

            container.innerHTML = I18n.t('pageCopy.hostDetail.hostInformationGrid', { value0: Utils.escapeHtml(this.currentHost.name), value1: Utils.escapeHtml(config.system.hostname), value2: Utils.escapeHtml(config.system.os_name), value3: Utils.escapeHtml(config.system.os_version), value4: I18n.t('hostDetail.refreshConfig'), value5: I18n.t('hostDetail.collectedAt', { time: this._formatDateTime(config.collected_at) }), value6: I18n.t('hostDetail.systemInfo'), value7: I18n.t('hostDetail.hostname'), value8: Utils.escapeHtml(config.system.hostname), value9: I18n.t('hostDetail.operatingSystem'), value10: Utils.escapeHtml(config.system.os_name), value11: I18n.t('hostDetail.systemVersion'), value12: Utils.escapeHtml(config.system.os_version || '-'), value13: I18n.t('hostDetail.kernelVersion'), value14: Utils.escapeHtml(config.system.kernel), value15: I18n.t('hostDetail.uptimeLabel'), value16: uptimeText, value17: I18n.t('hostDetail.loadAverage'), value18: config.system.load_avg_1, value19: config.system.load_avg_5, value20: config.system.load_avg_15, value21: I18n.t('hostDetail.cpuInfo'), value22: I18n.t('hostDetail.processorModel'), value23: Utils.escapeHtml(config.cpu.model), value24: I18n.t('hostDetail.physicalCpuCount'), value25: config.cpu.physical_cpus, value26: I18n.t('hostDetail.logicalCoreCount'), value27: config.cpu.cores, value28: I18n.t('hostDetail.cpuFrequency'), value29: config.cpu.mhz, value30: I18n.t('hostDetail.memoryInfo'), value31: I18n.t('hostDetail.totalMemory'), value32: this._formatBytes(memTotal), value33: I18n.t('hostDetail.usedMemory'), value34: this._formatBytes(memUsed), value35: memUsedPercent, value36: I18n.t('hostDetail.availableMemory'), value37: this._formatBytes(memAvailable), value38: I18n.t('hostDetail.buffers'), value39: this._formatBytes(memBuffers), value40: I18n.t('hostDetail.cache'), value41: this._formatBytes(memCached), value42: swapTotal > 0 ? `
                                <div class="host-config-item">
                                    <span class="host-config-label">${I18n.t('hostDetail.swap')}</span>
                                    <span class="host-config-value">${this._formatBytes(swapUsed)} / ${this._formatBytes(swapTotal)} (${swapUsedPercent}%)</span>
                                </div>
                                ` : '', value43: I18n.t('hostDetail.diskInfo'), value44: config.disk.length > 0 ? `
                                    <div class="host-config-table-container">
                                        <table class="host-config-table">
                                            <thead>
                                                <tr>
                                                    <th>${I18n.t('hostDetail.filesystem')}</th>
                                                    <th>${I18n.t('hostDetail.mountPoint')}</th>
                                                    <th>${I18n.t('hostDetail.totalCapacity')}</th>
                                                    <th>${I18n.t('hostDetail.used')}</th>
                                                    <th>${I18n.t('hostDetail.available')}</th>
                                                    <th>${I18n.t('hostDetail.usage')}</th>
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
                                ` : `<p class="host-config-empty">${I18n.t('hostDetail.noDiskInfo')}</p>`, value45: I18n.t('hostDetail.networkInterfaces'), value46: config.network.length > 0 ? `
                                    <div class="host-config-table-container">
                                        <table class="host-config-table">
                                            <thead>
                                                <tr>
                                                    <th>${I18n.t('hostDetail.interfaceName')}</th>
                                                    <th>${I18n.t('hostDetail.addressFamily')}</th>
                                                    <th>${I18n.t('hostDetail.ipAddress')}</th>
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
                                ` : `<p class="host-config-empty">${I18n.t('hostDetail.noNetworkInterfaces')}</p>` });

            DOM.createIcons();

            // 绑定刷新按钮
            DOM.$('#refresh-config-btn')?.addEventListener('click', async () => {
                const btn = DOM.$('#refresh-config-btn');
                btn.disabled = true;
                btn.innerHTML = `<i data-lucide="loader" class="spin"></i> ${I18n.t('hostDetail.refreshing')}`;
                DOM.createIcons();

                try {
                    await API.refreshHostConfig(this.currentHost.id);
                    await this._renderInfoTab(container);
                    Toast.success(I18n.t('hostDetail.configRefreshed'));
                } catch (error) {
                    Toast.error(I18n.t('hostDetail.refreshFailed', { message: error.message }));
                    btn.disabled = false;
                    btn.innerHTML = `<i data-lucide="refresh-cw"></i> ${I18n.t('hostDetail.refreshConfig')}`;
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
            : I18n.t('hostDetail.unavailable');
        const statusText = metric
            ? I18n.t('hostDetail.historicalMetricsOnly')
            : I18n.t('hostDetail.hostUnreachable');

        container.innerHTML = `
            <div class="host-config-page">
                <div class="host-config-header">
                    <div class="host-config-header-info">
                        <h2>${Utils.escapeHtml(this.currentHost.name)}</h2>
                        <p>${Utils.escapeHtml(this.currentHost.host)}:${this.currentHost.port} · ${Utils.escapeHtml(this.currentHost.username)}</p>
                    </div>
                    <button class="btn btn-secondary btn-sm" id="retry-config-btn">
                        <i data-lucide="refresh-cw"></i> ${I18n.t('hostDetail.retryConnection')}
                    </button>
                </div>
                <div class="host-config-grid">
                    <div class="host-config-card host-config-card-wide">
                        <div class="host-config-card-header">
                            <i data-lucide="wifi-off"></i>
                            <h3>${I18n.t('hostDetail.configUnavailable')}</h3>
                        </div>
                        <div class="host-config-card-body">
                            <p class="host-config-empty">${Utils.escapeHtml(statusText)}</p>
                            <p class="host-config-empty">${I18n.t('hostDetail.errorInfo', { message: Utils.escapeHtml(error?.message || I18n.t('common.unknown')) })}</p>
                            <p class="host-config-empty">${I18n.t('hostDetail.latestMetricAt', { time: Utils.escapeHtml(metricTimeText) })}</p>
                        </div>
                    </div>
                </div>
            </div>
        `;

        DOM.createIcons();

        DOM.$('#retry-config-btn')?.addEventListener('click', async () => {
            const btn = DOM.$('#retry-config-btn');
            btn.disabled = true;
            btn.innerHTML = `<i data-lucide="loader" class="spin"></i> ${I18n.t('hostDetail.retrying')}`;
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

        const memoryTotal = Number.isFinite(memoryTotalBytes) ? this._formatBytes(memoryTotalBytes) : I18n.t('hostDetail.unknownValue');
        const diskTotal = Number.isFinite(diskTotalBytes) ? this._formatBytes(diskTotalBytes) : I18n.t('hostDetail.unknownValue');
        const memoryUsed = Number.isFinite(memoryUsedBytes) ? this._formatBytes(memoryUsedBytes) : I18n.t('hostDetail.unknownValue');
        const diskUsed = Number.isFinite(diskUsedBytes) ? this._formatBytes(diskUsedBytes) : I18n.t('hostDetail.unknownValue');

        container.innerHTML = I18n.t('pageCopy.hostDetail.hostInformationGrid2', { value0: I18n.t('hostDetail.performanceMonitoring'), value1: this.currentTimeRange === 1 ? 'selected' : '', value2: I18n.t('hostDetail.ranges.minute1'), value3: this.currentTimeRange === 10 ? 'selected' : '', value4: I18n.t('hostDetail.ranges.minute10'), value5: this.currentTimeRange === 60 ? 'selected' : '', value6: I18n.t('hostDetail.ranges.hour1'), value7: this.currentTimeRange === 360 ? 'selected' : '', value8: I18n.t('hostDetail.ranges.hour6'), value9: this.currentTimeRange === 1440 ? 'selected' : '', value10: I18n.t('hostDetail.ranges.day1'), value11: this.currentTimeRange === 10080 ? 'selected' : '', value12: I18n.t('hostDetail.ranges.day7'), value13: this.currentTimeRange === 43200 ? 'selected' : '', value14: I18n.t('hostDetail.ranges.month1'), value15: I18n.t('hostDetail.ranges.custom'), value16: metric ? `
                <div class="grid-4 mb-24">
                    <div class="metric-card">
                        <div class="metric-card-label">${I18n.t('hostDetail.cpuUsage')}</div>
                        <div class="metric-card-value">${cpuUsage}%</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-label">${I18n.t('hostDetail.memoryUsage')}</div>
                        <div class="metric-card-value">${memoryUsage}%</div>
                        <div class="metric-card-meta">${memoryUsed} / ${memoryTotal}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-label">${I18n.t('hostDetail.diskUsage')}</div>
                        <div class="metric-card-value">${diskUsage}%</div>
                        <div class="metric-card-meta">${diskUsed} / ${diskTotal}</div>
                    </div>
                    <div class="metric-card">
                        <div class="metric-card-label">${I18n.t('hostDetail.uptimeLabel')}</div>
                        <div class="metric-card-value" style="font-size:16px">${Number.isFinite(summary?.uptime_seconds) ? this._formatUptime(summary.uptime_seconds) : I18n.t('hostDetail.unknownValue')}</div>
                        <div class="metric-card-meta">${I18n.t('hostDetail.lastUpdated', { time: this._formatDateTime(metric.collected_at, 'time') })}</div>
                    </div>
                </div>
                ` : '', value17: I18n.t('hostDetail.basicMetrics'), value18: I18n.t('hostDetail.cpuUsage'), value19: I18n.t('hostDetail.memoryUsageRate'), value20: I18n.t('hostDetail.diskUsageRate'), value21: I18n.t('hostDetail.loadAverage1m'), value22: I18n.t('hostDetail.diskAndNetworkIo'), value23: I18n.t('hostDetail.diskIops'), value24: I18n.t('hostDetail.diskIoThroughput'), value25: I18n.t('hostDetail.networkIoThroughput') });

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
                return I18n.formatTime(date, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
            }
            return I18n.formatDate(date, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
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
            I18n.t('hostDetail.cpuUsage'),
            metrics.map(m => m.cpu_usage || 0),
            '#2f81f7',
            { max: 100, ticks: { callback: value => value + '%' } }
        );

        // 内存图表
        window.hostMonitorCharts.memory = createLineChart(
            'memory-chart',
            I18n.t('hostDetail.memoryUsageRate'),
            metrics.map(m => m.memory_usage || 0),
            '#10b981',
            { max: 100, ticks: { callback: value => value + '%' } }
        );

        // 磁盘使用率图表
        window.hostMonitorCharts.disk = createLineChart(
            'disk-chart',
            I18n.t('hostDetail.diskUsageRate'),
            metrics.map(m => m.disk_usage || 0),
            '#f59e0b',
            { max: 100, ticks: { callback: value => value + '%' } }
        );

        // 负载平均图表
        window.hostMonitorCharts.load = createLineChart(
            'load-chart',
            I18n.t('hostDetail.loadAverage'),
            metrics.map(m => m.data?.load_avg_1min || 0),
            '#8b5cf6'
        );

        // 磁盘 IOPS 图表
        window.hostMonitorCharts.diskIops = createMultiLineChart(
            'disk-iops-chart',
            [
                {
                    label: I18n.t('hostDetail.read'),
                    data: metrics.map(m => m.data?.disk_read_iops || 0),
                    color: '#2f81f7'
                },
                {
                    label: I18n.t('hostDetail.write'),
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
                    label: I18n.t('hostDetail.read'),
                    data: metrics.map(m => m.data?.disk_read_kb_per_sec || 0),
                    color: '#2f81f7'
                },
                {
                    label: I18n.t('hostDetail.write'),
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
                    label: I18n.t('hostDetail.receive'),
                    data: metrics.map(m => m.data?.network_rx_kb_per_sec || 0),
                    color: '#10b981'
                },
                {
                    label: I18n.t('hostDetail.send'),
                    data: metrics.map(m => m.data?.network_tx_kb_per_sec || 0),
                    color: '#8b5cf6'
                }
            ],
            { ticks: { callback: value => value.toFixed(0) + ' KB/s' } }
        );
    },

    async _renderProcessesTab(container) {
        const processes = await API.getHostProcesses(this.currentHost.id);

        container.innerHTML = I18n.t('pageCopy.hostDetail.pidValueCpuValueValueValueValue', { value0: I18n.t('hostDetail.processSearch'), value1: I18n.t('hostDetail.user'), value2: I18n.t('hostDetail.memoryUsageRate'), value3: I18n.t('hostDetail.state'), value4: I18n.t('hostDetail.command'), value5: I18n.t('hostDetail.processDetails'), value6: I18n.t('hostDetail.closeProcessDetails') });

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

            content.innerHTML = I18n.t('pageCopy.hostDetail.processDetails', { value0: I18n.t('hostDetail.tabs.info'), value1: detail.pid, value2: I18n.t('hostDetail.user'), value3: Utils.escapeHtml(detail.user || '-'), value4: I18n.t('hostDetail.state'), value5: Utils.escapeHtml(detail.state || '-'), value6: I18n.t('hostDetail.startTime'), value7: Utils.escapeHtml(detail.start_time || '-'), value8: I18n.t('hostDetail.cpuUsage'), value9: this._formatPercent(detail.cpu_percent), value10: I18n.t('hostDetail.memoryUsageRate'), value11: this._formatPercent(detail.memory_percent), value12: I18n.t('hostDetail.virtualMemory'), value13: formatBytes(detail.vsz * 1024), value14: I18n.t('hostDetail.residentMemory'), value15: formatBytes(detail.rss * 1024), value16: I18n.t('hostDetail.cpuTime'), value17: Utils.escapeHtml(detail.cpu_time || '-'), value18: I18n.t('hostDetail.workingDirectory'), value19: Utils.escapeHtml(detail.cwd || '-'), value20: I18n.t('hostDetail.commandDetails'), value21: I18n.t('hostDetail.command'), value22: Utils.escapeHtml(detail.command || '-'), value23: detail.cmdline ? `
                                <div style="margin-top:12px"><strong>${I18n.t('hostDetail.fullCommandLine')}:</strong></div>
                                <pre>${Utils.escapeHtml(detail.cmdline)}</pre>
                            ` : '', value24: I18n.t('hostDetail.diskIo'), value25: I18n.t('hostDetail.readBytes'), value26: formatBytes(detail.io?.read_bytes || 0), value27: I18n.t('hostDetail.writeBytes'), value28: formatBytes(detail.io?.write_bytes || 0), value29: I18n.t('hostDetail.readChars'), value30: formatBytes(detail.io?.read_chars || 0), value31: I18n.t('hostDetail.writeChars'), value32: formatBytes(detail.io?.write_chars || 0), value33: I18n.t('hostDetail.readSyscalls'), value34: detail.io?.read_syscalls || 0, value35: I18n.t('hostDetail.writeSyscalls'), value36: detail.io?.write_syscalls || 0, value37: I18n.t('hostDetail.networkConnections'), value38: detail.network_connections && detail.network_connections.length > 0 ? `
                            <div class="process-network-table-container">
                                <table class="process-network-table">
                                    <thead>
                                        <tr>
                                            <th>${I18n.t('hostDetail.state')}</th>
                                            <th>${I18n.t('hostDetail.localAddress')}</th>
                                            <th>${I18n.t('hostDetail.localPort')}</th>
                                            <th>${I18n.t('hostDetail.remoteAddress')}</th>
                                            <th>${I18n.t('hostDetail.remotePort')}</th>
                                            <th>${I18n.t('hostDetail.receiveQueue')}</th>
                                            <th>${I18n.t('hostDetail.sendQueue')}</th>
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
                                                <td>${I18n.t('hostDetail.bytes', { count: I18n.formatNumber(conn.recv_bytes || 0) })}</td>
                                                <td>${I18n.t('hostDetail.bytes', { count: I18n.formatNumber(conn.send_bytes || 0) })}</td>
                                            </tr>
                                        `).join('')}
                                    </tbody>
                                </table>
                            </div>
                        ` : `<p style="color:var(--text-secondary);padding:12px">${I18n.t('hostDetail.noActiveConnections')}</p>`, value39: detail.environment && Object.keys(detail.environment).length > 0 ? `
                        <div class="process-detail-section">
                            <h4><i data-lucide="settings"></i> ${I18n.t('hostDetail.environmentPreview')}</h4>
                            <div class="process-detail-code">
                                <pre>${Object.entries(detail.environment).map(([k, v]) =>
                                    `${Utils.escapeHtml(k)}=${Utils.escapeHtml(v)}`
                                ).join('\n')}</pre>
                            </div>
                        </div>
                    ` : '' });

            DOM.createIcons();
        } catch (error) {
            console.error('Failed to load process detail:', error);
            content.innerHTML = `
                <div class="empty-state">
                    <i data-lucide="alert-circle"></i>
                    <p>${I18n.t('hostDetail.processLoadFailed', { message: Utils.escapeHtml(error.message) })}</p>
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
            initialSessionTitle: I18n.t('hostDetail.diagnosisSessionTitle', {
                host: this.currentHost?.name || this.currentHost?.host || hostId
            }),
            initialAsk: null,
            preferFreshSession: false,
        });
    },

    _formatUptime(seconds) {
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return I18n.t('hostDetail.uptime', { days, hours, minutes });
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
            title: I18n.t('hostDetail.customRangeTitle'),
            width: '480px',
            content: `
                <div class="form-group">
                    <label>${I18n.t('hostDetail.rangeStart')}</label>
                    <input type="datetime-local" class="filter-input" id="custom-start-time" data-date-picker />
                </div>
                <div class="form-group">
                    <label>${I18n.t('hostDetail.rangeEnd')}</label>
                    <input type="datetime-local" class="filter-input" id="custom-end-time" data-date-picker />
                </div>
            `,
            buttons: [
                { text: I18n.t('common.cancel'), variant: 'secondary', onClick: () => {
                    Modal.hide();
                    DOM.$('#monitor-time-range').value = this.currentTimeRange;
                }},
                { text: I18n.t('common.confirm'), variant: 'primary', onClick: () => {
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
            if (startInput) DatePicker.setValue(startInput, startTime);
            if (endInput) DatePicker.setValue(endInput, endTime);
        }, 0);
    },

    async _applyCustomTimeRange() {
        const startInput = DOM.$('#custom-start-time');
        const endInput = DOM.$('#custom-end-time');

        if (!startInput || !endInput) return;

        const start = startInput.value;
        const end = endInput.value;

        if (!start || !end) {
            Toast.warning(I18n.t('hostDetail.selectRange'));
            return;
        }

        const startDate = new Date(start);
        const endDate = new Date(end);

        if (startDate >= endDate) {
            Toast.warning(I18n.t('hostDetail.invalidRange'));
            return;
        }

        Modal.hide();

        try {
            await this._loadCustomRangeData(start, end);
        } catch (error) {
            console.error('Failed to load custom range data:', error);
            Toast.error(I18n.t('hostDetail.dataLoadFailed', { message: error.message }));
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
                Toast.warning(I18n.t('hostDetail.noDataInRange'));
                DOM.$('#monitor-time-range').value = this.currentTimeRange;
                return;
            }

            this._renderMonitorCharts(metrics);
            Toast.success(I18n.t('hostDetail.customRangeLoaded'));
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
