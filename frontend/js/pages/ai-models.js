/* AI Models management page */
const AIModelsPage = {
    models: [],

    async render() {
        Header.render(I18n.t('pageCopy.aiModels.aiModels'), DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: I18n.t('pageCopy.aiModels.newModel'),
            onClick: () => this._showForm(null)
        }));

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            this.models = await API.getAIModels();
            content.innerHTML = '';

            if (this.models.length === 0) {
                content.innerHTML = I18n.t('pageCopy.aiModels.noAiModelsAddAModelConfiguration');
                DOM.createIcons();
                return;
            }

            const bar = DOM.el('div', { className: 'flex-between mb-16' });
            bar.appendChild(DOM.el('span', { className: 'text-muted text-sm', textContent: I18n.t('pageCopy.aiModels.configuredModelCount', { value0: this.models.length }) }));
            content.appendChild(bar);

            const grid = DOM.el('div', { className: 'datasource-grid' });
            for (const model of this.models) {
                grid.appendChild(this._createCard(model));
            }
            content.appendChild(grid);
            DOM.createIcons();
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        }
    },

    _createCard(model) {
        const card = DOM.el('div', { className: 'datasource-card ai-model-card' });
        card.innerHTML = I18n.t('pageCopy.aiModels.modelCard', { value0: this._escapeHtml(model.name), value1: model.is_default ? 'badge-success' : 'badge-info', value2: model.is_default ? I18n.t('pageCopy.aiModels.default') : this._escapeHtml(this._providerLabel(model.provider)), value3: this._escapeHtml(model.model_name), value4: this._escapeHtml(this._protocolLabel(model.protocol)), value5: I18n.t('aiModels.reasoningEffort', { value: this._escapeHtml(this._reasoningEffortLabel(model.reasoning_effort)) }), value6: model.context_window ? `${String(Number(model.context_window))} tokens` : I18n.t('pageCopy.aiModels.contextLimitNotConfigured'), value7: this._escapeHtml(model.base_url), value8: this._escapeHtml(model.api_key_masked), value9: !model.is_default ? I18n.t('pageCopy.aiModels.setAsDefault') : I18n.t('pageCopy.aiModels.default2') });

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
        form.innerHTML = I18n.t('pageCopy.aiModels.nameProviderOpenaiDashscopeAnthropicOtherProtocol', { value0: this._escapeAttr(model?.name || ''), value1: model?.provider === 'openai' ? 'selected' : '', value2: model?.provider === 'dashscope' ? 'selected' : '', value3: model?.provider === 'anthropic' ? 'selected' : '', value4: model?.provider === 'other' ? 'selected' : '', value5: model?.protocol === 'openai' || !model?.protocol ? 'selected' : '', value6: model?.protocol === 'anthropic' ? 'selected' : '', value7: this._escapeAttr(model?.model_name || ''), value8: !model?.reasoning_effort ? 'selected' : '', value9: model?.reasoning_effort === 'low' ? 'selected' : '', value10: model?.reasoning_effort === 'medium' ? 'selected' : '', value11: model?.reasoning_effort === 'high' ? 'selected' : '', value12: I18n.t('placeholders.contextWindow'), value13: this._escapeAttr(model?.context_window || ''), value14: this._escapeAttr(model?.base_url || ''), value15: isEdit ? '' : 'required', value16: isEdit ? I18n.t('placeholders.keepApiKey') : 'sk-ant-...' });

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
                if (!isEdit || !apiKeyEl.placeholder) apiKeyEl.placeholder = isEdit ? I18n.t('placeholders.keepApiKey') : 'sk-ant-...';
            } else if (protocolEl.value === 'anthropic') {
                baseUrlEl.placeholder = 'https://api.anthropic.com';
                modelNameEl.placeholder = 'claude-opus-4-6';
                if (!isEdit || !apiKeyEl.placeholder) apiKeyEl.placeholder = isEdit ? I18n.t('placeholders.keepApiKey') : 'sk-ant-...';
            } else {
                baseUrlEl.placeholder = 'https://api.openai.com/v1';
                modelNameEl.placeholder = 'gpt-4o';
                if (!isEdit || !apiKeyEl.placeholder) apiKeyEl.placeholder = isEdit ? I18n.t('placeholders.keepApiKey') : 'sk-...';
            }
        };

        providerEl.addEventListener('change', syncProtocolHints);
        protocolEl.addEventListener('change', syncProtocolHints);
        syncProtocolHints();

        const submitBtn = DOM.el('button', {
            className: 'btn btn-primary',
            textContent: isEdit ? I18n.t('pageCopy.aiModels.save') : I18n.t('pageCopy.aiModels.create'),
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
                    Toast.success(I18n.t('pageCopy.aiModels.modelUpdated'));
                } else {
                    await API.createAIModel(data);
                    Toast.success(I18n.t('pageCopy.aiModels.modelCreated'));
                }
                Modal.hide();
                this.render();
            } catch (err) {
                Toast.error(err.message);
            }
        }, { submitControls: [submitBtn] });

        const footer = DOM.el('div');
        footer.appendChild(DOM.el('button', { className: 'btn btn-secondary', textContent: I18n.t('pageCopy.aiModels.cancel'), type: 'button', onClick: () => Modal.hide() }));
        footer.appendChild(submitBtn);

        Modal.show({ title: isEdit ? I18n.t('pageCopy.aiModels.editModel') : I18n.t('pageCopy.aiModels.newAiModel'), content: form, footer, width: '520px' });
    },

    _showTestDialog(model) {
        const state = {
            model,
            messages: [],
            sending: false,
        };

        const wrapper = DOM.el('div');
        wrapper.innerHTML = I18n.t('pageCopy.aiModels.modelValueProviderValueAgreementValueModel', { value0: this._escapeHtml(model.name), value1: this._escapeHtml(this._providerLabel(model.provider)), value2: this._escapeHtml(this._protocolLabel(model.protocol)), value3: this._escapeHtml(model.model_name), value4: this._escapeHtml(this._reasoningEffortLabel(model.reasoning_effort)), value5: model.context_window ? `${String(Number(model.context_window))} tokens` : I18n.t('pageCopy.aiModels.notConfigured'), value6: this._escapeHtml(model.base_url), value7: I18n.t('placeholders.modelTestMessage') });

        const messagesEl = wrapper.querySelector('.test-chat-messages');
        const inputEl = wrapper.querySelector('.test-chat-input');

        const renderMessages = () => {
            if (state.messages.length === 0) {
                messagesEl.innerHTML = I18n.t('pageCopy.aiModels.enterAMessageToVerifyThatThe');
                return;
            }

            messagesEl.innerHTML = state.messages.map((message) => {
                const isUser = message.role === 'user';
                return `
                    <div style="display: flex; ${isUser ? 'justify-content: flex-end;' : 'justify-content: flex-start;'}">
                        <div style="max-width: 85%; padding: 10px 12px; border-radius: 10px; ${isUser ? 'background: #2563eb; color: #fff;' : 'background: var(--card-bg, #1f2937); border: 1px solid var(--border-color, #374151); color: inherit;'}">
                            <div class="text-xs text-muted" style="margin-bottom: 6px; ${isUser ? 'color: rgba(255,255,255,0.8);' : ''}">${isUser ? I18n.t('pageCopy.aiModels.currentUserLabel') : I18n.t('pageCopy.aiModels.model')}</div>
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
            innerHTML: I18n.t('pageCopy.aiModels.send'),
        });
        const clearBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            type: 'button',
            textContent: I18n.t('pageCopy.aiModels.clearConversation'),
        });
        const closeBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            type: 'button',
            textContent: I18n.t('pageCopy.aiModels.close'),
            onClick: () => Modal.hide(),
        });

        const updateSendButton = () => {
            sendBtn.disabled = state.sending;
            inputEl.disabled = state.sending;
            sendBtn.innerHTML = state.sending
                ? I18n.t('pageCopy.aiModels.sending')
                : I18n.t('pageCopy.aiModels.send');
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

        Modal.show({ title: I18n.t('pageCopy.aiModels.testModelValue', { value0: model.name }), content: wrapper, footer, width: '760px' });
        renderMessages();
        updateSendButton();
        inputEl.focus();
    },

    async _deleteModel(model) {
        if (!confirm(I18n.t('pageCopy.aiModels.okToDeleteModelValueThisAction', { value0: model.name }))) return;
        try {
            await API.deleteAIModel(model.id);
            Toast.success(I18n.t('pageCopy.aiModels.modelDeleted'));
            this.render();
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        }
    },

    async _setDefault(id) {
        try {
            await API.setDefaultAIModel(id);
            Toast.success(I18n.t('pageCopy.aiModels.defaultModelUpdated'));
            this.render();
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        }
    },

    _providerLabel(provider) {
        const labels = {
            openai: 'OpenAI',
            dashscope: 'DashScope',
            anthropic: 'Anthropic',
            other: 'Other',
        };
        return labels[provider] || provider || I18n.t('pageCopy.aiModels.unknown');
    },

    _protocolLabel(protocol) {
        const labels = {
            openai: I18n.t('pageCopy.aiModels.openaiProtocol'),
            anthropic: I18n.t('pageCopy.aiModels.anthropicProtocol'),
        };
        return labels[protocol] || protocol || I18n.t('pageCopy.aiModels.unknownProtocol');
    },

    _reasoningEffortLabel(reasoningEffort) {
        const labels = {
            low: I18n.t('status.low'),
            medium: I18n.t('status.medium'),
            high: I18n.t('status.high'),
        };
        return labels[reasoningEffort] || I18n.t('pageCopy.aiModels.default');
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
