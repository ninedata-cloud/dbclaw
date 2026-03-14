/* Datasources management page */
const DatasourcesPage = {
    allDatasources: [],
    filteredDatasources: [],

    async render() {
        console.log('DatasourcesPage: Using NEW table layout');
        Header.render('Datasources', DOM.el('button', {
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
                        <h3>No Datasources Yet</h3>
                        <p>Add your first database datasource to start monitoring and diagnosing.</p>
                    </div>
                `;
                DOM.createIcons();
                return;
            }

            // Filters
            const filterBar = DOM.el('div', { style: { marginBottom: '20px', display: 'flex', gap: '10px', alignItems: 'end', flexWrap: 'wrap' } });

            const nameFilter = DOM.el('div');
            nameFilter.innerHTML = `
                <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">Name</label>
                <input type="text" id="filterName" class="form-input" placeholder="Search by name..." style="padding:8px;border-radius:4px;min-width:200px;">
            `;

            const typeFilter = DOM.el('div');
            typeFilter.innerHTML = `
                <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">Database Type</label>
                <select id="filterType" class="form-select" style="padding:8px;border-radius:4px;">
                    <option value="">All Types</option>
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
                <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">Importance</label>
                <select id="filterImportance" class="form-select" style="padding:8px;border-radius:4px;">
                    <option value="">All Levels</option>
                    <option value="core">核心系统</option>
                    <option value="production">生产系统</option>
                    <option value="development">开发测试</option>
                    <option value="temporary">临时</option>
                </select>
            `;

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
            Toast.error('Failed to load datasources: ' + err.message);
        }
    },

    _setupFilterListeners() {
        DOM.$('#filterName')?.addEventListener('input', () => this._applyFilters());
        DOM.$('#filterType')?.addEventListener('change', () => this._applyFilters());
        DOM.$('#filterImportance')?.addEventListener('change', () => this._applyFilters());
    },

    _applyFilters() {
        const nameFilter = DOM.$('#filterName')?.value.toLowerCase() || '';
        const typeFilter = DOM.$('#filterType')?.value || '';
        const importanceFilter = DOM.$('#filterImportance')?.value || '';

        this.filteredDatasources = this.allDatasources.filter(ds => {
            const matchName = !nameFilter || ds.name.toLowerCase().includes(nameFilter);
            const matchType = !typeFilter || ds.db_type === typeFilter;
            const matchImportance = !importanceFilter || ds.importance_level === importanceFilter;
            return matchName && matchType && matchImportance;
        });

        this._renderTable();
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

        container.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Name</th>
                        <th>Type</th>
                        <th>Host</th>
                        <th>Database</th>
                        <th>Importance</th>
                        <th>Interval</th>
                        <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                    ${this.filteredDatasources.map(conn => {
                        const importance = importanceLevels[conn.importance_level] || importanceLevels.production;
                        return `
                            <tr>
                                <td><strong>${conn.name}</strong></td>
                                <td><span class="badge badge-info">${conn.db_type}</span></td>
                                <td>${conn.host}:${conn.port}</td>
                                <td>${conn.database || '-'}</td>
                                <td><span style="color:${importance.color};font-weight:500;">${importance.label}</span></td>
                                <td>${conn.monitoring_interval || 60}s</td>
                                <td>
                                    <div style="display:flex;gap:4px;flex-wrap:wrap;">
                                        <button class="btn btn-sm btn-secondary" onclick="DatasourcesPage._testDatasource(${conn.id})" title="Test">
                                            <i data-lucide="plug"></i>
                                        </button>
                                        <button class="btn btn-sm btn-secondary" onclick="DatasourcesPage._editDatasource(${conn.id})" title="Edit">
                                            <i data-lucide="pencil"></i>
                                        </button>
                                        <button class="btn btn-sm btn-secondary" onclick="DatasourcesPage._showInspectionConfig(${conn.id})" title="Inspection Config">
                                            <i data-lucide="settings"></i>
                                        </button>
                                        <button class="btn btn-sm btn-secondary" onclick="DatasourcesPage._triggerInspection(${conn.id})" title="Diagnose">
                                            <i data-lucide="zap"></i>
                                        </button>
                                        <button class="btn btn-sm btn-danger" onclick="DatasourcesPage._deleteDatasource(${conn.id})" title="Delete">
                                            <i data-lucide="trash-2"></i>
                                        </button>
                                        <button class="btn btn-sm btn-primary" onclick="DatasourcesPage._monitorDatasource(${conn.id})" title="Monitor">
                                            <i data-lucide="activity"></i>
                                        </button>
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

    async _testDatasource(id) {
        const btn = event.target.closest('button');
        btn.innerHTML = '<div class="spinner"></div>';
        btn.disabled = true;
        try {
            const result = await API.testDatasource(id);
            if (result.success) {
                Toast.success(`Connection successful! ${result.version || ''}`);
            } else {
                Toast.error(`Connection failed: ${result.message}`);
            }
        } catch (err) {
            Toast.error('Test failed: ' + err.message);
        } finally {
            btn.innerHTML = '<i data-lucide="plug"></i>';
            btn.disabled = false;
            DOM.createIcons();
        }
    },

    _editDatasource(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (conn) DatasourceForm.show(conn, () => this.render());
    },

    async _deleteDatasource(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (!conn || !confirm(`Delete datasource "${conn.name}"? This cannot be undone.`)) return;
        try {
            await API.deleteDatasource(id);
            Toast.success('Datasource deleted');
            this.render();
        } catch (err) {
            Toast.error('Failed to delete: ' + err.message);
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
        if (!confirm('Trigger manual inspection? This will generate a comprehensive diagnostic report.')) {
            return;
        }
        const btn = event.target.closest('button');
        btn.innerHTML = '<div class="spinner"></div>';
        btn.disabled = true;
        try {
            await API.post(`/api/inspections/trigger/${datasourceId}`);
            Toast.success('Inspection triggered successfully!');
        } catch (err) {
            Toast.error('Failed to trigger inspection: ' + err.message);
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
            const diskDuration = thresholdRules.disk_usage?.duration || 300;

            const connectionsEnabled = !hasCustomExpression && !!thresholdRules.connections;
            const connectionsThreshold = thresholdRules.connections?.threshold || 20;
            const connectionsDuration = thresholdRules.connections?.duration || 120;

            Modal.show({
                title: 'Inspection Configuration',
                content: `
                    <div style="padding:10px;">
                        <label style="display:block;margin-bottom:15px;">
                            <input type="checkbox" id="enableAuto" ${config?.enabled ? 'checked' : ''}>
                            Enable Automatic Inspection
                        </label>
                        <label style="display:block;margin-bottom:10px;">
                            Schedule Interval (seconds):
                            <input type="number" id="scheduleInterval" value="${config?.schedule_interval || 86400}"
                                   style="width:100%;padding:8px;margin-top:5px;"
                                   placeholder="86400 (daily)">
                        </label>
                        <p style="font-size:12px;color:#666;margin-top:5px;">
                            Examples: 86400 (daily), 21600 (every 6 hours), 3600 (hourly)
                        </p>
                        <label style="display:block;margin-bottom:15px;margin-top:15px;">
                            <input type="checkbox" id="useAI" ${config?.use_ai_analysis !== false ? 'checked' : ''}>
                            Use AI Analysis
                        </label>

                        <div style="border-top:1px solid #ddd;margin-top:20px;padding-top:20px;">
                            <h4 style="margin-bottom:15px;font-size:14px;font-weight:600;">Threshold Configuration</h4>

                            <div id="presetThresholds" style="margin-bottom:20px;">
                                <p style="font-size:13px;color:#666;margin-bottom:10px;">Preset Thresholds:</p>

                                <label style="display:flex;align-items:center;margin-bottom:10px;">
                                    <input type="checkbox" id="cpuEnabled" ${cpuEnabled ? 'checked' : ''} style="margin-right:8px;">
                                    <span style="flex:1;">CPU Usage &gt;</span>
                                    <input type="number" id="cpuThreshold" value="${cpuThreshold}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="0" max="100">
                                    <span>% for</span>
                                    <input type="number" id="cpuDuration" value="${cpuDuration}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="1">
                                    <span>seconds</span>
                                </label>

                                <label style="display:flex;align-items:center;margin-bottom:10px;">
                                    <input type="checkbox" id="diskEnabled" ${diskEnabled ? 'checked' : ''} style="margin-right:8px;">
                                    <span style="flex:1;">Disk Usage &gt;</span>
                                    <input type="number" id="diskThreshold" value="${diskThreshold}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="0" max="100">
                                    <span>% for</span>
                                    <input type="number" id="diskDuration" value="${diskDuration}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="1">
                                    <span>seconds</span>
                                </label>

                                <label style="display:flex;align-items:center;margin-bottom:10px;">
                                    <input type="checkbox" id="connectionsEnabled" ${connectionsEnabled ? 'checked' : ''} style="margin-right:8px;">
                                    <span style="flex:1;">Active Connections &gt;</span>
                                    <input type="number" id="connectionsThreshold" value="${connectionsThreshold}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="0">
                                    <span>for</span>
                                    <input type="number" id="connectionsDuration" value="${connectionsDuration}"
                                           style="width:60px;padding:4px;margin:0 5px;" min="1">
                                    <span>seconds</span>
                                </label>
                            </div>

                            <div style="text-align:center;margin:15px 0;color:#999;">OR</div>

                            <div id="customExpression">
                                <label style="display:block;margin-bottom:10px;">
                                    <input type="checkbox" id="useCustomExpression" ${hasCustomExpression ? 'checked' : ''}>
                                    Use Custom Expression
                                </label>

                                <div id="customExpressionFields" style="display:${hasCustomExpression ? 'block' : 'none'};">
                                    <label style="display:block;margin-bottom:5px;font-size:12px;">
                                        Expression:
                                    </label>
                                    <textarea id="customExpressionText"
                                              style="width:100%;padding:8px;font-family:monospace;font-size:12px;min-height:60px;margin-bottom:10px;"
                                              placeholder="cpu_usage > 50 and connections > 20">${customExpression}</textarea>

                                    <label style="display:flex;align-items:center;margin-bottom:10px;">
                                        <span style="margin-right:10px;">Duration:</span>
                                        <input type="number" id="customExpressionDuration" value="${customDuration}"
                                               style="width:80px;padding:4px;" min="1">
                                        <span style="margin-left:5px;">seconds</span>
                                    </label>

                                    <button id="testExpressionBtn" class="btn btn-secondary" style="margin-bottom:10px;">
                                        Test Expression
                                    </button>
                                    <div id="expressionValidation" style="font-size:12px;margin-top:5px;"></div>

                                    <p style="font-size:11px;color:#666;margin-top:10px;">
                                        Available metrics: cpu_usage, memory_usage, disk_usage, connections, qps, tps
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                `,
                buttons: [
                    { text: 'Cancel', variant: 'secondary', onClick: () => Modal.hide() },
                    { text: 'Save', variant: 'primary', onClick: () => this._saveInspectionConfig(datasourceId) }
                ]
            });

            // Setup event listeners for threshold UI
            this._setupThresholdListeners();

        } catch (error) {
            Toast.error('Failed to load configuration');
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
