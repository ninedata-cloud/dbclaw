/**
 * Integration 管理页面
 */

class IntegrationsPage {
    constructor() {
        this.integrations = [];
        this.currentIntegration = null;
    }

    async init() {
        this.render();
        await this.loadIntegrations();
        await this.loadBotBindings();
    }

    render() {
        Header.render('外部集成管理');

        const content = document.getElementById('page-content');
        content.innerHTML = `
            <div class="integrations-container">
                <div class="integrations-header">
                    <div class="integrations-actions">
                        <button class="btn btn-secondary" onclick="integrationsPage.loadBuiltinTemplates()">
                            加载内置模板
                        </button>
                        <button class="btn btn-primary" onclick="integrationsPage.showCreateIntegrationModal()">
                            创建 Integration
                        </button>
                    </div>
                </div>

                <div id="bot-bindings-summary"></div>

                <div id="integrations-list"></div>
            </div>
        `;
    }

    async loadBotBindings() {
        const container = document.getElementById('bot-bindings-summary');
        if (!container) return;
        try {
            const bindings = await API.getWeixinBotBindings();
            const statusMap = {
                'not_ready': { label: '未配置', color: '#999' },
                'pending': { label: '等待扫码', color: '#f59e0b' },
                'confirmed': { label: '已登录', color: '#10b981' },
                'error': { label: '失败', color: '#ef4444' },
            };
            const rows = bindings.map(b => {
                const rawParams = b.params?.raw?.params || {};
                const loginStatus = rawParams.login_status || 'not_ready';
                const s = statusMap[loginStatus] || statusMap['not_ready'];
                const isWeixin = b.code === 'weixin_bot';
                const configureBtn = isWeixin
                    ? `<button class="btn btn-sm" style="padding: 2px 10px; font-size: 11px;" onclick="integrationsPage.showWeixinBotModal()">配置</button>`
                    : '';
                return `
                    <div style="display: flex; align-items: center; gap: 16px; padding: 8px 12px; background: #fff; border: 1px solid #e5e7eb; border-radius: 6px;">
                        <span style="font-size: 18px;">${b.code === 'weixin_bot' ? '💬' : '🚀'}</span>
                        <div>
                            <div style="font-weight: 600; font-size: 14px;">${b.name}</div>
                            <div style="font-size: 11px; color: ${s.color};">${s.label}</div>
                        </div>
                        ${configureBtn}
                    </div>
                `;
            }).join('');
            if (rows) {
                container.innerHTML = `
                    <div style="margin-bottom: 20px;">
                        <div style="font-size: 13px; font-weight: 600; color: #666; margin-bottom: 10px;">🤖 Bot 绑定状态</div>
                        <div style="display: flex; gap: 12px; flex-wrap: wrap;">
                            ${rows}
                        </div>
                    </div>
                `;
            }
        } catch (error) {
            // Bot bindings not critical; silent fail
        }
    }

    async loadIntegrations() {
        try {
            const response = await API.get('/api/integrations');
            this.integrations = response;
            this.renderIntegrations();
        } catch (error) {
            Toast.error('加载 Integrations 失败: ' + error.message);
        }
    }

    renderIntegrations() {
        const container = document.getElementById('integrations-list');

        if (this.integrations.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📦</div>
                    <h3>暂无 Integration</h3>
                    <p>点击“加载内置模板”或“创建 Integration”开始使用</p>
                </div>
            `;
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
        for (const group of Object.values(groups)) {
            if (group.items.length === 0) continue;
            html += `
                <div class="integration-section">
                    <h3>${group.label}</h3>
                    <div class="integration-grid">
                        ${group.items.map(integration => this.renderIntegrationCard(integration)).join('')}
                    </div>
                </div>
            `;
        }

        container.innerHTML = html;
    }

    renderIntegrationCard(integration) {
        const categoryIcons = {
            webhook: '🔗',
            email: '📧',
            sms: '📱',
            im: '💬',
            monitoring: '📊',
            custom: '⚙️'
        };

        const isWeixinBot = integration.integration_id === 'builtin_weixin_bot';
        const configureBotButton = isWeixinBot
            ? `<button class="btn btn-sm" style="padding: 4px 12px; font-size: 12px;" onclick="integrationsPage.showWeixinBotModal()">配置</button>`
            : '';

        return `
            <div class="integration-card ${integration.is_builtin ? 'builtin' : 'custom'}">
                <div class="card-header">
                    <span class="category-icon">${categoryIcons[integration.category] || '⚙️'}</span>
                    <h4>${integration.name}</h4>
                    ${integration.is_builtin ? '<span class="builtin-badge">内置</span>' : ''}
                </div>
                <p class="description">${integration.description || '无描述'}</p>
                <div style="font-size: 12px; color: #666; margin-bottom: 12px;">
                    类型：${integration.integration_type}
                </div>
                <div class="card-footer">
                    <span class="status ${integration.enabled ? 'enabled' : 'disabled'}">
                        ${integration.enabled ? '已启用' : '已禁用'}
                    </span>
                    <div class="actions">
                        <button class="btn-icon" onclick="integrationsPage.viewIntegration(${integration.id})" title="查看">👁️</button>
                        <button class="btn-icon" onclick="integrationsPage.testIntegration(${integration.id})" title="测试">🧪</button>
                        ${configureBotButton}
                        ${integration.is_builtin ? `
                            <button class="btn-icon" onclick="integrationsPage.editIntegration(${integration.id})" title="编辑">✏️</button>
                        ` : `
                            <button class="btn-icon" onclick="integrationsPage.editIntegration(${integration.id})" title="编辑">✏️</button>
                            <button class="btn-icon" onclick="integrationsPage.deleteIntegration(${integration.id})" title="删除">🗑️</button>
                        `}
                    </div>
                </div>
            </div>
        `;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async viewIntegration(id) {
        const integration = this.integrations.find(i => i.id === id);
        if (!integration) return;

        Modal.show({
            title: integration.name,
            content: `
                <div class="form-group">
                    <label>描述</label>
                    <p>${integration.description || '无描述'}</p>
                </div>
                <div class="form-group">
                    <label>类型</label>
                    <p>${integration.integration_type}</p>
                </div>
                <div class="form-group">
                    <label>分类</label>
                    <p>${integration.category}</p>
                </div>
                <div class="form-group">
                    <label>配置 Schema</label>
                    <pre style="padding: 12px; border-radius: 6px; overflow-x: auto; max-height: 240px;"><code>${this.escapeHtml(JSON.stringify(integration.config_schema || {}, null, 2))}</code></pre>
                </div>
                <div class="form-group">
                    <label>代码</label>
                    <pre style="padding: 12px; border-radius: 6px; overflow-x: auto; max-height: 400px;"><code>${this.escapeHtml(integration.code)}</code></pre>
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
                        <select id="test-datasource-id">
                            <option value="">请选择</option>
                            ${datasources.map(ds => `
                                <option value="${ds.id}">${ds.name} (${ds.db_type})</option>
                            `).join('')}
                        </select>
                    </div>
                `;
            } catch (error) {
                datasourcesHtml = `<div class="form-group"><p style="color: #f56c6c;">加载数据源失败: ${error.message}</p></div>`;
            }
        }

        const schema = integration.config_schema;
        let paramsHtml = '';
        if (schema && schema.properties) {
            for (const [key, prop] of Object.entries(schema.properties)) {
                const required = schema.required?.includes(key) ? 'required' : '';
                paramsHtml += `
                    <div class="form-group">
                        <label>${prop.title || key} ${required ? '*' : ''}</label>
                        <input type="${prop.format === 'password' ? 'password' : 'text'}" id="test-param-${key}" placeholder="${prop.description || ''}" ${required}>
                    </div>
                `;
            }
        }

        Modal.show({
            title: `测试 ${integration.name}`,
            content: `
                <form id="test-integration-form">
                    ${datasourcesHtml}
                    ${paramsHtml || '<p>此 Integration 无需参数</p>'}
                </form>
                <div id="test-result" style="margin-top: 20px; display: none;">
                    <h3 style="font-size: 16px; margin-bottom: 12px;">测试结果</h3>
                    <pre id="test-result-content" style="padding: 12px; border-radius: 6px; overflow-x: auto; max-height: 300px;"></pre>
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
            document.getElementById('test-result').style.display = 'block';
            document.getElementById('test-result-content').textContent = JSON.stringify(response, null, 2);
            if (response.success) Toast.success('测试成功');
            else Toast.error('测试失败: ' + response.message);
        } catch (error) {
            Toast.error('测试失败: ' + error.message);
        }
    }


    async deleteIntegration(id) {
        if (!confirm('确定要删除此 Integration 吗？')) return;
        try {
            await API.delete(`/api/integrations/${id}`);
            Toast.success('删除成功');
            await this.loadIntegrations();
        } catch (error) {
            Toast.error('删除失败: ' + error.message);
        }
    }

    async editIntegration(id) {
        const integration = this.integrations.find(i => i.id === id);
        if (!integration) return;
        this.currentIntegration = integration;

        Modal.show({
            title: '编辑 Integration',
            content: `
                <form id="edit-integration-form">
                    <div class="form-group">
                        <label>名称 *</label>
                        <input type="text" id="integration-name" value="${integration.name}" required>
                    </div>
                    <div class="form-group">
                        <label>描述</label>
                        <textarea id="integration-description">${integration.description || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label>配置 Schema (JSON)</label>
                        <textarea id="integration-config-schema" rows="6">${integration.config_schema ? JSON.stringify(integration.config_schema, null, 2) : ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label>代码 *</label>
                        ${integration.integration_id === 'builtin_feishu_bot' ? `
                            <div class="alert alert-info" style="margin-bottom: 12px; padding: 10px 12px; border-radius: 8px; background: #eff6ff; color: #1e40af; border: 1px solid #bfdbfe;">
                                直接修改代码顶部的 APP_ID、APP_SECRET、SIGNING_SECRET 三个常量即可配置飞书机器人。
                            </div>
                        ` : ''}
                        <textarea id="integration-code" rows="12" required>${integration.code}</textarea>
                    </div>
                    <div class="form-group">
                        <label style="display: flex; align-items: center; gap: 8px;">
                            <input type="checkbox" id="integration-enabled" ${integration.enabled ? 'checked' : ''}>
                            启用此 Integration
                        </label>
                    </div>
                </form>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '保存', variant: 'primary', onClick: () => this.updateIntegration() }
            ],
            size: 'large'
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
            title: '创建 Integration',
            content: `
                <form id="create-integration-form">
                    <div class="form-group">
                        <label>名称 *</label>
                        <input type="text" id="integration-name" required>
                    </div>
                    <div class="form-group">
                        <label>描述</label>
                        <textarea id="integration-description"></textarea>
                    </div>
                    <div class="form-group">
                        <label>类型 *</label>
                        <select id="integration-type" required>
                            <option value="">请选择</option>
                            <option value="outbound_notification">出站通知</option>
                            <option value="inbound_metric">入站指标</option>
                            <option value="bot">机器人</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>分类 *</label>
                        <select id="integration-category" required>
                            <option value="">请选择</option>
                            <option value="webhook">Webhook</option>
                            <option value="email">Email</option>
                            <option value="sms">SMS</option>
                            <option value="im">即时通讯</option>
                            <option value="monitoring">监控系统</option>
                            <option value="custom">自定义</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>配置 Schema (JSON)</label>
                        <textarea id="integration-config-schema" rows="6" placeholder='{"properties": {"url": {"type": "string", "title": "URL"}}, "required": ["url"]}'></textarea>
                    </div>
                    <div class="form-group">
                        <label>代码 *</label>
                        <textarea id="integration-code" rows="12" required placeholder="async def execute(context, params):&#10;    return {'success': True}"></textarea>
                    </div>
                </form>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '保存', variant: 'primary', onClick: () => this.saveIntegration() }
            ],
            size: 'large'
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
            'not_ready': { label: '未配置', color: '#999' },
            'pending': { label: '等待扫码', color: '#f59e0b' },
            'confirmed': { label: '已登录', color: '#10b981' },
            'error': { label: '登录失败', color: '#ef4444' },
        };
        const rawParams = binding?.params?.raw?.params || binding?.params || {};
        const s = statusMap[rawParams.login_status] || statusMap['not_ready'];
        const isLoggedIn = rawParams.login_status === 'confirmed';

        Modal.show({
            title: '微信机器人配置',
            content: `
                <div style="margin-bottom: 16px;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                        <span style="font-weight: 600;">登录状态：</span>
                        <span style="color: ${s.color}; font-weight: 600;">${s.label}</span>
                        ${isLoggedIn ? '<span style="color: #10b981; font-size: 12px;">（后端轮询服务已自动接收消息）</span>' : ''}
                    </div>
                    ${rawParams.last_error ? `<div style="color: #ef4444; font-size: 12px; margin-bottom: 8px;">错误：${rawParams.last_error}</div>` : ''}
                </div>
                <div id="weixin-login-body">
                    ${isLoggedIn ? this._weixinLoggedInHtml(rawParams) : this._weixinLoginFormHtml(rawParams)}
                </div>
                <div id="weixin-login-status" style="margin-top: 12px;"></div>
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
            <div class="form-group">
                <label>Step 1. 获取登录二维码</label>
                <div style="font-size: 12px; color: #666; margin-bottom: 10px;">点击后将显示微信登录二维码，请用微信扫码确认登录</div>
                <button class="btn btn-primary" id="weixin-get-qr-btn" onclick="integrationsPage._getWeixinQrcode()">获取二维码</button>
            </div>
            <div id="weixin-qrcode-area" style="display: none; margin: 16px 0; text-align: center;">
                <div style="background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; display: inline-block;">
                    <div id="weixin-qrcode-display" style="margin-bottom: 8px;"></div>
                    <div id="weixin-qrcode-hint" style="font-size: 12px; color: #666;"></div>
                </div>
                <div style="margin-top: 12px;">
                    <button class="btn btn-secondary" id="weixin-poll-status-btn" onclick="integrationsPage._pollWeixinLoginStatus()">查询扫码状态</button>
                </div>
            </div>
        `;
    }

    _weixinLoggedInHtml(binding) {
        return `
            <div style="padding: 16px; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 8px; text-align: center;">
                <div style="font-size: 32px; margin-bottom: 8px;">🤖</div>
                <div style="font-weight: 600; color: #166534; margin-bottom: 4px;">微信机器人已就绪</div>
                <div style="font-size: 13px; color: #15803d;">后端轮询服务正在运行，可以直接在微信中向机器人发送消息了。</div>
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
                display.innerHTML = `<img src="${resp.qrcode_img_content}" alt="QR Code" style="width: 200px; height: 200px;">`;
            } else {
                display.innerHTML = `<div style="width: 200px; height: 200px; display: flex; align-items: center; justify-content: center; background: #f9fafb; border: 1px solid #e5e7eb; font-size: 12px; color: #666; word-break: break-all; padding: 12px;">${resp.qrcode}</div>`;
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
            statusDiv.innerHTML = '<span style="color: #f59e0b;">查询中...</span>';
            const resp = await API.pollWeixinLoginStatus(qrcode);
            statusDiv.innerHTML = '';

            const statusMap = {
                'pending': { label: '等待扫码...', color: '#f59e0b' },
                'confirmed': { label: '登录成功！', color: '#10b981' },
                'expired': { label: '二维码已过期，请重新获取', color: '#ef4444' },
                'error': { label: '扫码失败，请重试', color: '#ef4444' },
            };
            const s = statusMap[resp.status] || { label: resp.status, color: '#666' };
            statusDiv.innerHTML = `<span style="color: ${s.color}; font-weight: 600;">${s.label}</span>`;

            if (resp.status === 'confirmed') {
                await new Promise(r => setTimeout(r, 800));
                const bindings = await API.getWeixinBotBindings();
                const weixinBinding = bindings.find(b => b.code === 'weixin_bot');
                await this._showWeixinLoginModal(weixinBinding);
                Toast.success('微信机器人登录成功！');
            }
        } catch (error) {
            statusDiv.innerHTML = `<span style="color: #ef4444;">查询失败：${error.message}</span>`;
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