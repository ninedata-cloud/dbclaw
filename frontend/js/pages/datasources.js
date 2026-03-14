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
                    </div>
                `,
                buttons: [
                    { text: 'Cancel', variant: 'secondary', onClick: () => Modal.hide() },
                    { text: 'Save', variant: 'primary', onClick: () => this._saveInspectionConfig(datasourceId) }
                ]
            });
        } catch (error) {
            Toast.error('Failed to load configuration');
        }
    },

    async _saveInspectionConfig(datasourceId) {
        const enabled = DOM.$('#enableAuto')?.checked;
        const schedule_interval = parseInt(DOM.$('#scheduleInterval')?.value) || 86400;
        const use_ai_analysis = DOM.$('#useAI')?.checked;

        try {
            await API.post(`/api/inspections/config/${datasourceId}`, {
                enabled,
                schedule_interval,
                use_ai_analysis,
                threshold_rules: {}
            });
            Modal.hide();
            Toast.success('Configuration saved');
        } catch (error) {
            Toast.error('Failed to save configuration');
        }
    }
};
