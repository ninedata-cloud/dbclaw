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
                <label>${I18n.t('datasourceForm.name')}</label>
                <input type="text" class="form-input" name="name" value="${this._escapeHtml(datasource?.name || '')}" required placeholder="${I18n.t('datasourceForm.namePlaceholder')}">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>${I18n.t('datasourceForm.databaseType')}</label>
                    <select class="form-select" name="db_type" required>
                        <option value="mysql" ${datasource?.db_type === 'mysql' ? 'selected' : ''}>MySQL</option>
                        <option value="postgresql" ${datasource?.db_type === 'postgresql' ? 'selected' : ''}>PostgreSQL</option>
                        <option value="oracle" ${datasource?.db_type === 'oracle' ? 'selected' : ''}>Oracle</option>
                        <option value="sqlserver" ${datasource?.db_type === 'sqlserver' ? 'selected' : ''}>SQL Server</option>
                        <option value="tdsql-c-mysql" ${datasource?.db_type === 'tdsql-c-mysql' ? 'selected' : ''}>TDSQL-C MySQL</option>
                        <option value="oceanbase-mysql" ${datasource?.db_type === 'oceanbase-mysql' ? 'selected' : ''}>OceanBase MySQL</option>
                        <option value="opengauss" ${datasource?.db_type === 'opengauss' ? 'selected' : ''}>openGauss</option>
                        <option value="hana" ${datasource?.db_type === 'hana' ? 'selected' : ''}>SAP HANA</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>${I18n.t('datasourceForm.port')}</label>
                    <input type="number" class="form-input" name="port" value="${this._escapeHtml(String(datasource?.port || this._defaultPort('mysql')))}" required>
                </div>
            </div>
            <div class="form-group">
                <label>${I18n.t('datasourceForm.host')}</label>
                <input type="text" class="form-input" name="host" value="${this._escapeHtml(datasource?.host || '')}" required placeholder="127.0.0.1">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>${I18n.t('datasourceForm.username')}</label>
                    <input type="text" class="form-input" name="username" value="${this._escapeHtml(datasource?.username || '')}" placeholder="root">
                </div>
                <div class="form-group">
                    <label>${I18n.t('datasourceForm.password')}</label>
                    <input type="password" class="form-input" name="password" value="" placeholder="${isEdit ? I18n.t('datasourceForm.keepPassword') : ''}">
                </div>
            </div>
            <div class="form-group">
                <label>${I18n.t('datasourceForm.database')}</label>
                <input type="text" class="form-input" name="database" value="${this._escapeHtml(datasource?.database || '')}" placeholder="mydb">
            </div>
            <div class="form-group">
                <label>${I18n.t('datasourceForm.tags')}</label>
                <input type="text" class="form-input" name="tags" value="${this._escapeHtml((datasource?.tags || []).join(', '))}" placeholder="${I18n.t('datasourceForm.tagsPlaceholder')}">
                <small class="text-muted">${I18n.t('datasourceForm.tagsHint')}</small>
            </div>
            <div class="form-group">
                <label>${I18n.t('datasourceForm.remark')}</label>
                <textarea class="form-input" name="remark" rows="2" placeholder="${I18n.t('datasourceForm.remarkPlaceholder')}">${this._escapeHtml(datasource?.remark || '')}</textarea>
                <small class="text-muted">${I18n.t('datasourceForm.remarkHint')}</small>
            </div>
            <div class="form-group" id="oracle-conn-mode-group" style="display: ${datasource?.db_type === 'oracle' ? 'block' : 'none'};">
                <label>${I18n.t('datasourceForm.connectionMode')}</label>
                <select class="form-select" name="oracle_conn_mode">
                    <option value="default" ${this._getExtraParam(datasource, 'oracle_conn_mode', 'default') === 'default' ? 'selected' : ''}>${I18n.t('datasourceForm.defaultMode')}</option>
                    <option value="sysdba" ${this._getExtraParam(datasource, 'oracle_conn_mode', 'default') === 'sysdba' ? 'selected' : ''}>SYSDBA</option>
                    <option value="sysoper" ${this._getExtraParam(datasource, 'oracle_conn_mode', 'default') === 'sysoper' ? 'selected' : ''}>SYSOPER</option>
                </select>
                <small class="text-muted">${I18n.t('datasourceForm.oracleModeHint')}</small>
            </div>
            <div class="form-group">
                <label>${I18n.t('datasourceForm.relatedHost')}</label>
                <select class="form-select" name="host_id">
                    <option value="">${I18n.t('common.none')}</option>
                </select>
            </div>
            <div class="form-group">
                <label>${I18n.t('datasourceForm.monitoringSource')}</label>
                <select class="form-select" name="metric_source" id="metric-source-select" required>
                    <option value="system" ${!datasource || datasource?.metric_source === 'system' ? 'selected' : ''}>${I18n.t('datasourceForm.directCollection')}</option>
                    <option value="integration" ${datasource?.metric_source === 'integration' ? 'selected' : ''}>${I18n.t('datasourceForm.integrationCollection')}</option>
                </select>
                <small class="text-muted">${I18n.t('datasourceForm.monitoringSourceHint')}</small>
            </div>
            <div id="integration-config-section" style="display: ${datasource?.metric_source === 'integration' ? 'block' : 'none'};">
                <div class="form-group">
                    <label>${I18n.t('datasourceForm.inboundIntegration')}</label>
                    <select class="form-select" id="inbound-integration-select">
                        <option value="">${I18n.t('common.loading')}</option>
                    </select>
                    <small class="text-muted">${I18n.t('datasourceForm.inboundIntegrationHint')}</small>
                </div>
                <div class="form-group">
                    <label id="external-instance-id-label">${I18n.t('datasourceForm.externalId')}</label>
                    <input
                        type="text"
                        class="form-input"
                        name="external_instance_id"
                        id="external-instance-id-input"
                        value="${datasource?.external_instance_id || ''}"
                        placeholder="${I18n.t('datasourceForm.externalIdPlaceholder')}"
                    >
                    <small class="text-muted" id="external-instance-id-help">${I18n.t('datasourceForm.initialExternalIdHelp')}</small>
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
                <option value="">${I18n.t('datasourceForm.select')}</option>
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
                    <div style="font-weight:600;margin-bottom:8px;">${I18n.t('datasourceForm.collectionParams')}</div>
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
                            <input type="${type}" class="form-input inbound-param" data-key="${key}" data-format="${prop.format || ''}" value="${value}" placeholder="${this._escapeHtml(prop.description || '')}">
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
            textContent: isEdit ? I18n.t('datasourceForm.update') : I18n.t('datasourceForm.create'),
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
                    Toast.error(I18n.t('datasourceForm.integrationRequired'));
                    return;
                }

                const selectedIntegration = this._getInboundIntegration(inboundIntegrations, integrationId);
                if (this._integrationRequiresExternalInstanceId(selectedIntegration) && !data.external_instance_id) {
                    Toast.error(I18n.t('datasourceForm.externalIdRequired'));
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
                    Toast.success(I18n.t('datasourceForm.updated'));
                } else {
                    await API.createDatasource(data);
                    Toast.success(I18n.t('datasourceForm.created'));
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
            textContent: I18n.t('datasourceForm.cancel'),
            type: 'button',
            onClick: () => Modal.hide()
        }));

        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: `<i data-lucide="plug"></i> ${I18n.t('datasourceForm.testConnection')}`,
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
                    if (result.success) Toast.success(I18n.t('datasourceForm.connectionSuccess', { version: result.version || '' }));
                    else Toast.error(I18n.t('datasourceForm.connectionFailed', { message: result.message }));
                } catch (err) {
                    Toast.error(I18n.t('datasourceForm.testFailed', { message: err.message }));
                } finally {
                    btn.innerHTML = `<i data-lucide="plug"></i> ${I18n.t('datasourceForm.testConnection')}`;
                    btn.disabled = false;
                    DOM.createIcons();
                }
            }
        }));

        footer.appendChild(submitBtn);

        Modal.show({
            title: isEdit ? I18n.t('datasourceForm.editTitle') : I18n.t('datasourceForm.createTitle'),
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
                label: I18n.t('datasourceForm.huaweiId'),
                placeholder: I18n.t('datasourceForm.huaweiIdPlaceholder'),
                help: I18n.t('datasourceForm.huaweiIdHelp'),
                required: true,
            };
        }

        if (integration?.integration_id === 'builtin_aliyun_rds') {
            return {
                label: I18n.t('datasourceForm.aliyunId'),
                placeholder: I18n.t('datasourceForm.aliyunIdPlaceholder'),
                help: I18n.t('datasourceForm.aliyunIdHelp'),
                required: true,
            };
        }

        if (integration?.integration_id === 'builtin_tencentcloud_rds') {
            return {
                label: I18n.t('datasourceForm.tencentId'),
                placeholder: I18n.t('datasourceForm.tencentIdPlaceholder'),
                help: I18n.t('datasourceForm.tencentIdHelp'),
                required: true,
            };
        }

        return {
            label: I18n.t('datasourceForm.externalId'),
            placeholder: I18n.t('datasourceForm.externalIdPlaceholder'),
            help: I18n.t('datasourceForm.externalIdHelp'),
            required: false,
        };
    },

    _getInboundParamIntro(integration) {
        if (integration?.integration_id === 'builtin_huaweicloud_rds') {
            return I18n.t('datasourceForm.huaweiParams');
        }

        if (integration?.integration_id === 'builtin_aliyun_rds') {
            return I18n.t('datasourceForm.aliyunParams');
        }

        if (integration?.integration_id === 'builtin_tencentcloud_rds') {
            return I18n.t('datasourceForm.tencentParams');
        }

        return I18n.t('datasourceForm.genericParams');
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
            'oceanbase-mysql': 2883,
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
