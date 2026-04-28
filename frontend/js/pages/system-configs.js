// System Configuration page
const SystemConfigsPage = {
    configs: [],
    filteredConfigs: [],
    editingId: null,
    sortState: {
        key: 'key',
        direction: 'asc'
    },

    render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading">Loading configurations...</div>';
        this.loadConfigs();
    },

    _buildHeaderActions(categories) {
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters' });
        filtersContainer.innerHTML = `
            <input type="text" id="search-input" class="filter-input" placeholder="搜索参数..." style="min-width:180px;">
            <select id="category-filter" class="filter-select">
                <option value="">所有分类</option>
                ${categories.map(cat => `<option value="${cat}">${cat}</option>`).join('')}
            </select>
            <button id="btn-search" class="btn btn-primary">
                <i data-lucide="search"></i> 检索
            </button>
        `;

        const addBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="plus"></i> 添加参数'
        });
        addBtn.addEventListener('click', () => this.showAddModal());

        setTimeout(() => {
            const btnSearch = DOM.$('#btn-search');
            const searchInput = DOM.$('#search-input');
            const categoryFilter = DOM.$('#category-filter');

            if (btnSearch) btnSearch.addEventListener('click', () => this.filterConfigs());
            if (searchInput) searchInput.addEventListener('keypress', e => {
                if (e.key === 'Enter') this.filterConfigs();
            });
            if (categoryFilter) categoryFilter.addEventListener('change', () => this.filterConfigs());
        }, 0);

        return [filtersContainer, addBtn];
    },

    async loadConfigs() {
        const content = DOM.$('#page-content');

        try {
            this.configs = await API.get('/api/system-configs');
            this.filteredConfigs = [...this.configs];
            this.applySort();

            Header.render('系统参数配置', this._buildHeaderActions(this.getCategories()));

            content.innerHTML = `
                <div class="system-configs-page">
                    <div class="configs-table-container">
                        <table class="configs-table">
                            <thead>
                                <tr>
                                    ${this.renderSortableHeader('key', '参数名')}
                                    ${this.renderSortableHeader('value', '参数值')}
                                    ${this.renderSortableHeader('value_type', '类型')}
                                    ${this.renderSortableHeader('category', '分类')}
                                    ${this.renderSortableHeader('description', '描述')}
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
        this.applySort();

        const tbody = DOM.$('#configs-tbody');
        if (tbody) {
            tbody.innerHTML = this.renderConfigRows();
            DOM.createIcons();
        }
    },

    renderSortableHeader(key, label) {
        const isActive = this.sortState.key === key;
        const sortIcon = isActive
            ? (this.sortState.direction === 'asc' ? '↑' : '↓')
            : '↕';
        const sortClass = isActive ? 'active' : '';
        return `
            <th class="sortable-header ${sortClass}" onclick="SystemConfigsPage.toggleSort('${key}')">
                <span>${label}</span>
                <span class="sort-indicator">${sortIcon}</span>
            </th>
        `;
    },

    toggleSort(key) {
        if (this.sortState.key === key) {
            this.sortState.direction = this.sortState.direction === 'asc' ? 'desc' : 'asc';
        } else {
            this.sortState.key = key;
            this.sortState.direction = 'asc';
        }
        this.applySort();
        this.renderTable();
    },

    applySort() {
        const { key, direction } = this.sortState;
        const multiplier = direction === 'asc' ? 1 : -1;

        this.filteredConfigs.sort((a, b) => {
            const left = this._getSortableValue(a, key);
            const right = this._getSortableValue(b, key);
            return left.localeCompare(right, 'zh-Hans-CN', { numeric: true }) * multiplier;
        });
    },

    _getSortableValue(config, key) {
        const value = config[key];
        if (value === null || value === undefined) return '';
        return String(value).toLowerCase();
    },

    renderTable() {
        const table = DOM.$('.configs-table');
        if (!table) return;
        table.innerHTML = `
            <thead>
                <tr>
                    ${this.renderSortableHeader('key', '参数名')}
                    ${this.renderSortableHeader('value', '参数值')}
                    ${this.renderSortableHeader('value_type', '类型')}
                    ${this.renderSortableHeader('category', '分类')}
                    ${this.renderSortableHeader('description', '描述')}
                    <th>操作</th>
                </tr>
            </thead>
            <tbody id="configs-tbody">
                ${this.renderConfigRows()}
            </tbody>
        `;
        DOM.createIcons();
    },

    renderConfigRows() {
        if (this.filteredConfigs.length === 0) {
            return '<tr><td colspan="6" class="empty-state">暂无配置参数</td></tr>';
        }

        return this.filteredConfigs.map(config => `
            <tr>
                <td><code>${config.key}</code></td>
                <td class="config-value">
                    ${config.is_encrypted
                        ? `<span class="encrypted-value-cell" data-raw="${this._escapeAttr(config.value)}">
                               <span class="encrypted-mask"><i data-lucide="lock" style="width:13px;height:13px;vertical-align:middle;margin-right:4px;"></i>${this._maskValue(config.value)}</span>
                               <button class="btn-copy-secret" onclick="SystemConfigsPage.copySecret(this)" title="复制原始值">
                                   <i data-lucide="copy"></i>
                               </button>
                           </span>`
                        : this.formatValue(config.value, config.value_type)
                    }
                </td>
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

    _maskValue(value) {
        if (!value) return '****';
        if (value.length <= 4) return '****';
        return value.slice(0, 2) + '****' + value.slice(-2);
    },

    _escapeAttr(value) {
        if (!value) return '';
        return value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },

    copySecret(btn) {
        const cell = btn.closest('.encrypted-value-cell');
        const raw = cell?.dataset.raw || '';
        navigator.clipboard.writeText(raw).then(() => {
            btn.innerHTML = '<i data-lucide="check"></i>';
            DOM.createIcons();
            setTimeout(() => {
                btn.innerHTML = '<i data-lucide="copy"></i>';
                DOM.createIcons();
            }, 1500);
        });
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
        const isEncrypted = config.is_encrypted || false;

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
                        ${this.renderValueInput(config.value, config.value_type, isEncrypted && isEdit)}
                    </div>
                    <div class="form-group">
                        <label class="checkbox-label">
                            <input type="checkbox" id="config-is-encrypted" ${isEncrypted ? 'checked' : ''}>
                            <i data-lucide="lock" style="width:14px;height:14px;"></i>
                            加密存储（适用于 API Key、密码等敏感信息）
                        </label>
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

    renderValueInput(value, type, isEncryptedEdit = false) {
        const placeholder = isEncryptedEdit ? '留空则保持原值不变' : '';
        switch (type) {
            case 'string':
                return `
                    <label for="config-value">参数值 *</label>
                    <input type="text" id="config-value" value="${isEncryptedEdit ? '' : (value || '')}" placeholder="${placeholder}" ${isEncryptedEdit ? '' : 'required'}>
                `;
            case 'integer':
                return `
                    <label for="config-value">参数值 *</label>
                    <input type="number" id="config-value" value="${isEncryptedEdit ? '' : (value || '')}" step="1" placeholder="${placeholder}" ${isEncryptedEdit ? '' : 'required'}>
                `;
            case 'float':
                return `
                    <label for="config-value">参数值 *</label>
                    <input type="number" id="config-value" value="${isEncryptedEdit ? '' : (value || '')}" step="0.01" placeholder="${placeholder}" ${isEncryptedEdit ? '' : 'required'}>
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
                    <textarea id="config-value" rows="6" placeholder="${placeholder}" ${isEncryptedEdit ? '' : 'required'}>${isEncryptedEdit ? '' : (value || '')}</textarea>
                    <small class="form-hint">请输入有效的 JSON 格式</small>
                `;
            default:
                return `
                    <label for="config-value">参数值 *</label>
                    <input type="text" id="config-value" value="${isEncryptedEdit ? '' : (value || '')}" placeholder="${placeholder}" ${isEncryptedEdit ? '' : 'required'}>
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

        const isEncrypted = DOM.$('#config-is-encrypted')?.checked || false;

        let value;
        if (valueType === 'boolean') {
            value = DOM.$('#config-value').checked ? 'true' : 'false';
        } else {
            value = DOM.$('#config-value').value.trim();
        }

        // For new configs, value is required; for encrypted edits, empty means keep existing
        if (!key) {
            Toast.error('请填写必填字段');
            return;
        }
        if (!this.editingId && !value) {
            Toast.error('请填写必填字段');
            return;
        }

        // Validate JSON
        if (valueType === 'json' && value) {
            try {
                JSON.parse(value);
            } catch (e) {
                Toast.error('JSON 格式无效');
                return;
            }
        }

        const data = {
            key,
            value_type: valueType,
            category: category || null,
            description: description || null,
            is_encrypted: isEncrypted
        };
        // Only send value if non-empty (empty means keep existing encrypted value)
        if (value !== '') {
            data.value = value;
        }

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
