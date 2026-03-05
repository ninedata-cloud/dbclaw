/* AI Models management page */
const AIModelsPage = {
    models: [],

    async render() {
        Header.render('AI Models', DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> Add Model',
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
                        <h3>No AI Models</h3>
                        <p>Add your first AI model configuration to enable model switching during diagnosis.</p>
                    </div>
                `;
                lucide.createIcons();
                return;
            }

            const bar = DOM.el('div', { className: 'flex-between mb-16' });
            bar.appendChild(DOM.el('span', { className: 'text-muted text-sm', textContent: `${this.models.length} model(s) configured` }));
            content.appendChild(bar);

            const grid = DOM.el('div', { className: 'connection-grid' });
            for (const model of this.models) {
                grid.appendChild(this._createCard(model));
            }
            content.appendChild(grid);
            lucide.createIcons();

        } catch (err) {
            Toast.error('Failed to load models: ' + err.message);
        }
    },

    _createCard(model) {
        const card = DOM.el('div', { className: 'connection-card' });
        card.innerHTML = `
            <div class="connection-card-header">
                <span class="connection-card-name">${model.name}</span>
                <span class="badge ${model.is_default ? 'badge-success' : 'badge-info'}">${model.is_default ? 'Default' : model.provider}</span>
            </div>
            <div class="connection-card-info">
                <span><i data-lucide="cpu"></i> ${model.model_name}</span>
                <span><i data-lucide="link"></i> ${model.base_url}</span>
                <span><i data-lucide="key-round"></i> ${model.api_key_masked}</span>
            </div>
            <div class="connection-card-actions">
                ${!model.is_default ? '<button class="btn btn-sm btn-secondary default-btn"><i data-lucide="star"></i> Set Default</button>' : '<button class="btn btn-sm btn-success" disabled><i data-lucide="check"></i> Default</button>'}
                <button class="btn btn-sm btn-secondary edit-btn"><i data-lucide="pencil"></i> Edit</button>
                <button class="btn btn-sm btn-danger delete-btn"><i data-lucide="trash-2"></i></button>
            </div>
        `;

        if (!model.is_default) {
            card.querySelector('.default-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                this._setDefault(model.id);
            });
        }
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
            <div class="form-group"><label>Name</label><input type="text" class="form-input" name="name" required placeholder="GPT-4o" value="${model?.name || ''}"></div>
            <div class="form-row">
                <div class="form-group"><label>Provider</label>
                    <select class="form-select" name="provider">
                        <option value="openai" ${model?.provider === 'openai' ? 'selected' : ''}>OpenAI</option>
                        <option value="dashscope" ${model?.provider === 'dashscope' ? 'selected' : ''}>DashScope</option>
                        <option value="other" ${model?.provider === 'other' ? 'selected' : ''}>Other</option>
                    </select>
                </div>
                <div class="form-group"><label>Model Name</label><input type="text" class="form-input" name="model_name" required placeholder="gpt-4o" value="${model?.model_name || ''}"></div>
            </div>
            <div class="form-group"><label>Base URL</label><input type="text" class="form-input" name="base_url" required placeholder="https://api.openai.com/v1" value="${model?.base_url || ''}"></div>
            <div class="form-group"><label>API Key</label><input type="password" class="form-input" name="api_key" ${isEdit ? '' : 'required'} placeholder="${isEdit ? 'Leave blank to keep current' : 'sk-...'}"></div>
        `;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(form).entries());
            try {
                if (isEdit) {
                    if (!data.api_key) delete data.api_key;
                    await API.updateAIModel(model.id, data);
                    Toast.success('Model updated');
                } else {
                    await API.createAIModel(data);
                    Toast.success('Model created');
                }
                Modal.hide();
                this.render();
            } catch (err) {
                Toast.error(err.message);
            }
        });

        const footer = DOM.el('div', { style: { display: 'flex', gap: '8px' } });
        footer.appendChild(DOM.el('button', { className: 'btn btn-secondary', textContent: 'Cancel', type: 'button', onClick: () => Modal.hide() }));
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-primary', textContent: isEdit ? 'Save' : 'Create', type: 'button',
            onClick: () => form.requestSubmit()
        }));

        Modal.show({ title: isEdit ? 'Edit Model' : 'New AI Model', content: form, footer, width: '520px' });
    },

    async _deleteModel(model) {
        if (!confirm(`Delete model "${model.name}"? This cannot be undone.`)) return;
        try {
            await API.deleteAIModel(model.id);
            Toast.success('Model deleted');
            this.render();
        } catch (err) {
            Toast.error('Failed to delete: ' + err.message);
        }
    },

    async _setDefault(id) {
        try {
            await API.setDefaultAIModel(id);
            Toast.success('Default model updated');
            this.render();
        } catch (err) {
            Toast.error('Failed to set default: ' + err.message);
        }
    },
};
