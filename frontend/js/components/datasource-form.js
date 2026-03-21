/* Datasource form component */
const DatasourceForm = {
    show(datasource = null, onSave) {
        const isEdit = !!datasource;
        const form = DOM.el('form', { id: 'datasource-form' });

        form.innerHTML = `
            <div class="form-group">
                <label>数据源名称</label>
                <input type="text" class="form-input" name="name" value="${datasource?.name || ''}" required placeholder="我的数据库">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>数据库类型</label>
                    <select class="form-select" name="db_type" required>
                        <option value="mysql" ${datasource?.db_type === 'mysql' ? 'selected' : ''}>MySQL</option>
                        <option value="postgresql" ${datasource?.db_type === 'postgresql' ? 'selected' : ''}>PostgreSQL</option>
                        <option value="oracle" ${datasource?.db_type === 'oracle' ? 'selected' : ''}>Oracle</option>
                        <option value="sqlserver" ${datasource?.db_type === 'sqlserver' ? 'selected' : ''}>SQL Server</option>
                        <option value="tidb" ${datasource?.db_type === 'tidb' ? 'selected' : ''}>TiDB</option>
                        <option value="dm" ${datasource?.db_type === 'dm' ? 'selected' : ''}>DM (达梦)</option>
                        <option value="oceanbase" ${datasource?.db_type === 'oceanbase' ? 'selected' : ''}>OceanBase</option>
                        <option value="opengauss" ${datasource?.db_type === 'opengauss' ? 'selected' : ''}>openGauss</option>
                        <option value="mongodb" ${datasource?.db_type === 'mongodb' ? 'selected' : ''}>MongoDB</option>
                        <option value="redis" ${datasource?.db_type === 'redis' ? 'selected' : ''}>Redis</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Port</label>
                    <input type="number" class="form-input" name="port" value="${datasource?.port || this._defaultPort('mysql')}" required>
                </div>
            </div>
            <div class="form-group">
                <label>Host</label>
                <input type="text" class="form-input" name="host" value="${datasource?.host || 'localhost'}" required placeholder="localhost">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" class="form-input" name="username" value="${datasource?.username || ''}" placeholder="root">
                </div>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" class="form-input" name="password" value="" placeholder="${isEdit ? '(保持不变)' : ''}">
                </div>
            </div>
            <div class="form-group">
                <label>Database</label>
                <input type="text" class="form-input" name="database" value="${datasource?.database || ''}" placeholder="mydb">
            </div>
            <div class="form-group" id="oracle-conn-mode-group" style="display: ${datasource?.db_type === 'oracle' ? 'block' : 'none'};">
                <label>连接模式</label>
                <select class="form-select" name="oracle_conn_mode">
                    <option value="default" ${this._getExtraParam(datasource, 'oracle_conn_mode', 'default') === 'default' ? 'selected' : ''}>Default</option>
                    <option value="sysdba" ${this._getExtraParam(datasource, 'oracle_conn_mode', 'default') === 'sysdba' ? 'selected' : ''}>SYSDBA</option>
                    <option value="sysoper" ${this._getExtraParam(datasource, 'oracle_conn_mode', 'default') === 'sysoper' ? 'selected' : ''}>SYSOPER</option>
                </select>
                <small class="text-muted">以 SYSDBA/SYSOPER 身份连接（需要对应权限）</small>
            </div>
            <div class="form-group">
                <label>Host (可选)</label>
                <select class="form-select" name="host_id">
                    <option value="">无</option>
                </select>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>重要性级别</label>
                    <select class="form-select" name="importance_level" required>
                        <option value="core" ${datasource?.importance_level === 'core' ? 'selected' : ''}>核心系统 (Core)</option>
                        <option value="production" ${datasource?.importance_level === 'production' || !datasource ? 'selected' : ''}>生产系统 (Production)</option>
                        <option value="development" ${datasource?.importance_level === 'development' ? 'selected' : ''}>开发测试 (Development)</option>
                        <option value="temporary" ${datasource?.importance_level === 'temporary' ? 'selected' : ''}>临时 (Temporary)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>监控间隔（秒）</label>
                    <input type="number" class="form-input" name="monitoring_interval" value="${datasource?.monitoring_interval || 60}" min="5" max="3600" required>
                </div>
            </div>
            <div class="form-group">
                <label>监控数据来源</label>
                <select class="form-select" name="metric_source" id="metric-source-select" required>
                    <option value="system" ${!datasource || datasource?.metric_source === 'system' ? 'selected' : ''}>系统采集（直连数据库）</option>
                    <option value="integration" ${datasource?.metric_source === 'integration' ? 'selected' : ''}>集成采集（外部集成系统）</option>
                </select>
                <small class="text-muted">选择监控数据的采集方式</small>
            </div>
            <div id="integration-config-section" style="display: ${datasource?.metric_source === 'integration' ? 'block' : 'none'};">
                <div class="form-group">
                    <label>外部实例 ID</label>
                    <input type="text" class="form-input" name="external_instance_id" id="external-instance-id" value="${datasource?.external_instance_id || ''}" placeholder="例如：rm-bp16knn4mo4fvh99ieo">
                    <small class="text-muted">外部监控系统中的实例标识（如阿里云 RDS 实例 ID）</small>
                </div>
            </div>
        `;

        // Update port when db_type changes
        const dbTypeSelect = form.querySelector('[name="db_type"]');
        const portInput = form.querySelector('[name="port"]');
        const oracleConnModeGroup = form.querySelector('#oracle-conn-mode-group');
        dbTypeSelect.addEventListener('change', () => {
            if (!datasource) portInput.value = this._defaultPort(dbTypeSelect.value);
            oracleConnModeGroup.style.display = dbTypeSelect.value === 'oracle' ? 'block' : 'none';
        });

        // Handle metric source change
        const metricSourceSelect = form.querySelector('#metric-source-select');
        const integrationConfigSection = form.querySelector('#integration-config-section');
        metricSourceSelect.addEventListener('change', () => {
            if (metricSourceSelect.value === 'integration') {
                integrationConfigSection.style.display = 'block';
            } else {
                integrationConfigSection.style.display = 'none';
            }
        });

        // Load hosts
        this._loadHosts(form.querySelector('[name="host_id"]'), datasource?.host_id);

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());
            data.port = parseInt(data.port);
            data.monitoring_interval = parseInt(data.monitoring_interval);
            if (!data.password) delete data.password;
            if (!data.host_id) data.host_id = null;
            else data.host_id = parseInt(data.host_id);
            if (!data.database) data.database = null;

            // 构建 extra_params（Oracle 连接模式等）
            const extraParams = {};
            if (data.db_type === 'oracle' && data.oracle_conn_mode && data.oracle_conn_mode !== 'default') {
                extraParams.oracle_conn_mode = data.oracle_conn_mode;
            }
            data.extra_params = Object.keys(extraParams).length > 0 ? JSON.stringify(extraParams) : null;
            delete data.oracle_conn_mode;

            // 处理监控来源配置
            if (data.metric_source === 'system') {
                // 如果选择系统采集，清空外部实例 ID
                data.external_instance_id = null;
            } else if (data.metric_source === 'integration') {
                // 验证集成配置
                if (!data.external_instance_id) {
                    Toast.error('使用集成采集时，必须填写外部实例 ID');
                    return;
                }
            }

            try {
                if (isEdit) {
                    await API.updateDatasource(datasource.id, data);
                    Toast.success('数据源已更新');
                } else {
                    await API.createDatasource(data);
                    Toast.success('数据源已创建');
                }
                Modal.hide();
                if (onSave) onSave();
            } catch (err) {
                Toast.error(err.message);
            }
        });

        const footer = DOM.el('div');
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            textContent: 'Cancel',
            type: 'button',
            onClick: () => Modal.hide()
        }));

        // Add test button for both create and edit modes
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="plug"></i> Test',
            type: 'button',
            onClick: async (e) => {
                const btn = e.currentTarget;
                btn.innerHTML = '<div class="spinner"></div>';
                btn.disabled = true;
                try {
                    // Get current form values
                    const formData = new FormData(form);
                    const data = {
                        db_type: formData.get('db_type'),
                        host: formData.get('host'),
                        port: parseInt(formData.get('port')),
                        username: formData.get('username') || null,
                        password: formData.get('password') || null,
                        database: formData.get('database') || null
                    };

                    // Oracle 连接模式
                    if (data.db_type === 'oracle') {
                        const connMode = formData.get('oracle_conn_mode');
                        if (connMode && connMode !== 'default') {
                            data.extra_params = JSON.stringify({ oracle_conn_mode: connMode });
                        }
                    }

                    // If editing, include datasource_id so backend can use saved password if needed
                    if (isEdit) {
                        data.datasource_id = datasource.id;
                    }

                    const result = await API.testDatasourceConnection(data);
                    if (result.success) {
                        Toast.success(`连接成功! ${result.version || ''}`);
                    } else {
                        Toast.error(`连接失败: ${result.message}`);
                    }
                } catch (err) {
                    Toast.error('测试失败: ' + err.message);
                } finally {
                    btn.innerHTML = '<i data-lucide="plug"></i> Test';
                    btn.disabled = false;
                    DOM.createIcons();
                }
            }
        }));

        footer.appendChild(DOM.el('button', {
            className: 'btn btn-primary',
            textContent: isEdit ? 'Update' : 'Create',
            type: 'button',
            onClick: () => form.requestSubmit()
        }));

        Modal.show({
            title: isEdit ? 'Edit Datasource' : 'New Datasource',
            content: form,
            footer: footer,
        });
    },

    _getExtraParam(datasource, key, defaultValue) {
        if (!datasource?.extra_params) return defaultValue;
        try {
            const params = JSON.parse(datasource.extra_params);
            return params[key] || defaultValue;
        } catch (e) {
            return defaultValue;
        }
    },

    _defaultPort(dbType) {
        const ports = {
            mysql: 3306,
            postgresql: 5432,
            oracle: 1521,
            sqlserver: 1433,
            tidb: 4000,
            dm: 5236,
            oceanbase: 2881,
            opengauss: 5432,
            mongodb: 27017,
            redis: 6379
        };
        return ports[dbType] || 3306;
    },

    async _loadHosts(select, selectedId) {
        try {
            const hosts = await API.getHosts();
            Store.set('hosts', hosts);
            for (const host of hosts) {
                const opt = DOM.el('option', { value: host.id, textContent: `${host.name} (${host.host})` });
                if (selectedId && host.id === selectedId) opt.selected = true;
                select.appendChild(opt);
            }
        } catch (e) {
            // Ignore
        }
    }
};
