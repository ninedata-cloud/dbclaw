/* Datasource form component */
const DatasourceForm = {
    _escapeHtml(text) {
        return Utils.escapeHtml(text);
    },

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
                <input type="text" class="form-input" name="name" value="${this._escapeHtml(datasource?.name || '')}" required placeholder="我的数据库">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>数据库类型</label>
                    <select class="form-select" name="db_type" required>
                        <option value="mysql" ${datasource?.db_type === 'mysql' ? 'selected' : ''}>MySQL</option>
                        <option value="postgresql" ${datasource?.db_type === 'postgresql' ? 'selected' : ''}>PostgreSQL</option>
                        <option value="oracle" ${datasource?.db_type === 'oracle' ? 'selected' : ''}>Oracle</option>
                        <option value="sqlserver" ${datasource?.db_type === 'sqlserver' ? 'selected' : ''}>SQL Server</option>
                        <option value="tdsql-c-mysql" ${datasource?.db_type === 'tdsql-c-mysql' ? 'selected' : ''}>TDSQL-C MySQL</option>
                        <option value="opengauss" ${datasource?.db_type === 'opengauss' ? 'selected' : ''}>openGauss</option>
                        <option value="hana" ${datasource?.db_type === 'hana' ? 'selected' : ''}>SAP HANA</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>端口</label>
                    <input type="number" class="form-input" name="port" value="${this._escapeHtml(String(datasource?.port || this._defaultPort('mysql')))}" required>
                </div>
            </div>
            <div class="form-group">
                <label>主机地址</label>
                <input type="text" class="form-input" name="host" value="${this._escapeHtml(datasource?.host || '')}" required placeholder="127.0.0.1">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>用户名</label>
                    <input type="text" class="form-input" name="username" value="${this._escapeHtml(datasource?.username || '')}" placeholder="root">
                </div>
                <div class="form-group">
                    <label>密码</label>
                    <input type="password" class="form-input" name="password" value="" placeholder="${isEdit ? '(保持不变)' : ''}">
                </div>
            </div>
            <div class="form-group">
                <label>数据库名</label>
                <input type="text" class="form-input" name="database" value="${this._escapeHtml(datasource?.database || '')}" placeholder="mydb">
            </div>
            <div class="form-group">
                <label>标签</label>
                <input type="text" class="form-input" name="tags" value="${this._escapeHtml((datasource?.tags || []).join(', '))}" placeholder="例如：生产, 会员, 核心系统">
                <small class="text-muted">多个标签请用逗号分隔</small>
            </div>
            <div class="form-group">
                <label>备注</label>
                <textarea class="form-input" name="remark" rows="2" placeholder="可选备注信息，如业务背景、特殊配置等">${this._escapeHtml(datasource?.remark || '')}</textarea>
                <small class="text-muted">AI 诊断时会自动附带此备注</small>
            </div>
            <div class="form-group" id="oracle-conn-mode-group" style="display: ${datasource?.db_type === 'oracle' ? 'block' : 'none'};">
                <label>连接模式</label>
                <select class="form-select" name="oracle_conn_mode">
                    <option value="default" ${this._getExtraParam(datasource, 'oracle_conn_mode', 'default') === 'default' ? 'selected' : ''}>默认</option>
                    <option value="sysdba" ${this._getExtraParam(datasource, 'oracle_conn_mode', 'default') === 'sysdba' ? 'selected' : ''}>SYSDBA</option>
                    <option value="sysoper" ${this._getExtraParam(datasource, 'oracle_conn_mode', 'default') === 'sysoper' ? 'selected' : ''}>SYSOPER</option>
                </select>
                <small class="text-muted">以 SYSDBA/SYSOPER 身份连接（需要对应权限）</small>
            </div>
            <div class="form-group">
                <label>关联主机（可选）</label>
                <select class="form-select" name="host_id">
                    <option value="">无</option>
                </select>
            </div>
            <div class="form-group">
                <label>重要性级别</label>
                <select class="form-select" name="importance_level" required>
                    <option value="core" ${datasource?.importance_level === 'core' ? 'selected' : ''}>核心系统</option>
                    <option value="production" ${datasource?.importance_level === 'production' || !datasource ? 'selected' : ''}>生产系统</option>
                    <option value="development" ${datasource?.importance_level === 'development' ? 'selected' : ''}>开发测试</option>
                    <option value="temporary" ${datasource?.importance_level === 'temporary' ? 'selected' : ''}>临时</option>
                </select>
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
                    <label>入站集成</label>
                    <select class="form-select" id="inbound-integration-select">
                        <option value="">加载中...</option>
                    </select>
                    <small class="text-muted">选择 inbound_metric 类型的集成，用于拉取外部监控指标</small>
                </div>
                <div class="form-group">
                    <label id="external-instance-id-label">外部实例 ID</label>
                    <input
                        type="text"
                        class="form-input"
                        name="external_instance_id"
                        id="external-instance-id-input"
                        value="${datasource?.external_instance_id || ''}"
                        placeholder="例如：云厂商或外部监控系统中的实例 ID"
                    >
                    <small class="text-muted" id="external-instance-id-help">外部监控系统中的实例标识。华为云/阿里云 RDS 场景通常必填。</small>
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

            const externalInstanceInput = form.querySelector('#external-instance-id-input');
            if (externalInstanceInput) {
                externalInstanceInput.required = metricSourceSelect.value === 'integration'
                    && externalInstanceInput.dataset.required === 'true';
            }
        });

        this._loadHosts(form.querySelector('[name="host_id"]'), datasource?.host_id);

        // inbound integration dynamic section
        let inboundIntegrations = [];
        (async () => {
            inboundIntegrations = await this._loadInboundIntegrations();
            const select = form.querySelector('#inbound-integration-select');
            if (!select) return;

            const currentId = inboundSource.integration_id ? String(inboundSource.integration_id) : '';
            select.innerHTML = `
                <option value="">请选择</option>
                ${inboundIntegrations.map(item => `
                    <option value="${item.id}" ${String(item.id) === currentId ? 'selected' : ''}>${item.name}</option>
                `).join('')}
            `;

            const updateExternalInstanceField = (integrationId) => {
                const integration = this._getInboundIntegration(inboundIntegrations, integrationId);
                const meta = this._getExternalInstanceFieldMeta(integration);
                const label = form.querySelector('#external-instance-id-label');
                const input = form.querySelector('#external-instance-id-input');
                const help = form.querySelector('#external-instance-id-help');

                if (label) label.textContent = meta.label;
                if (help) help.textContent = meta.help;
                if (input) {
                    input.placeholder = meta.placeholder;
                    input.dataset.required = meta.required ? 'true' : 'false';
                    input.required = metricSourceSelect.value === 'integration' && meta.required;
                }
            };

            const renderParams = (integrationId, existingParams = {}) => {
                const integration = this._getInboundIntegration(inboundIntegrations, integrationId);
                const container = form.querySelector('#inbound-params-container');
                if (!container) return;

                if (!integration || !integration.config_schema || !integration.config_schema.properties) {
                    container.innerHTML = '';
                    return;
                }

                let html = `
                    <div style="font-weight:600;margin-bottom:8px;">采集参数</div>
                    <div class="text-muted" style="margin-bottom:12px;">${this._getInboundParamIntro(integration)}</div>
                `;
                for (const [key, prop] of Object.entries(integration.config_schema.properties)) {
                    if (!this._shouldRenderInboundParam(integration, key)) continue;
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
            updateExternalInstanceField(select.value);

            // change
            select.addEventListener('change', () => {
                renderParams(select.value, {});
                updateExternalInstanceField(select.value);
            });
        })();

        const submitBtn = DOM.el('button', {
            className: 'btn btn-primary',
            textContent: isEdit ? '更新' : '创建',
            type: 'button',
            onClick: () => form.requestSubmit()
        });

        DOM.bindAsyncSubmit(form, async () => {
            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());
            data.port = parseInt(data.port);
            data.tags = this._normalizeTags(data.tags);
            if (!data.password) delete data.password;
            if (!data.host_id) data.host_id = null;
            else data.host_id = parseInt(data.host_id);
            if (!data.database) data.database = null;
            data.external_instance_id = (data.external_instance_id || '').trim() || null;

            const extraParams = {};
            if (data.db_type === 'oracle' && data.oracle_conn_mode && data.oracle_conn_mode !== 'default') {
                extraParams.oracle_conn_mode = data.oracle_conn_mode;
            }
            data.extra_params = Object.keys(extraParams).length > 0 ? extraParams : null;
            delete data.oracle_conn_mode;

            if (data.metric_source === 'system') {
                data.inbound_source = null;
                data.external_instance_id = null;
            } else if (data.metric_source === 'integration') {
                const integrationId = form.querySelector('#inbound-integration-select')?.value;
                if (!integrationId) {
                    Toast.error('使用集成采集时，必须选择入站集成');
                    return;
                }

                const selectedIntegration = this._getInboundIntegration(inboundIntegrations, integrationId);
                if (this._integrationRequiresExternalInstanceId(selectedIntegration) && !data.external_instance_id) {
                    Toast.error('当前集成必须填写外部实例 ID');
                    return;
                }

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
                    params
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
        }, { submitControls: [submitBtn] });

        const footer = DOM.el('div');
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            textContent: '取消',
            type: 'button',
            onClick: () => Modal.hide()
        }));

        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="plug"></i> 测试连接',
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
                            data.extra_params = { oracle_conn_mode: connMode };
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
                    btn.innerHTML = '<i data-lucide="plug"></i> 测试连接';
                    btn.disabled = false;
                    DOM.createIcons();
                }
            }
        }));

        footer.appendChild(submitBtn);

        Modal.show({
            title: isEdit ? '编辑数据源' : '新建数据源',
            content: form,
            footer: footer,
            closeOnOverlayClick: false,
        });
    },

    _getInboundIntegration(integrations, integrationId) {
        return (integrations || []).find(item => String(item.id) === String(integrationId)) || null;
    },

    _integrationRequiresExternalInstanceId(integration) {
        return ['builtin_aliyun_rds', 'builtin_huaweicloud_rds', 'builtin_tencentcloud_rds'].includes(integration?.integration_id);
    },

    _shouldRenderInboundParam(integration, key) {
        if (integration?.integration_id === 'builtin_huaweicloud_rds' && ['access_key_id', 'access_key_secret'].includes(key)) {
            return false;
        }
        if (integration?.integration_id === 'builtin_tencentcloud_rds' && ['secret_id', 'secret_key'].includes(key)) {
            return false;
        }
        return true;
    },

    _getExternalInstanceFieldMeta(integration) {
        if (integration?.integration_id === 'builtin_huaweicloud_rds') {
            return {
                label: '华为云 RDS 实例 ID *',
                placeholder: '例如：8ad0f7d4c0f74f7e9c0f4d8f3b1e2a6din01',
                help: '这里填写华为云 RDS 的实例 ID。region_id 用于定位 CES/IAM 接口；AK/SK 固定从系统参数读取，无需在数据源里填写。',
                required: true,
            };
        }

        if (integration?.integration_id === 'builtin_aliyun_rds') {
            return {
                label: '阿里云 RDS 实例 ID *',
                placeholder: '例如：rm-uf6wjk5xxxxxxx',
                help: '这里填写阿里云 RDS 的实例 ID。AccessKey 可留空并从系统配置读取。',
                required: true,
            };
        }

        if (integration?.integration_id === 'builtin_tencentcloud_rds') {
            return {
                label: '腾讯云实例 ID *',
                placeholder: 'MySQL 示例：cdb-xxx；PostgreSQL/SQL Server 示例：postgres-xxx / mssql-xxx；TDSQL-C 示例：cynosdbmysql-ins-xxx',
                help: '这里填写腾讯云监控维度里的实例标识。MySQL/TDSQL-C 通常使用 InstanceId，PostgreSQL/SQL Server 使用 resourceId；SecretId/SecretKey 固定从系统参数读取，下方只需配置 region_id 等运行参数。',
                required: true,
            };
        }

        return {
            label: '外部实例 ID',
            placeholder: '例如：云厂商或外部监控系统中的实例 ID',
            help: '外部监控系统中的实例标识。是否必填取决于所选入站集成。',
            required: false,
        };
    },

    _getInboundParamIntro(integration) {
        if (integration?.integration_id === 'builtin_huaweicloud_rds') {
            return '以下参数用于调用华为云 CES/IAM API，不是数据库连接信息。区域 ID 仍需填写，因为接口端点不能仅靠实例 ID 自动推断；AK/SK 固定从系统参数读取。';
        }

        if (integration?.integration_id === 'builtin_aliyun_rds') {
            return '以下参数用于调用阿里云 RDS API，不是数据库连接信息。';
        }

        if (integration?.integration_id === 'builtin_tencentcloud_rds') {
            return '以下参数用于调用腾讯云监控 API，不是数据库连接信息。SecretId/SecretKey 固定从系统参数读取，这里只需填写 region_id；推荐使用 ap-guangzhou 这类标准地域，也兼容 gz/1 这类监控文档里的地域简写；MySQL 如需采集只读/代理节点，可额外填写 mysql_instance_type。';
        }

        return '以下参数用于调用外部监控集成，不是数据库连接信息。';
    },

    _getExtraParam(datasource, key, defaultValue) {
        if (!datasource?.extra_params) return defaultValue;
        try {
            const params = typeof datasource.extra_params === 'string'
                ? JSON.parse(datasource.extra_params)
                : datasource.extra_params;
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
            'tdsql-c-mysql': 3306,
            opengauss: 5432,
            hana: 30015
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
