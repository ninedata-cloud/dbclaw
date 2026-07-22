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
        filtersContainer.innerHTML = I18n.t('pageCopy.systemConfigs.allCategoriesValueSearch', { value0: I18n.t('placeholders.searchParams'), value1: categories.map(cat => `<option value="${cat}">${cat}</option>`).join('') });

        const addBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: I18n.t('pageCopy.systemConfigs.addParameter')
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

            Header.render(I18n.t('pageCopy.systemConfigs.systemParameters'), this._buildHeaderActions(this.getCategories()));

            content.innerHTML = I18n.t('pageCopy.systemConfigs.configurationPage', { value0: this.renderSortableHeader('key', I18n.t('pageCopy.systemConfigs.key')), value1: this.renderSortableHeader('value', I18n.t('pageCopy.systemConfigs.parameterValueColumn')), value2: this.renderSortableHeader('value_type', I18n.t('pageCopy.systemConfigs.type')), value3: this.renderSortableHeader('category', I18n.t('pageCopy.systemConfigs.category')), value4: this.renderSortableHeader('description', I18n.t('pageCopy.systemConfigs.description')), value5: this.renderConfigRows() });

            DOM.createIcons();
        } catch (error) {
            console.error('Error loading configurations:', error);
            Toast.error(error.message || I18n.t('common.requestFailed'));
            content.innerHTML = I18n.t('pageCopy.systemConfigs.couldNotLoadConfigurationsValueRetry', { value0: error.message });
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
                (this._localizedDescription(config).toLowerCase().includes(searchTerm));
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
            return left.localeCompare(right, I18n.getLocale(), { numeric: true }) * multiplier;
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
        table.innerHTML = I18n.t('pageCopy.systemConfigs.configurationTable', { value0: this.renderSortableHeader('key', I18n.t('pageCopy.systemConfigs.key')), value1: this.renderSortableHeader('value', I18n.t('pageCopy.systemConfigs.parameterValueColumn')), value2: this.renderSortableHeader('value_type', I18n.t('pageCopy.systemConfigs.type')), value3: this.renderSortableHeader('category', I18n.t('pageCopy.systemConfigs.category')), value4: this.renderSortableHeader('description', I18n.t('pageCopy.systemConfigs.description')), value5: this.renderConfigRows() });
        DOM.createIcons();
    },

    renderConfigRows() {
        if (this.filteredConfigs.length === 0) {
            return I18n.t('pageCopy.systemConfigs.noConfigurationParameters');
        }

        return this.filteredConfigs.map(config => I18n.t('pageCopy.systemConfigs.configurationRow', { value0: config.key, value1: config.is_encrypted
                        ? I18n.t('pageCopy.systemConfigs.encryptedValue', { value0: this._escapeAttr(config.value), value1: this._maskValue(config.value) })
                        : this.formatValue(config.value, config.value_type), value2: config.value_type, value3: config.category || '-', value4: Utils.escapeHtml(this._localizedDescription(config) || '-'), value5: config.id, value6: config.id })).join('');
    },

    _localizedDescription(config) {
        return I18n.configDescription(config.key, config.description || '');
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
        const title = isEdit ? I18n.t('pageCopy.systemConfigs.editParameter') : I18n.t('pageCopy.systemConfigs.addParameter2');
        const isEncrypted = config.is_encrypted || false;

        Modal.show({
            title: title,
            content: I18n.t('pageCopy.systemConfigs.configForm', {
                key: this._escapeAttr(config.key || ''),
                readonly: isEdit ? 'readonly' : '',
                stringSelected: config.value_type === 'string' ? 'selected' : '',
                integerSelected: config.value_type === 'integer' ? 'selected' : '',
                floatSelected: config.value_type === 'float' ? 'selected' : '',
                booleanSelected: config.value_type === 'boolean' ? 'selected' : '',
                jsonSelected: config.value_type === 'json' ? 'selected' : '',
                valueInput: this.renderValueInput(config.value, config.value_type, isEncrypted && isEdit),
                encryptedChecked: isEncrypted ? 'checked' : '',
                category: this._escapeAttr(config.category || ''),
                categoryPlaceholder: I18n.t('placeholders.configCategories'),
                description: Utils.escapeHtml(config.description || '')
            }),
            buttons: [
                {
                    text: I18n.t('pageCopy.systemConfigs.cancel'),
                    variant: 'secondary',
                    onClick: () => Modal.hide()
                },
                {
                    text: I18n.t('pageCopy.systemConfigs.save'),
                    variant: 'primary',
                    onClick: () => this.saveConfig()
                }
            ]
        });
    },

    renderValueInput(value, type, isEncryptedEdit = false) {
        const placeholder = isEncryptedEdit ? I18n.t('placeholders.keepOriginal') : '';
        switch (type) {
            case 'string':
                return I18n.t('pageCopy.systemConfigs.stringValueInput', { value0: isEncryptedEdit ? '' : (value || ''), value1: placeholder, value2: isEncryptedEdit ? '' : 'required' });
            case 'integer':
                return I18n.t('pageCopy.systemConfigs.integerValueInput', { value0: isEncryptedEdit ? '' : (value || ''), value1: placeholder, value2: isEncryptedEdit ? '' : 'required' });
            case 'float':
                return I18n.t('pageCopy.systemConfigs.floatValueInput', { value0: isEncryptedEdit ? '' : (value || ''), value1: placeholder, value2: isEncryptedEdit ? '' : 'required' });
            case 'boolean':
                const checked = value === 'true' || value === '1' || value === 'yes';
                return I18n.t('pageCopy.systemConfigs.booleanValueInput', { value0: checked ? 'checked' : '' });
            case 'json':
                return I18n.t('pageCopy.systemConfigs.parameterValueJsonValueEnterValidJson', { value0: placeholder, value1: isEncryptedEdit ? '' : 'required', value2: isEncryptedEdit ? '' : (value || '') });
            default:
                return I18n.t('pageCopy.systemConfigs.stringValueInput', { value0: isEncryptedEdit ? '' : (value || ''), value1: placeholder, value2: isEncryptedEdit ? '' : 'required' });
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
            Toast.error(I18n.t('pageCopy.systemConfigs.requiredFields'));
            return;
        }
        if (!this.editingId && !value) {
            Toast.error(I18n.t('pageCopy.systemConfigs.requiredFields'));
            return;
        }

        // Validate JSON
        if (valueType === 'json' && value) {
            try {
                JSON.parse(value);
            } catch (e) {
                Toast.error(I18n.t('pageCopy.systemConfigs.invalidJson'));
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
                Toast.success(I18n.t('pageCopy.systemConfigs.parameterUpdated'));
            } else {
                await API.post('/api/system-configs', data);
                Toast.success(I18n.t('pageCopy.systemConfigs.parameterAdded'));
            }
            Modal.hide();
            this.loadConfigs();
        } catch (error) {
            console.error('Error saving config:', error);
            Toast.error(I18n.t('pageCopy.systemConfigs.saveFailed', { message: error.message }));
        }
    },

    async deleteConfig(id) {
        const config = this.configs.find(c => c.id === id);
        if (!config) return;

        if (!confirm(I18n.t('pageCopy.systemConfigs.areYouSureYouWantToDelete', { value0: config.key }))) {
            return;
        }

        try {
            await API.delete(`/api/system-configs/${id}`);
            Toast.success(I18n.t('pageCopy.systemConfigs.parameterDeleted'));
            this.loadConfigs();
        } catch (error) {
            console.error('Error deleting config:', error);
            Toast.error(I18n.t('pageCopy.systemConfigs.deleteFailed', { message: error.message }));
        }
    }
};
