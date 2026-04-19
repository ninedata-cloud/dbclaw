/* Datasource Selector Component - 强大的数据源下拉选择组件 */

class DatasourceSelector {
    constructor(options = {}) {
        this.options = {
            container: null,
            placeholder: '选择数据源',
            multiple: false,
            searchable: true,
            groupByType: true,
            showStatus: true,
            showDetails: true,
            showDescription: false,
            allowEmpty: true,
            emptyText: '所有数据源',
            disabled: false,
            filter: null,
            onChange: null,
            onLoad: null,
            minWidth: '400px',
            maxWidth: '400px',
            ...options
        };

        if (!this.options.container) {
            throw new Error('DatasourceSelector: container is required');
        }

        this.datasources = [];
        this.selectedIds = new Set();
        this.isOpen = false;
        this.searchQuery = '';
        this.button = null;
        this.dropdown = null;
        this.searchInput = null;
        this.itemsContainer = null;

        this.init();
    }

    async init() {
        this.render();
        await this.loadDatasources();
        this.setupEventListeners();
    }

    _getDbTypeLabel(dbType) {
        const labels = {
            mysql: 'MySQL',
            postgresql: 'PostgreSQL',
            sqlserver: 'SQL Server',
            oracle: 'Oracle',
            'tdsql-c-mysql': 'TDSQL-C MySQL',
            opengauss: 'openGauss',
            hana: 'SAP HANA',
        };
        return labels[dbType] || dbType || 'unknown';
    }

    render() {
        const { container, minWidth, maxWidth, disabled } = this.options;

        container.innerHTML = '';
        container.classList.add('datasource-selector');
        container.style.position = 'relative';
        container.style.minWidth = minWidth;
        container.style.maxWidth = maxWidth;
        container.style.opacity = disabled ? '0.6' : '1';
        container.style.pointerEvents = disabled ? 'none' : 'auto';

        this.button = DOM.el('button', {
            type: 'button',
            className: 'datasource-selector-button',
            'aria-haspopup': 'listbox',
            'aria-expanded': 'false'
        });
        this.renderButtonContent();

        this.dropdown = DOM.el('div', {
            className: 'datasource-selector-dropdown',
            style: { display: 'none' }
        });

        container.appendChild(this.button);
        container.appendChild(this.dropdown);
    }

    getSelectedDatasource() {
        if (this.selectedIds.size === 0) return null;
        const [selectedId] = this.selectedIds;
        return this.datasources.find(ds => ds.id === selectedId) || null;
    }

    formatDatasourceName(ds) {
        return ds?.name || this.options.placeholder;
    }

    getStatusMeta(status) {
        if (status === 'connected' || status === 'success' || status === 'healthy' || status === 'normal') {
            return { className: 'success', label: '连接正常' };
        }

        if (status === 'error' || status === 'failed' || status === 'disconnected') {
            return { className: 'error', label: '连接异常' };
        }

        if (status === 'warning') {
            return { className: 'warning', label: '连接警告' };
        }

        return { className: 'unknown', label: '状态未知' };
    }

    renderButtonContent() {
        const { placeholder, multiple, allowEmpty, emptyText } = this.options;
        const textWrap = DOM.el('span', { className: 'datasource-selector-button-content' });
        const mainText = DOM.el('span', { className: 'datasource-selector-text' });

        if (this.selectedIds.size === 0) {
            mainText.textContent = allowEmpty ? emptyText : placeholder;
            textWrap.appendChild(mainText);
        } else if (multiple) {
            mainText.textContent = `已选择 ${this.selectedIds.size} 项`;
            textWrap.appendChild(mainText);
        } else {
            const selected = this.getSelectedDatasource();
            mainText.textContent = selected ? this.formatDatasourceName(selected) : placeholder;
            textWrap.appendChild(mainText);
        }

        const icon = DOM.el('i', {
            'data-lucide': 'chevron-down',
            style: 'width:16px;height:16px;'
        });

        this.button.replaceChildren(textWrap, icon);
        DOM.createIcons();
    }

    async loadDatasources() {
        try {
            const data = await API.getDatasources();
            this.datasources = this.options.filter ? data.filter(this.options.filter) : data;
            this.renderDropdown();

            if (this.options.onLoad) {
                this.options.onLoad(this.datasources);
            }
        } catch (error) {
            console.error('[DatasourceSelector] Failed to load datasources:', error);
            Toast.error('加载数据源失败');
        }
    }

    renderDropdown() {
        const { searchable } = this.options;

        this.dropdown.innerHTML = '';

        if (searchable) {
            const searchBox = DOM.el('div', { className: 'datasource-selector-search' });
            this.searchInput = DOM.el('input', {
                type: 'text',
                placeholder: '搜索数据源...',
                className: 'datasource-selector-search-input',
                value: this.searchQuery,
                'aria-label': '搜索数据源'
            });
            this.searchInput.addEventListener('input', (e) => {
                this.searchQuery = e.target.value.toLowerCase();
                this.renderItems();
            });
            searchBox.appendChild(this.searchInput);
            this.dropdown.appendChild(searchBox);
        } else {
            this.searchInput = null;
        }

        this.itemsContainer = DOM.el('div', {
            className: 'datasource-selector-items',
            role: 'listbox'
        });
        this.dropdown.appendChild(this.itemsContainer);

        this.renderItems();
    }

    renderItems() {
        const { groupByType, allowEmpty, emptyText, multiple } = this.options;

        this.itemsContainer.innerHTML = '';

        if (allowEmpty && !multiple) {
            this.itemsContainer.appendChild(this.createDatasourceItem(null, emptyText));
        }

        const filtered = this.filterDatasources();

        if (filtered.length === 0) {
            this.itemsContainer.appendChild(DOM.el('div', {
                className: 'datasource-selector-empty',
                textContent: this.searchQuery ? '未找到匹配的数据源' : '暂无数据源'
            }));
            return;
        }

        if (groupByType) {
            this.renderGrouped(filtered);
        } else {
            this.renderList(filtered);
        }
    }

    filterDatasources() {
        if (!this.searchQuery) return this.datasources;

        const terms = this.searchQuery.split(/\s+/).filter(Boolean);
        return this.datasources.filter(ds => {
            const searchText = [
                ds.name,
                ds.db_type,
                ds.host,
                ds.port,
                ds.description,
                ds.database
            ].filter(Boolean).join(' ').toLowerCase();

            return terms.every(term => searchText.includes(term));
        });
    }

    renderGrouped(datasources) {
        const groups = {};
        datasources.forEach(ds => {
            const type = (ds.db_type || 'unknown').toUpperCase();
            if (!groups[type]) groups[type] = [];
            groups[type].push(ds);
        });

        Object.keys(groups).sort().forEach(type => {
            const groupHeader = DOM.el('div', { className: 'datasource-selector-group-header' });
            groupHeader.append(
                DOM.el('span', { textContent: type }),
                DOM.el('span', {
                    className: 'datasource-selector-group-count',
                    textContent: String(groups[type].length)
                })
            );
            this.itemsContainer.appendChild(groupHeader);

            groups[type].forEach(ds => {
                this.itemsContainer.appendChild(this.createDatasourceItem(ds));
            });
        });
    }

    renderList(datasources) {
        datasources.forEach(ds => {
            this.itemsContainer.appendChild(this.createDatasourceItem(ds));
        });
    }

    createDatasourceItem(datasource, customText = null) {
        const { multiple, showStatus, showDetails, showDescription } = this.options;
        const isEmptyOption = datasource === null;
        const isSelected = isEmptyOption ? this.selectedIds.size === 0 : this.selectedIds.has(datasource.id);

        const item = DOM.el('div', {
            className: `datasource-selector-item${isSelected ? ' selected' : ''}${isEmptyOption ? ' datasource-selector-item-empty' : ''}`,
            role: 'option',
            'aria-selected': isSelected ? 'true' : 'false'
        });

        if (isEmptyOption) {
            const content = DOM.el('div', { className: 'datasource-selector-item-main' },
                DOM.el('div', { className: 'datasource-selector-item-name', textContent: customText }),
                DOM.el('div', {
                    className: 'datasource-selector-item-details datasource-selector-item-empty-hint',
                    textContent: '不过滤数据源'
                })
            );

            item.appendChild(content);
            if (isSelected) {
                item.appendChild(DOM.el('span', {
                    className: 'datasource-selector-item-check',
                    textContent: '当前'
                }));
            }
            item.addEventListener('click', () => this.selectDatasource(null));
            return item;
        }

        if (multiple) {
            const checkbox = DOM.el('input', {
                type: 'checkbox',
                disabled: 'disabled',
                tabindex: '-1',
                className: 'datasource-selector-item-checkbox'
            });
            checkbox.checked = isSelected;
            item.appendChild(checkbox);
        }

        const main = DOM.el('div', { className: 'datasource-selector-item-main' });
        const name = DOM.el('div', {
            className: 'datasource-selector-item-name',
            textContent: datasource.name,
            title: datasource.name
        });
        main.appendChild(name);

        if (showDetails || showDescription) {
            const details = DOM.el('div', { className: 'datasource-selector-item-details' });

            if (showDetails && datasource.host) {
                const hostText = datasource.port ? `${datasource.host}:${datasource.port}` : datasource.host;
                details.appendChild(DOM.el('span', {
                    className: 'datasource-selector-item-host',
                    textContent: hostText,
                    title: hostText
                }));
            }

            if (showDescription && datasource.description) {
                details.appendChild(DOM.el('span', {
                    className: 'datasource-selector-item-desc',
                    textContent: datasource.description,
                    title: datasource.description
                }));
            }

            if (details.childNodes.length > 0) {
                main.appendChild(details);
            }
        }

        item.appendChild(main);
        item.appendChild(DOM.el('span', {
            className: 'datasource-selector-item-type',
            textContent: this._getDbTypeLabel(datasource.db_type)
        }));

        if (showStatus) {
            const statusMeta = this.getStatusMeta(datasource.connection_status || datasource.status);
            item.appendChild(DOM.el('span', {
                className: `datasource-selector-item-status status-${statusMeta.className}`,
                title: statusMeta.label,
                'aria-label': statusMeta.label
            }));
        }

        if (isSelected) {
            item.appendChild(DOM.el('span', {
                className: 'datasource-selector-item-check',
                textContent: '已选'
            }));
        }

        item.addEventListener('click', () => this.selectDatasource(datasource));
        return item;
    }

    selectDatasource(datasource) {
        const { multiple, onChange } = this.options;

        if (datasource === null) {
            this.selectedIds.clear();
            this.close();
            this.updateButton();
            this.renderItems();
            if (onChange) onChange(null);
            return;
        }

        if (multiple) {
            if (this.selectedIds.has(datasource.id)) {
                this.selectedIds.delete(datasource.id);
            } else {
                this.selectedIds.add(datasource.id);
            }
            this.renderItems();
            this.updateButton();

            if (onChange) {
                onChange(this.datasources.filter(ds => this.selectedIds.has(ds.id)));
            }
            return;
        }

        this.selectedIds.clear();
        this.selectedIds.add(datasource.id);
        this.close();
        this.updateButton();
        this.renderItems();

        if (onChange) onChange(datasource);
    }

    updateButton() {
        this.renderButtonContent();
    }

    setupEventListeners() {
        this.button.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });

        this.outsideClickHandler = (e) => {
            if (!this.options.container.contains(e.target)) {
                this.close();
            }
        };
        document.addEventListener('click', this.outsideClickHandler);
    }

    toggle() {
        if (this.isOpen) {
            this.close();
        } else {
            this.open();
        }
    }

    open() {
        this.isOpen = true;
        this.dropdown.style.display = 'flex';
        this.button.classList.add('open');
        this.button.setAttribute('aria-expanded', 'true');
        this.renderItems();

        if (this.searchInput) {
            requestAnimationFrame(() => {
                this.searchInput.focus();
                this.searchInput.select();
            });
        }

        requestAnimationFrame(() => this.scrollSelectedItemIntoView());
    }

    close() {
        this.isOpen = false;
        this.dropdown.style.display = 'none';
        this.button.classList.remove('open');
        this.button.setAttribute('aria-expanded', 'false');
        this.searchQuery = '';

        if (this.searchInput) {
            this.searchInput.value = '';
        }

        if (this.itemsContainer) {
            this.renderItems();
        }
    }

    scrollSelectedItemIntoView() {
        const selectedItem = this.itemsContainer?.querySelector('.datasource-selector-item.selected');
        if (selectedItem) {
            selectedItem.scrollIntoView({ block: 'nearest' });
        }
    }

    getValue() {
        const { multiple } = this.options;

        if (multiple) {
            return this.datasources.filter(ds => this.selectedIds.has(ds.id));
        }

        return this.getSelectedDatasource();
    }

    setValue(value) {
        this.selectedIds.clear();

        if (value !== null && value !== undefined) {
            const { multiple } = this.options;
            if (multiple) {
                const ids = Array.isArray(value) ? value : [value];
                ids.forEach(id => this.selectedIds.add(id));
            } else {
                this.selectedIds.add(value);
            }
        }

        this.updateButton();
        if (this.itemsContainer) {
            this.renderItems();
        }
    }

    async refresh() {
        await this.loadDatasources();
    }

    setDisabled(disabled) {
        this.options.disabled = disabled;
        this.options.container.style.opacity = disabled ? '0.6' : '1';
        this.options.container.style.pointerEvents = disabled ? 'none' : 'auto';
    }

    destroy() {
        if (this.outsideClickHandler) {
            document.removeEventListener('click', this.outsideClickHandler);
        }
        this.options.container.innerHTML = '';
    }
}

window.DatasourceSelector = DatasourceSelector;
