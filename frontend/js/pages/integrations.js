/**
 * Integration 管理页面
 */

class IntegrationsPage {
    constructor() {
        this.integrations = [];
        this.currentIntegration = null;
        this.botBindings = [];
    }

    _displayDescription(integration) {
        if (integration?.integration_id === 'builtin_aliyun_rds') {
            return '从阿里云 RDS API 采集 MySQL、PostgreSQL、SQL Server 指标，AccessKey 从系统配置中读取';
        }
        if (integration?.integration_id === 'builtin_huaweicloud_rds') {
            return '从华为云 CES API 采集 RDS 指标，AK/SK 从系统参数中读取';
        }
        if (integration?.integration_id === 'builtin_tencentcloud_rds') {
            return '从腾讯云可观测平台采集 MySQL、PostgreSQL、SQL Server、TDSQL-C MySQL 指标，SecretId/SecretKey 从系统参数读取';
        }
        return integration?.description || '暂无描述';
    }

    _renderIntegrationHint(integration) {
        if (integration?.integration_id === 'builtin_aliyun_rds') {
            return `
                <div class="integration-modal-note">
                    当前支持阿里云 RDS MySQL、PostgreSQL、SQL Server。
                    测试前请确认数据源已配置 <code>external_instance_id</code>，并且数据库类型与阿里云实例引擎一致。
                </div>
            `;
        }

        if (integration?.integration_id === 'builtin_huaweicloud_rds') {
            return `
                <div class="integration-modal-note">
                    测试前请确认数据源已配置 <code>external_instance_id</code>。
                    其中 <code>region_id</code> 用于定位华为云 CES/IAM 接口端点，不能仅靠实例 ID 自动推断；
                    <code>AK/SK</code> 固定从系统参数读取，测试时无需填写。
                </div>
            `;
        }

        if (integration?.integration_id === 'builtin_tencentcloud_rds') {
            return `
                <div class="integration-modal-note">
                    测试前请确认数据源已配置 <code>external_instance_id</code>，并且实例 ID 与数据库类型匹配：
                    MySQL/TDSQL-C 使用实例 ID，PostgreSQL/SQL Server 通常使用监控维度里的 <code>resourceId</code>。
                    <code>region_id</code> 建议填写标准地域（如 <code>ap-guangzhou</code>），也兼容腾讯云监控文档里的地域缩写/数字 ID（如 <code>gz</code> / <code>1</code>）。
                    <code>SecretId</code>、<code>SecretKey</code> 固定从系统参数读取，无需在测试或数据源参数中填写。
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
                    当前默认使用飞书长连接模式。
                    直接修改代码顶部的 <code>APP_ID</code>、<code>APP_SECRET</code> 即可启用；
                    <code>SIGNING_SECRET</code> 仅在保留公网事件回调模式时才需要。
                </div>
            `
            : integration?.integration_id === 'builtin_dingtalk_bot'
                ? `
                <div class="integration-modal-note">
                    当前默认使用钉钉 Stream Mode 长连接。
                    直接修改代码顶部的 <code>CLIENT_ID</code>、<code>CLIENT_SECRET</code> 即可启用；
                    保存并重启后端后，机器人会自动建立长连接收消息。
                </div>
            `
            : `
                <div class="integration-modal-note integration-editor-note">
                    代码区支持直接粘贴完整 Python 模板。入站指标需要实现 <code>fetch_metrics</code>，出站通知需要实现 <code>send_notification</code>。
                </div>
            `;

        return `
            <form id="${formId}" class="integration-modal-form integration-editor-form">
                <div class="integration-editor-meta">
                    <div class="form-group">
                        <label>名称 *</label>
                        <input type="text" id="integration-name" class="form-input" value="${this.escapeHtml(integration?.name || '')}" required>
                    </div>
                    ${isEdit ? '' : `
                        <div class="form-group">
                            <label>类型 *</label>
                            <select id="integration-type" class="form-select" required>
                                <option value="">请选择</option>
                                <option value="outbound_notification">出站通知</option>
                                <option value="inbound_metric">入站指标</option>
                                <option value="bot">机器人</option>
                            </select>
                        </div>
                    `}
                    <div class="form-group integration-editor-meta-full">
                        <label>描述</label>
                        <textarea id="integration-description" class="form-textarea integration-editor-description">${this.escapeHtml(description)}</textarea>
                    </div>
                    ${isEdit ? '' : `
                        <div class="form-group">
                            <label>分类 *</label>
                            <select id="integration-category" class="form-select" required>
                                <option value="">请选择</option>
                                <option value="webhook">Webhook</option>
                                <option value="email">Email</option>
                                <option value="sms">SMS</option>
                                <option value="im">即时通讯</option>
                                <option value="monitoring">监控系统</option>
                                <option value="custom">自定义</option>
                            </select>
                        </div>
                    `}
                    ${isEdit ? `
                        <div class="form-group integration-editor-toggle">
                            <label class="integration-checkbox-row">
                                <input type="checkbox" id="integration-enabled" ${enabledChecked}>
                                启用此集成
                            </label>
                        </div>
                    ` : ''}
                </div>

                <div class="integration-editor-workspace">
                    <section class="integration-editor-panel">
                        <div class="integration-editor-panel-header">
                            <div>
                                <label>配置 Schema (JSON)</label>
                                <p>定义测试和运行时参数。</p>
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
                                <label>代码 *</label>
                                <p>建议直接在这里维护完整实现，方便查看和编辑。</p>
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
            innerHTML: '<i data-lucide="refresh-cw"></i> 加载内置模板',
            onClick: () => this.loadBuiltinTemplates()
        });

        const createBtn = DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> 创建集成',
            onClick: () => this.showCreateIntegrationModal()
        });

        return [loadBtn, createBtn];
    }

    _typeMeta(type) {
        const map = {
            outbound_notification: {
                label: '出站通知',
                description: '向外部系统发送告警、恢复和执行结果',
            },
            inbound_metric: {
                label: '入站指标',
                description: '从外部平台采集指标并写入监控链路',
            },
            bot: {
                label: '机器人',
                description: '通过 IM 机器人接收消息并触发自动化能力',
            }
        };
        return map[type] || {
            label: type || '未分类',
            description: '自定义集成能力',
        };
    }

    _categoryMeta(category) {
        const map = {
            webhook: { label: 'Webhook', icon: 'link-2' },
            email: { label: '邮件', icon: 'mail' },
            sms: { label: '短信', icon: 'smartphone' },
            im: { label: '即时通讯', icon: 'messages-square' },
            monitoring: { label: '监控', icon: 'activity' },
            custom: { label: '自定义', icon: 'blocks' }
        };
        return map[category] || { label: category || '其他', icon: 'plug-zap' };
    }

    _bindingMeta(binding) {
        const map = {
            weixin_bot: { icon: 'message-circle-more', label: '微信机器人' },
            feishu_bot: { icon: 'send', label: '飞书机器人' },
            dingtalk_bot: { icon: 'message-square-dot', label: '钉钉机器人' }
        };
        return map[binding?.code] || { icon: 'bot', label: binding?.name || '机器人' };
    }

    _bindingStatusMeta(status) {
        const map = {
            not_ready: { label: '未配置', className: 'idle' },
            pending: { label: '等待扫码', className: 'warning' },
            configured: { label: '已配置', className: 'warning' },
            confirmed: { label: '运行中', className: 'success' },
            error: { label: '失败', className: 'danger' }
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
            ? { label: '已启用', className: 'success' }
            : { label: '已禁用', className: 'muted' };
    }

    async init() {
        this.render();
        await this.loadIntegrations();
        await this.loadBotBindings();
    }

    render() {
        Header.render('外部集成管理', this._buildHeaderActions());

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
            Toast.error('加载集成失败: ' + error.message);
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
                    <h3>暂无集成</h3>
                    <p>点击“加载内置模板”或“创建集成”开始使用</p>
                </div>
            `;
            DOM.createIcons();
            return;
        }

        const groups = {
            outbound_notification: { label: '出站通知', items: [] },
            inbound_metric: { label: '入站指标', items: [] },
            bot: { label: '机器人', items: [] }
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
            ? `<button class="btn btn-sm btn-secondary integration-config-btn" onclick="integrationsPage.showWeixinBotModal()">配置机器人</button>`
            : '';
        const botStatusHtml = botBinding
            ? `
                <div class="integration-binding-meta">
                    <span class="integration-chip">${this.escapeHtml(botBindingMeta.label)} 绑定状态</span>
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
                            <h4>${this.escapeHtml(integration.name)}</h4>
                            ${integration.is_builtin ? '<span class="integration-card-badge">内置</span>' : ''}
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
                        <button class="integration-action-btn" onclick="integrationsPage.viewIntegration(${integration.id})" title="查看详情">
                            <i data-lucide="eye"></i>
                        </button>
                        <button class="integration-action-btn" onclick="integrationsPage.testIntegration(${integration.id})" title="测试">
                            <i data-lucide="flask-conical"></i>
                        </button>
                        ${configureBotButton}
                        ${integration.is_builtin ? `
                            <button class="integration-action-btn" onclick="integrationsPage.editIntegration(${integration.id})" title="编辑">
                                <i data-lucide="pencil"></i>
                            </button>
                        ` : `
                            <button class="integration-action-btn" onclick="integrationsPage.editIntegration(${integration.id})" title="编辑">
                                <i data-lucide="pencil"></i>
                            </button>
                            <button class="integration-action-btn danger" onclick="integrationsPage.deleteIntegration(${integration.id})" title="删除">
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
            title: integration.name,
            content: `
                <div class="integration-modal-stack">
                    <div class="integration-detail-grid">
                        <div class="integration-detail-item">
                            <div class="integration-detail-label">状态</div>
                            <div class="integration-detail-value">
                                <span class="integration-status-chip ${statusMeta.className}">${statusMeta.label}</span>
                            </div>
                        </div>
                        <div class="integration-detail-item">
                            <div class="integration-detail-label">类型</div>
                            <div class="integration-detail-value">${typeMeta.label}</div>
                        </div>
                        <div class="integration-detail-item">
                            <div class="integration-detail-label">分类</div>
                            <div class="integration-detail-value">${categoryMeta.label}</div>
                        </div>
                        <div class="integration-detail-item">
                            <div class="integration-detail-label">描述</div>
                            <div class="integration-detail-value">${this.escapeHtml(this._displayDescription(integration))}</div>
                        </div>
                    </div>
                    <div class="integration-detail-block">
                        <div class="integration-detail-label">配置 Schema</div>
                        <pre class="integration-code-block"><code>${this.escapeHtml(JSON.stringify(integration.config_schema || {}, null, 2))}</code></pre>
                    </div>
                    <div class="integration-detail-block">
                        <div class="integration-detail-label">代码</div>
                        <pre class="integration-code-block integration-code-block-lg"><code>${this.escapeHtml(integration.code)}</code></pre>
                    </div>
                </div>
            `,
            buttons: [
                { text: '关闭', variant: 'secondary', onClick: () => Modal.hide() }
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
                        <label>测试数据源</label>
                        <select id="test-datasource-id" class="form-select">
                            <option value="">请选择</option>
                            ${datasources.map(ds => `
                                <option value="${ds.id}">${this.escapeHtml(ds.name)} (${this.escapeHtml(ds.db_type)})</option>
                            `).join('')}
                        </select>
                    </div>
                `;
            } catch (error) {
                datasourcesHtml = `
                    <div class="integration-modal-note danger">
                        加载数据源失败: ${this.escapeHtml(error.message)}
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
                        <label>${this.escapeHtml(prop.title || key)} ${required ? '*' : ''}</label>
                        <input type="${prop.format === 'password' ? 'password' : 'text'}" class="form-input" id="test-param-${key}" value="${this.escapeHtml(String(defaultValue))}" placeholder="${this.escapeHtml(prop.description || '')}" ${required}>
                    </div>
                `;
            }
        }

        Modal.show({
            title: `测试 ${integration.name}`,
            content: `
                <form id="test-integration-form" class="integration-modal-form">
                    ${this._renderIntegrationHint(integration)}
                    ${datasourcesHtml || ''}
                    ${paramsHtml || '<div class="integration-modal-note">此集成无需额外参数，可以直接执行测试。</div>'}
                </form>
                <div id="test-result" class="integration-test-result">
                    <h3 class="integration-test-result-title">测试结果</h3>
                    <pre id="test-result-content" class="integration-code-block"></pre>
                </div>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '执行测试', variant: 'primary', onClick: () => this.executeTest(id) }
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
            if (response.success) Toast.success('测试成功');
            else Toast.error('测试失败: ' + response.message);
        } catch (error) {
            Toast.error('测试失败: ' + error.message);
        }
    }


    async deleteIntegration(id) {
        if (!confirm('确定要删除这个集成吗？')) return;
        try {
            await API.delete(`/api/integrations/${id}`);
            Toast.success('删除成功');
            await this.loadIntegrations();
        } catch (error) {
            Toast.error('删除失败: ' + error.message);
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
            title: '编辑集成',
            content: this._renderIntegrationEditorForm(integration),
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '保存', variant: 'primary', onClick: () => this.updateIntegration() }
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
            Toast.error('请填写必填项');
            return;
        }

        let configSchema = null;
        if (configSchemaText.trim()) {
            try {
                configSchema = JSON.parse(configSchemaText);
            } catch (error) {
                Toast.error('配置 Schema 格式错误: ' + error.message);
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
            Toast.success('更新成功');
            Modal.hide();
            await this.loadIntegrations();
        } catch (error) {
            Toast.error('更新失败: ' + error.message);
        }
    }

    async loadBuiltinTemplates() {
        try {
            await API.post('/api/integrations/load-builtin');
            Toast.success('内置模板加载成功');
            await this.loadIntegrations();
        } catch (error) {
            Toast.error('加载失败: ' + error.message);
        }
    }

    showCreateIntegrationModal() {
        Modal.show({
            title: '创建集成',
            content: this._renderIntegrationEditorForm(),
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '保存', variant: 'primary', onClick: () => this.saveIntegration() }
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
            Toast.error('请填写必填项');
            return;
        }

        let configSchema = null;
        if (configSchemaText.trim()) {
            try {
                configSchema = JSON.parse(configSchemaText);
            } catch (error) {
                Toast.error('配置 Schema 格式错误: ' + error.message);
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
            Toast.success('创建成功');
            Modal.hide();
            await this.loadIntegrations();
        } catch (error) {
            Toast.error('创建失败: ' + error.message);
        }
    }

    async showWeixinBotModal() {
        try {
            const bindings = await API.getWeixinBotBindings();
            const weixinBinding = bindings.find(b => b.code === 'weixin_bot');
            await this._showWeixinLoginModal(weixinBinding);
        } catch (error) {
            Toast.error('加载微信机器人状态失败: ' + error.message);
        }
    }

    async _showWeixinLoginModal(binding) {
        const statusMap = {
            'not_ready': { label: '未配置', className: 'idle' },
            'pending': { label: '等待扫码', className: 'warning' },
            'confirmed': { label: '已登录', className: 'success' },
            'error': { label: '登录失败', className: 'danger' },
        };
        const rawParams = binding?.params?.raw?.params || binding?.params || {};
        const s = statusMap[rawParams.login_status] || statusMap['not_ready'];
        const isLoggedIn = rawParams.login_status === 'confirmed';

        Modal.show({
            title: '微信机器人配置',
            content: `
                <div class="integration-weixin-panel">
                    <div class="integration-weixin-status-row">
                        <span class="integration-detail-label">登录状态</span>
                        <span class="integration-status-chip ${s.className}">${s.label}</span>
                        ${isLoggedIn ? '<span class="integration-weixin-inline-status">后端轮询服务正在自动接收消息</span>' : ''}
                    </div>
                    ${rawParams.last_error ? `<div class="integration-weixin-error">错误：${this.escapeHtml(rawParams.last_error)}</div>` : ''}
                </div>
                <div id="weixin-login-body">
                    ${isLoggedIn ? this._weixinLoggedInHtml(rawParams) : this._weixinLoginFormHtml(rawParams)}
                </div>
                <div id="weixin-login-status" class="integration-weixin-status-message"></div>
            `,
            buttons: [
                { text: '关闭', variant: 'secondary', onClick: () => Modal.hide() },
                ...(isLoggedIn ? [
                    { text: '退出登录', variant: 'danger', onClick: () => this._weixinLogout(rawParams) }
                ] : [])
            ],
            size: 'medium'
        });
    }

    _weixinLoginFormHtml(binding) {
        return `
            <div class="integration-modal-form">
                <div class="form-group">
                    <label>Step 1. 获取登录二维码</label>
                    <div class="integration-modal-note">点击后将显示微信登录二维码，请用微信扫码确认登录。</div>
                    <button class="btn btn-primary" id="weixin-get-qr-btn" onclick="integrationsPage._getWeixinQrcode()">获取二维码</button>
                </div>
            </div>
            <div id="weixin-qrcode-area" class="integration-qr-panel">
                <div class="integration-qr-frame">
                    <div id="weixin-qrcode-display" class="integration-qr-display"></div>
                    <div id="weixin-qrcode-hint" class="integration-qr-hint"></div>
                </div>
                <div class="integration-qr-actions">
                    <button class="btn btn-secondary" id="weixin-poll-status-btn" onclick="integrationsPage._pollWeixinLoginStatus()">查询扫码状态</button>
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
                <div class="integration-weixin-ready-title">微信机器人已就绪</div>
                <div class="integration-weixin-ready-text">后端轮询服务正在运行，可以直接在微信中向机器人发送消息。</div>
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
            hint.textContent = '请使用微信扫码登录';
            window._weixinQrcode = resp.qrcode;
        } catch (error) {
            Toast.error('获取二维码失败: ' + error.message);
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async _pollWeixinLoginStatus() {
        const qrcode = window._weixinQrcode;
        if (!qrcode) {
            Toast.error('请先获取二维码');
            return;
        }
        const btn = document.getElementById('weixin-poll-status-btn');
        if (btn) btn.disabled = true;
        const statusDiv = document.getElementById('weixin-login-status');

        try {
            statusDiv.innerHTML = '<span class="integration-status-chip warning">查询中...</span>';
            const resp = await API.pollWeixinLoginStatus(qrcode);
            statusDiv.innerHTML = '';

            const statusMap = {
                'pending': { label: '等待扫码...', className: 'warning' },
                'confirmed': { label: '登录成功！', className: 'success' },
                'expired': { label: '二维码已过期，请重新获取', className: 'danger' },
                'error': { label: '扫码失败，请重试', className: 'danger' },
            };
            const s = statusMap[resp.status] || { label: resp.status, className: 'idle' };
            statusDiv.innerHTML = `<span class="integration-status-chip ${s.className}">${this.escapeHtml(s.label)}</span>`;

            if (resp.status === 'confirmed') {
                await new Promise(r => setTimeout(r, 800));
                const bindings = await API.getWeixinBotBindings();
                const weixinBinding = bindings.find(b => b.code === 'weixin_bot');
                await this._showWeixinLoginModal(weixinBinding);
                Toast.success('微信机器人登录成功！');
            }
        } catch (error) {
            statusDiv.innerHTML = `<span class="integration-status-chip danger">查询失败：${this.escapeHtml(error.message)}</span>`;
        } finally {
            if (btn) btn.disabled = false;
        }
    }

    async _weixinLogout(params) {
        if (!confirm('确定要退出微信机器人登录吗？退出后轮询服务将停止接收消息。')) return;
        try {
            await API.updateWeixinBotBinding('weixin_bot', { enabled: false, params: { bot_token: '', login_status: 'not_ready', api_baseurl: '', gateway_url: '' } });
            Toast.success('已退出登录');
            await this.showWeixinBotModal();
        } catch (error) {
            Toast.error('退出失败: ' + error.message);
        }
    }
}

const integrationsPage = new IntegrationsPage();
