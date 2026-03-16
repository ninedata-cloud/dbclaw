// System Configuration page
const SystemConfigsPage = {
    configs: [],
    filteredConfigs: [],
    editingId: null,

    render() {
        Header.render('系统参数配置', DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> 添加参数',
            onClick: () => this.showAddModal()
        }));

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading">Loading configurations...</div>';
        this.loadConfigs();
    },

    async loadConfigs() {
        const content = DOM.$('#page-content');

        try {
            this.configs = await API.get('/api/system-configs');
            this.filteredConfigs = [...this.configs];

            content.innerHTML = `
                <div class="system-configs-page">
                    <div class="configs-filters">
                        <input type="text" id="search-input" placeholder="搜索参数..." 
                               oninput="SystemConfigsPage.filterConfigs()">
                        <select id="category-filter" onchange="SystemConfigsPage.filterConfigs()">
                            <option value="">所有分类</option>
                            ${this.getCategories().map(cat => `<option value="${cat}">${cat}</option>`).join('')}
                        </select>
                    </div>

                    <div class="configs-table-container">
                        <table class="configs-table">
                            <thead>
                                <tr>
                                    <th>参数名</th>
                                    <th>参数值</th>
                                    <th>类型</th>
                                    <th>分类</th>
                                    <th>描述</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody id="configs-tbody">
                                ${this.renderConfigRows()}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;

            DOM.createIcons();
        } catch (error) {
            console.error('Error loading configurations:', error);
            Toast.error('加载配置失败: ' + error.message);
            content.innerHTML = `
                <div class="error-state">
                    <h3>加载配置失败</h3>
                    <p>${error.message}</p>
                    <button class="btn btn-primary" onclick="SystemConfigsPage.loadConfigs()">重试</button>
                </div>
            `;
        }
    },

    getCategories() {
        const categories = new Set();
        this.configs.forEach(config => {
            if (config.category) categories.add(config.category);
        });
        return Array.from(categories).sort();
    },

    filterConfigs() {
        const searchTerm = DOM.$('#search-input')?.value.toLowerCase() || '';
        const category = DOM.$('#category-filter')?.value || '';

        this.filteredConfigs = this.configs.filter(config => {
            const matchesSearch = !searchTerm || 
                config.key.toLowerCase().includes(searchTerm) ||
                (config.description && config.description.toLowerCase().includes(searchTerm));
            const matchesCategory = !category || config.category === category;
            return matchesSearch && matchesCategory;
        });

        const tbody = DOM.$('#configs-tbody');
        if (tbody) {
            tbody.innerHTML = this.renderConfigRows();
            DOM.createIcons();
        }
    },

    renderConfigRows() {
        if (this.filteredConfigs.length === 0) {
            return '<tr><td colspan="6" class="empty-state">暂无配置参数</td></tr>';
        }

        return this.filteredConfigs.map(config => `
            <tr>
                <td><code>${config.key}</code></td>
                <td class="config-value">${this.formatValue(config.value, config.value_type)}</td>
                <td><span class="badge badge-type">${config.value_type}</span></td>
                <td>${config.category || '-'}</td>
                <td>${config.description || '-'}</td>
                <td class="actions">
                    <button class="btn btn-sm" onclick="SystemConfigsPage.showEditModal(${config.id})" title="编辑">
                        <i data-lucide="edit"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="SystemConfigsPage.deleteConfig(${config.id})" title="删除">
                        <i data-lucide="trash-2"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    },

    formatValue(value, type) {
        if (!value) return '-';
        if (type === 'string' && value.length > 50) {
            return value.substring(0, 50) + '...';
        }
        if (type === 'json') {
            try {
                return JSON.stringify(JSON.parse(value), null, 2).substring(0, 100) + '...';
            } catch {
                return value;
            }
        }
        return value;
    },

    showAddModal() {
        this.editingId = null;
        this.showConfigModal({
            key: '',
            value: '',
            value_type: 'string',
            description: '',
            category: ''
        });
    },

    showEditModal(id) {
        const config = this.configs.find(c => c.id === id);
        if (!config) return;
        this.editingId = id;
        this.showConfigModal(config);
    },

    showConfigModal(config) {
        const isEdit = this.editingId !== null;
        const title = isEdit ? '编辑参数' : '添加参数';

        Modal.show({
            title: title,
            content: `
                <form id="config-form" class="config-form">
                    <div class="form-group">
                        <label for="config-key">参数名 *</label>
                        <input type="text" id="config-key" value="${config.key}" 
                               ${isEdit ? 'readonly' : ''} required>
                    </div>
                    <div class="form-group">
                        <label for="config-value-type">类型 *</label>
                        <select id="config-value-type" onchange="SystemConfigsPage.onTypeChange()" required>
                            <option value="string" ${config.value_type === 'string' ? 'selected' : ''}>字符串</option>
                            <option value="integer" ${config.value_type === 'integer' ? 'selected' : ''}>整数</option>
                            <option value="float" ${config.value_type === 'float' ? 'selected' : ''}>浮点数</option>
                            <option value="boolean" ${config.value_type === 'boolean' ? 'selected' : ''}>布尔值</option>
                            <option value="json" ${config.value_type === 'json' ? 'selected' : ''}>JSON</option>
                        </select>
                    </div>
                    <div class="form-group" id="value-input-container">
                        ${this.renderValueInput(config.value, config.value_type)}
                    </div>
                    <div class="form-group">
                        <label for="config-category">分类</label>
                        <input type="text" id="config-category" value="${config.category || ''}" 
                               placeholder="例如: external_api, system">
                    </div>
                    <div class="form-group">
                        <label for="config-description">描述</label>
                        <textarea id="config-description" rows="3">${config.description || ''}</textarea>
                    </div>
                </form>
            `,
            buttons: [
                {
                    text: '取消',
                    variant: 'secondary',
                    onClick: () => Modal.hide()
                },
                {
                    text: '保存',
                    variant: 'primary',
                    onClick: () => this.saveConfig()
                }
            ]
        });
    },

    renderValueInput(value, type) {
        switch (type) {
            case 'string':
                return `
                    <label for="config-value">参数值 *</label>
                    <input type="text" id="config-value" value="${value || ''}" required>
                `;
            case 'integer':
                return `
                    <label for="config-value">参数值 *</label>
                    <input type="number" id="config-value" value="${value || ''}" step="1" required>
                `;
            case 'float':
                return `
                    <label for="config-value">参数值 *</label>
                    <input type="number" id="config-value" value="${value || ''}" step="0.01" required>
                `;
            case 'boolean':
                const checked = value === 'true' || value === '1' || value === 'yes';
                return `
                    <label>
                        <input type="checkbox" id="config-value" ${checked ? 'checked' : ''}>
                        参数值
                    </label>
                `;
            case 'json':
                return `
                    <label for="config-value">参数值 (JSON) *</label>
                    <textarea id="config-value" rows="6" required>${value || ''}</textarea>
                    <small class="form-hint">请输入有效的 JSON 格式</small>
                `;
            default:
                return `
                    <label for="config-value">参数值 *</label>
                    <input type="text" id="config-value" value="${value || ''}" required>
                `;
        }
    },

    onTypeChange() {
        const type = DOM.$('#config-value-type').value;
        const container = DOM.$('#value-input-container');
        container.innerHTML = this.renderValueInput('', type);
    },

    async saveConfig() {
        const key = DOM.$('#config-key').value.trim();
        const valueType = DOM.$('#config-value-type').value;
        const category = DOM.$('#config-category').value.trim();
        const description = DOM.$('#config-description').value.trim();

        let value;
        if (valueType === 'boolean') {
            value = DOM.$('#config-value').checked ? 'true' : 'false';
        } else {
            value = DOM.$('#config-value').value.trim();
        }

        if (!key || !value) {
            Toast.error('请填写必填字段');
            return;
        }

        // Validate JSON
        if (valueType === 'json') {
            try {
                JSON.parse(value);
            } catch (e) {
                Toast.error('JSON 格式无效');
                return;
            }
        }

        const data = {
            key,
            value,
            value_type: valueType,
            category: category || null,
            description: description || null
        };

        try {
            if (this.editingId) {
                await API.put(`/api/system-configs/${this.editingId}`, data);
                Toast.success('参数更新成功');
            } else {
                await API.post('/api/system-configs', data);
                Toast.success('参数添加成功');
            }
            Modal.hide();
            this.loadConfigs();
        } catch (error) {
            console.error('Error saving config:', error);
            Toast.error('保存失败: ' + error.message);
        }
    },

    async deleteConfig(id) {
        const config = this.configs.find(c => c.id === id);
        if (!config) return;

        if (!confirm(`确定要删除参数 "${config.key}" 吗？`)) {
            return;
        }

        try {
            await API.delete(`/api/system-configs/${id}`);
            Toast.success('参数删除成功');
            this.loadConfigs();
        } catch (error) {
            console.error('Error deleting config:', error);
            Toast.error('删除失败: ' + error.message);
        }
    }
};
