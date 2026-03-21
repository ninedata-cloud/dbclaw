/* Datasources management page */
const DatasourcesPage = {
    allDatasources: [],
    filteredDatasources: [],

    async render() {
        console.log('DatasourcesPage: Using NEW table layout');
        Header.render('数据源管理', DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> New Datasource',
            onClick: () => DatasourceForm.show(null, () => this.render())
        }));

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            this.allDatasources = await API.getDatasources();
            this.filteredDatasources = [...this.allDatasources];
            Store.set('datasources', this.allDatasources);
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

            // Filters + Refresh button
            const filterBar = DOM.el('div', { style: { marginBottom: '20px', display: 'flex', gap: '10px', alignItems: 'end', flexWrap: 'wrap' } });

            const nameFilter = DOM.el('div');
            nameFilter.innerHTML = `
                <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">名称</label>
                <input type="text" id="filterName" class="form-input" placeholder="按名称搜索..." style="padding:8px;border-radius:4px;min-width:200px;">
            `;

            const typeFilter = DOM.el('div');
            typeFilter.innerHTML = `
                <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">数据库类型</label>
                <select id="filterType" class="form-select" style="padding:8px;border-radius:4px;">
                    <option value="">所有类型</option>
                    <option value="mysql">MySQL</option>
                    <option value="postgresql">PostgreSQL</option>
                    <option value="oracle">Oracle</option>
                    <option value="sqlserver">SQL Server</option>
                    <option value="dm">DM</option>
                    <option value="mongodb">MongoDB</option>
                    <option value="redis">Redis</option>
                </select>
            `;

            const importanceFilter = DOM.el('div');
            importanceFilter.innerHTML = `
                <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">重要性</label>
                <select id="filter重要性" class="form-select" style="padding:8px;border-radius:4px;">
                    <option value="">所有级别</option>
                    <option value="core">核心系统</option>
                    <option value="production">生产系统</option>
                    <option value="development">开发测试</option>
                    <option value="temporary">临时</option>
                </select>
            `;

            const refreshBtn = DOM.el('button', {
                className: 'btn btn-sm btn-outline-primary',
                innerHTML: '<i data-lucide="refresh-cw"></i> 刷新状态',
                style: { marginLeft: 'auto' },
                onclick: () => this._refreshStatus()
            });

            filterBar.appendChild(nameFilter);
            filterBar.appendChild(typeFilter);
            filterBar.appendChild(importanceFilter);
            content.appendChild(filterBar);

            // Table container
            const tableContainer = DOM.el('div', { id: 'datasource-table-container' });
            content.appendChild(tableContainer);

            this._renderTable();
            this._setupFilterListeners();
            DOM.createIcons();

        } catch (err) {
            Toast.error('加载数据源失败: ' + err.message);
        }
    },

    _setupFilterListeners() {
        DOM.$('#filterName')?.addEventListener('input', () => this._applyFilters());
        DOM.$('#filterType')?.addEventListener('change', () => this._applyFilters());
        DOM.$('#filter重要性')?.addEventListener('change', () => this._applyFilters());
    },

    _applyFilters() {
        const nameFilter = DOM.$('#filterName')?.value.toLowerCase() || '';
        const typeFilter = DOM.$('#filterType')?.value || '';
        const importanceFilter = DOM.$('#filter重要性')?.value || '';

        this.filteredDatasources = this.allDatasources.filter(ds => {
            const matchName = !nameFilter || ds.name.toLowerCase().includes(nameFilter);
            const matchType = !typeFilter || ds.db_type === typeFilter;
            const match重要性 = !importanceFilter || ds.importance_level === importanceFilter;
            return matchName && matchType && match重要性;
        });

        this._renderTable();
    },

    _getStatusCell(conn, statusConfig) {
        const status = conn.connection_status || 'unknown';
        const config = statusConfig[status] || statusConfig.unknown;
        return `
            <div style="display:flex;align-items:center;gap:6px;">
                <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${config.color}"></span>
                <span style="padding:2px 8px;border-radius:12px;font-size:12px;background:${config.bg};color:${config.color};font-weight:500;">
                    ${config.label}
                </span>
            </div>
        `;
    },

    _renderTable() {
        const container = DOM.$('#datasource-table-container');
        if (!container) return;

        const importanceLevels = {
            core: { label: '核心系统', color: '#ef4444' },
            production: { label: '生产系统', color: '#f59e0b' },
            development: { label: '开发测试', color: '#3b82f6' },
            temporary: { label: '临时', color: '#6b7280' }
        };

        const statusConfig = {
            'normal': { label: '正常', color: '#10b981', bg: '#ecfdf5' },
            'failed': { label: '连接失败', color: '#ef4444', bg: '#fef2f2' },
            'warning': { label: '警告', color: '#f59e0b', bg: '#fffbeb' },
            'unknown': { label: '未知', color: '#6b7280', bg: '#f3f4f6' }
        };

        container.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>名称</th>
                        <th>类型</th>
                        <th>连接状态</th>
                        <th>主机</th>
                        <th>数据库</th>
                        <th>重要性</th>
                        <th>监控间隔</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${this.filteredDatasources.map(conn => {
                        const importance = importanceLevels[conn.importance_level] || importanceLevels.production;
                        return `
                            <tr>
                                <td><strong>${conn.name}</strong></td>
                                <td><span class="badge badge-info">${conn.db_type}</span></td>
                                <td>
                                    ${this._getStatusCell(conn, statusConfig)}
                                </td>
                                <td>${conn.host}:${conn.port}</td>
                                <td>${conn.database || '-'}</td>
                                <td><span style="color:${importance.color};font-weight:500;">${importance.label}</span></td>
                                <td>${conn.monitoring_interval || 60}s</td>
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
