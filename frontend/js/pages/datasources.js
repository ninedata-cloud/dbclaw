/* Datasources management page */
const DatasourcesPage = {
    allDatasources: [],
    filteredDatasources: [],
    latestMetrics: {},
    _sort: {
        field: 'name',
        direction: 'asc'
    },

    async render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            this.allDatasources = await API.getDatasources();
            this.filteredDatasources = [...this.allDatasources];
            this._applySort();
            Store.set('datasources', this.allDatasources);

            Header.render('数据源管理', this._buildHeaderActions());

            content.innerHTML = '';

            if (this.allDatasources.length === 0) {
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="database"></i>
                        <h3>暂无数据源</h3>
                        <p>添加第一个数据库连接以开始监控和诊断</p>
                    </div>
                `;
                DOM.createIcons();
                return;
            }

            // Table container
            const tableContainer = DOM.el('div', { id: 'datasource-table-container' });
            content.appendChild(tableContainer);

            this._renderTable();
            DOM.createIcons();

            // Fetch latest metrics separately (after table renders for fast initial load)
            this._loadLatestMetrics();

        } catch (err) {
            Toast.error('加载数据源失败: ' + err.message);
        }
    },

    _escapeHtml(value) {
        return Utils.escapeHtml(String(value ?? ''));
    },

    _escapeAttr(value) {
        return this._escapeHtml(value).replace(/"/g, '&quot;');
    },

    _getDbTypeLabel(dbType) {
        const labels = {
            mysql: 'MySQL',
            postgresql: 'PostgreSQL',
            sqlserver: 'SQL Server',
            oracle: 'Oracle',
            'tdsql-c-mysql': 'TDSQL-C MySQL',
            opengauss: 'openGauss',
            hana: 'SAP HANA',
        };
        return labels[dbType] || dbType || '-';
    },

    _formatHourValue(hours) {
        const value = Number(hours);
        if (!Number.isFinite(value)) return '-';
        return String(parseFloat(value.toFixed(2)));
    },

    _getSilenceState(datasource) {
        if (!datasource?.silence_until) {
            return {
                isSilenced: false,
                remainingHours: null,
                silenceUntil: null,
                reason: datasource?.silence_reason || null,
            };
        }

        const silenceUntil = new Date(datasource.silence_until);
        if (Number.isNaN(silenceUntil.getTime())) {
            return {
                isSilenced: false,
                remainingHours: null,
                silenceUntil: null,
                reason: datasource?.silence_reason || null,
            };
        }

        const remainingMs = silenceUntil.getTime() - Date.now();
        if (remainingMs <= 0) {
            return {
                isSilenced: false,
                remainingHours: null,
                silenceUntil,
                reason: datasource?.silence_reason || null,
            };
        }

        return {
            isSilenced: true,
            remainingHours: Math.round((remainingMs / 3600000) * 100) / 100,
            silenceUntil,
            reason: datasource?.silence_reason || null,
        };
    },

    _renderSilenceBadge(datasource) {
        const state = this._getSilenceState(datasource);
        if (!state.isSilenced) return '';

        const titleParts = [
            `静默至：${Format.datetime(datasource.silence_until)}`,
            `剩余：${this._formatHourValue(state.remainingHours)} 小时`,
        ];
        if (state.reason) {
            titleParts.push(`原因：${state.reason}`);
        }

        return `
            <div style="margin-top:6px;">
                <span class="badge badge-warning" title="${this._escapeAttr(titleParts.join('\n'))}">
                    告警静默中 ${this._escapeHtml(this._formatHourValue(state.remainingHours))}h
                </span>
            </div>
        `;
    },

    async _loadLatestMetrics() {
        try {
            this.latestMetrics = await API.getDatasourcesLatestMetrics();
            this._renderTable();
        } catch (err) {
            console.warn('Failed to load latest metrics:', err);
        }
    },

    _buildHeaderActions() {
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters' });
        filtersContainer.innerHTML = `
            <input type="text" id="filterName" class="filter-input" placeholder="搜索名称/IP/主机名/数据库名...">
            <input type="text" id="filterTags" class="filter-input" placeholder="标签筛选（逗号分隔，可组合）">
            <select id="filterType" class="filter-select">
                <option value="">所有类型</option>
                <option value="mysql">MySQL</option>
                <option value="postgresql">PostgreSQL</option>
                <option value="oracle">Oracle</option>
                <option value="sqlserver">SQL Server</option>
                <option value="tdsql-c-mysql">TDSQL-C MySQL</option>
                <option value="opengauss">openGauss</option>
                <option value="hana">SAP HANA</option>
            </select>
        `;

        const newBtn = DOM.el('button', { className: 'btn btn-primary' });
        newBtn.innerHTML = '<i data-lucide="plus"></i> 新建数据源';
        newBtn.onclick = () => DatasourceForm.show(null, () => this.render());

        setTimeout(() => {
            this._setupFilterListeners();
            DOM.createIcons();
        }, 0);

        return [filtersContainer, newBtn];
    },

    _setupFilterListeners() {
        DOM.$('#filterName')?.addEventListener('input', () => this._applyFilters());
        DOM.$('#filterTags')?.addEventListener('input', () => this._applyFilters());
        DOM.$('#filterType')?.addEventListener('change', () => this._applyFilters());
    },

    _applyFilters() {
        clearTimeout(this._filterDebounce);
        this._filterDebounce = setTimeout(() => this._reloadWithFilters(), 250);
    },

    async _reloadWithFilters() {
        const q = DOM.$('#filterName')?.value.trim() || '';
        const tagsRaw = DOM.$('#filterTags')?.value.trim() || '';
        const db_type = DOM.$('#filterType')?.value || '';

        const params = {};
        if (q) params.q = q;
        if (tagsRaw) params.tags = tagsRaw;
        if (db_type) params.db_type = db_type;

        try {
            this.allDatasources = await API.getDatasources(params);
            this.filteredDatasources = [...this.allDatasources];
            this._applySort();
            Store.set('datasources', this.allDatasources);
            this._renderTable();
            this._loadLatestMetrics();
        } catch (err) {
            Toast.error('筛选失败: ' + err.message);
        }
    },

    _getStatusBadge(conn) {
        const status = conn.connection_status || 'unknown';
        const message = conn.connection_error || '';

        const statusMap = {
            normal: { icon: '✓', label: '正常', class: 'badge-success', title: message || '连接正常' },
            failed: { icon: '✗', label: '失败', class: 'badge-danger', title: message || '连接失败' },
            warning: { icon: '⚠', label: '警告', class: 'badge-warning', title: message || '连接警告' },
            unknown: { icon: '○', label: '未知', class: 'badge-secondary', title: message || '暂无监控数据' }
        };

        const s = statusMap[status] || statusMap.unknown;
        return `<span class="badge ${s.class}" title="${s.title}" style="cursor:help">${s.icon} ${s.label}</span>`;
    },

    _getMetricColor(value) {
        if (value == null) return '';
        if (value >= 90) return 'text-danger';
        if (value >= 80) return 'text-warning';
        return '';
    },

    _toggleSort(field) {
        if (this._sort.field === field) {
            this._sort.direction = this._sort.direction === 'asc' ? 'desc' : 'asc';
        } else {
            this._sort.field = field;
            this._sort.direction = 'asc';
        }
        this._applySort();
    },

    _applySort() {
        const { field, direction } = this._sort;
        this.filteredDatasources.sort((a, b) => {
            let va, vb;
            // For CPU, QPS, connections - get from latestMetrics
            if (field === 'cpu_usage' || field === 'qps' || field === 'connections_active') {
                const metricsA = this.latestMetrics[a.id] || {};
                const metricsB = this.latestMetrics[b.id] || {};
                va = metricsA[field];
                vb = metricsB[field];
            } else {
                va = a[field];
                vb = b[field];
            }
            const vaNull = va == null;
            const vbNull = vb == null;
            if (vaNull) va = direction === 'asc' ? Infinity : -Infinity;
            if (vbNull) vb = direction === 'asc' ? Infinity : -Infinity;
            if (typeof va === 'string') va = va.toLowerCase();
            if (typeof vb === 'string') vb = vb.toLowerCase();
            if (vaNull && vbNull) return 0;
            if (vaNull) return 1;
            if (vbNull) return -1;
            if (va < vb) return direction === 'asc' ? -1 : 1;
            if (va > vb) return direction === 'asc' ? 1 : -1;
            return 0;
        });
    },

    _updateSortIcons() {
        document.querySelectorAll('.sort-icon').forEach(icon => {
            const field = icon.dataset.field;
            if (field === this._sort.field) {
                icon.textContent = this._sort.direction === 'asc' ? '▲' : '▼';
            } else {
                icon.textContent = '';
            }
        });
    },

    _renderTags(tags = []) {
        if (!tags.length) {
            return '<span style="color:var(--text-tertiary);">-</span>';
        }

        return `
            <div style="display:flex;flex-wrap:wrap;gap:6px;">
                ${tags.map(tag => `
                    <span style="display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;background:var(--bg-tertiary);color:var(--text-secondary);font-size:12px;line-height:1.5;">
                        ${tag}
                    </span>
                `).join('')}
            </div>
        `;
    },

    _renderMetricsCell(conn) {
        const metrics = this.latestMetrics[conn.id] || {};
        const cpu = metrics.cpu_usage;
        const qps = metrics.qps;
        const connections = metrics.connections_active;
        const cpuColor = this._getMetricColor(cpu);

        return `
            <td class="${cpuColor}">${cpu != null ? cpu.toFixed(1) + '%' : '-'}</td>
            <td>${qps != null ? qps.toFixed(1) : '-'}</td>
            <td>${connections != null ? connections : '-'}</td>
        `;
    },

    _renderActionMenuItem({ label, icon, onClick, danger = false, dividerBefore = false }) {
        return `
            ${dividerBefore ? '<div class="datasource-more-menu-divider"></div>' : ''}
            <button
                type="button"
                class="ds-more-menu-item datasource-more-menu-item${danger ? ' danger' : ''}"
                onclick="${onClick}"
            >
                <i data-lucide="${icon}" class="datasource-more-menu-icon"></i>
                <span>${this._escapeHtml(label)}</span>
            </button>
        `;
    },

    _renderTable() {
        const container = DOM.$('#datasource-table-container');
        if (!container) return;

        container.innerHTML = `
            <div class="data-table-container datasource-table-shell">
                <table class="data-table datasource-table">
                    <colgroup>
                        <col class="datasource-col-id">
                        <col class="datasource-col-name">
                        <col class="datasource-col-type">
                        <col class="datasource-col-tags">
                        <col class="datasource-col-host">
                        <col class="datasource-col-database">
                        <col class="datasource-col-status">
                        <col class="datasource-col-cpu">
                        <col class="datasource-col-qps">
                        <col class="datasource-col-connections">
                        <col class="datasource-col-actions">
                    </colgroup>
                    <thead>
                        <tr>
                            <th class="sortable" data-sort="id">编号 <span class="sort-icon" data-field="id"></span></th>
                            <th class="sortable" data-sort="name">名称 <span class="sort-icon" data-field="name"></span></th>
                            <th class="sortable" data-sort="db_type">类型 <span class="sort-icon" data-field="db_type"></span></th>
                            <th>标签</th>
                            <th class="sortable" data-sort="host">主机 <span class="sort-icon" data-field="host"></span></th>
                            <th class="sortable" data-sort="database">数据库 <span class="sort-icon" data-field="database"></span></th>
                            <th class="sortable" data-sort="connection_status">连接状态 <span class="sort-icon" data-field="connection_status"></span></th>
                            <th class="sortable" data-sort="cpu_usage">CPU <span class="sort-icon" data-field="cpu_usage"></span></th>
                            <th class="sortable" data-sort="qps">QPS <span class="sort-icon" data-field="qps"></span></th>
                            <th class="sortable" data-sort="connections_active">活跃连接 <span class="sort-icon" data-field="connections_active"></span></th>
                            <th class="datasource-actions-header">操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${this.filteredDatasources.map(conn => {
                            const silenceState = this._getSilenceState(conn);
                            const hostDisplay = `${conn.host}:${conn.port}`;
                            const silenceMenuItems = silenceState.isSilenced
                                ? [
                                    this._renderActionMenuItem({
                                        label: '调整告警静默',
                                        icon: 'bell-ring',
                                        onClick: `DatasourcesPage._showSilenceModal(${conn.id})`
                                    }),
                                    this._renderActionMenuItem({
                                        label: '取消告警静默',
                                        icon: 'bell-off',
                                        onClick: `DatasourcesPage._cancelDatasourceSilence(${conn.id})`,
                                        danger: true
                                    })
                                ].join('')
                                : this._renderActionMenuItem({
                                    label: '设置告警静默',
                                    icon: 'bell-off',
                                    onClick: `DatasourcesPage._showSilenceModal(${conn.id})`
                                });

                            return `
                                <tr>
                                    <td class="instance-mono">${conn.id}</td>
                                    <td>
                                        <strong>${this._escapeHtml(conn.name)}</strong>
                                        ${this._renderSilenceBadge(conn)}
                                    </td>
                                    <td><span class="badge badge-info">${this._escapeHtml(this._getDbTypeLabel(conn.db_type))}</span></td>
                                    <td>${this._renderTags(conn.tags || [])}</td>
                                    <td class="datasource-host-cell" title="${this._escapeAttr(hostDisplay)}">${this._escapeHtml(hostDisplay)}</td>
                                    <td title="${this._escapeAttr(conn.database || '-')}">${this._escapeHtml(conn.database || '-')}</td>
                                    <td>${this._getStatusBadge(conn)}</td>
                                    ${this._renderMetricsCell(conn)}
                                    <td class="datasource-actions-cell">
                                        <div class="ds-action-more datasource-action-menu">
                                            <button
                                                type="button"
                                                class="btn btn-sm btn-secondary datasource-action-trigger"
                                                onclick="DatasourcesPage._toggleMoreMenu(event, ${conn.id})"
                                                title="操作菜单"
                                                aria-label="操作菜单"
                                            >
                                                <i data-lucide="more-horizontal"></i>
                                            </button>
                                            <div class="ds-more-menu datasource-more-menu" id="more-menu-${conn.id}" style="display:none;">
                                                ${this._renderActionMenuItem({
                                                    label: '实例详情',
                                                    icon: 'panel-left',
                                                    onClick: `DatasourcesPage._openInstanceDetail(${conn.id})`
                                                })}
                                                ${this._renderActionMenuItem({
                                                    label: '编辑数据源',
                                                    icon: 'pencil',
                                                    onClick: `DatasourcesPage._editDatasource(${conn.id})`
                                                })}
                                                ${this._renderActionMenuItem({
                                                    label: '立即诊断',
                                                    icon: 'zap',
                                                    onClick: `DatasourcesPage._triggerInspection(${conn.id}, event)`
                                                })}
                                                ${this._renderActionMenuItem({
                                                    label: '测试连接',
                                                    icon: 'plug',
                                                    onClick: `DatasourcesPage._testDatasource(${conn.id})`
                                                })}
                                                ${this._renderActionMenuItem({
                                                    label: '巡检与告警配置',
                                                    icon: 'settings',
                                                    onClick: `DatasourcesPage._showInspectionConfig(${conn.id})`
                                                })}
                                                ${silenceMenuItems}
                                                ${this._renderActionMenuItem({
                                                    label: '删除数据源',
                                                    icon: 'trash-2',
                                                    onClick: `DatasourcesPage._deleteDatasource(${conn.id})`,
                                                    danger: true,
                                                    dividerBefore: true
                                                })}
                                            </div>
                                        </div>
                                    </td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        `;
        this._updateSortIcons();
        container.querySelectorAll('th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const field = th.dataset.sort;
                this._toggleSort(field);
                this._renderTable();
            });
        });
        DOM.createIcons();
    },

    _toggleMoreMenu(event, id) {
        event.stopPropagation();
        const menu = document.getElementById(`more-menu-${id}`);
        if (!menu) return;
        const isOpen = menu.style.display !== 'none';
        // close all open menus first
        document.querySelectorAll('.ds-more-menu').forEach(m => m.style.display = 'none');
        if (!isOpen) {
            // use fixed positioning to escape table overflow clipping
            const btn = event.currentTarget;
            const rect = btn.getBoundingClientRect();
            menu.style.position = 'fixed';
            menu.style.top = '0px';
            menu.style.left = '';
            menu.style.right = '';
            menu.style.display = 'block';
            const menuWidth = menu.offsetWidth || 180;
            const menuHeight = menu.offsetHeight || 260;
            const viewportPadding = 8;
            const preferredLeft = rect.right - menuWidth;
            const preferredTop = rect.bottom + 4;
            const fitsBelow = preferredTop + menuHeight <= window.innerHeight - viewportPadding;
            const resolvedTop = fitsBelow
                ? preferredTop
                : Math.max(viewportPadding, rect.top - menuHeight - 4);
            const resolvedLeft = Math.min(
                window.innerWidth - menuWidth - viewportPadding,
                Math.max(viewportPadding, preferredLeft)
            );
            menu.style.top = `${resolvedTop}px`;
            menu.style.left = `${resolvedLeft}px`;
            DOM.createIcons();
            // close on next outside click
            const handler = () => {
                menu.style.display = 'none';
                document.removeEventListener('click', handler, true);
            };
            document.addEventListener('click', handler, true);
        }
    },

    async _testDatasource(id) {
        try {
            const datasource = this.allDatasources.find(d => d.id === id);
            const result = await API.testDatasource(id);
            if (result.success) {
                const versionDisplay = result.version && datasource
                    ? this._simplifyVersion(result.version, datasource.db_type).short
                    : result.version || '';
                Toast.success(`连接成功! ${versionDisplay}`);
            } else {
                Toast.error(`连接失败: ${result.message}`);
            }
            // 重新加载数据源列表以更新连接状态
            await this._reloadWithFilters();
        } catch (err) {
            Toast.error('测试失败: ' + err.message);
        }
    },

    _editDatasource(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (conn) DatasourceForm.show(conn, () => this.render());
    },

    _openInstanceDetail(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (!conn) return;
        Store.set('currentInstance', conn);
        Store.set('currentInstanceId', conn.id);
        Store.set('currentConnection', conn);
        Store.set('currentDatasource', conn);
        Router.navigate(`instance-detail?datasource=${conn.id}&tab=monitor`);
    },

    _showSilenceModal(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (!conn) return;

        const state = this._getSilenceState(conn);
        const defaultHours = state.isSilenced ? this._formatHourValue(state.remainingHours) : '1';
        const currentStatusHtml = state.isSilenced ? `
            <div style="margin-bottom:12px;padding:10px 12px;border-radius:8px;background:rgba(217,119,6,0.12);color:var(--text-primary);">
                <div style="font-weight:600;margin-bottom:4px;">当前处于告警静默中</div>
                <div style="font-size:12px;color:var(--text-secondary);">截止时间：${this._escapeHtml(Format.datetime(conn.silence_until))}</div>
                <div style="font-size:12px;color:var(--text-secondary);">剩余时长：${this._escapeHtml(this._formatHourValue(state.remainingHours))} 小时</div>
                ${state.reason ? `<div style="font-size:12px;color:var(--text-secondary);">静默原因：${this._escapeHtml(state.reason)}</div>` : ''}
            </div>
        ` : '';

        Modal.show({
            title: '设置告警静默',
            content: `
                <div style="padding:6px 0;">
                    <div style="margin-bottom:12px;color:var(--text-secondary);line-height:1.6;">
                        为数据源 <strong>${this._escapeHtml(conn.name)}</strong> 设置告警静默。静默期间将暂停该数据源的告警触发与通知。
                    </div>
                    ${currentStatusHtml}
                    <div class="form-group">
                        <label for="datasource-silence-hours">静默时长（小时）</label>
                        <input id="datasource-silence-hours" type="number" class="form-input" min="0.5" max="240" step="0.5" value="${this._escapeAttr(defaultHours)}" placeholder="1">
                        <small class="text-muted">默认 1 小时，可设置范围 0.5 ~ 240 小时</small>
                    </div>
                    <div class="form-group" style="margin-top:12px;">
                        <label for="datasource-silence-reason">静默原因（可选）</label>
                        <textarea id="datasource-silence-reason" class="form-input" rows="3" maxlength="500" placeholder="例如：计划变更窗口、已知故障处理中">${this._escapeHtml(state.reason || '')}</textarea>
                    </div>
                </div>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: state.isSilenced ? '更新静默' : '开始静默',
                    variant: 'primary',
                    onClick: () => this._setDatasourceSilence(id)
                }
            ]
        });
    },

    async _setDatasourceSilence(id) {
        const hoursValue = DOM.$('#datasource-silence-hours')?.value;
        const reasonValue = DOM.$('#datasource-silence-reason')?.value?.trim() || '';
        const hours = parseFloat(hoursValue);

        if (!Number.isFinite(hours)) {
            Toast.error('请输入有效的静默时长');
            return;
        }
        if (hours < 0.5 || hours > 240) {
            Toast.error('静默时长必须在 0.5 到 240 小时之间');
            return;
        }

        try {
            const result = await API.setDatasourceSilence(id, {
                hours,
                reason: reasonValue || null,
            });
            Modal.hide();
            Toast.success(`已设置告警静默 ${this._formatHourValue(result.remaining_hours ?? hours)} 小时`);
            await this.render();
        } catch (err) {
            Toast.error('设置告警静默失败: ' + err.message);
        }
    },

    async _cancelDatasourceSilence(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (!conn) return;

        Modal.show({
            title: '取消告警静默',
            content: `确认取消数据源 <strong>${this._escapeHtml(conn.name)}</strong> 的告警静默吗？取消后将立即恢复该数据源的告警触发与通知。`,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: '确认取消',
                    variant: 'danger',
                    onClick: async () => {
                        try {
                            await API.cancelDatasourceSilence(id);
                            Modal.hide();
                            Toast.success('已取消告警静默');
                            await this.render();
                        } catch (err) {
                            Toast.error('取消告警静默失败: ' + err.message);
                        }
                    }
                }
            ]
        });
    },

    async _deleteDatasource(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (!conn || !confirm(`删除数据源 "${conn.name}"? 此操作无法撤销`)) return;
        try {
            await API.deleteDatasource(id);
            Toast.success('数据源已删除');
            this.render();
        } catch (err) {
            Toast.error('删除失败: ' + err.message);
        }
    },

    async _triggerInspection(datasourceId, triggerEvent = null) {
        if (!confirm('触发手动巡检? 这将生成一份全面的诊断报告')) {
            return;
        }
        const trigger = triggerEvent?.target?.closest('button');
        if (trigger) {
            trigger.innerHTML = '<div class="spinner"></div>';
            trigger.disabled = true;
        }
        try {
            await API.post(`/api/inspections/trigger/${datasourceId}`);
            Toast.success('巡检已成功触发!');
        } catch (err) {
            Toast.error('触发巡检失败: ' + err.message);
        } finally {
            if (trigger) {
                trigger.innerHTML = '<i data-lucide="more-horizontal"></i>';
                trigger.disabled = false;
                DOM.createIcons();
            }
        }
    },

    async _showInspectionConfig(datasourceId, draft = null) {
        try {
            const [config, templates, baselineSummary] = await Promise.all([
                API.get(`/api/inspections/config/${datasourceId}`),
                API.getAlertTemplates(),
                API.get(`/api/inspections/baseline/${datasourceId}`),
            ]);
            this._inspectionConfigSnapshot = config;
            this._inspectionTemplates = Array.isArray(templates) ? templates : [];
            this._inspectionBaselineSummary = baselineSummary || null;
            const effectiveConfig = {
                ...config,
                ...(draft && typeof draft === 'object' ? draft : {}),
            };
            const selectedTemplateId = effectiveConfig?.alert_template_id || this._inspectionTemplates.find((item) => item.is_default)?.id || '';

            Modal.show({
                title: '巡检与告警配置',
                content: `
                    <div style="padding:10px;">
                        <label style="display:block;margin-bottom:15px;">
                            <input type="checkbox" id="enableAuto" ${effectiveConfig?.enabled ? 'checked' : ''}>
                            启用自动巡检
                        </label>
                        <label style="display:block;margin-bottom:10px;">
                            巡检频率:
                            <select id="scheduleInterval" style="width:100%;padding:8px;margin-top:5px;">
                                ${this._buildScheduleIntervalOptions(effectiveConfig?.schedule_interval || 86400)}
                            </select>
                        </label>
                        <p style="font-size:12px;color:#666;margin-top:5px;">
                            推荐先使用模板默认策略，实例侧只保留少量运行开关，降低配置门槛。
                        </p>
                        <label style="display:block;margin-bottom:15px;margin-top:15px;">
                            <input type="checkbox" id="useAI" ${effectiveConfig?.use_ai_analysis !== false ? 'checked' : ''}>
                            使用 AI 分析
                        </label>

                        <div style="border-top:1px solid #ddd;margin-top:20px;padding-top:20px;">
                            <h4 style="margin-bottom:15px;font-size:14px;font-weight:600;">告警模板</h4>
                            <label style="display:block;margin-bottom:10px;">
                                <select id="alertTemplateId" style="width:100%;padding:8px;margin-top:5px;">
                                    <option value="">请选择告警模板</option>
                                    ${this._inspectionTemplates.filter((item) => item.enabled || item.id === selectedTemplateId).map((item) => `
                                        <option value="${item.id}" ${String(selectedTemplateId) === String(item.id) ? 'selected' : ''}>
                                            ${this._escapeHtml(item.name)}${item.is_default ? '（默认）' : ''}
                                        </option>
                                    `).join('')}
                                </select>
                            </label>
                            <div id="alertTemplatePreview" style="font-size:12px;color:#666;border:1px solid #eee;border-radius:8px;padding:12px;min-height:96px;">
                                ${this._renderAlertTemplatePreview(selectedTemplateId, baselineSummary)}
                            </div>
                            <div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;">
                                <button id="openAlertTemplatesBtn" class="btn btn-secondary" type="button">管理告警模板</button>
                                <button id="viewBaselineDetailBtn" class="btn btn-secondary" type="button">查看基线详情</button>
                                <button id="rebuildBaselineBtn" class="btn btn-secondary" type="button">重建当前实例基线</button>
                            </div>
                            <p style="font-size:12px;color:#666;margin-top:8px;">
                                阈值、基线和事件级 AI 诊断都统一维护在模板里，实例配置只负责“选哪套策略”。
                            </p>
                        </div>

                        <div style="border-top:1px solid #ddd;margin-top:20px;padding-top:20px;">
                            <h4 style="margin-bottom:15px;font-size:14px;font-weight:600;">当前运行状态</h4>
                            <div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;font-size:12px;color:#666;">
                                <div>当前模板：${this._escapeHtml(config?.alert_template_name || '未绑定模板')}</div>
                                <div>下次计划时间：${this._escapeHtml(config?.next_scheduled_at ? Format.datetime(config.next_scheduled_at) : '-')}</div>
                                <div>上次执行时间：${this._escapeHtml(config?.last_scheduled_at ? Format.datetime(config.last_scheduled_at) : '-')}</div>
                                <div>基线画像：${baselineSummary?.profile_count || 0} 个时间槽</div>
                            </div>
                        </div>
                    </div>
                `,
                buttons: [
                    { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                    { text: '保存', variant: 'primary', onClick: () => this._saveInspectionConfig(datasourceId) }
                ]
            });

            this._setupInspectionConfigListeners(datasourceId);
        } catch (error) {
            Toast.error('加载巡检与告警配置失败: ' + error.message);
        }
    },

    _buildScheduleIntervalOptions(currentValue) {
        const presets = [
            { value: 3600, label: '每小时' },
            { value: 21600, label: '每 6 小时' },
            { value: 86400, label: '每天' },
            { value: 604800, label: '每周' },
            { value: 2592000, label: '每月' },
        ];
        const numericCurrent = parseInt(currentValue, 10) || 86400;
        const hasCurrent = presets.some((item) => item.value === numericCurrent);
        const items = hasCurrent ? presets : presets.concat([{ value: numericCurrent, label: `自定义（${numericCurrent} 秒）` }]);
        return items.map((item) => `<option value="${item.value}" ${item.value === numericCurrent ? 'selected' : ''}>${item.label}</option>`).join('');
    },

    _normalizeAlertTemplateConfig(config) {
        const payload = config && typeof config === 'object' ? config : {};
        const thresholdRules = payload.threshold_rules && typeof payload.threshold_rules === 'object' ? payload.threshold_rules : {};
        return {
            alert_engine_mode: payload.alert_engine_mode === 'ai' ? 'ai' : 'threshold',
            threshold_rules: thresholdRules,
            baseline_config: payload.baseline_config || {},
            event_ai_config: payload.event_ai_config || {},
            ai_policy_text: payload.ai_policy_text || null,
        };
    },

    _renderAlertTemplatePreview(templateId, baselineSummary = null) {
        const template = (this._inspectionTemplates || []).find((item) => String(item.id) === String(templateId));
        if (!template) {
            return '选择模板后，这里会展示该模板的阈值、基线和事件诊断摘要。';
        }

        const config = this._normalizeAlertTemplateConfig(template.template_config);
        const customExpression = config.threshold_rules?.custom_expression;
        const thresholdSummary = customExpression?.expression
            ? `自定义表达式：${customExpression.expression}`
            : [
                ['cpu_usage', 'CPU'],
                ['disk_usage', '磁盘'],
                ['connections_active', '连接'],
            ].map(([key, label]) => {
                const rule = config.threshold_rules?.[key];
                return rule?.threshold != null ? `${label}>${rule.threshold}（${rule.duration || '-'}秒）` : null;
            }).filter(Boolean).join(' / ');
        const baselineText = config.baseline_config?.enabled
            ? `已启用${baselineSummary ? `，当前实例已有 ${baselineSummary.profile_count || 0} 个时间槽画像` : ''}`
            : '未启用';
        const eventAIText = config.event_ai_config?.enabled !== false ? '开启' : '关闭';
        return `
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-bottom:8px;">
                <strong>${this._escapeHtml(template.name)}</strong>
                ${template.is_default ? '<span class="badge badge-info">默认模板</span>' : ''}
                <span class="badge ${template.enabled ? 'badge-success' : 'badge-secondary'}">${template.enabled ? '启用中' : '已停用'}</span>
            </div>
            <div style="line-height:1.7;">
                <div>判警方式：${this._escapeHtml(config.alert_engine_mode === 'ai' ? 'AI 判警' : '阈值判警')}</div>
                <div>基础阈值：${this._escapeHtml(thresholdSummary || '未配置')}</div>
                <div>实例基线：${this._escapeHtml(baselineText)}</div>
                <div>事件级 AI 诊断：${this._escapeHtml(eventAIText)}</div>
                ${config.alert_engine_mode === 'ai' && config.ai_policy_text ? `<div>AI 规则：${this._escapeHtml(config.ai_policy_text)}</div>` : ''}
                ${template.summary ? `<div>摘要：${this._escapeHtml(template.summary)}</div>` : ''}
            </div>
        `;
    },

    _syncInspectionTemplatePreview(selectedTemplateId = null) {
        const templateId = selectedTemplateId ?? DOM.$('#alertTemplateId')?.value;
        const preview = DOM.$('#alertTemplatePreview');
        if (preview) {
            preview.innerHTML = this._renderAlertTemplatePreview(templateId, this._inspectionBaselineSummary);
        }
        const template = (this._inspectionTemplates || []).find((item) => String(item.id) === String(templateId));
        const config = this._normalizeAlertTemplateConfig(template?.template_config);
        const rebuildBtn = DOM.$('#rebuildBaselineBtn');
        const detailBtn = DOM.$('#viewBaselineDetailBtn');
        if (rebuildBtn) {
            rebuildBtn.style.display = config.baseline_config?.enabled ? 'inline-flex' : 'none';
        }
        if (detailBtn) {
            detailBtn.style.display = config.baseline_config?.enabled ? 'inline-flex' : 'none';
        }
    },

    _setupInspectionConfigListeners(datasourceId) {
        DOM.$('#alertTemplateId')?.addEventListener('change', (event) => {
            this._syncInspectionTemplatePreview(event.target.value);
        });

        DOM.$('#openAlertTemplatesBtn')?.addEventListener('click', () => {
            Modal.hide();
            Router.navigate('alerts?tab=templates');
        });

        DOM.$('#viewBaselineDetailBtn')?.addEventListener('click', async () => {
            await this._showBaselineDetail(datasourceId, this._captureInspectionConfigDraft());
        });

        DOM.$('#rebuildBaselineBtn')?.addEventListener('click', async () => {
            const btn = DOM.$('#rebuildBaselineBtn');
            btn.disabled = true;
            btn.textContent = '重建中...';
            try {
                const result = await API.post(`/api/inspections/baseline/${datasourceId}/rebuild`);
                this._inspectionBaselineSummary = result;
                this._syncInspectionTemplatePreview();
                Toast.success('历史基线重建完成');
            } catch (err) {
                Toast.error('重建基线失败: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.textContent = '重建当前实例基线';
            }
        });

        this._syncInspectionTemplatePreview();
    },

    _captureInspectionConfigDraft() {
        return {
            enabled: Boolean(DOM.$('#enableAuto')?.checked),
            schedule_interval: parseInt(DOM.$('#scheduleInterval')?.value, 10) || 86400,
            use_ai_analysis: Boolean(DOM.$('#useAI')?.checked),
            alert_template_id: DOM.$('#alertTemplateId')?.value ? parseInt(DOM.$('#alertTemplateId')?.value, 10) : null,
        };
    },

    async _showBaselineDetail(datasourceId, draft = null) {
        try {
            const summary = await API.get(`/api/inspections/baseline/${datasourceId}?limit=500`);
            const content = this._renderBaselineDetailContent(summary || {});
            Modal.show({
                title: '实例基线详情',
                content,
                size: 'xlarge',
                width: '1080px',
                bodyClassName: 'baseline-detail-modal-body',
                onHide: () => this._showInspectionConfig(datasourceId, draft),
                buttons: [
                    { text: '关闭', variant: 'secondary', onClick: () => Modal.hide() },
                ],
            });
        } catch (error) {
            Toast.error('加载基线详情失败: ' + error.message);
        }
    },

    _renderBaselineDetailContent(summary) {
        const wrapper = DOM.el('div', { className: 'baseline-detail-modal' });
        const enabled = Boolean(summary?.enabled);
        const profiles = Array.isArray(summary?.profiles) ? summary.profiles : [];
        const groupedProfiles = this._groupBaselineProfiles(profiles);

        const summaryCard = DOM.el('div', { className: 'baseline-detail-summary' });
        summaryCard.innerHTML = `
            <div class="baseline-detail-summary-item">
                <div class="baseline-detail-summary-label">基线状态</div>
                <div class="baseline-detail-summary-value">${enabled ? '已启用' : '未启用'}</div>
            </div>
            <div class="baseline-detail-summary-item">
                <div class="baseline-detail-summary-label">画像数量</div>
                <div class="baseline-detail-summary-value">${summary?.profile_count || 0}</div>
            </div>
            <div class="baseline-detail-summary-item">
                <div class="baseline-detail-summary-label">学习天数</div>
                <div class="baseline-detail-summary-value">${summary?.diagnostics?.learning_days || '-'}</div>
            </div>
            <div class="baseline-detail-summary-item">
                <div class="baseline-detail-summary-label">最少样本数</div>
                <div class="baseline-detail-summary-value">${summary?.diagnostics?.min_samples || '-'}</div>
            </div>
            <div class="baseline-detail-summary-item">
                <div class="baseline-detail-summary-label">默认指标</div>
                <div class="baseline-detail-summary-value baseline-detail-summary-metrics">${Array.isArray(summary?.diagnostics?.default_metrics) && summary.diagnostics.default_metrics.length
                    ? summary.diagnostics.default_metrics.map((metric) => this._escapeHtml(this._getBaselineMetricLabel(metric))).join(' / ')
                    : '-'}</div>
            </div>
            <div class="baseline-detail-summary-item baseline-detail-summary-item-wide">
                <div class="baseline-detail-summary-label">最近更新时间</div>
                <div class="baseline-detail-summary-value">${summary?.last_profile_updated_at ? this._escapeHtml(Format.datetime(summary.last_profile_updated_at)) : '-'}</div>
            </div>
        `;
        wrapper.appendChild(summaryCard);

        if (!enabled) {
            wrapper.appendChild(DOM.el('div', {
                className: 'empty-state',
                innerHTML: '<h3>当前模板未启用实例基线</h3><p>请选择启用基线的告警模板后，再查看画像明细。</p>',
            }));
            return wrapper;
        }

        if (!profiles.length) {
            wrapper.appendChild(DOM.el('div', {
                className: 'empty-state',
                innerHTML: '<h3>暂无基线画像</h3><p>可以先等待系统自然积累样本，或回到上一层点击“重建当前实例基线”。</p>',
            }));
            return wrapper;
        }

        const metricsBoard = DOM.el('div', { className: 'baseline-detail-metrics-board' });
        const metricConfigs = summary?.baseline_config?.metrics || {};
        this._getOrderedBaselineMetricGroups(groupedProfiles).forEach(([metricName, items]) => {
            metricsBoard.appendChild(this._renderBaselineMetricCard(metricName, items, metricConfigs[metricName] || {}));
        });
        wrapper.appendChild(metricsBoard);

        return wrapper;
    },

    _getOrderedBaselineMetricGroups(groupedProfiles) {
        const preferredOrder = ['cpu_usage', 'disk_usage', 'connections_active', 'qps', 'tps'];
        const keys = Object.keys(groupedProfiles || {});
        return keys
            .sort((left, right) => {
                const leftIndex = preferredOrder.indexOf(left);
                const rightIndex = preferredOrder.indexOf(right);
                if (leftIndex === -1 && rightIndex === -1) return left.localeCompare(right);
                if (leftIndex === -1) return 1;
                if (rightIndex === -1) return -1;
                return leftIndex - rightIndex;
            })
            .map((key) => [key, groupedProfiles[key]]);
    },

    _renderBaselineMetricCard(metricName, items, metricConfig = {}) {
        const card = DOM.el('div', {
            className: `baseline-metric-card baseline-metric-card-${this._escapeHtml(metricName)}`,
        });
        const slotMap = this._buildBaselineSlotMap(items);
        const latestItem = [...items].sort((left, right) => {
            const leftTime = left?.updated_at ? new Date(left.updated_at).getTime() : 0;
            const rightTime = right?.updated_at ? new Date(right.updated_at).getTime() : 0;
            return rightTime - leftTime;
        })[0];

        const hoursHeader = [0, 6, 12, 18, 23].map((hour) => `
            <span style="grid-column:${hour + 1};">${String(hour).padStart(2, '0')}</span>
        `).join('');

        const rows = Array.from({ length: 7 }, (_, weekday) => {
            const cells = Array.from({ length: 24 }, (_, hour) => {
                const item = slotMap[`${weekday}-${hour}`];
                if (!item) {
                    return '<span class="baseline-heatmap-cell is-empty"></span>';
                }
                const levelClass = this._getBaselineCellLevel(metricName, item, metricConfig);
                const sampleCount = item.sample_count ?? '-';
                const label = `${this._getWeekdayLabel(weekday)} ${String(hour).padStart(2, '0')}:00 | 均值 ${this._formatBaselineNumber(item.avg_value)}${this._getBaselineMetricUnit(metricName)} | P95 ${this._formatBaselineNumber(item.p95_value)}${this._getBaselineMetricUnit(metricName)} | 样本 ${sampleCount}`;
                return `<span class="baseline-heatmap-cell ${levelClass}" title="${this._escapeAttr(label)}"></span>`;
            }).join('');
            return `
                <div class="baseline-heatmap-row">
                    <div class="baseline-heatmap-row-label">${this._escapeHtml(this._getWeekdayLabel(weekday).replace('周', ''))}</div>
                    <div class="baseline-heatmap-row-cells">${cells}</div>
                </div>
            `;
        }).join('');

        const avgRange = this._buildBaselineRangeText(items, 'avg_value', metricName);
        const p95Range = this._buildBaselineRangeText(items, 'p95_value', metricName);

        card.innerHTML = `
            <div class="baseline-metric-card-header">
                <div>
                    <div class="baseline-metric-card-title">${this._escapeHtml(this._getBaselineMetricLabel(metricName))}</div>
                    <div class="baseline-metric-card-subtitle">
                        ${items.length} 个时间槽
                        ${latestItem?.updated_at ? ` · 更新于 ${this._escapeHtml(Format.datetime(latestItem.updated_at))}` : ''}
                    </div>
                </div>
                <div class="baseline-metric-card-stats">
                    <span>均值区间 ${this._escapeHtml(avgRange)}</span>
                    <span>P95 区间 ${this._escapeHtml(p95Range)}</span>
                </div>
            </div>
            <div class="baseline-heatmap">
                <div class="baseline-heatmap-hours">
                    ${hoursHeader}
                </div>
                <div class="baseline-heatmap-body">
                    ${rows}
                </div>
            </div>
            <div class="baseline-metric-card-legend">
                <span class="baseline-legend-dot baseline-legend-dot-low"></span> 低负载
                <span class="baseline-legend-dot baseline-legend-dot-medium"></span> 中等负载
                <span class="baseline-legend-dot baseline-legend-dot-high"></span> 高负载
            </div>
        `;
        return card;
    },

    _groupBaselineProfiles(profiles) {
        const groups = {};
        (profiles || []).forEach((item) => {
            const metricName = item.metric_name || 'unknown';
            if (!groups[metricName]) {
                groups[metricName] = [];
            }
            groups[metricName].push(item);
        });
        Object.values(groups).forEach((items) => {
            items.sort((a, b) => {
                const weekdayDiff = Number(a.weekday || 0) - Number(b.weekday || 0);
                if (weekdayDiff !== 0) return weekdayDiff;
                return Number(a.hour || 0) - Number(b.hour || 0);
            });
        });
        return groups;
    },

    _buildBaselineSlotMap(items) {
        return (items || []).reduce((acc, item) => {
            acc[`${Number(item.weekday || 0)}-${Number(item.hour || 0)}`] = item;
            return acc;
        }, {});
    },

    _getBaselineCellLevel(metricName, item, metricConfig = {}) {
        const representativeValue = Number(item?.p95_value ?? item?.avg_value ?? item?.max_value ?? 0);
        if (!Number.isFinite(representativeValue)) {
            return 'baseline-level-low';
        }

        if (metricName === 'cpu_usage' || metricName === 'disk_usage') {
            if (representativeValue < 20) return 'baseline-level-low';
            if (representativeValue <= 80) return 'baseline-level-medium';
            return 'baseline-level-high';
        }

        if (metricName === 'connections_active') {
            if (representativeValue < 5) return 'baseline-level-low';
            if (representativeValue <= 20) return 'baseline-level-medium';
            return 'baseline-level-high';
        }

        const minimum = Number(metricConfig?.minimum);
        if (Number.isFinite(minimum) && minimum > 0) {
            if (representativeValue < minimum) return 'baseline-level-low';
            if (representativeValue <= minimum * 2) return 'baseline-level-medium';
            return 'baseline-level-high';
        }

        if (representativeValue < 20) return 'baseline-level-low';
        if (representativeValue <= 80) return 'baseline-level-medium';
        return 'baseline-level-high';
    },

    _buildBaselineRangeText(items, fieldName, metricName) {
        const values = (items || [])
            .map((item) => Number(item?.[fieldName]))
            .filter((value) => Number.isFinite(value));
        if (!values.length) {
            return '-';
        }
        const minValue = Math.min(...values);
        const maxValue = Math.max(...values);
        const unit = this._getBaselineMetricUnit(metricName);
        return `${this._formatBaselineNumber(minValue)}${unit} - ${this._formatBaselineNumber(maxValue)}${unit}`;
    },

    _getWeekdayLabel(weekday) {
        return ['周一', '周二', '周三', '周四', '周五', '周六', '周日'][Number(weekday) || 0] || `星期${weekday}`;
    },

    _getBaselineMetricLabel(metricName) {
        return {
            cpu_usage: 'CPU 使用率',
            disk_usage: '磁盘使用率',
            connections_active: '活跃连接数',
            qps: 'QPS',
            tps: 'TPS',
        }[metricName] || metricName || '-';
    },

    _getBaselineMetricUnit(metricName) {
        if (metricName === 'cpu_usage' || metricName === 'disk_usage') return '%';
        return '';
    },

    _formatBaselineNumber(value) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
        const numericValue = Number(value);
        if (Math.abs(numericValue) >= 100) return numericValue.toFixed(0);
        if (Math.abs(numericValue) >= 10) return numericValue.toFixed(1);
        return numericValue.toFixed(2);
    },

    async _saveInspectionConfig(datasourceId) {
        const baseConfig = this._inspectionConfigSnapshot || await API.get(`/api/inspections/config/${datasourceId}`);
        const enabled = DOM.$('#enableAuto')?.checked;
        const schedule_interval = parseInt(DOM.$('#scheduleInterval')?.value) || 86400;
        const use_ai_analysis = DOM.$('#useAI')?.checked;
        const alert_template_id = DOM.$('#alertTemplateId')?.value ? parseInt(DOM.$('#alertTemplateId')?.value, 10) : null;

        if (!alert_template_id) {
            Toast.error('请先选择告警模板');
            return;
        }

        try {
            await API.post(`/api/inspections/config/${datasourceId}`, {
                enabled,
                schedule_interval,
                use_ai_analysis,
                ai_model_id: baseConfig?.ai_model_id || null,
                kb_ids: Array.isArray(baseConfig?.kb_ids) ? baseConfig.kb_ids : [],
                alert_template_id,
                threshold_rules: baseConfig?.threshold_rules || {},
                alert_engine_mode: baseConfig?.alert_engine_mode || 'inherit',
                ai_policy_source: baseConfig?.ai_policy_source || 'inline',
                ai_policy_text: baseConfig?.ai_policy_text || null,
                ai_policy_id: baseConfig?.ai_policy_id || null,
                alert_ai_model_id: baseConfig?.alert_ai_model_id || null,
                ai_shadow_enabled: Boolean(baseConfig?.ai_shadow_enabled),
                baseline_config: baseConfig?.baseline_config || {},
                event_ai_config: baseConfig?.event_ai_config || {},
            });
            Modal.hide();
            Toast.success('巡检与告警配置已保存');
        } catch (error) {
            Toast.error('保存巡检与告警配置失败: ' + error.message);
        }
    },

    _simplifyVersion(fullVersion, dbType) {
        if (!fullVersion) return { short: '未知版本', full: '', details: '' };

        const patterns = {
            'postgresql': /PostgreSQL\s+([\d.]+)/i,
            'mysql': /([\d.]+)/,
            'oracle': /Oracle Database ([\d.]+)/i,
            'sqlserver': /Microsoft SQL Server\s+([\d.]+)/i,
            'opengauss': /openGauss\s+([\d.]+)/i,
            'hana': /HDB\s+([\d.]+)/i,
            'tdsql': /([\d.]+)/
        };

        const dbTypeNormalized = (dbType || '').toLowerCase().replace(/[_-]/g, '');
        const pattern = patterns[dbTypeNormalized];

        if (pattern) {
            const match = fullVersion.match(pattern);
            if (match) {
                const versionNum = match[1];
                const dbDisplayNames = {
                    'postgresql': 'PostgreSQL',
                    'mysql': 'MySQL',
                    'oracle': 'Oracle',
                    'sqlserver': 'SQL Server',
                    'opengauss': 'openGauss',
                    'hana': 'SAP HANA',
                    'tdsql': 'TDSQL-C'
                };
                const displayName = dbDisplayNames[dbTypeNormalized] || dbType.toUpperCase();
                const short = `${displayName} ${versionNum}`;
                const details = fullVersion.substring(match.index + match[0].length).trim().replace(/^[,\s]+/, '');

                return { short, full: fullVersion, details };
            }
        }

        if (fullVersion.length > 50) {
            return {
                short: fullVersion.substring(0, 50) + '...',
                full: fullVersion,
                details: fullVersion.substring(50)
            };
        }

        return { short: fullVersion, full: fullVersion, details: '' };
    }
};
