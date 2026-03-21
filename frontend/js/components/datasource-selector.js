/* Datasource Selector Component - 强大的数据源下拉选择组件 */

/**
 * 数据源选择器组件
 *
 * 功能特性：
 * - 支持搜索过滤
 * - 按数据库类型分组
 * - 显示连接状态
 * - 支持多选模式
 * - 显示数据源详细信息（主机、端口、描述）
 * - 支持禁用特定数据源
 * - 支持自定义过滤条件
 * - 响应式设计
 *
 * 使用示例：
 *
 * // 单选模式
 * const selector = new DatasourceSelector({
 *     container: document.getElementById('my-container'),
 *     placeholder: '请选择数据源',
 *     onChange: (datasource) => console.log('Selected:', datasource),
 *     showStatus: true,
 *     showDetails: true
 * });
 *
 * // 多选模式
 * const multiSelector = new DatasourceSelector({
 *     container: document.getElementById('my-container'),
 *     multiple: true,
 *     onChange: (datasources) => console.log('Selected:', datasources),
 *     filter: (ds) => ds.db_type === 'mysql' // 只显示 MySQL
 * });
 *
 * // 获取选中值
 * const selected = selector.getValue();
 *
 * // 设置选中值
 * selector.setValue(datasourceId);
 *
 * // 刷新数据源列表
 * await selector.refresh();
 *
 * // 销毁组件
 * selector.destroy();
 */

class DatasourceSelector {
    constructor(options = {}) {
        this.options = {
            container: null,              // 容器元素（必需）
            placeholder: '选择数据源',    // 占位符文本
            multiple: false,              // 是否多选
            searchable: true,             // 是否可搜索
            groupByType: true,            // 是否按数据库类型分组
            showStatus: true,             // 是否显示连接状态
            showDetails: true,            // 是否显示详细信息（主机、端口）
            showDescription: false,       // 是否显示描述
            allowEmpty: true,             // 是否允许不选择
            emptyText: '所有数据源',      // 空选项文本
            disabled: false,              // 是否禁用
            filter: null,                 // 自定义过滤函数 (datasource) => boolean
            onChange: null,               // 选择变化回调
            onLoad: null,                 // 数据加载完成回调
            minWidth: '400px',            // 最小宽度
            maxWidth: '400px',            // 最大宽度
            ...options
        };

        if (!this.options.container) {
            throw new Error('DatasourceSelector: container is required');
        }

        this.datasources = [];
        this.selectedIds = new Set();
        this.isOpen = false;
        this.searchQuery = '';

        this.init();
    }

    async init() {
        this.render();
        await this.loadDatasources();
        this.setupEventListeners();
    }

    render() {
        const { container, minWidth, maxWidth, disabled } = this.options;

        container.innerHTML = '';
        container.className = 'datasource-selector';
        container.style.cssText = `
            position: relative;
            min-width: ${minWidth};
            max-width: ${maxWidth};
            ${disabled ? 'opacity: 0.6; pointer-events: none;' : ''}
        `;

        // 选择器按钮
        this.button = DOM.el('button', {
            type: 'button',
            className: 'datasource-selector-button',
            innerHTML: this.getButtonContent()
        });

        // 下拉面板
        this.dropdown = DOM.el('div', {
            className: 'datasource-selector-dropdown',
            style: { display: 'none' }
        });

        container.appendChild(this.button);
        container.appendChild(this.dropdown);
    }

    getButtonContent() {
        const { placeholder, multiple, allowEmpty, emptyText } = this.options;

        if (this.selectedIds.size === 0) {
            const text = allowEmpty ? emptyText : placeholder;
            return `
                <span class="datasource-selector-text">${text}</span>
                <i data-lucide="chevron-down" style="width:16px;height:16px;"></i>
            `;
        }

        if (multiple) {
            const count = this.selectedIds.size;
            return `
                <span class="datasource-selector-text">已选择 ${count} 项</span>
                <i data-lucide="chevron-down" style="width:16px;height:16px;"></i>
            `;
        }

        const selected = this.datasources.find(ds => this.selectedIds.has(ds.id));
        if (selected) {
            return `
                <span class="datasource-selector-text">${this.formatDatasourceName(selected)}</span>
                <i data-lucide="chevron-down" style="width:16px;height:16px;"></i>
            `;
        }

        return `
            <span class="datasource-selector-text">${placeholder}</span>
            <i data-lucide="chevron-down" style="width:16px;height:16px;"></i>
        `;
    }

    formatDatasourceName(ds) {
        return `${ds.name} (${ds.db_type.toUpperCase()})`;
    }

    async loadDatasources() {
        try {
            const data = await API.getDatasources();
            this.datasources = data;

            // 应用自定义过滤
            if (this.options.filter) {
                this.datasources = this.datasources.filter(this.options.filter);
            }

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

        // 搜索框
        if (searchable) {
            const searchBox = DOM.el('div', { className: 'datasource-selector-search' });
            this.searchInput = DOM.el('input', {
                type: 'text',
                placeholder: '搜索数据源...',
                className: 'datasource-selector-search-input',
                value: this.searchQuery
            });
            this.searchInput.addEventListener('input', (e) => {
                this.searchQuery = e.target.value.toLowerCase();
                this.renderItems();
            });
            searchBox.appendChild(this.searchInput);
            this.dropdown.appendChild(searchBox);
        }

        // 创建数据源列表容器
        this.itemsContainer = DOM.el('div', { className: 'datasource-selector-items' });
        this.dropdown.appendChild(this.itemsContainer);

        // 渲染数据源列表
        this.renderItems();
    }

    renderItems() {
        const { groupByType, allowEmpty, emptyText } = this.options;

        this.itemsContainer.innerHTML = '';

        // 空选项
        if (allowEmpty && !this.options.multiple) {
            const emptyItem = this.createDatasourceItem(null, emptyText);
            this.itemsContainer.appendChild(emptyItem);
        }

        // 过滤数据源
        const filtered = this.filterDatasources();

        if (filtered.length === 0) {
            const empty = DOM.el('div', {
                className: 'datasource-selector-empty',
                textContent: this.searchQuery ? '未找到匹配的数据源' : '暂无数据源'
            });
            this.itemsContainer.appendChild(empty);
            return;
        }

        // 分组或列表显示
        if (groupByType) {
            this.renderGrouped(filtered);
        } else {
            this.renderList(filtered);
        }
    }

    filterDatasources() {
        if (!this.searchQuery) return this.datasources;

        return this.datasources.filter(ds => {
            const searchText = `${ds.name} ${ds.db_type} ${ds.host || ''} ${ds.description || ''}`.toLowerCase();
            return searchText.includes(this.searchQuery);
        });
    }

    renderGrouped(datasources) {
        // 按数据库类型分组
        const groups = {};
        datasources.forEach(ds => {
            const type = ds.db_type.toUpperCase();
            if (!groups[type]) groups[type] = [];
            groups[type].push(ds);
        });

        // 渲染每个分组
        Object.keys(groups).sort().forEach(type => {
            const groupHeader = DOM.el('div', {
                className: 'datasource-selector-group-header',
                textContent: type
            });
            this.itemsContainer.appendChild(groupHeader);

            groups[type].forEach(ds => {
                const item = this.createDatasourceItem(ds);
                this.itemsContainer.appendChild(item);
            });
        });
    }

    renderList(datasources) {
        datasources.forEach(ds => {
            const item = this.createDatasourceItem(ds);
            this.itemsContainer.appendChild(item);
        });
    }

    createDatasourceItem(datasource, customText = null) {
        const { multiple, showStatus, showDetails, showDescription } = this.options;

        const item = DOM.el('div', {
            className: 'datasource-selector-item'
        });

        if (datasource === null) {
            // 空选项
            item.innerHTML = `<span>${customText}</span>`;
            item.addEventListener('click', () => this.selectDatasource(null));
            return item;
        }

        const isSelected = this.selectedIds.has(datasource.id);
        if (isSelected) {
            item.classList.add('selected');
        }

        // 构建内容
        let content = '';

        // 多选复选框
        if (multiple) {
            content += `<input type="checkbox" ${isSelected ? 'checked' : ''} style="margin-right: 8px;">`;
        }

        // 主要信息
        content += `<div class="datasource-selector-item-main">`;
        content += `<div class="datasource-selector-item-name">${datasource.name}</div>`;

        // 详细信息
        if (showDetails || showDescription) {
            content += `<div class="datasource-selector-item-details">`;

            if (showDetails && datasource.host) {
                content += `<span class="datasource-selector-item-host">${datasource.host}:${datasource.port || ''}</span>`;
            }

            if (showDescription && datasource.description) {
                content += `<span class="datasource-selector-item-desc">${datasource.description}</span>`;
            }

            content += `</div>`;
        }

        content += `</div>`;

        // 数据库类型标签
        content += `<span class="datasource-selector-item-type">${datasource.db_type.toUpperCase()}</span>`;

        // 连接状态
        if (showStatus) {
            const statusClass = datasource.status === 'connected' ? 'success' :
                              datasource.status === 'error' ? 'error' : 'warning';
            content += `<span class="datasource-selector-item-status status-${statusClass}"></span>`;
        }

        item.innerHTML = content;
        item.addEventListener('click', () => this.selectDatasource(datasource));

        return item;
    }

    selectDatasource(datasource) {
        const { multiple, onChange } = this.options;

        if (datasource === null) {
            // 清空选择
            this.selectedIds.clear();
            this.close();
            this.updateButton();
            if (onChange) onChange(null);
            return;
        }

        if (multiple) {
            // 多选模式
            if (this.selectedIds.has(datasource.id)) {
                this.selectedIds.delete(datasource.id);
            } else {
                this.selectedIds.add(datasource.id);
            }
            this.renderItems();
            this.updateButton();

            if (onChange) {
                const selected = this.datasources.filter(ds => this.selectedIds.has(ds.id));
                onChange(selected);
            }
        } else {
            // 单选模式
            this.selectedIds.clear();
            this.selectedIds.add(datasource.id);
            this.close();
            this.updateButton();

            if (onChange) onChange(datasource);
        }
    }

    updateButton() {
        this.button.innerHTML = this.getButtonContent();
        if (window.lucide) {
            window.lucide.createIcons();
        }
    }

    setupEventListeners() {
        // 按钮点击
        this.button.addEventListener('click', (e) => {
            e.stopPropagation();
            this.toggle();
        });

        // 点击外部关闭
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
        this.dropdown.style.display = 'block';
        this.button.classList.add('open');
    }

    close() {
        this.isOpen = false;
        this.dropdown.style.display = 'none';
        this.button.classList.remove('open');
        this.searchQuery = '';
    }

    // 公共 API

    getValue() {
        const { multiple } = this.options;

        if (multiple) {
            return this.datasources.filter(ds => this.selectedIds.has(ds.id));
        }

        if (this.selectedIds.size === 0) return null;
        return this.datasources.find(ds => this.selectedIds.has([...this.selectedIds][0]));
    }

    setValue(value) {
        this.selectedIds.clear();

        if (value === null || value === undefined) {
            this.updateButton();
            return;
        }

        const { multiple } = this.options;

        if (multiple) {
            // 多选：接受数组
            const ids = Array.isArray(value) ? value : [value];
            ids.forEach(id => this.selectedIds.add(id));
        } else {
            // 单选：接受单个 ID
            this.selectedIds.add(value);
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

// 导出
window.DatasourceSelector = DatasourceSelector;
