/* Dashboard page - Tech Dark Theme */
const DashboardPage = {
    _timer: null,
    _datasources: [],
    _hosts: [],
    _healthStatuses: {},
    _healthReasons: {},
    _metricCache: {},
    _filters: { health: '', dbType: '', hostId: '', search: '' },

    // ── Helpers ──────────────────────────────────────────────
    _donut(online, total, r) {
        if (total === 0) return `<svg width="${r*2+16}" height="${r*2+16}" viewBox="0 0 ${r*2+16} ${r*2+16}"><circle cx="${r+8}" cy="${r+8}" r="${r}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="8"/><text class="donut-center-text" x="${r+8}" y="${r+8}">--</text></svg>`;
        const cx = r + 8, cy = r + 8, sw = 8;
        const pct = online / total;
        const circ = 2 * Math.PI * r;
        const dash = circ * pct;
        const gap  = circ - dash;
        const startAngle = -Math.PI / 2;
        const x1 = cx + r * Math.cos(startAngle);
        const y1 = cy + r * Math.sin(startAngle);
        const label = Math.round(pct * 100) + '%';
        return `<svg width="${r*2+16}" height="${r*2+16}" viewBox="0 0 ${r*2+16} ${r*2+16}">
  <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="${sw}"/>
  <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${pct > 0.8 ? '#3fb950' : pct > 0.5 ? '#d29922' : '#f85149'}" stroke-width="${sw}" stroke-dasharray="${dash} ${gap}" stroke-dashoffset="${circ * 0.25}" stroke-linecap="round" style="transition:stroke-dasharray 0.6s ease"/>
  <text class="donut-center-text" x="${cx}" y="${cy}">${label}</text>
</svg>`;
    },

    _relTime(iso) {
        const diff = Math.max(0, (Date.now() - new Date(iso)) / 1000);
        if (diff < 60) return I18n.formatRelativeTime(-Math.round(diff), 'second', { numeric: 'always' });
        if (diff < 3600) return I18n.formatRelativeTime(-Math.round(diff / 60), 'minute', { numeric: 'always' });
        if (diff < 86400) return I18n.formatRelativeTime(-Math.round(diff / 3600), 'hour', { numeric: 'always' });
        if (diff < 2592000) return I18n.formatRelativeTime(-Math.round(diff / 86400), 'day', { numeric: 'always' });
        if (diff < 31536000) return I18n.formatRelativeTime(-Math.round(diff / 2592000), 'month', { numeric: 'always' });
        return I18n.formatRelativeTime(-Math.round(diff / 31536000), 'year', { numeric: 'always' });
    },

    _formatAlertTitle(alert) {
        if (typeof AlertsPage !== 'undefined' && typeof AlertsPage.formatAlertTitle === 'function') {
            return AlertsPage.formatAlertTitle(alert);
        }
        const title = String(alert?.title || '').trim();
        if (/^(?:Database connection failed|\u6570\u636e\u5e93\u8fde\u63a5\u5931\u8d25)$/i.test(title)) {
            return I18n.t('alerts.titles.connectionFailure');
        }
        return title || '-';
    },

    _dbDotClass(type) {
        const map = {
            mysql: 'db-dot-mysql',
            postgresql: 'db-dot-postgresql',
            oracle: 'db-dot-oracle',
            sqlserver: 'db-dot-sqlserver',
            'tdsql-c-mysql': 'db-dot-tdsql-c-mysql',
            'oceanbase-mysql': 'db-dot-oceanbase-mysql',
            opengauss: 'db-dot-postgresql',
            hana: 'db-dot-hana'
        };
        return map[type] || 'db-dot-other';
    },

    _isConnectionFailureHealth(health) {
        if (!health) return false;
        if (Array.isArray(health.violations) && health.violations.some(item => item?.type === 'connection_failure')) {
            return true;
        }
        return String(health.message || '').includes(I18n.t('pageCopy.dashboard.connectionFailed'));
    },

    openAlertFromDashboard(alertId) {
        Router.navigate('alerts');
        setTimeout(async () => {
            try {
                const alert = await API.getAlert(alertId);
                await AlertsPage.showAlertDetail(alert);
            } catch (e) {
                Toast.error(I18n.t('dashboard.loadAlertFailed', { message: e.message }));
            }
        }, 0);
    },

    openDatasourceFromDashboard(datasourceId) {
        const datasource = this._datasources.find(item => item.id === datasourceId);
        if (datasource) {
            Store.set('currentConnection', datasource);
            Store.set('currentDatasource', datasource);
            Store.set('currentInstance', datasource);
            Store.set('currentInstanceId', datasource.id);
        }
        Router.navigate(`instance-detail?datasource=${datasourceId}&tab=monitor`);
    },

    openHostFromDashboard(hostId) {
        Router.navigate(`host-detail?host=${hostId}&tab=monitor`);
    },

    _hostAnomalyReason(host) {
        const reason = String(host?.status_message || '').trim();
        if (reason) {
            const fixedReasons = {
                '\u8fde\u63a5\u5931\u8d25\uff08\u8d85\u8fc75\u5206\u949f\u672a\u6536\u5230\u6570\u636e\uff09': 'staleMetrics',
                '\u6682\u65e0\u76d1\u63a7\u6570\u636e': 'noMetrics',
                '\u8fd0\u884c\u6b63\u5e38': 'normal'
            };
            if (fixedReasons[reason]) return I18n.t(`dashboard.hostReasons.${fixedReasons[reason]}`);

            const metrics = { CPU: 'cpu', '\u5185\u5b58': 'memory', '\u78c1\u76d8': 'disk' };
            const localizedIssues = reason.split('\uff1b').map(issue => {
                const match = issue.match(/^(CPU|\u5185\u5b58|\u78c1\u76d8)\u4f7f\u7528\u7387(\u8fc7\u9ad8|\u8f83\u9ad8)\s*\(([^)]+)\)$/);
                if (!match) return issue;
                return I18n.t(
                    match[2] === '\u8fc7\u9ad8' ? 'dashboard.hostReasons.metricTooHigh' : 'dashboard.hostReasons.metricHigh',
                    { metric: I18n.t(`dashboard.hostReasons.${metrics[match[1]]}`), value: match[3] }
                );
            });
            return localizedIssues.join(I18n.getLocale() === 'zh-CN' ? '\uff1b' : '; ');
        }

        const status = host?.status;
        if (status === 'offline') return I18n.t('dashboard.hostReasons.offline');
        if (status === 'error') return I18n.t('dashboard.hostReasons.error');
        if (status === 'warning') return I18n.t('dashboard.hostReasons.warning');
        return I18n.t('dashboard.hostReasons.unknown');
    },

    // ── Main render ──────────────────────────────────────────
    async render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';
        this._stopTimer();

        try {
            const [datasources, hosts] = await Promise.all([
                API.getDatasources(),
                API.getHosts()
            ]);
            Store.set('datasources', datasources);
            this._datasources = datasources;
            this._hosts = hosts;

            Header.render(I18n.t('navigation.dashboard'), this._buildHeaderActions());
            content.innerHTML = '';

            if (datasources.length === 0) {
                content.innerHTML = `<div class="empty-state"><i data-lucide="database"></i><h3>${I18n.t('dashboard.noDatasources')}</h3><p>${I18n.t('dashboard.addDatasourcePrompt')}</p><button class="btn btn-primary mt-16" onclick="Router.navigate('datasources')"><i data-lucide="plus"></i> ${I18n.t('dashboard.addDatasource')}</button></div>`;
                DOM.createIcons();
                return;
            }

            // Overview panel
            const overview = DOM.el('div', { className: 'dashboard-overview', id: 'dashboard-overview' });
            overview.innerHTML = this._buildOverviewSkeleton();
            content.appendChild(overview);

            // Anomaly section
            const anomalySection = DOM.el('div', { className: 'resource-section', id: 'anomaly-section', style: { display: 'none' } });
            anomalySection.innerHTML = `<div class="resource-section-header anomaly" id="anomaly-header"><span>⚠ ${I18n.t('dashboard.needsAttention')}</span><span class="resource-count-badge anomaly" id="anomaly-count">0</span></div><div class="dashboard-grid" id="anomaly-grid"></div>`;
            content.appendChild(anomalySection);

            // Normal section
            const normalSection = DOM.el('div', { className: 'resource-section', id: 'normal-section' });
            normalSection.innerHTML = `<div class="resource-section-header normal" id="normal-header"><span>${I18n.t('dashboard.otherResources')}</span><span class="resource-count-badge normal" id="normal-count">0</span></div><div class="dashboard-grid" id="normal-grid"></div>`;
            content.appendChild(normalSection);

            // Live status bar
            const liveBar = DOM.el('div', { style: { display: 'flex', justifyContent: 'flex-end', marginBottom: '8px', marginTop: '-16px' } });
            liveBar.innerHTML = `<div class="live-indicator"><span class="live-dot"></span><span id="last-update">${I18n.t('common.loading')}</span></div>`;
            content.insertBefore(liveBar, anomalySection);

            this._renderCards();
            DOM.createIcons();

            await this._refreshAll();
            this._startTimer();
        } catch (err) {
            content.innerHTML = `<div class="empty-state"><h3>${I18n.t('dashboard.loadFailed')}</h3><p>${err.message}</p></div>`;
        }
    },

    _buildHeaderActions() {
        const dbTypes = [...new Set(this._datasources.map(d => d.db_type))];
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters' });
        filtersContainer.innerHTML = `
            <select id="filter-health" class="filter-select">
                <option value="">${I18n.t('dashboard.allStatuses')}</option>
                <option value="healthy">${I18n.t('dashboard.health.healthy')}</option>
                <option value="warning">${I18n.t('dashboard.health.warning')}</option>
                <option value="critical">${I18n.t('dashboard.health.abnormal')}</option>
                <option value="unknown">${I18n.t('dashboard.health.unknown')}</option>
            </select>
            <select id="filter-dbtype" class="filter-select">
                <option value="">${I18n.t('dashboard.allTypes')}</option>
                ${dbTypes.map(t => `<option value="${t}">${t}</option>`).join('')}
            </select>
            <select id="filter-host" class="filter-select">
                <option value="">${I18n.t('dashboard.allHosts')}</option>
                ${this._hosts.map(h => `<option value="${h.id}">${h.name || h.host}</option>`).join('')}
            </select>
            <input id="filter-search" class="filter-input" type="text" placeholder="${I18n.t('dashboard.searchPlaceholder')}" value="${this._filters.search}">
        `;
        setTimeout(() => {
            const bindFilter = (id, key) => {
                const el = DOM.$(`#${id}`);
                if (!el) return;
                el.value = this._filters[key];
                el.addEventListener('change', () => { this._filters[key] = el.value; this._renderCards(); });
            };
            bindFilter('filter-health', 'health');
            bindFilter('filter-dbtype', 'dbType');
            bindFilter('filter-host', 'hostId');
            const searchEl = DOM.$('#filter-search');
            if (searchEl) searchEl.addEventListener('input', () => { this._filters.search = searchEl.value.toLowerCase().trim(); this._renderCards(); });
        }, 0);
        return filtersContainer;
    },

    // ── Overview panels ──────────────────────────────────────
    _renderHostPanel(hosts) {
        const anomaly = hosts.filter(h => h.status === 'offline' || h.status === 'error');
        const online  = hosts.length - anomaly.length;
        const donutSvg = this._donut(online, hosts.length, 52);
        const listHtml = anomaly.length === 0
            ? `<div class="all-healthy-text">✓ ${I18n.t('dashboard.allOnline')}</div>`
            : `<div class="anomaly-host-list">${anomaly.slice(0,3).map(h =>
                `<div class="anomaly-host-item clickable" onclick="DashboardPage.openHostFromDashboard(${h.id})">
                    <div class="anomaly-host-main"><span class="status-dot ${h.status}"></span>${Utils.escapeHtml(h.name || h.host)}</div>
                    <div class="anomaly-host-reason" title="${Utils.escapeHtml(this._hostAnomalyReason(h))}">${Utils.escapeHtml(this._hostAnomalyReason(h))}</div>
                </div>`
              ).join('')}${anomaly.length > 3 ? `<div class="anomaly-host-item" style="color:rgba(255,255,255,0.3)">${I18n.t('dashboard.moreAbnormalHosts', { count: anomaly.length - 3 })}</div>` : ''}</div>`;

        const panel = DOM.$('#panel-hosts');
        if (!panel) return;
        panel.innerHTML = `
            <div class="overview-panel-title">${I18n.t('dashboard.hostHealth')}</div>
            <div class="donut-container">
                ${donutSvg}
                <div class="donut-legend">
                    <div class="donut-legend-item"><span class="donut-legend-dot" style="background:#3fb950"></span>${I18n.t('dashboard.online')} ${online}</div>
                    <div class="donut-legend-item"><span class="donut-legend-dot" style="background:#f85149"></span>${I18n.t('dashboard.abnormal')} ${anomaly.length}</div>
                </div>
            </div>
            ${listHtml}`;
    },

    async _renderAlertPanel() {
        const panel = DOM.$('#panel-alerts');
        if (!panel) return;
        try {
            const resp = await API.getAlerts({ status: 'active', limit: 5 });
            const alerts = resp.alerts || [];
            const total  = resp.total  || 0;
            const titleBadge = total > 0 ? `<span class="alert-count-badge">${total}</span>` : '';
            const viewAllHtml = total > 0 ? `<div class="alert-view-all"><span class="alert-view-all-link" onclick="Router.navigate('alerts')">${I18n.t('dashboard.viewAllAlerts', { count: total })}</span></div>` : '';
            const listHtml = alerts.length === 0
                ? `<div class="no-alerts-text">✓ ${I18n.t('dashboard.systemHealthy')}</div>`
                : `<div class="alert-list">${alerts.map(a => {
                    const ds = this._datasources.find(d => d.id === a.datasource_id);
                    const dsName = ds ? (ds.name || ds.host || `#${a.datasource_id}`) : `#${a.datasource_id}`;
                    const alertTitle = this._formatAlertTitle(a);
                    return `
                    <div class="alert-list-item" onclick="DashboardPage.openAlertFromDashboard(${a.id})" style="cursor:pointer;">
                        <div class="alert-severity-bar ${a.severity}"></div>
                        <div class="alert-content">
                            <div class="alert-title">${Utils.escapeHtml(alertTitle)}</div>
                            <div class="alert-meta"><span class="alert-ds-tag">${Utils.escapeHtml(dsName)}</span><span class="alert-time">${this._relTime(a.created_at)}</span></div>
                        </div>
                    </div>`;
                }).join('')}</div>`;
            const titleCls = total > 10 ? ' alert-title-critical' : '';
            panel.innerHTML = `<div class="overview-panel-title${titleCls}">⚡ ${I18n.t('dashboard.activeAlerts')}${titleBadge}</div>${listHtml}${viewAllHtml}`;
        } catch {
            panel.innerHTML = `<div class="overview-panel-title">⚡ ${I18n.t('dashboard.activeAlerts')}</div><div style="color:rgba(255,255,255,0.3);font-size:13px">${I18n.t('dashboard.loadFailed')}</div>`;
        }
    },

    _renderDbPanel(datasources, healthStatuses) {
        const total   = datasources.length;
        const healthy = datasources.filter(d => (healthStatuses[d.id] || 'unknown') === 'healthy').length;
        const donutSvg = this._donut(healthy, total, 52);
        const unhealthy = datasources
            .filter(d => (healthStatuses[d.id] || 'unknown') !== 'healthy')
            .sort((a, b) => {
                const rank = { critical: 0, error: 0, warning: 1, unknown: 2, healthy: 3 };
                return (rank[healthStatuses[a.id] || 'unknown'] ?? 9) - (rank[healthStatuses[b.id] || 'unknown'] ?? 9);
            });
        const visibleItems = (unhealthy.length > 0 ? unhealthy : datasources).slice(0, 4);
        const hiddenCount = (unhealthy.length > 0 ? unhealthy.length : datasources.length) - visibleItems.length;
        const listTitle = unhealthy.length > 0 ? I18n.t('dashboard.unhealthyDatasources') : I18n.t('dashboard.healthyDatasources');
        const listHtml = visibleItems.length === 0
            ? `<div class="all-healthy-text">${I18n.t('dashboard.noDatasources')}</div>`
            : `<div class="db-health-list">
                <div class="db-health-list-title">${listTitle}</div>
                ${visibleItems.map(d => {
                    const status = healthStatuses[d.id] || 'unknown';
                    const statusCls = this._statusClass(status);
                    const name = Utils.escapeHtml(d.name || d.host || I18n.t('dashboard.datasourceFallback', { id: d.id }));
                    const type = Utils.escapeHtml(d.db_type || '-');
                    const host = Utils.escapeHtml(`${d.host || '-'}:${d.port || '-'}`);
                    const statusLabel = Utils.escapeHtml(this._healthLabelShort(status, this._healthReasons[d.id]));
                    return `
                        <div class="db-health-item" title="${name} · ${host}" onclick="DashboardPage.openDatasourceFromDashboard(${d.id})">
                            <span class="status-dot ${statusCls}"></span>
                            <span class="db-health-name">${name}</span>
                            <span class="db-health-type">${type}</span>
                            <span class="db-health-status health-badge-${statusCls}">${statusLabel}</span>
                        </div>
                    `;
                }).join('')}
                ${hiddenCount > 0 ? `<div class="db-health-more">${I18n.t(unhealthy.length > 0 ? 'dashboard.moreUnhealthyDatasources' : 'dashboard.moreDatasources', { count: hiddenCount })}</div>` : ''}
            </div>`;

        const panel = DOM.$('#panel-dbs');
        if (!panel) return;
        panel.innerHTML = `
            <div class="overview-panel-title">${I18n.t('dashboard.datasourceHealth')}</div>
            <div class="donut-container">
                ${donutSvg}
                <div class="donut-legend">
                    <div class="donut-legend-item"><span class="donut-legend-dot" style="background:#3fb950"></span>${I18n.t('dashboard.healthy')} ${healthy}</div>
                    <div class="donut-legend-item"><span class="donut-legend-dot" style="background:#f85149"></span>${I18n.t('dashboard.abnormal')} ${total - healthy}</div>
                </div>
            </div>
            ${listHtml}`;
    },

    _buildOverviewSkeleton() {
        return `
        <div class="overview-panel" id="panel-hosts">
            <div class="overview-panel-title">${I18n.t('dashboard.hostHealth')}</div>
            <div class="donut-container"><div style="width:120px;height:120px;background:rgba(255,255,255,0.04);border-radius:50%;"></div></div>
        </div>
        <div class="overview-panel" id="panel-dbs">
            <div class="overview-panel-title">${I18n.t('dashboard.datasourceHealth')}</div>
            <div class="donut-container"><div style="width:120px;height:120px;background:rgba(255,255,255,0.04);border-radius:50%;"></div></div>
        </div>
        <div class="overview-panel panel-alerts" id="panel-alerts">
            <div class="overview-panel-title">⚡ ${I18n.t('dashboard.activeAlerts')}</div>
            <div style="color:rgba(255,255,255,0.3);font-size:13px">${I18n.t('common.loading')}</div>
        </div>`;
    },

    // ── Card rendering ───────────────────────────────────────
    _filterDatasources() {
        return this._datasources.filter(conn => {
            if (this._filters.health) {
                const s = this._healthStatuses[conn.id] || 'unknown';
                if (s !== this._filters.health) return false;
            }
            if (this._filters.dbType && conn.db_type !== this._filters.dbType) return false;
            if (this._filters.hostId && conn.host_id !== parseInt(this._filters.hostId)) return false;
            if (this._filters.search) {
                const q = this._filters.search;
                const host = this._hosts.find(h => h.id === conn.host_id);
                const inHost = host ? (host.name||'').toLowerCase().includes(q) || host.host.toLowerCase().includes(q) : false;
                if (!conn.name.toLowerCase().includes(q) && !conn.host.toLowerCase().includes(q) &&
                    !(conn.database||'').toLowerCase().includes(q) && !inHost) return false;
            }
            return true;
        });
    },

    _statusClass(status) {
        if (status === 'healthy') return 'healthy';
        if (status === 'warning') return 'warning';
        if (status === 'critical' || status === 'error') return 'critical';
        return 'unknown';
    },

    _renderCards() {
        const filtered  = this._filterDatasources();
        const anomalies = filtered.filter(c => {
            const s = this._healthStatuses[c.id] || 'unknown';
            return s === 'critical' || s === 'error' || s === 'warning';
        });
        const normals = filtered.filter(c => {
            const s = this._healthStatuses[c.id] || 'unknown';
            return s !== 'critical' && s !== 'error' && s !== 'warning';
        });

        // Anomaly section visibility
        const anomalySection = DOM.$('#anomaly-section');
        if (anomalySection) anomalySection.style.display = anomalies.length > 0 ? '' : 'none';
        const anomalyCount = DOM.$('#anomaly-count');
        if (anomalyCount) anomalyCount.textContent = anomalies.length;

        const normalCount = DOM.$('#normal-count');
        if (normalCount) normalCount.textContent = normals.length;

        this._fillGrid('anomaly-grid', anomalies);
        this._fillGrid('normal-grid', normals);
        DOM.createIcons();
    },

    _fillGrid(gridId, list) {
        const grid = DOM.$(`#${gridId}`);
        if (!grid) return;
        if (list.length === 0) {
            grid.innerHTML = `<div style="color:rgba(255,255,255,0.3);font-size:13px;padding:8px 0">${I18n.t('dashboard.noMatchingResources')}</div>`;
            return;
        }
        grid.innerHTML = '';
        for (const conn of list) {
            const status = this._healthStatuses[conn.id] || 'unknown';
            const statusCls = this._statusClass(status);
            const m = this._metricCache[conn.id] || null;
            const card = DOM.el('div', {
                className: `dash-card status-${statusCls}`,
                onClick: () => {
                    Store.set('currentConnection', conn);
                    Store.set('currentDatasource', conn);
                    Store.set('currentInstance', conn);
                    Store.set('currentInstanceId', conn.id);
                    Router.navigate(`instance-detail?datasource=${conn.id}&tab=monitor`);
                }
            });
            card.innerHTML = `
                <div class="dash-card-header">
                    <div class="dash-card-name">
                        <span class="status-dot ${statusCls}"></span>
                        ${conn.name}
                    </div>
                    <div class="dash-card-header-right">
                        <span class="dash-card-health health-badge-${statusCls}" id="health-${conn.id}">${this._healthLabelShort(status, this._healthReasons[conn.id])}</span>
                        <span class="dash-card-type type-${conn.db_type}">${conn.db_type}</span>
                    </div>
                </div>
                <div class="dash-card-host">${conn.host}:${conn.port}${conn.database ? ' / ' + conn.database : ''}</div>
                <div class="dash-card-divider"></div>
                <div class="dash-card-metrics" id="dash-metrics-${conn.id}">
                    <div><div class="dash-metric-label">${I18n.t('dashboard.activeConnections')}</div><div class="dash-metric-value" id="conn-${conn.id}">${m ? m.active : '--'}</div></div>
                    <div>
                        <div class="dash-metric-label">CPU</div>
                        <div class="dash-metric-value" id="cpu-${conn.id}">${m && m.cpu != null ? m.cpu + '%' : '--'}</div>
                        <div class="dash-metric-bar"><div class="dash-metric-bar-fill${m && m.cpu != null && parseFloat(m.cpu) >= 80 ? ' level-high' : m && m.cpu != null && parseFloat(m.cpu) >= 60 ? ' level-medium' : ''}" id="cpu-bar-${conn.id}" style="width:${m && m.cpu != null ? Math.min(100, parseFloat(m.cpu)) + '%' : '0%'}"></div></div>
                    </div>
                    <div><div class="dash-metric-label">QPS</div><div class="dash-metric-value" id="qps-${conn.id}">${m && m.qps != null ? m.qps : '--'}</div></div>
                </div>`;
            grid.appendChild(card);
        }
    },

    _healthLabel(status, reason = '') {
        if (reason === 'connection_failure') return `✗ ${I18n.t('dashboard.health.connectionFailed')}`;
        const map = {
            healthy: `✓ ${I18n.t('dashboard.health.healthy')}`,
            warning: `⚠ ${I18n.t('dashboard.health.warning')}`,
            critical: `✗ ${I18n.t('dashboard.health.abnormal')}`,
            error: `✗ ${I18n.t('dashboard.health.abnormal')}`,
            unknown: `-- ${I18n.t('dashboard.health.unknown')}`
        };
        return map[status] || map.unknown;
    },

    _healthLabelShort(status, reason = '') {
        if (reason === 'connection_failure') return I18n.t('dashboard.health.connectionFailed');
        const map = {
            healthy: I18n.t('dashboard.health.healthy'),
            warning: I18n.t('dashboard.health.warning'),
            critical: I18n.t('dashboard.health.abnormal'),
            error: I18n.t('dashboard.health.abnormal'),
            unknown: I18n.t('dashboard.health.unknown')
        };
        return map[status] || map.unknown;
    },

    // ── Metrics & refresh ────────────────────────────────────
    async _refreshAll() {
        await Promise.all([
            this._refreshHostPanel(),
            this._renderAlertPanel(),
            this._refreshMetrics()
        ]);
        const el = DOM.$('#last-update');
        if (el) el.textContent = I18n.t('dashboard.lastUpdated', { time: I18n.formatTime(new Date(), { hour12: false }) });
    },

    async _refreshHostPanel() {
        try {
            const hosts = await API.getHosts();
            this._hosts = hosts;
            this._renderHostPanel(hosts);
        } catch { /* keep skeleton */ }
    },

    async _refreshMetrics() {
        const filtered = this._filterDatasources();
        if (filtered.length === 0) {
            this._renderDbPanel(this._datasources, this._healthStatuses);
            this._renderCards();
            return;
        }
        try {
            const connIds = filtered.map(c => c.id);
            const batchResult = await API.getBatchDashboard(connIds);
            for (const c of filtered) {
                const entry = batchResult[String(c.id)];
                if (!entry) continue;
                // Health
                if (entry.health) {
                    const h = entry.health;
                    let status = 'unknown';
                    if (h.status === 'healthy') status = 'healthy';
                    else if (h.status === 'warning') status = 'warning';
                    else if (h.status === 'error' || h.status === 'critical') status = 'critical';
                    this._healthStatuses[c.id] = status;
                    this._healthReasons[c.id] = this._isConnectionFailureHealth(h) ? 'connection_failure' : '';
                    const hEl = DOM.$(`#health-${c.id}`);
                    if (hEl) {
                        hEl.textContent = this._healthLabelShort(status, this._healthReasons[c.id]);
                        hEl.className = `dash-card-health health-badge-${this._statusClass(status)}`;
                    }
                }
                // Metric
                const metricData = entry.metric ? (entry.metric.data || {}) : null;
                if (metricData) {
                    const active = metricData.connections_active ?? metricData.connected_clients ?? metricData.user_sessions ?? metricData.connections_current ?? 0;
                    const cpuVal = metricData.cpu_usage != null ? metricData.cpu_usage : metricData.os_cpu_usage;
                    const cpu = cpuVal != null ? cpuVal.toFixed(1) : null;
                    const qps = metricData.qps != null ? metricData.qps.toFixed(1) : null;
                    this._metricCache[c.id] = { active, cpu, qps };
                    const connEl = DOM.$(`#conn-${c.id}`);
                    const cpuEl  = DOM.$(`#cpu-${c.id}`);
                    const barEl  = DOM.$(`#cpu-bar-${c.id}`);
                    const qpsEl  = DOM.$(`#qps-${c.id}`);
                    if (connEl) connEl.textContent = active;
                    if (cpuEl)  cpuEl.textContent  = cpu != null ? cpu + '%' : '--';
                    if (qpsEl)  qpsEl.textContent  = qps != null ? qps : '--';
                    if (barEl && cpu != null) {
                        const pct = Math.min(100, parseFloat(cpu));
                        barEl.style.width = pct + '%';
                        barEl.className = 'dash-metric-bar-fill' + (pct >= 80 ? ' level-high' : pct >= 60 ? ' level-medium' : '');
                    }
                }
            }
        } catch (e) { /* keep existing values */ }
        this._renderDbPanel(this._datasources, this._healthStatuses);
        this._renderCards();
    },

    _startTimer() {
        this._stopTimer();
        this._timer = setInterval(() => this._refreshAll(), 15000);
    },

    _stopTimer() {
        if (this._timer) { clearInterval(this._timer); this._timer = null; }
    }
};
