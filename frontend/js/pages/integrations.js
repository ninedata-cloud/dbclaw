/**
 * Integration 管理页面
 */

class IntegrationsPage {
    constructor() {
        this.integrations = [];
        this.currentIntegration = null;
        this.botBindings = [];
    }

    _t(key, params = {}) {
        return I18n.t(`integrations.${key}`, params);
    }

    _builtinKey(integrationId) {
        return {
            builtin_feishu_webhook: 'feishuWebhook',
            builtin_dingtalk_webhook: 'dingtalkWebhook',
            builtin_email: 'email',
            builtin_generic_webhook: 'genericWebhook',
            builtin_aliyun_rds: 'aliyunRds',
            builtin_huaweicloud_rds: 'huaweiRds',
            builtin_tencentcloud_rds: 'tencentRds',
            builtin_feishu_bot: 'feishuBot',
            builtin_dingtalk_bot: 'dingtalkBot',
            builtin_weixin_bot: 'weixinBot',
        }[integrationId] || null;
    }

    _enterpriseWechatKey(integration) {
        if (!integration) return null;
        // Integration `code` contains executable source, while binding `code`
        // is its stable identifier. Never classify an integration by source text.
        const identifier = String(integration.integration_id || integration.code || '').toLowerCase();
        const name = String(integration.name || '');
        const isEnterpriseWechat = /(?:wecom|wechat[_-]?work|wework|qyweixin|enterprise[_-]?wechat)/.test(identifier)
            || /企业微信|企微/.test(name);
        if (!isEnterpriseWechat) return null;
        return integration.integration_type === 'bot' || /bot|机器人/.test(`${identifier} ${name}`)
            ? 'enterpriseWechatBot'
            : 'enterpriseWechatWebhook';
    }

    _knownIntegrationKey(integration) {
        return this._builtinKey(integration?.integration_id) || this._enterpriseWechatKey(integration);
    }

    _displayName(integration) {
        const knownKey = this._knownIntegrationKey(integration);
        return knownKey ? this._t(`builtinNames.${knownKey}`) : (integration?.name || '');
    }

    _displayDescription(integration) {
        const knownKey = this._knownIntegrationKey(integration);
        return knownKey
            ? this._t(`builtinDescriptions.${knownKey}`)
            : (integration?.description || this._t('noDescription'));
    }

    _schemaPropertyText(integration, key, prop, field) {
        const metadata = {
            builtin_feishu_webhook: {
                webhook_url: { description: 'feishuWebhook' },
                secret: { title: 'secretOptional', description: 'feishuSecret' },
            },
            builtin_dingtalk_webhook: {
                webhook_url: { description: 'dingtalkWebhook' },
                secret: { title: 'secret', description: 'dingtalkSecret' },
            },
            builtin_email: {
                to: { title: 'recipient', description: 'recipientHelp' },
                cc: { title: 'ccOptional', description: 'ccHelp' },
            },
            builtin_generic_webhook: {
                webhook_url: { description: 'targetWebhook' }, method: { title: 'httpMethod' },
                auth_type: { title: 'authMethod' }, auth_token: { title: 'authTokenOptional' },
            },
            builtin_aliyun_rds: { region_id: { title: 'regionId', description: 'aliyunRegion' } },
            builtin_huaweicloud_rds: {
                region_id: { title: 'areaId', description: 'huaweiRegion' },
                project_id: { title: 'projectIdOptional', description: 'projectHelp' },
            },
            builtin_tencentcloud_rds: {
                region_id: { title: 'region', description: 'tencentRegion' },
                mysql_instance_type: { title: 'mysqlInstanceType', description: 'mysqlInstanceHelp' },
            },
        };
        const localeKey = metadata[integration?.integration_id]?.[key]?.[field];
        if (localeKey) return this._t(`schemaFields.${localeKey}`);
        const fallback = field === 'title' ? (prop.title || key) : (prop.description || '');
        return I18n.translateLegacyText(fallback);
    }

    _localizedSchema(integration) {
        const schema = JSON.parse(JSON.stringify(integration?.config_schema || {}));
        for (const [key, prop] of Object.entries(schema.properties || {})) {
            if (prop.title) prop.title = this._schemaPropertyText(integration, key, prop, 'title');
            if (prop.description) prop.description = this._schemaPropertyText(integration, key, prop, 'description');
        }
        return schema;
    }

    _renderIntegrationHint(integration) {
        if (integration?.integration_id === 'builtin_aliyun_rds') {
            return `
                <div class="integration-modal-note">
                    ${this._t('hints.aliyun')}
                </div>
            `;
        }

        if (integration?.integration_id === 'builtin_huaweicloud_rds') {
            return `
                <div class="integration-modal-note">
                    ${this._t('hints.huawei')}
                </div>
            `;
        }

        if (integration?.integration_id === 'builtin_tencentcloud_rds') {
            return `
                <div class="integration-modal-note">
                    ${this._t('hints.tencent')}
                </div>
            `;
        }

        return '';
    }

    _renderIntegrationEditorForm(integration = null) {
        const isEdit = !!integration;
        const formId = isEdit ? 'edit-integration-form' : 'create-integration-form';
        const description = integration?.description || '';
        const configSchema = integration?.config_schema ? JSON.stringify(integration.config_schema, null, 2) : '';
        const codeValue = integration?.code || '';
        const enabledChecked = integration?.enabled !== false ? 'checked' : '';
        const codeNote = integration?.integration_id === 'builtin_feishu_bot'
            ? `
                <div class="integration-modal-note">
                    ${this._t('notes.feishu')}
                </div>
            `
            : integration?.integration_id === 'builtin_dingtalk_bot'
                ? `
                <div class="integration-modal-note">
                    ${this._t('notes.dingtalk')}
                </div>
            `
            : `
                <div class="integration-modal-note integration-editor-note">
                    ${this._t('notes.generic')}
                </div>
            `;

        return `
            <form id="${formId}" class="integration-modal-form integration-editor-form">
                <div class="integration-editor-meta">
                    <div class="form-group">
                        <label>${this._t('name')}</label>
                        <input type="text" id="integration-name" class="form-input" value="${this.escapeHtml(integration?.name || '')}" required>
                    </div>
                    ${isEdit ? '' : `
                        <div class="form-group">
                            <label>${this._t('type')}</label>
                            <select id="integration-type" class="form-select" required>
                                <option value="">${this._t('select')}</option>
                                <option value="outbound_notification">${this._t('typeOutbound')}</option>
                                <option value="inbound_metric">${this._t('typeInbound')}</option>
                                <option value="bot">${this._t('typeBot')}</option>
                            </select>
                        </div>
                    `}
                    <div class="form-group integration-editor-meta-full">
                        <label>${this._t('description')}</label>
                        <textarea id="integration-description" class="form-textarea integration-editor-description">${this.escapeHtml(description)}</textarea>
                    </div>
                    ${isEdit ? '' : `
                        <div class="form-group">
                            <label>${this._t('category')}</label>
                            <select id="integration-category" class="form-select" required>
                                <option value="">${this._t('select')}</option>
                                <option value="webhook">Webhook</option>
                                <option value="email">Email</option>
                                <option value="sms">SMS</option>
                                <option value="im">${this._t('categoryIm')}</option>
                                <option value="monitoring">${this._t('categoryMonitoringSystem')}</option>
                                <option value="custom">${this._t('categoryCustom')}</option>
                            </select>
                        </div>
                    `}
                    ${isEdit ? `
                        <div class="form-group integration-editor-toggle">
                            <label class="integration-checkbox-row">
                                <input type="checkbox" id="integration-enabled" ${enabledChecked}>
                                ${this._t('enable')}
                            </label>
                        </div>
                    ` : ''}
                </div>

                <div class="integration-editor-workspace">
                    <section class="integration-editor-panel">
                        <div class="integration-editor-panel-header">
                            <div>
                                <label>${this._t('schema')}</label>
                                <p>${this._t('schemaHint')}</p>
                            </div>
                        </div>
                        <textarea
                            id="integration-config-schema"
                            class="form-textarea integration-schema-input"
                            rows="10"
                            placeholder='{"properties": {"url": {"type": "string", "title": "URL"}}, "required": ["url"]}'
                        >${this.escapeHtml(configSchema)}</textarea>
                    </section>

                    <section class="integration-editor-panel integration-editor-panel-code">
                        <div class="integration-editor-panel-header">
                            <div>
                                <label>${this._t('code')}</label>
                                <p>${this._t('codeHint')}</p>
                            </div>
                        </div>
                        ${codeNote}
                        <textarea
                            id="integration-code"
                            class="form-textarea integration-code-input"
                            rows="20"
                            required
                            placeholder="async def execute(context, params):&#10;    return {'success': True}"
                        >${this.escapeHtml(codeValue)}</textarea>
                    </section>
                </div>
            </form>
        `;
    }

    _buildHeaderActions() {
        const loadBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: `<i data-lucide="refresh-cw"></i> ${this._t('loadBuiltins')}`,
            onClick: () => this.loadBuiltinTemplates()
        });

        const createBtn = DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: `<i data-lucide="plus"></i> ${this._t('create')}`,
            onClick: () => this.showCreateIntegrationModal()
        });

        return [loadBtn, createBtn];
    }

    _typeMeta(type) {
        const map = {
            outbound_notification: {
                label: this._t('typeOutbound'),
                description: this._t('typeOutboundDesc'),
            },
            inbound_metric: {
                label: this._t('typeInbound'),
                description: this._t('typeInboundDesc'),
            },
            bot: {
                label: this._t('typeBot'),
                description: this._t('typeBotDesc'),
            }
        };
        return map[type] || {
            label: type || this._t('uncategorized'),
            description: this._t('customCapability'),
        };
    }

    _categoryMeta(category) {
        const map = {
            webhook: { label: 'Webhook', icon: 'link-2' },
            email: { label: this._t('categoryEmail'), icon: 'mail' },
            sms: { label: this._t('categorySms'), icon: 'smartphone' },
            im: { label: this._t('categoryIm'), icon: 'messages-square' },
            monitoring: { label: this._t('categoryMonitoring'), icon: 'activity' },
            custom: { label: this._t('categoryCustom'), icon: 'blocks' }
        };
        return map[category] || { label: category || this._t('categoryOther'), icon: 'plug-zap' };
    }

    _bindingMeta(binding) {
        if (this._enterpriseWechatKey({ ...binding, integration_type: 'bot' })) {
            return { icon: 'message-circle-more', label: this._t('enterpriseWechatBot') };
        }
        const map = {
            weixin_bot: { icon: 'message-circle-more', label: this._t('weixinBot') },
            feishu_bot: { icon: 'send', label: this._t('feishuBot') },
            dingtalk_bot: { icon: 'message-square-dot', label: this._t('dingtalkBot') }
        };
        return map[binding?.code] || { icon: 'bot', label: binding?.name || this._t('typeBot') };
    }

    _bindingStatusMeta(status) {
        const map = {
            not_ready: { label: this._t('statusNotReady'), className: 'idle' },
            pending: { label: this._t('statusPending'), className: 'warning' },
            configured: { label: this._t('statusConfigured'), className: 'warning' },
            confirmed: { label: this._t('statusRunning'), className: 'success' },
            error: { label: this._t('statusFailed'), className: 'danger' }
        };
        return map[status] || map.not_ready;
    }

    _resolveBindingStatus(binding) {
        const params = binding?.params || {};
        const loginStatus = params.login_status;
        if (loginStatus) return loginStatus;
        if (params.last_error) return 'error';
        if (binding?.enabled) return 'configured';
        return 'not_ready';
    }

    _integrationStatusMeta(enabled) {
        return enabled
            ? { label: this._t('statusEnabled'), className: 'success' }
            : { label: this._t('statusDisabled'), className: 'muted' };
    }

    async init() {
        this.render();
        await this.loadIntegrations();
        await this.loadBotBindings();
    }

    render() {
        Header.render(this._t('title'), this._buildHeaderActions());

        const content = document.getElementById('page-content');
        content.innerHTML = `
            <div class="integrations-page">
                <div id="integrations-list"></div>
            </div>
        `;
    }

    async loadBotBindings() {
        try {
            this.botBindings = await API.getWeixinBotBindings();
            this.renderIntegrations();
        } catch (error) {
            this.botBindings = [];
            // Bot bindings not critical; silent fail
        }
    }

    async loadIntegrations() {
        try {
            const response = await API.get('/api/integrations');
            this.integrations = response;
            this.renderIntegrations();
        } catch (error) {
            Toast.error(this._t('loadFailed', { message: error.message }));
        }
    }

    renderIntegrations() {
        const container = document.getElementById('integrations-list');

        if (this.integrations.length === 0) {
            container.innerHTML = `
                <div class="integrations-empty-state">
                    <div class="integrations-empty-icon">
                        <i data-lucide="package-search"></i>
                    </div>
                    <h3>${this._t('emptyTitle')}</h3>
                    <p>${this._t('emptyHint')}</p>
                </div>
            `;
            DOM.createIcons();
            return;
        }

        const groups = {
            outbound_notification: { items: [] },
            inbound_metric: { items: [] },
            bot: { items: [] }
        };

        this.integrations.forEach(integration => {
            if (groups[integration.integration_type]) {
                groups[integration.integration_type].items.push(integration);
            }
        });

        let html = '';
        for (const [groupKey, group] of Object.entries(groups)) {
            if (group.items.length === 0) continue;
            const typeMeta = this._typeMeta(groupKey);
            html += `
                <section class="integrations-section-card integration-group">
                    <div class="integration-group-header">
                        <div>
                            <h3>${typeMeta.label}</h3>
                            <p>${typeMeta.description}</p>
                        </div>
                        <span class="integration-count-pill">${group.items.length}</span>
                    </div>
                    <div class="integration-grid">
                        ${group.items.map(integration => this.renderIntegrationCard(integration)).join('')}
                    </div>
                </section>
            `;
        }

        container.innerHTML = html;
        DOM.createIcons();
    }

    renderIntegrationCard(integration) {
        const categoryMeta = this._categoryMeta(integration.category);
        const typeMeta = this._typeMeta(integration.integration_type);
        const statusMeta = this._integrationStatusMeta(integration.enabled);
        const isWeixinBot = integration.integration_id === 'builtin_weixin_bot';
        const botBinding = integration.integration_type === 'bot'
            ? this._getBindingForIntegration(integration)
            : null;
        const botRawParams = botBinding?.params || {};
        const botStatusMeta = botBinding
            ? this._bindingStatusMeta(this._resolveBindingStatus(botBinding))
            : null;
        const botBindingMeta = botBinding ? this._bindingMeta(botBinding) : null;
        const configureBotButton = isWeixinBot
            ? `<button class="btn btn-sm btn-secondary integration-config-btn" onclick="integrationsPage.showWeixinBotModal()">${this._t('configureBot')}</button>`
            : '';
        const botStatusHtml = botBinding
            ? `
                <div class="integration-binding-meta">
                    <span class="integration-chip">${this._t('bindingStatus', { name: this.escapeHtml(botBindingMeta.label) })}</span>
                    <span class="integration-status-chip ${botStatusMeta.className}">${botStatusMeta.label}</span>
                    ${botRawParams.last_error ? `<span class="integration-binding-error">${this.escapeHtml(botRawParams.last_error)}</span>` : ''}
                </div>
            `
            : '';

        return `
            <div class="integration-card ${integration.is_builtin ? 'builtin' : 'custom'}">
                <div class="integration-card-top">
                    <div class="integration-card-main">
                        <div class="integration-card-title-row">
                            <div class="integration-card-icon">
                                <i data-lucide="${categoryMeta.icon}"></i>
                            </div>
                            <h4>${this.escapeHtml(this._displayName(integration))}</h4>
                            ${integration.is_builtin ? `<span class="integration-card-badge">${this._t('builtin')}</span>` : ''}
                        </div>
                        <p class="integration-card-description">${this.escapeHtml(this._displayDescription(integration))}</p>
                    </div>
                </div>
                <div class="integration-card-meta">
                    <span class="integration-chip">${typeMeta.label}</span>
                    <span class="integration-chip">${categoryMeta.label}</span>
                </div>
                ${botStatusHtml}
                <div class="integration-card-footer">
                    <span class="integration-status-chip ${statusMeta.className}">
                        ${statusMeta.label}
                    </span>
                    <div class="integration-card-actions">
                        <button class="integration-action-btn" onclick="integrationsPage.viewIntegration(${integration.id})" title="${this._t('viewDetails')}">
                            <i data-lucide="eye"></i>
                        </button>
                        <button class="integration-action-btn" onclick="integrationsPage.testIntegration(${integration.id})" title="${this._t('test')}">
                            <i data-lucide="flask-conical"></i>
                        </button>
                        ${configureBotButton}
                        ${integration.is_builtin ? `
                            <button class="integration-action-btn" onclick="integrationsPage.editIntegration(${integration.id})" title="${this._t('edit')}">
                                <i data-lucide="pencil"></i>
                            </button>
                        ` : `
                            <button class="integration-action-btn" onclick="integrationsPage.editIntegration(${integration.id})" title="${this._t('edit')}">
                                <i data-lucide="pencil"></i>
                            </button>
                            <button class="integration-action-btn danger" onclick="integrationsPage.deleteIntegration(${integration.id})" title="${this._t('delete')}">
                                <i data-lucide="trash-2"></i>
                            </button>
                        `}
                    </div>
                </div>
            </div>
        `;
    }

    _getBindingForIntegration(integration) {
        if (!integration || integration.integration_type !== 'bot' || !Array.isArray(this.botBindings)) {
            return null;
        }
        const bindingCode = (integration.integration_id || '').replace(/^builtin_/, '');
        return this.botBindings.find(b => b.code === bindingCode) || null;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async viewIntegration(id) {
        const integration = this.integrations.find(i => i.id === id);
        if (!integration) return;
        const typeMeta = this._typeMeta(integration.integration_type);
        const categoryMeta = this._categoryMeta(integration.category);
        const statusMeta = this._integrationStatusMeta(integration.enabled);

        Modal.show({
            title: this._displayName(integration),
            content: `
                <div class="integration-modal-stack">
                    <div class="integration-detail-grid">
                        <div class="integration-detail-item">
                            <div class="integration-detail-label">${this._t('detailStatus')}</div>
                            <div class="integration-detail-value">
                                <span class="integration-status-chip ${statusMeta.className}">${statusMeta.label}</span>
                            </div>
                        </div>
                        <div class="integration-detail-item">
                            <div class="integration-detail-label">${this._t('detailType')}</div>
                            <div class="integration-detail-value">${typeMeta.label}</div>
                        </div>
                        <div class="integration-detail-item">
                            <div class="integration-detail-label">${this._t('detailCategory')}</div>
                            <div class="integration-detail-value">${categoryMeta.label}</div>
                        </div>
                        <div class="integration-detail-item">
                            <div class="integration-detail-label">${this._t('detailDescription')}</div>
                            <div class="integration-detail-value">${this.escapeHtml(this._displayDescription(integration))}</div>
                        </div>
                    </div>
                    <div class="integration-detail-block">
                        <div class="integration-detail-label">${this._t('detailSchema')}</div>
                        <pre class="integration-code-block"><code>${this.escapeHtml(JSON.stringify(this._localizedSchema(integration), null, 2))}</code></pre>
                    </div>
                    <div class="integration-detail-block">
                        <div class="integration-detail-label">${this._t('detailCode')}</div>
                        <pre class="integration-code-block integration-code-block-lg"><code>${this.escapeHtml(integration.code)}</code></pre>
                    </div>
                </div>
            `,
            buttons: [
                { text: this._t('close'), variant: 'secondary', onClick: () => Modal.hide() }
            ]
        });
    }

    async testIntegration(id) {
        const integration = this.integrations.find(i => i.id === id);
        if (!integration) return;

        let datasourcesHtml = '';
        if (integration.integration_type === 'inbound_metric') {
            try {
                const datasources = await API.get('/api/datasources');
                datasourcesHtml = `
                    <div class="form-group">
                        <label>${this._t('testDatasource')}</label>
                        <select id="test-datasource-id" class="form-select">
                            <option value="">${this._t('select')}</option>
                            ${datasources.map(ds => `
                                <option value="${ds.id}">${this.escapeHtml(ds.name)} (${this.escapeHtml(ds.db_type)})</option>
                            `).join('')}
                        </select>
                    </div>
                `;
            } catch (error) {
                datasourcesHtml = `
                    <div class="integration-modal-note danger">
                        ${this._t('loadDatasourceFailed', { message: this.escapeHtml(error.message) })}
                    </div>
                `;
            }
        }

        const schema = integration.config_schema;
        let paramsHtml = '';
        if (schema && schema.properties) {
            for (const [key, prop] of Object.entries(schema.properties)) {
                if (!this._shouldRenderTestParam(integration, key)) continue;
                const required = schema.required?.includes(key) ? 'required' : '';
                const defaultValue = prop.format === 'password' ? '' : (prop.default ?? '');
                paramsHtml += `
                    <div class="form-group">
                        <label>${this.escapeHtml(this._schemaPropertyText(integration, key, prop, 'title'))} ${required ? '*' : ''}</label>
                        <input type="${prop.format === 'password' ? 'password' : 'text'}" class="form-input" id="test-param-${key}" value="${this.escapeHtml(String(defaultValue))}" placeholder="${this.escapeHtml(this._schemaPropertyText(integration, key, prop, 'description'))}" ${required}>
                    </div>
                `;
            }
        }

        Modal.show({
            title: this._t('testTitle', { name: this._displayName(integration) }),
            content: `
                <form id="test-integration-form" class="integration-modal-form">
                    ${this._renderIntegrationHint(integration)}
                    ${datasourcesHtml || ''}
                    ${paramsHtml || `<div class="integration-modal-note">${this._t('noTestParams')}</div>`}
                </form>
                <div id="test-result" class="integration-test-result">
                    <h3 class="integration-test-result-title">${this._t('testResult')}</h3>
                    <pre id="test-result-content" class="integration-code-block"></pre>
                </div>
            `,
            buttons: [
                { text: this._t('cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: this._t('runTest'), variant: 'primary', onClick: () => this.executeTest(id) }
            ],
            size: 'large'
        });
    }

    async executeTest(id) {
        const integration = this.integrations.find(i => i.id === id);
        if (!integration) return;

        const params = {};
        const schema = integration.config_schema;
        if (schema && schema.properties) {
            for (const key of Object.keys(schema.properties)) {
                if (!this._shouldRenderTestParam(integration, key)) continue;
                const input = document.getElementById(`test-param-${key}`);
                if (input) {
                    params[key] = schema.properties[key].format === 'password' && input.value
                        ? `ENCRYPT:${input.value}`
                        : input.value;
                }
            }
        }

        const testData = { params };
        if (integration.integration_type === 'inbound_metric') {
            const datasourceSelect = document.getElementById('test-datasource-id');
            if (datasourceSelect && datasourceSelect.value) {
                testData.datasource_id = parseInt(datasourceSelect.value);
            }
        }

        try {
            const response = await API.post(`/api/integrations/${id}/test`, testData);
            document.getElementById('test-result').classList.add('show');
            document.getElementById('test-result-content').textContent = JSON.stringify(response, null, 2);
            if (response.success) Toast.success(this._t('testSucceeded'));
            else Toast.error(this._t('testFailed', { message: response.message }));
        } catch (error) {
            Toast.error(this._t('testFailed', { message: error.message }));
        }
    }


    async deleteIntegration(id) {
        if (!confirm(this._t('deleteConfirm'))) return;
        try {
            await API.delete(`/api/integrations/${id}`);
            Toast.success(this._t('deleted'));
            await this.loadIntegrations();
        } catch (error) {
            Toast.error(this._t('deleteFailed', { message: error.message }));
        }
    }

    _shouldRenderTestParam(integration, key) {
        if (integration?.integration_id === 'builtin_huaweicloud_rds' && ['access_key_id', 'access_key_secret'].includes(key)) {
            return false;
        }
        if (integration?.integration_id === 'builtin_tencentcloud_rds' && ['secret_id', 'secret_key'].includes(key)) {
            return false;
        }
        return true;
    }

    async editIntegration(id) {
        const integration = this.integrations.find(i => i.id === id);
        if (!integration) return;
        this.currentIntegration = integration;

        Modal.show({
            title: this._t('editTitle'),
            content: this._renderIntegrationEditorForm(integration),
            buttons: [
                { text: this._t('cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: this._t('save'), variant: 'primary', onClick: () => this.updateIntegration() }
            ],
            size: 'xlarge',
            width: 'min(1240px, 94vw)',
            maxHeight: '92vh',
            containerClassName: 'integration-editor-modal',
            bodyClassName: 'integration-editor-modal-body'
        });
    }

    async updateIntegration() {
        const name = document.getElementById('integration-name').value;
        const description = document.getElementById('integration-description').value;
        const configSchemaText = document.getElementById('integration-config-schema').value;
        const code = document.getElementById('integration-code').value;
        const enabled = document.getElementById('integration-enabled').checked;

        if (!name || !code) {
            Toast.error(this._t('required'));
            return;
        }

        let configSchema = null;
        if (configSchemaText.trim()) {
            try {
                configSchema = JSON.parse(configSchemaText);
            } catch (error) {
                Toast.error(this._t('invalidSchema', { message: error.message }));
                return;
            }
        }

        try {
            await API.put(`/api/integrations/${this.currentIntegration.id}`, {
                name,
                description,
                config_schema: configSchema,
                code,
                enabled
            });
            Toast.success(this._t('updated'));
            Modal.hide();
            await this.loadIntegrations();
        } catch (error) {
            Toast.error(this._t('updateFailed', { message: error.message }));
        }
    }

    async loadBuiltinTemplates() {
        try {
            await API.post('/api/integrations/load-builtin');
            Toast.success(this._t('builtinsLoaded'));
            await this.loadIntegrations();
        } catch (error) {
            Toast.error(this._t('builtinLoadFailed', { message: error.message }));
        }
    }

    showCreateIntegrationModal() {
        Modal.show({
            title: this._t('createTitle'),
            content: this._renderIntegrationEditorForm(),
            buttons: [
                { text: this._t('cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: this._t('save'), variant: 'primary', onClick: () => this.saveIntegration() }
            ],
            size: 'xlarge',
            width: 'min(1240px, 94vw)',
            maxHeight: '92vh',
            containerClassName: 'integration-editor-modal',
            bodyClassName: 'integration-editor-modal-body'
        });
    }

    async saveIntegration() {
        const name = document.getElementById('integration-name').value;
        const description = document.getElementById('integration-description').value;
        const integrationType = document.getElementById('integration-type').value;
        const category = document.getElementById('integration-category').value;
        const configSchemaText = document.getElementById('integration-config-schema').value;
        const code = document.getElementById('integration-code').value;

        if (!name || !integrationType || !category || !code) {
            Toast.error(this._t('required'));
            return;
        }

        let configSchema = null;
        if (configSchemaText.trim()) {
            try {
                configSchema = JSON.parse(configSchemaText);
            } catch (error) {
                Toast.error(this._t('invalidSchema', { message: error.message }));
                return;
            }
        }

        const integrationId = name.toLowerCase()
            .replace(/\s+/g, '_')
            .replace(/[^\w\u4e00-\u9fa5]+/g, '_')
            .replace(/^_+|_+$/g, '');

        try {
            await API.post('/api/integrations', {
                integration_id: integrationId,
                name,
                description,
                integration_type: integrationType,
                category,
                config_schema: configSchema,
                code,
                enabled: true
            });
            Toast.success(this._t('created'));
            Modal.hide();
            await this.loadIntegrations();
        } catch (error) {
            Toast.error(this._t('createFailed', { message: error.message }));
        }
    }

    async showWeixinBotModal() {
        try {
            const bindings = await API.getWeixinBotBindings();
            const weixinBinding = bindings.find(b => b.code === 'weixin_bot');
            await this._showWeixinLoginModal(weixinBinding);
        } catch (error) {
            Toast.error(this._t('weixin.loadFailed', { message: error.message }));
        }
    }

    async _showWeixinLoginModal(binding) {
        const statusMap = {
            'not_ready': { label: this._t('statusNotReady'), className: 'idle' },
            'pending': { label: this._t('statusPending'), className: 'warning' },
            'confirmed': { label: this._t('statusLoggedIn'), className: 'success' },
            'error': { label: this._t('statusLoginFailed'), className: 'danger' },
        };
        const rawParams = binding?.params?.raw?.params || binding?.params || {};
        const s = statusMap[rawParams.login_status] || statusMap['not_ready'];
        const isLoggedIn = rawParams.login_status === 'confirmed';

        Modal.show({
            title: this._t('weixin.title'),
            content: `
                <div class="integration-weixin-panel">
                    <div class="integration-weixin-status-row">
                        <span class="integration-detail-label">${this._t('weixin.loginStatus')}</span>
                        <span class="integration-status-chip ${s.className}">${s.label}</span>
                        ${isLoggedIn ? `<span class="integration-weixin-inline-status">${this._t('weixin.polling')}</span>` : ''}
                    </div>
                    ${rawParams.last_error ? `<div class="integration-weixin-error">${this._t('weixin.error', { message: this.escapeHtml(rawParams.last_error) })}</div>` : ''}
                </div>
                <div id="weixin-login-body">
                    ${isLoggedIn ? this._weixinLoggedInHtml(rawParams) : this._weixinLoginFormHtml(rawParams)}
                </div>
                <div id="weixin-login-status" class="integration-weixin-status-message"></div>
            `,
            buttons: [
                { text: this._t('close'), variant: 'secondary', onClick: () => Modal.hide() },
                ...(isLoggedIn ? [
                    { text: this._t('weixin.logout'), variant: 'danger', onClick: () => this._weixinLogout(rawParams) }
                ] : [])
            ],
            size: 'medium'
        });
    }

    _weixinLoginFormHtml(binding) {
        return `
            <div class="integration-modal-form">
                <div class="form-group">
                    <label>${this._t('weixin.step1')}</label>
                    <div class="integration-modal-note">${this._t('weixin.qrHelp')}</div>
                    <button class="btn btn-primary" id="weixin-get-qr-btn" onclick="integrationsPage._getWeixinQrcode()">${this._t('weixin.getQr')}</button>
                </div>
            </div>
            <div id="weixin-qrcode-area" class="integration-qr-panel">
                <div class="integration-qr-frame">
                    <div id="weixin-qrcode-display" class="integration-qr-display"></div>
                    <div id="weixin-qrcode-hint" class="integration-qr-hint"></div>
                </div>
                <div class="integration-qr-actions">
                    <button class="btn btn-secondary" id="weixin-poll-status-btn" onclick="integrationsPage._pollWeixinLoginStatus()">${this._t('weixin.checkStatus')}</button>
                </div>
            </div>
        `;
    }

    _weixinLoggedInHtml(binding) {
        return `
            <div class="integration-weixin-ready">
                <div class="integration-weixin-ready-icon">
                    <i data-lucide="bot"></i>
                </div>
                <div class="integration-weixin-ready-title">${this._t('weixin.ready')}</div>
                <div class="integration-weixin-ready-text">${this._t('weixin.readyHint')}</div>
            </div>
        `;
    }

    async _getWeixinQrcode() {
        const btn = document.getElementById('weixin-get-qr-btn');
        if (btn) btn.disabled = true;

        try {
            const resp = await API.createWeixinLoginQrcode();
            document.getElementById('weixin-qrcode-area').style.display = 'block';
            const display = document.getElementById('weixin-qrcode-display');
            const hint = document.getElementById('weixin-qrcode-hint');

            if (resp.qrcode_img_content) {
                // 使用 JavaScript 动态创建 img 元素，避免 innerHTML 转义问题
                display.innerHTML = '';
                const img = document.createElement('img');
                img.src = resp.qrcode_img_content;
                img.alt = 'QR Code';
                img.onerror = () => {
                    // 图片加载失败时显示文本二维码
                    display.innerHTML = `<div class="integration-qr-placeholder">${this.escapeHtml(resp.qrcode)}</div>`;
                };
                display.appendChild(img);
            } else {
                display.innerHTML = `<div class="integration-qr-placeholder">${this.escapeHtml(resp.qrcode)}</div>`;
            }
            hint.textContent = this._t('weixin.scanHint');
            window._weixinQrcode = resp.qrcode;
        } catch (error) {
            Toast.error(this._t('weixin.qrFailed', { message: error.message }));
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async _pollWeixinLoginStatus() {
        const qrcode = window._weixinQrcode;
        if (!qrcode) {
            Toast.error(this._t('weixin.getQrFirst'));
            return;
        }
        const btn = document.getElementById('weixin-poll-status-btn');
        if (btn) btn.disabled = true;
        const statusDiv = document.getElementById('weixin-login-status');

        try {
            statusDiv.innerHTML = `<span class="integration-status-chip warning">${this._t('weixin.querying')}</span>`;
            const resp = await API.pollWeixinLoginStatus(qrcode);
            statusDiv.innerHTML = '';

            const statusMap = {
                'pending': { label: this._t('weixin.pending'), className: 'warning' },
                'confirmed': { label: this._t('weixin.success'), className: 'success' },
                'expired': { label: this._t('weixin.expired'), className: 'danger' },
                'error': { label: this._t('weixin.scanFailed'), className: 'danger' },
            };
            const s = statusMap[resp.status] || { label: resp.status, className: 'idle' };
            statusDiv.innerHTML = `<span class="integration-status-chip ${s.className}">${this.escapeHtml(s.label)}</span>`;

            if (resp.status === 'confirmed') {
                await new Promise(r => setTimeout(r, 800));
                const bindings = await API.getWeixinBotBindings();
                const weixinBinding = bindings.find(b => b.code === 'weixin_bot');
                await this._showWeixinLoginModal(weixinBinding);
                Toast.success(this._t('weixin.loginSucceeded'));
            }
        } catch (error) {
            statusDiv.innerHTML = `<span class="integration-status-chip danger">${this._t('weixin.queryFailed', { message: this.escapeHtml(error.message) })}</span>`;
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async _weixinLogout(params) {
        if (!confirm(this._t('weixin.logoutConfirm'))) return;
        try {
            await API.updateWeixinBotBinding('weixin_bot', { enabled: false, params: { bot_token: '', login_status: 'not_ready', api_baseurl: '', gateway_url: '' } });
            Toast.success(this._t('weixin.loggedOut'));
            await this.showWeixinBotModal();
        } catch (error) {
            Toast.error(this._t('weixin.logoutFailed', { message: error.message }));
        }
    }
}

const integrationsPage = new IntegrationsPage();
