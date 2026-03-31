/* Datasource form component */
const DatasourceForm = {
    _normalizeTags(rawValue) {
        if (!rawValue) return [];

        const tags = rawValue
            .split(/[，,]/)
            .map(tag => tag.trim())
            .filter(Boolean);

        return [...new Map(tags.map(tag => [tag.toLowerCase(), tag])).values()];
    },

    async _loadInboundIntegrations() {
        try {
            const items = await API.get('/api/integrations');
            return (items || []).filter(item => item.integration_type === 'inbound_metric' && item.enabled);
        } catch (error) {
            console.error('Failed to load inbound integrations:', error);
            return [];
        }
    },

    _getInboundSource(datasource) {
        return datasource?.inbound_source || {};
    },

    show(datasource = null, onSave) {
        const isEdit = !!datasource;
        const form = DOM.el('form', { id: 'datasource-form' });
        const inboundSource = this._getInboundSource(datasource);

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
                        <option value="oceanbase_mysql" ${datasource?.db_type === 'oceanbase_mysql' ? 'selected' : ''}>OceanBase MySQL</option>
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
            <div class="form-group">
                <label>标签</label>
                <input type="text" class="form-input" name="tags" value="${(datasource?.tags || []).join(', ')}" placeholder="例如：生产, 会员, 核心系统">
                <small class="text-muted">多个标签请用逗号分隔</small>
            </div>
            <div class="form-group">
                <label>备注</label>
                <textarea class="form-input" name="remark" rows="2" placeholder="可选备注信息，如业务背景、特殊配置等">${datasource?.remark || ''}</textarea>
                <small class="text-muted">AI 诊断时会自动附带此备注</small>
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
                    <label>入站 Integration</label>
                    <select class="form-select" id="inbound-integration-select">
                        <option value="">加载中...</option>
                    </select>
                    <small class="text-muted">选择 inbound_metric 类型的 Integration，用于拉取外部监控指标</small>
                </div>
                <div class="form-group">
                    <label>采集间隔（秒）</label>
                    <input type="number" class="form-input" id="inbound-schedule-seconds" value="${(inboundSource.schedule && inboundSource.schedule.seconds) ? inboundSource.schedule.seconds : 60}" min="5" max="3600">
                </div>
                <div id="inbound-params-container"></div>
            </div>
        `;

        const dbTypeSelect = form.querySelector('[name="db_type"]');
        const portInput = form.querySelector('[name="port"]');
        const oracleConnModeGroup = form.querySelector('#oracle-conn-mode-group');
        dbTypeSelect.addEventListener('change', () => {
            if (!datasource) portInput.value = this._defaultPort(dbTypeSelect.value);
            oracleConnModeGroup.style.display = dbTypeSelect.value === 'oracle' ? 'block' : 'none';
        });

        const metricSourceSelect = form.querySelector('#metric-source-select');
        const integrationConfigSection = form.querySelector('#integration-config-section');
        metricSourceSelect.addEventListener('change', () => {
            if (metricSourceSelect.value === 'integration') integrationConfigSection.style.display = 'block';
            else integrationConfigSection.style.display = 'none';
        });

        this._loadHosts(form.querySelector('[name="host_id"]'), datasource?.host_id);

        // inbound integration dynamic section
        (async () => {
            const integrations = await this._loadInboundIntegrations();
            const select = form.querySelector('#inbound-integration-select');
            if (!select) return;

            const currentId = inboundSource.integration_id ? String(inboundSource.integration_id) : '';
            select.innerHTML = `
                <option value="">请选择</option>
                ${integrations.map(item => `
                    <option value="${item.id}" ${String(item.id) === currentId ? 'selected' : ''}>${item.name}</option>
                `).join('')}
            `;

            const renderParams = (integrationId, existingParams = {}) => {
                const integration = integrations.find(item => String(item.id) === String(integrationId));
                const container = form.querySelector('#inbound-params-container');
                if (!container) return;

                if (!integration || !integration.config_schema || !integration.config_schema.properties) {
                    container.innerHTML = '';
                    return;
                }

                let html = '<div style="font-weight:600;margin-bottom:8px;">采集参数</div>';
                for (const [key, prop] of Object.entries(integration.config_schema.properties)) {
                    const required = integration.config_schema.required?.includes(key) ? 'required' : '';
                    const type = prop.format === 'password' ? 'password' : 'text';
                    const value = prop.format === 'password' ? '' : (existingParams[key] || prop.default || '');
                    html += `
                        <div class="form-group">
                            <label>${prop.title || key} ${required ? '*' : ''}</label>
                            <input type="${type}" class="form-input inbound-param" data-key="${key}" data-format="${prop.format || ''}" value="${value}" placeholder="${prop.description || ''}">
                        </div>
                    `;
                }
                container.innerHTML = html;
            };

            // initial
            renderParams(select.value, inboundSource.params || {});

            // change
            select.addEventListener('change', () => renderParams(select.value, {}));
        })();

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());
            data.port = parseInt(data.port);
            data.monitoring_interval = parseInt(data.monitoring_interval);
            data.tags = this._normalizeTags(data.tags);
            if (!data.password) delete data.password;
            if (!data.host_id) data.host_id = null;
            else data.host_id = parseInt(data.host_id);
            if (!data.database) data.database = null;

            const extraParams = {};
            if (data.db_type === 'oracle' && data.oracle_conn_mode && data.oracle_conn_mode !== 'default') {
                extraParams.oracle_conn_mode = data.oracle_conn_mode;
            }
            data.extra_params = Object.keys(extraParams).length > 0 ? JSON.stringify(extraParams) : null;
            delete data.oracle_conn_mode;

            if (data.metric_source === 'system') {
                data.inbound_source = null;
            } else if (data.metric_source === 'integration') {
                const integrationId = form.querySelector('#inbound-integration-select')?.value;
                if (!integrationId) {
                    Toast.error('使用集成采集时，必须选择入站 Integration');
                    return;
                }

                const scheduleSeconds = parseInt(form.querySelector('#inbound-schedule-seconds')?.value || '60');
                const params = {};
                form.querySelectorAll('.inbound-param').forEach(input => {
                    const key = input.dataset.key;
                    const format = input.dataset.format;
                    if (!key) return;
                    if (format === 'password') {
                        if (input.value) params[key] = `ENCRYPT:${input.value}`;
                    } else {
                        params[key] = input.value;
                    }
                });

                data.inbound_source = {
                    integration_id: parseInt(integrationId),
                    enabled: true,
                    params,
                    schedule: { mode: 'interval', seconds: scheduleSeconds }
                };
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

        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="plug"></i> Test',
            type: 'button',
            onClick: async (e) => {
                const btn = e.currentTarget;
                btn.innerHTML = '<div class="spinner"></div>';
                btn.disabled = true;
                try {
                    const formData = new FormData(form);
                    const data = {
                        db_type: formData.get('db_type'),
                        host: formData.get('host'),
                        port: parseInt(formData.get('port')),
                        username: formData.get('username') || null,
                        password: formData.get('password') || null,
                        database: formData.get('database') || null
                    };

                    if (data.db_type === 'oracle') {
                        const connMode = formData.get('oracle_conn_mode');
                        if (connMode && connMode !== 'default') {
                            data.extra_params = JSON.stringify({ oracle_conn_mode: connMode });
                        }
                    }

                    if (isEdit) {
                        data.datasource_id = datasource.id;
                    }

                    const result = await API.testDatasourceConnection(data);
                    if (result.success) Toast.success(`连接成功! ${result.version || ''}`);
                    else Toast.error(`连接失败: ${result.message}`);
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
            return params[key] !== undefined ? params[key] : defaultValue;
        } catch {
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
            oceanbase_mysql: 2881,
            opengauss: 5432,
            mongodb: 27017,
            redis: 6379
        };
        return ports[dbType] || 3306;
    },

    async _loadHosts(selectEl, selectedId) {
        try {
            const hosts = await API.get('/api/hosts');
            if (!Array.isArray(hosts)) return;
            hosts.forEach(host => {
                const opt = document.createElement('option');
                opt.value = host.id;
                opt.textContent = `${host.name || host.host} (${host.host})`;
                if (selectedId && String(host.id) === String(selectedId)) opt.selected = true;
                selectEl.appendChild(opt);
            });
        } catch (error) {
            console.error('Failed to load hosts', error);
        }
    }
};