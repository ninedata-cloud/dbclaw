/**
 * Integration 管理页面
 */

class IntegrationsPage {
    constructor() {
        this.integrations = [];
        this.channels = [];
        this.currentTab = 'integrations';
        this.codeEditor = null;
        this.currentIntegration = null;
        this.currentChannel = null;
    }

    async init() {
        this.render();
        await this.loadData();
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

                <div class="integrations-tabs">
                    <button class="integrations-tab active" data-tab="integrations" onclick="integrationsPage.switchTab('integrations')">
                        Integrations
                    </button>
                    <button class="integrations-tab" data-tab="channels" onclick="integrationsPage.switchTab('channels')">
                        Channels
                    </button>
                </div>

                <div id="integrations-tab-content" class="tab-content">
                    <div id="integrations-list"></div>
                </div>

                <div id="channels-tab-content" class="tab-content" style="display: none;">
                    <div class="integrations-header" style="margin-top: 0;">
                        <h2 style="font-size: 18px; margin: 0;">通知渠道</h2>
                        <button class="btn btn-primary" onclick="integrationsPage.showCreateChannelModal()">
                            创建 Channel
                        </button>
                    </div>
                    <div id="channels-list"></div>
                </div>
            </div>
        `;
    }

    switchTab(tab) {
        this.currentTab = tab;

        // 更新 tab 样式
        document.querySelectorAll('.integrations-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === tab);
        });

        // 切换内容
        document.getElementById('integrations-tab-content').style.display = tab === 'integrations' ? 'block' : 'none';
        document.getElementById('channels-tab-content').style.display = tab === 'channels' ? 'block' : 'none';
    }

    async loadData() {
        await this.loadIntegrations();
        await this.loadChannels();
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

    async loadChannels() {
        try {
            const response = await API.get('/api/alert-channels');
            this.channels = response;
            this.renderChannels();
        } catch (error) {
            Toast.error('加载 Channels 失败: ' + error.message);
        }
    }

    renderIntegrations() {
        const container = document.getElementById('integrations-list');

        if (this.integrations.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📦</div>
                    <h3>暂无 Integration</h3>
                    <p>点击"加载内置模板"或"创建 Integration"开始使用</p>
                </div>
            `;
            return;
        }

        // 按类型分组
        const groups = {
            'outbound_notification': { label: '出站通知', items: [] },
            'inbound_metric': { label: '入站指标', items: [] }
        };

        this.integrations.forEach(integration => {
            if (groups[integration.integration_type]) {
                groups[integration.integration_type].items.push(integration);
            }
        });

        let html = '';
        for (const [type, group] of Object.entries(groups)) {
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
            'webhook': '🔗',
            'email': '📧',
            'sms': '📱',
            'im': '💬',
            'monitoring': '📊',
            'custom': '⚙️'
        };

        return `
            <div class="integration-card ${integration.is_builtin ? 'builtin' : 'custom'}">
                <div class="card-header">
                    <span class="category-icon">${categoryIcons[integration.category] || '⚙️'}</span>
                    <h4>${integration.name}</h4>
                    ${integration.is_builtin ? '<span class="builtin-badge">内置</span>' : ''}
                </div>
                <p class="description">${integration.description || '无描述'}</p>
                <div class="card-footer">
                    <span class="status ${integration.enabled ? 'enabled' : 'disabled'}">
                        ${integration.enabled ? '已启用' : '已禁用'}
                    </span>
                    <div class="actions">
                        <button class="btn-icon" onclick="integrationsPage.viewIntegration(${integration.id})" title="查看">
                            👁️
                        </button>
                        <button class="btn-icon" onclick="integrationsPage.testIntegration(${integration.id})" title="测试">
                            🧪
                        </button>
                        ${!integration.is_builtin ? `
                            <button class="btn-icon" onclick="integrationsPage.editIntegration(${integration.id})" title="编辑">
                                ✏️
                            </button>
                            <button class="btn-icon" onclick="integrationsPage.deleteIntegration(${integration.id})" title="删除">
                                🗑️
                            </button>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    renderChannels() {
        const container = document.getElementById('channels-list');

        if (this.channels.length === 0) {
            container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">📢</div>
                    <h3>暂无 Channel</h3>
                    <p>创建 Channel 以配置通知渠道</p>
                </div>
            `;
            return;
        }

        const html = `
            <div class="channel-list">
                ${this.channels.map(channel => this.renderChannelItem(channel)).join('')}
            </div>
        `;

        container.innerHTML = html;
    }

    renderChannelItem(channel) {
        return `
            <div class="channel-item">
                <div class="channel-info">
                    <h4 class="channel-name">${channel.name}</h4>
                    <div class="channel-meta">
                        ${channel.integration_name || 'Unknown Integration'} ·
                        ${channel.enabled ? '已启用' : '已禁用'}
                    </div>
                </div>
                <div class="channel-actions">
                    <button class="btn-icon" onclick="integrationsPage.editChannel(${channel.id})" title="编辑">
                        ✏️
                    </button>
                    <button class="btn-icon" onclick="integrationsPage.deleteChannel(${channel.id})" title="删除">
                        🗑️
                    </button>
                </div>
            </div>
        `;
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
                    <label>代码</label>
                    <pre style="padding: 12px; border-radius: 6px; overflow-x: auto; max-height: 400px;"><code>${this.escapeHtml(integration.code)}</code></pre>
                </div>
            `,
            buttons: [
                { text: '关闭', variant: 'secondary', onClick: () => Modal.hide() }
            ]
        });
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async testIntegration(id) {
        const integration = this.integrations.find(i => i.id === id);
        if (!integration) return;

        // 如果是入站指标类型，需要加载数据源列表
        let datasourcesHtml = '';
        if (integration.integration_type === 'inbound_metric') {
            try {
                const datasources = await API.get('/api/datasources');
                if (datasources && datasources.length > 0) {
                    datasourcesHtml = `
                        <div class="form-group">
                            <label>测试数据源 *</label>
                            <select id="test-datasource-id" required>
                                <option value="">请选择数据源</option>
                                ${datasources.map(ds => `
                                    <option value="${ds.id}">
                                        ${ds.name} (${ds.db_type})
                                        ${ds.external_instance_id ? ' - ' + ds.external_instance_id : ''}
                                    </option>
                                `).join('')}
                            </select>
                            <small style="color: #666; display: block; margin-top: 4px;">
                                提示：请选择已配置 external_instance_id 的数据源
                            </small>
                        </div>
                    `;
                } else {
                    datasourcesHtml = `
                        <div class="form-group">
                            <p style="color: #f56c6c;">没有可用的数据源，请先创建数据源</p>
                        </div>
                    `;
                }
            } catch (error) {
                console.error('加载数据源失败:', error);
                datasourcesHtml = `
                    <div class="form-group">
                        <p style="color: #f56c6c;">加载数据源失败: ${error.message}</p>
                    </div>
                `;
            }
        }

        // 构建测试参数表单
        const schema = integration.config_schema;
        let paramsHtml = '';

        if (schema && schema.properties) {
            for (const [key, prop] of Object.entries(schema.properties)) {
                const required = schema.required?.includes(key) ? 'required' : '';
                paramsHtml += `
                    <div class="form-group">
                        <label>${prop.title || key} ${required ? '*' : ''}</label>
                        <input type="${prop.format === 'password' ? 'password' : 'text'}"
                               id="test-param-${key}"
                               placeholder="${prop.description || ''}"
                               ${required}>
                    </div>
                `;
            }
        }

        const content = `
            <form id="test-integration-form">
                ${datasourcesHtml}
                ${paramsHtml || '<p>此 Integration 无需参数</p>'}
            </form>
            <div id="test-result" style="margin-top: 20px; display: none;">
                <h3 style="font-size: 16px; margin-bottom: 12px;">测试结果</h3>
                <pre id="test-result-content" style="padding: 12px; border-radius: 6px; overflow-x: auto; max-height: 300px;"></pre>
            </div>
        `;

        Modal.show({
            title: `测试 ${integration.name}`,
            content: content,
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

        // 收集参数
        const params = {};
        const schema = integration.config_schema;

        if (schema && schema.properties) {
            for (const key of Object.keys(schema.properties)) {
                const input = document.getElementById(`test-param-${key}`);
                if (input) {
                    params[key] = input.value;
                }
            }
        }

        // 收集数据源 ID（如果是入站指标类型）
        const testData = { params };
        if (integration.integration_type === 'inbound_metric') {
            const datasourceSelect = document.getElementById('test-datasource-id');
            if (datasourceSelect && datasourceSelect.value) {
                testData.datasource_id = parseInt(datasourceSelect.value);
            }
        }

        try {
            const response = await API.post(`/api/integrations/${id}/test`, testData);

            // 显示结果
            document.getElementById('test-result').style.display = 'block';
            document.getElementById('test-result-content').textContent = JSON.stringify(response, null, 2);

            if (response.success) {
                Toast.success('测试成功');
            } else {
                Toast.error('测试失败: ' + response.message);
            }
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

        const content = `
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
                    <label>类型 *</label>
                    <select id="integration-type" required disabled>
                        <option value="outbound_notification" ${integration.integration_type === 'outbound_notification' ? 'selected' : ''}>出站通知</option>
                        <option value="inbound_metric" ${integration.integration_type === 'inbound_metric' ? 'selected' : ''}>入站指标</option>
                    </select>
                    <small style="color: #6b7280; font-size: 12px;">类型不可修改</small>
                </div>
                <div class="form-group">
                    <label>分类 *</label>
                    <select id="integration-category" required disabled>
                        <option value="webhook" ${integration.category === 'webhook' ? 'selected' : ''}>Webhook</option>
                        <option value="email" ${integration.category === 'email' ? 'selected' : ''}>Email</option>
                        <option value="sms" ${integration.category === 'sms' ? 'selected' : ''}>SMS</option>
                        <option value="im" ${integration.category === 'im' ? 'selected' : ''}>即时通讯</option>
                        <option value="monitoring" ${integration.category === 'monitoring' ? 'selected' : ''}>监控系统</option>
                        <option value="custom" ${integration.category === 'custom' ? 'selected' : ''}>自定义</option>
                    </select>
                    <small style="color: #6b7280; font-size: 12px;">分类不可修改</small>
                </div>
                <div class="form-group">
                    <label>配置 Schema (JSON)</label>
                    <textarea id="integration-config-schema" rows="6" placeholder='{"properties": {"url": {"type": "string", "title": "URL"}}, "required": ["url"]}'>${integration.config_schema ? JSON.stringify(integration.config_schema, null, 2) : ''}</textarea>
                </div>
                <div class="form-group">
                    <label>代码 *</label>
                    <textarea id="integration-code" rows="12" required>${integration.code}</textarea>
                </div>
                <div class="form-group">
                    <label style="display: flex; align-items: center; gap: 8px;">
                        <input type="checkbox" id="integration-enabled" ${integration.enabled ? 'checked' : ''}>
                        启用此 Integration
                    </label>
                </div>
            </form>
        `;

        Modal.show({
            title: '编辑 Integration',
            content: content,
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
        const content = `
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
                    <textarea id="integration-code" rows="12" required placeholder="async def execute(context, params):&#10;    # 实现代码&#10;    return {'success': True}"></textarea>
                </div>
            </form>
        `;

        Modal.show({
            title: '创建 Integration',
            content: content,
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

        // 生成 integration_id：使用名称的拼音或英文，转小写并替换空格为下划线
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

    showCreateChannelModal() {
        // 获取可用的 Integration
        const notificationIntegrations = this.integrations.filter(
            i => i.integration_type === 'outbound_notification' && i.enabled
        );

        if (notificationIntegrations.length === 0) {
            Toast.error('没有可用的通知 Integration');
            return;
        }

        const content = `
            <form id="create-channel-form">
                <div class="form-group">
                    <label>名称 *</label>
                    <input type="text" id="channel-name" required>
                </div>
                <div class="form-group">
                    <label>描述</label>
                    <textarea id="channel-description"></textarea>
                </div>
                <div class="form-group">
                    <label>Integration *</label>
                    <select id="channel-integration" required onchange="integrationsPage.onIntegrationChange()">
                        <option value="">请选择</option>
                        ${notificationIntegrations.map(i => `
                            <option value="${i.id}">${i.name}</option>
                        `).join('')}
                    </select>
                </div>
                <div id="channel-params-container"></div>
            </form>
        `;

        Modal.show({
            title: '创建 Channel',
            content: content,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '保存', variant: 'primary', onClick: () => this.saveChannel() }
            ],
            size: 'large'
        });
    }

    onIntegrationChange() {
        const integrationId = document.getElementById('channel-integration').value;
        if (!integrationId) {
            document.getElementById('channel-params-container').innerHTML = '';
            return;
        }

        const integration = this.integrations.find(i => i.id === parseInt(integrationId));
        if (!integration || !integration.config_schema) {
            document.getElementById('channel-params-container').innerHTML = '';
            return;
        }

        // 根据 config_schema 生成参数表单
        const schema = integration.config_schema;
        let html = '<h3 style="font-size: 16px; margin: 20px 0 12px 0;">参数配置</h3>';

        for (const [key, prop] of Object.entries(schema.properties)) {
            const required = schema.required?.includes(key) ? 'required' : '';
            html += `
                <div class="form-group">
                    <label>${prop.title || key} ${required ? '*' : ''}</label>
                    <input type="${prop.format === 'password' ? 'password' : 'text'}"
                           id="channel-param-${key}"
                           placeholder="${prop.description || ''}"
                           ${required}>
                </div>
            `;
        }

        document.getElementById('channel-params-container').innerHTML = html;
    }

    async saveChannel() {
        const name = document.getElementById('channel-name').value;
        const description = document.getElementById('channel-description').value;
        const integrationId = document.getElementById('channel-integration').value;

        if (!name || !integrationId) {
            Toast.error('请填写必填项');
            return;
        }

        const integration = this.integrations.find(i => i.id === parseInt(integrationId));
        const params = {};

        if (integration && integration.config_schema) {
            for (const key of Object.keys(integration.config_schema.properties)) {
                const input = document.getElementById(`channel-param-${key}`);
                if (input) {
                    // 敏感参数加密标记
                    const prop = integration.config_schema.properties[key];
                    if (prop.format === 'password' && input.value) {
                        params[key] = 'ENCRYPT:' + input.value;
                    } else {
                        params[key] = input.value;
                    }
                }
            }
        }

        try {
            await API.post('/api/alert-channels', {
                name,
                description,
                integration_id: parseInt(integrationId),
                params,
                enabled: true
            });

            Toast.success('创建成功');
            Modal.hide();
            await this.loadChannels();
        } catch (error) {
            Toast.error('创建失败: ' + error.message);
        }
    }

    async deleteChannel(id) {
        if (!confirm('确定要删除此 Channel 吗？')) return;

        try {
            await API.delete(`/api/alert-channels/${id}`);
            Toast.success('删除成功');
            await this.loadChannels();
        } catch (error) {
            Toast.error('删除失败: ' + error.message);
        }
    }

    async editChannel(id) {
        const channel = this.channels.find(c => c.id === id);
        if (!channel) return;

        this.currentChannel = channel;

        // 获取可用的 Integration
        const notificationIntegrations = this.integrations.filter(
            i => i.integration_type === 'outbound_notification' && i.enabled
        );

        const integration = this.integrations.find(i => i.id === channel.integration_id);
        if (!integration) {
            Toast.error('关联的 Integration 不存在');
            return;
        }

        // 构建参数表单
        let paramsHtml = '';
        if (integration.config_schema && integration.config_schema.properties) {
            for (const [key, prop] of Object.entries(integration.config_schema.properties)) {
                const required = integration.config_schema.required?.includes(key) ? 'required' : '';
                const value = channel.params[key] || '';
                paramsHtml += `
                    <div class="form-group">
                        <label>${prop.title || key} ${required ? '*' : ''}</label>
                        <input type="${prop.format === 'password' ? 'password' : 'text'}"
                               id="channel-param-${key}"
                               value="${prop.format === 'password' ? '' : value}"
                               placeholder="${prop.description || ''}"
                               ${required}>
                    </div>
                `;
            }
        }

        const content = `
            <form id="edit-channel-form">
                <div class="form-group">
                    <label>名称 *</label>
                    <input type="text" id="channel-name" value="${channel.name}" required>
                </div>
                <div class="form-group">
                    <label>描述</label>
                    <textarea id="channel-description">${channel.description || ''}</textarea>
                </div>
                <div class="form-group">
                    <label>Integration *</label>
                    <select id="channel-integration" required disabled>
                        ${notificationIntegrations.map(i => `
                            <option value="${i.id}" ${i.id === channel.integration_id ? 'selected' : ''}>${i.name}</option>
                        `).join('')}
                    </select>
                </div>
                ${paramsHtml}
            </form>
        `;

        Modal.show({
            title: '编辑 Channel',
            content: content,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '保存', variant: 'primary', onClick: () => this.updateChannel() }
            ],
            size: 'large'
        });
    }

    async updateChannel() {
        const name = document.getElementById('channel-name').value;
        const description = document.getElementById('channel-description').value;

        if (!name) {
            Toast.error('请填写必填项');
            return;
        }

        const integration = this.integrations.find(i => i.id === this.currentChannel.integration_id);
        const params = {};

        if (integration && integration.config_schema) {
            for (const key of Object.keys(integration.config_schema.properties)) {
                const input = document.getElementById(`channel-param-${key}`);
                if (input && input.value) {
                    // 敏感参数加密标记
                    const prop = integration.config_schema.properties[key];
                    if (prop.format === 'password') {
                        params[key] = 'ENCRYPT:' + input.value;
                    } else {
                        params[key] = input.value;
                    }
                } else if (this.currentChannel.params[key]) {
                    // 保留原有值（密码字段未修改时）
                    params[key] = this.currentChannel.params[key];
                }
            }
        }

        try {
            await API.put(`/api/alert-channels/${this.currentChannel.id}`, {
                name,
                description,
                params,
                enabled: this.currentChannel.enabled
            });

            Toast.success('更新成功');
            Modal.hide();
            await this.loadChannels();
        } catch (error) {
            Toast.error('更新失败: ' + error.message);
        }
    }
}

// 全局实例
const integrationsPage = new IntegrationsPage();
