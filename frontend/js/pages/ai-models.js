/* AI Models management page */
const AIModelsPage = {
    models: [],

    async render() {
        Header.render('AI 模型', DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> 新建模型',
            onClick: () => this._showForm(null)
        }));

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            this.models = await API.getAIModels();
            content.innerHTML = '';

            if (this.models.length === 0) {
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="brain"></i>
                        <h3>暂无 AI 模型</h3>
                        <p>请先添加一个模型配置，用于诊断和对话能力测试。</p>
                    </div>
                `;
                DOM.createIcons();
                return;
            }

            const bar = DOM.el('div', { className: 'flex-between mb-16' });
            bar.appendChild(DOM.el('span', { className: 'text-muted text-sm', textContent: `${this.models.length} 个模型已配置` }));
            content.appendChild(bar);

            const grid = DOM.el('div', { className: 'datasource-grid' });
            for (const model of this.models) {
                grid.appendChild(this._createCard(model));
            }
            content.appendChild(grid);
            DOM.createIcons();
        } catch (err) {
            Toast.error('加载模型失败：' + err.message);
        }
    },

    _createCard(model) {
        const card = DOM.el('div', { className: 'datasource-card ai-model-card' });
        card.innerHTML = `
            <div class="datasource-card-header">
                <span class="datasource-card-name">${this._escapeHtml(model.name)}</span>
                <span class="badge ${model.is_default ? 'badge-success' : 'badge-info'}">${model.is_default ? '默认' : this._escapeHtml(this._providerLabel(model.provider))}</span>
            </div>
            <div class="datasource-card-info">
                <span><i data-lucide="cpu"></i> ${this._escapeHtml(model.model_name)}</span>
                <span><i data-lucide="plug-zap"></i> ${this._escapeHtml(this._protocolLabel(model.protocol))}</span>
                <span><i data-lucide="brain-cog"></i> 推理强度：${this._escapeHtml(this._reasoningEffortLabel(model.reasoning_effort))}</span>
                <span><i data-lucide="database"></i> ${model.context_window ? `${String(Number(model.context_window))} tokens` : '未配置上下文上限'}</span>
                <span><i data-lucide="link"></i> ${this._escapeHtml(model.base_url)}</span>
                <span><i data-lucide="key-round"></i> ${this._escapeHtml(model.api_key_masked)}</span>
            </div>
            <div class="datasource-card-actions">
                ${!model.is_default ? '<button class="btn btn-sm btn-secondary default-btn"><i data-lucide="star"></i> 设置为默认</button>' : '<button class="btn btn-sm btn-success" disabled><i data-lucide="check"></i> 默认</button>'}
                <button class="btn btn-sm btn-secondary test-btn"><i data-lucide="message-square"></i> 测试</button>
                <button class="btn btn-sm btn-secondary edit-btn"><i data-lucide="pencil"></i> 编辑</button>
                <button class="btn btn-sm btn-danger delete-btn"><i data-lucide="trash-2"></i></button>
            </div>
        `;

        if (!model.is_default) {
            card.querySelector('.default-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this._setDefault(model.id);
            });
        }
        card.querySelector('.test-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this._showTestDialog(model);
        });
        card.querySelector('.edit-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this._showForm(model);
        });
        card.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this._deleteModel(model);
        });

        return card;
    },

    _showForm(model) {
        const isEdit = !!model;
        const form = DOM.el('form');
        form.innerHTML = `
            <div class="form-group"><label>名称</label><input type="text" class="form-input" name="name" required placeholder="Claude Opus 4.6" value="${this._escapeAttr(model?.name || '')}"></div>
            <div class="form-row">
                <div class="form-group"><label>提供商</label>
                    <select class="form-select" name="provider">
                        <option value="openai" ${model?.provider === 'openai' ? 'selected' : ''}>OpenAI</option>
                        <option value="dashscope" ${model?.provider === 'dashscope' ? 'selected' : ''}>DashScope</option>
                        <option value="anthropic" ${model?.provider === 'anthropic' ? 'selected' : ''}>Anthropic</option>
                        <option value="other" ${model?.provider === 'other' ? 'selected' : ''}>Other</option>
                    </select>
                </div>
                <div class="form-group"><label>协议</label>
                    <select class="form-select" name="protocol">
                        <option value="openai" ${model?.protocol === 'openai' || !model?.protocol ? 'selected' : ''}>OpenAI 协议</option>
                        <option value="anthropic" ${model?.protocol === 'anthropic' ? 'selected' : ''}>Anthropic 原生协议</option>
                    </select>
                </div>
            </div>
            <div class="form-group"><label>模型名称</label><input type="text" class="form-input" name="model_name" required placeholder="claude-opus-4-6" value="${this._escapeAttr(model?.model_name || '')}"></div>
            <div class="form-group"><label>推理强度</label>
                <select class="form-select" name="reasoning_effort">
                    <option value="" ${!model?.reasoning_effort ? 'selected' : ''}>默认</option>
                    <option value="low" ${model?.reasoning_effort === 'low' ? 'selected' : ''}>低</option>
                    <option value="medium" ${model?.reasoning_effort === 'medium' ? 'selected' : ''}>中</option>
                    <option value="high" ${model?.reasoning_effort === 'high' ? 'selected' : ''}>高</option>
                </select>
            </div>
            <div class="form-group"><label>上下文上限（tokens）</label><input type="number" min="1" step="1" class="form-input" name="context_window" placeholder="例如 200000" value="${this._escapeAttr(model?.context_window || '')}"></div>
            <div class="form-group"><label>基础 URL</label><input type="text" class="form-input" name="base_url" required placeholder="https://api.anthropic.com" value="${this._escapeAttr(model?.base_url || '')}"></div>
            <div class="form-group"><label>API 密钥</label><input type="password" class="form-input" name="api_key" ${isEdit ? '' : 'required'} placeholder="${isEdit ? '留空保持不变' : 'sk-ant-...'}"></div>
            <div class="text-muted text-sm">选择 Anthropic 原生协议时，请填写 Anthropic Messages API 对应的 Base URL 与模型名。</div>
        `;

        const providerEl = form.querySelector('[name="provider"]');
        const protocolEl = form.querySelector('[name="protocol"]');
        const baseUrlEl = form.querySelector('[name="base_url"]');
        const modelNameEl = form.querySelector('[name="model_name"]');
        const apiKeyEl = form.querySelector('[name="api_key"]');

        const syncProtocolHints = () => {
            if (providerEl.value === 'anthropic') {
                protocolEl.value = 'anthropic';
                baseUrlEl.placeholder = 'https://api.anthropic.com';
                modelNameEl.placeholder = 'claude-opus-4-6';
                if (!isEdit || !apiKeyEl.placeholder) apiKeyEl.placeholder = isEdit ? '留空保持不变' : 'sk-ant-...';
            } else if (protocolEl.value === 'anthropic') {
                baseUrlEl.placeholder = 'https://api.anthropic.com';
                modelNameEl.placeholder = 'claude-opus-4-6';
                if (!isEdit || !apiKeyEl.placeholder) apiKeyEl.placeholder = isEdit ? '留空保持不变' : 'sk-ant-...';
            } else {
                baseUrlEl.placeholder = 'https://api.openai.com/v1';
                modelNameEl.placeholder = 'gpt-4o';
                if (!isEdit || !apiKeyEl.placeholder) apiKeyEl.placeholder = isEdit ? '留空保持不变' : 'sk-...';
            }
        };

        providerEl.addEventListener('change', syncProtocolHints);
        protocolEl.addEventListener('change', syncProtocolHints);
        syncProtocolHints();

        const submitBtn = DOM.el('button', {
            className: 'btn btn-primary',
            textContent: isEdit ? '保存' : '创建',
            type: 'button',
            onClick: () => form.requestSubmit()
        });

        DOM.bindAsyncSubmit(form, async () => {
            const data = Object.fromEntries(new FormData(form).entries());
            data.context_window = data.context_window ? parseInt(data.context_window, 10) : null;
            data.reasoning_effort = data.reasoning_effort || null;
            try {
                if (isEdit) {
                    if (!data.api_key) delete data.api_key;
                    await API.updateAIModel(model.id, data);
                    Toast.success('模型已更新');
                } else {
                    await API.createAIModel(data);
                    Toast.success('模型已创建');
                }
                Modal.hide();
                this.render();
            } catch (err) {
                Toast.error(err.message);
            }
        }, { submitControls: [submitBtn] });

        const footer = DOM.el('div');
        footer.appendChild(DOM.el('button', { className: 'btn btn-secondary', textContent: '取消', type: 'button', onClick: () => Modal.hide() }));
        footer.appendChild(submitBtn);

        Modal.show({ title: isEdit ? '编辑模型' : '新建 AI 模型', content: form, footer, width: '520px' });
    },

    _showTestDialog(model) {
        const state = {
            model,
            messages: [],
            sending: false,
        };

        const wrapper = DOM.el('div');
        wrapper.innerHTML = `
            <div class="mb-16" style="padding: 12px; border: 1px solid var(--border-color, #2a3441); border-radius: 10px; background: var(--panel-bg, rgba(255,255,255,0.02));">
                <div class="text-sm" style="display: grid; gap: 6px;">
                    <div><strong>模型：</strong>${this._escapeHtml(model.name)}</div>
                    <div><strong>提供商：</strong>${this._escapeHtml(this._providerLabel(model.provider))}</div>
                    <div><strong>协议：</strong>${this._escapeHtml(this._protocolLabel(model.protocol))}</div>
                    <div><strong>模型名：</strong>${this._escapeHtml(model.model_name)}</div>
                    <div><strong>推理强度：</strong>${this._escapeHtml(this._reasoningEffortLabel(model.reasoning_effort))}</div>
                    <div><strong>上下文上限：</strong>${model.context_window ? `${String(Number(model.context_window))} tokens` : '未配置'}</div>
                    <div><strong>基础 URL：</strong>${this._escapeHtml(model.base_url)}</div>
                </div>
            </div>
            <div class="test-chat-messages" style="height: 320px; overflow-y: auto; border: 1px solid var(--border-color, #2a3441); border-radius: 10px; padding: 12px; background: var(--panel-bg, rgba(255,255,255,0.02)); display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px;"></div>
            <div class="form-group" style="margin-bottom: 0;">
                <label>测试消息</label>
                <textarea class="form-input test-chat-input" rows="4" placeholder="例如：你好，请用一句话介绍你自己"></textarea>
            </div>
            <div class="text-muted text-sm" style="margin-top: 8px;">用于快速验证当前已保存模型是否可正常对话。</div>
        `;

        const messagesEl = wrapper.querySelector('.test-chat-messages');
        const inputEl = wrapper.querySelector('.test-chat-input');

        const renderMessages = () => {
            if (state.messages.length === 0) {
                messagesEl.innerHTML = '<div class="text-muted text-sm">请输入一条消息，验证该模型是否可正常回复。</div>';
                return;
            }

            messagesEl.innerHTML = state.messages.map((message) => {
                const isUser = message.role === 'user';
                return `
                    <div style="display: flex; ${isUser ? 'justify-content: flex-end;' : 'justify-content: flex-start;'}">
                        <div style="max-width: 85%; padding: 10px 12px; border-radius: 10px; ${isUser ? 'background: #2563eb; color: #fff;' : 'background: var(--card-bg, #1f2937); border: 1px solid var(--border-color, #374151); color: inherit;'}">
                            <div class="text-xs text-muted" style="margin-bottom: 6px; ${isUser ? 'color: rgba(255,255,255,0.8);' : ''}">${isUser ? '你' : '模型'}</div>
                            <div class="test-chat-message-content">${isUser ? this._escapeHtml(message.content).replace(/\n/g, '<br>') : MarkdownRenderer.render(message.content)}</div>
                        </div>
                    </div>
                `;
            }).join('');
            messagesEl.scrollTop = messagesEl.scrollHeight;
            if (typeof hljs !== 'undefined') {
                messagesEl.querySelectorAll('pre code').forEach((block) => hljs.highlightElement(block));
            }
        };

        const sendBtn = DOM.el('button', {
            className: 'btn btn-primary',
            type: 'button',
            innerHTML: '<i data-lucide="send"></i> 发送',
        });
        const clearBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            type: 'button',
            textContent: '清空对话',
        });
        const closeBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            type: 'button',
            textContent: '关闭',
            onClick: () => Modal.hide(),
        });

        const updateSendButton = () => {
            sendBtn.disabled = state.sending;
            inputEl.disabled = state.sending;
            sendBtn.innerHTML = state.sending
                ? '<div class="spinner"></div> 发送中'
                : '<i data-lucide="send"></i> 发送';
            DOM.createIcons();
        };

        const sendMessage = async () => {
            const content = inputEl.value.trim();
            if (!content || state.sending) return;

            state.messages.push({ role: 'user', content });
            inputEl.value = '';
            state.sending = true;
            renderMessages();
            updateSendButton();

            try {
                const result = await API.testAIModelChat(model.id, {
                    messages: state.messages.map((message) => ({
                        role: message.role,
                        content: message.content,
                    })),
                });
                state.messages.push({ role: 'assistant', content: result.reply });
                renderMessages();
            } catch (err) {
                Toast.error(err.message);
            } finally {
                state.sending = false;
                updateSendButton();
                inputEl.focus();
            }
        };

        sendBtn.addEventListener('click', sendMessage);
        clearBtn.addEventListener('click', () => {
            if (state.sending) return;
            state.messages = [];
            renderMessages();
            inputEl.focus();
        });
        inputEl.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });

        const footer = DOM.el('div');
        footer.appendChild(closeBtn);
        footer.appendChild(clearBtn);
        footer.appendChild(sendBtn);

        Modal.show({ title: `测试模型：${model.name}`, content: wrapper, footer, width: '760px' });
        renderMessages();
        updateSendButton();
        inputEl.focus();
    },

    async _deleteModel(model) {
        if (!confirm(`确定删除模型“${model.name}”吗？此操作不可撤销。`)) return;
        try {
            await API.deleteAIModel(model.id);
            Toast.success('模型已删除');
            this.render();
        } catch (err) {
            Toast.error('删除失败：' + err.message);
        }
    },

    async _setDefault(id) {
        try {
            await API.setDefaultAIModel(id);
            Toast.success('默认模型已更新');
            this.render();
        } catch (err) {
            Toast.error('设置默认模型失败：' + err.message);
        }
    },

    _providerLabel(provider) {
        const labels = {
            openai: 'OpenAI',
            dashscope: 'DashScope',
            anthropic: 'Anthropic',
            other: 'Other',
        };
        return labels[provider] || provider || '未知';
    },

    _protocolLabel(protocol) {
        const labels = {
            openai: 'OpenAI 协议',
            anthropic: 'Anthropic 协议',
        };
        return labels[protocol] || protocol || '未知协议';
    },

    _reasoningEffortLabel(reasoningEffort) {
        const labels = {
            low: '低',
            medium: '中',
            high: '高',
        };
        return labels[reasoningEffort] || '默认';
    },

    _escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },

    _escapeAttr(value) {
        return this._escapeHtml(value);
    },
};
