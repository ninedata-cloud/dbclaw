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
            mongodb: 'MongoDB',
            redis: 'Redis',
            sqlserver: 'SQL Server',
            oracle: 'Oracle',
            tidb: 'TiDB',
            'tdsql-c-mysql': 'TDSQL-C MySQL',
            oceanbase: 'OceanBase',
            oceanbase_mysql: 'OceanBase MySQL',
            opengauss: 'openGauss',
            dm: 'DM',
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
                <option value="dm">DM</option>
                <option value="tdsql-c-mysql">TDSQL-C MySQL</option>
                <option value="mongodb">MongoDB</option>
                <option value="redis">Redis</option>
            </select>
        `;

        const newBtn = DOM.el('button', { className: 'btn btn-primary' });
        newBtn.innerHTML = '<i data-lucide="plus"></i> New Datasource';
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

    _renderTable() {
        const container = DOM.$('#datasource-table-container');
        if (!container) return;

        container.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th class="sortable" data-sort="name">名称 <span class="sort-icon" data-field="name"></span></th>
                        <th class="sortable" data-sort="db_type">类型 <span class="sort-icon" data-field="db_type"></span></th>
                        <th>标签</th>
                        <th class="sortable" data-sort="host">主机 <span class="sort-icon" data-field="host"></span></th>
                        <th class="sortable" data-sort="database">数据库 <span class="sort-icon" data-field="database"></span></th>
                        <th class="sortable" data-sort="connection_status">连接状态 <span class="sort-icon" data-field="connection_status"></span></th>
                        <th class="sortable" data-sort="cpu_usage">CPU <span class="sort-icon" data-field="cpu_usage"></span></th>
                        <th class="sortable" data-sort="qps">QPS <span class="sort-icon" data-field="qps"></span></th>
                        <th class="sortable" data-sort="connections_active">活跃连接 <span class="sort-icon" data-field="connections_active"></span></th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${this.filteredDatasources.map(conn => {
                        const silenceState = this._getSilenceState(conn);
                        const silenceMenuItems = silenceState.isSilenced ? `
                            <div class="ds-more-menu-item" onclick="DatasourcesPage._showSilenceModal(${conn.id})" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:var(--text-primary);white-space:nowrap;">
                                <i data-lucide="bell-ring" style="width:14px;height:14px;"></i> 调整告警静默
                            </div>
                            <div class="ds-more-menu-item" onclick="DatasourcesPage._cancelDatasourceSilence(${conn.id})" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:#ef4444;white-space:nowrap;">
                                <i data-lucide="bell-off" style="width:14px;height:14px;"></i> 取消告警静默
                            </div>
                        ` : `
                            <div class="ds-more-menu-item" onclick="DatasourcesPage._showSilenceModal(${conn.id})" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:var(--text-primary);white-space:nowrap;">
                                <i data-lucide="bell-off" style="width:14px;height:14px;"></i> 设置告警静默
                            </div>
                        `;

                        return `
                            <tr>
                                <td>
                                    <strong>${conn.name}</strong>
                                    ${this._renderSilenceBadge(conn)}
                                </td>
                                <td><span class="badge badge-info">${this._escapeHtml(this._getDbTypeLabel(conn.db_type))}</span></td>
                                <td>${this._renderTags(conn.tags || [])}</td>
                                <td>${conn.host}:${conn.port}</td>
                                <td>${conn.database || '-'}</td>
                                <td>${this._getStatusBadge(conn)}</td>
                                ${this._renderMetricsCell(conn)}
                                <td>
                                    <div style="display:flex;gap:4px;align-items:center;">
                                        <button class="btn btn-sm btn-secondary" onclick="DatasourcesPage._editDatasource(${conn.id})" title="编辑">
                                            <i data-lucide="pencil"></i>
                                        </button>
                                        <button class="btn btn-sm btn-secondary" onclick="DatasourcesPage._triggerInspection(${conn.id})" title="诊断">
                                            <i data-lucide="zap"></i>
                                        </button>
                                        <div class="ds-action-more" style="position:relative;">
                                            <button class="btn btn-sm btn-secondary" onclick="DatasourcesPage._toggleMoreMenu(event, ${conn.id})" title="更多">
                                                <i data-lucide="more-horizontal"></i>
                                            </button>
                                            <div class="ds-more-menu" id="more-menu-${conn.id}" style="display:none;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:8px;box-shadow:0 4px 12px rgba(0,0,0,0.15);z-index:9999;min-width:140px;padding:4px 0;">
                                                <div class="ds-more-menu-item" onclick="DatasourcesPage._testDatasource(${conn.id})" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:var(--text-primary);white-space:nowrap;">
                                                    <i data-lucide="plug" style="width:14px;height:14px;"></i> 测试连接
                                                </div>
                                                <div class="ds-more-menu-item" onclick="DatasourcesPage._showInspectionConfig(${conn.id})" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:var(--text-primary);white-space:nowrap;">
                                                    <i data-lucide="settings" style="width:14px;height:14px;"></i> 巡检配置
                                                </div>
                                                <div class="ds-more-menu-item" onclick="DatasourcesPage._monitorDatasource(${conn.id})" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:var(--text-primary);white-space:nowrap;">
                                                    <i data-lucide="activity" style="width:14px;height:14px;"></i> 监控
                                                </div>
                                                ${silenceMenuItems}
                                                <div style="border-top:1px solid var(--border-color);margin:4px 0;"></div>
                                                <div class="ds-more-menu-item" onclick="DatasourcesPage._deleteDatasource(${conn.id})" style="display:flex;align-items:center;gap:8px;padding:8px 14px;cursor:pointer;font-size:13px;color:#ef4444;white-space:nowrap;">
                                                    <i data-lucide="trash-2" style="width:14px;height:14px;"></i> 删除
                                                </div>
                                            </div>
                                        </div>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }).join('')}
                </tbody>
            </table>
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
        const isOpen = menu.style.display !== 'none';
        // close all open menus first
        document.querySelectorAll('.ds-more-menu').forEach(m => m.style.display = 'none');
        if (!isOpen) {
            // use fixed positioning to escape table overflow clipping
            const btn = event.currentTarget;
            const rect = btn.getBoundingClientRect();
            menu.style.position = 'fixed';
            menu.style.top = (rect.bottom + 4) + 'px';
            menu.style.left = '';
            menu.style.right = '';
            menu.style.display = 'block';
            // align right edge of menu to right edge of button
            const menuWidth = 140;
            menu.style.left = Math.max(0, rect.right - menuWidth) + 'px';
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
            const result = await API.testDatasource(id);
            if (result.success) {
                Toast.success(`连接成功! ${result.version || ''}`);
            } else {
                Toast.error(`连接失败: ${result.message}`);
            }
        } catch (err) {
            Toast.error('测试失败: ' + err.message);
        }
    },

    _editDatasource(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (conn) DatasourceForm.show(conn, () => this.render());
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

    _monitorDatasource(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (conn) {
            Store.set('currentDatasource', conn);
            Router.navigate('monitor');
        }
    },

    async _triggerInspection(datasourceId) {
        if (!confirm('触发手动巡检? 这将生成一份全面的诊断报告')) {
            return;
        }
        const btn = event.target.closest('button');
        btn.innerHTML = '<div class="spinner"></div>';
        btn.disabled = true;
        try {
            await API.post(`/api/inspections/trigger/${datasourceId}`);
            Toast.success('巡检已成功触发!');
        } catch (err) {
            Toast.error('触发巡检失败: ' + err.message);
        } finally {
            btn.innerHTML = '<i data-lucide="zap"></i>';
            btn.disabled = false;
            DOM.createIcons();
        }
    },

    async _showInspectionConfig(datasourceId) {
        try {
            const config = await API.get(`/api/inspections/config/${datasourceId}`);
            const thresholdRules = config?.threshold_rules || {};

            // Check if custom expression is used
            const hasCustomExpression = !!thresholdRules.custom_expression;
            const customExpression = thresholdRules.custom_expression?.expression || '';
            const customDuration = thresholdRules.custom_expression?.duration || 60;

            // Preset threshold values
            const cpuEnabled = !hasCustomExpression && !!thresholdRules.cpu_usage;
            const cpuThreshold = thresholdRules.cpu_usage?.threshold || 50;
            const cpuDuration = thresholdRules.cpu_usage?.duration || 60;

            const diskEnabled = !hasCustomExpression && !!thresholdRules.disk_usage;
            const diskThreshold = thresholdRules.disk_usage?.threshold || 80;
            const diskDuration = thresholdRules.disk_usage?.duration || 60;

            const connectionsEnabled = !hasCustomExpression && !!thresholdRules.connections;
            const connectionsThreshold = thresholdRules.connections?.threshold || 20;
            const connectionsDuration = thresholdRules.connections?.duration || 60;

            Modal.show({
                title: '巡检配置',
                content: `
                    <div style="padding:10px;">
                        <label style="display:block;margin-bottom:15px;">
                            <input type="checkbox" id="enableAuto" ${config?.enabled ? 'checked' : ''}>
                            启用自动巡检
                        </label>
                        <label style="display:block;margin-bottom:10px;">
                            定时间隔（秒）:
                            <input type="number" id="scheduleInterval" value="${config?.schedule_interval || 86400}"
                                   style="width:100%;padding:8px;margin-top:5px;"
                                   placeholder="86400 (daily)">
                        </label>
                        <p style="font-size:12px;color:#666;margin-top:5px;">
                            示例: 86400（每天）, 21600（每 6 小时）, 3600（每小时）
                        </p>
                        <label style="display:block;margin-bottom:15px;margin-top:15px;">
                            <input type="checkbox" id="useAI" ${config?.use_ai_analysis !== false ? 'checked' : ''}>
                            使用 AI 分析
                        </label>

                        <div style="border-top:1px solid #ddd;margin-top:20px;padding-top:20px;">
                            <h4 style="margin-bottom:15px;font-size:14px;font-weight:600;">异常阈值配置</h4>

                            <div id="presetThresholds" style="margin-bottom:20px;">
                                <p style="font-size:13px;color:#666;margin-bottom:10px;">预设阈值:</p>

                                <label style="display:flex;align-items:center;margin-bottom:10px;">
                                    <input type="checkbox" id="cpuEnabled" ${cpuEnabled ? 'checked' : ''} style="margin-right:8px;">
                                    <span style="flex:1;">CPU 使用率 大于</span>
                                    <input type="number" id="cpuThreshold" value="${cpuThreshold}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="0" max="100">
                                    <span>% 持续</span>
                                    <input type="number" id="cpuDuration" value="${cpuDuration}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="1">
                                    <span>秒</span>
                                </label>

                                <label style="display:flex;align-items:center;margin-bottom:10px;">
                                    <input type="checkbox" id="diskEnabled" ${diskEnabled ? 'checked' : ''} style="margin-right:8px;">
                                    <span style="flex:1;">磁盘使用率 大于</span>
                                    <input type="number" id="diskThreshold" value="${diskThreshold}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="0" max="100">
                                    <span>% 持续</span>
                                    <input type="number" id="diskDuration" value="${diskDuration}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="1">
                                    <span>秒</span>
                                </label>

                                <label style="display:flex;align-items:center;margin-bottom:10px;">
                                    <input type="checkbox" id="connectionsEnabled" ${connectionsEnabled ? 'checked' : ''} style="margin-right:8px;">
                                    <span style="flex:1;">活跃连接数 大于</span>
                                    <input type="number" id="connectionsThreshold" value="${connectionsThreshold}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="0">
                                    <span>持续</span>
                                    <input type="number" id="connectionsDuration" value="${connectionsDuration}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="1">
                                    <span>秒</span>
                                </label>
                            </div>

                            <div style="text-align:center;margin:15px 0;color:#999;">OR</div>

                            <div id="customExpression">
                                <label style="display:block;margin-bottom:10px;">
                                    <input type="checkbox" id="useCustomExpression" ${hasCustomExpression ? 'checked' : ''}>
                                    使用自定义表达式
                                </label>

                                <div id="customExpressionFields" style="display:${hasCustomExpression ? 'block' : 'none'};">
                                    <label style="display:block;margin-bottom:5px;font-size:12px;">
                                        表达式:
                                    </label>
                                    <textarea id="customExpressionText"
                                              style="width:100%;padding:8px;font-family:monospace;font-size:12px;min-height:60px;margin-bottom:10px;"
                                              placeholder="cpu_usage > 50 and connections > 20">${customExpression}</textarea>

                                    <label style="display:flex;align-items:center;margin-bottom:10px;">
                                        <span style="margin-right:10px;">持续时间:</span>
                                        <input type="number" id="customExpressionDuration" value="${customDuration}"
                                               style="width:80px;padding:4px;" min="1">
                                        <span style="margin-left:5px;">秒</span>
                                    </label>

                                    <button id="testExpressionBtn" class="btn btn-secondary" style="margin-bottom:10px;">
                                        Test Expression
                                    </button>
                                    <div id="expressionValidation" style="font-size:12px;margin-top:5px;"></div>

                                    <p style="font-size:11px;color:#666;margin-top:10px;">
                                        可用指标: cpu_usage, memory_usage, disk_usage, connections, qps, tps
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                `,
                buttons: [
                    { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                    { text: '保存', variant: 'primary', onClick: () => this._saveInspectionConfig(datasourceId) }
                ]
            });

            // Setup event listeners for threshold UI
            this._setupThresholdListeners();

        } catch (error) {
            Toast.error('加载失败 configuration');
        }
    },

    _setupThresholdListeners() {
        // Toggle custom expression fields
        const useCustomCheckbox = DOM.$('#useCustomExpression');
        const customFields = DOM.$('#customExpressionFields');
        const presetThresholds = DOM.$('#presetThresholds');

        useCustomCheckbox?.addEventListener('change', (e) => {
            const isCustom = e.target.checked;
            customFields.style.display = isCustom ? 'block' : 'none';

            // Disable preset checkboxes when custom is enabled
            ['cpuEnabled', 'diskEnabled', 'connectionsEnabled'].forEach(id => {
                const checkbox = DOM.$(`#${id}`);
                if (checkbox) {
                    checkbox.disabled = isCustom;
                    if (isCustom) checkbox.checked = false;
                }
            });
        });

        // Test expression button
        const testBtn = DOM.$('#testExpressionBtn');
        testBtn?.addEventListener('click', async () => {
            const expression = DOM.$('#customExpressionText')?.value.trim();
            const validationDiv = DOM.$('#expressionValidation');

            if (!expression) {
                validationDiv.innerHTML = '<span style="color:#f44336;">Please enter an expression</span>';
                return;
            }

            testBtn.disabled = true;
            testBtn.textContent = 'Testing...';

            try {
                const result = await API.post('/api/inspections/validate-expression', { expression });

                if (result.valid) {
                    validationDiv.innerHTML = '<span style="color:#4caf50;">✓ Valid expression</span>';
                } else {
                    validationDiv.innerHTML = `<span style="color:#f44336;">✗ Invalid: ${result.error}</span>`;
                }
            } catch (err) {
                validationDiv.innerHTML = `<span style="color:#f44336;">✗ Validation failed: ${err.message}</span>`;
            } finally {
                testBtn.disabled = false;
                testBtn.textContent = 'Test Expression';
            }
        });
    },

    async _saveInspectionConfig(datasourceId) {
        const enabled = DOM.$('#enableAuto')?.checked;
        const schedule_interval = parseInt(DOM.$('#scheduleInterval')?.value) || 86400;
        const use_ai_analysis = DOM.$('#useAI')?.checked;

        // Build threshold_rules
        const threshold_rules = {};
        const useCustomExpression = DOM.$('#useCustomExpression')?.checked;

        if (useCustomExpression) {
            const expression = DOM.$('#customExpressionText')?.value.trim();
            const duration = parseInt(DOM.$('#customExpressionDuration')?.value) || 60;

            if (!expression) {
                Toast.error('Please enter a custom expression');
                return;
            }

            threshold_rules.custom_expression = {
                expression,
                duration
            };
        } else {
            // Preset thresholds
            if (DOM.$('#cpuEnabled')?.checked) {
                threshold_rules.cpu_usage = {
                    threshold: parseInt(DOM.$('#cpuThreshold')?.value) || 50,
                    duration: parseInt(DOM.$('#cpuDuration')?.value) || 60
                };
            }

            if (DOM.$('#diskEnabled')?.checked) {
                threshold_rules.disk_usage = {
                    threshold: parseInt(DOM.$('#diskThreshold')?.value) || 80,
                    duration: parseInt(DOM.$('#diskDuration')?.value) || 300
                };
            }

            if (DOM.$('#connectionsEnabled')?.checked) {
                threshold_rules.connections = {
                    threshold: parseInt(DOM.$('#connectionsThreshold')?.value) || 20,
                    duration: parseInt(DOM.$('#connectionsDuration')?.value) || 120
                };
            }
        }

        try {
            await API.post(`/api/inspections/config/${datasourceId}`, {
                enabled,
                schedule_interval,
                use_ai_analysis,
                threshold_rules
            });
            Modal.hide();
            Toast.success('Configuration saved');
        } catch (error) {
            Toast.error('Failed to save configuration');
        }
    }
};
