/* Hosts management page */
const HostsPage = {
    allHosts: [],
    filteredHosts: [],
    _filters: {
        name: '',
        host: ''
    },

    async render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            this.allHosts = await API.getHosts();
            this.filteredHosts = [...this.allHosts];
            Store.set('hosts', this.allHosts);

            Header.render('主机管理', this._buildHeaderActions());
            content.innerHTML = '';

            if (this.allHosts.length === 0) {
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="terminal"></i>
                        <h3>No Hosts</h3>
                        <p>Add your first host to enable tunnel connections to databases.</p>
                    </div>
                `;
                DOM.createIcons();
                return;
            }

            // Table container
            const tableContainer = DOM.el('div', { id: 'host-table-container' });
            content.appendChild(tableContainer);

            this._renderTable();
            DOM.createIcons();

        } catch (err) {
            Toast.error('加载失败 hosts: ' + err.message);
        }
    },

    _buildHeaderActions() {
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters' });
        filtersContainer.innerHTML = `
            <input type="text" id="filter-name" class="filter-input" placeholder="按名称搜索...">
            <input type="text" id="filter-host" class="filter-input" placeholder="按主机 IP 搜索...">
            <button id="btn-search" class="btn btn-primary">
                <i data-lucide="search"></i> 检索
            </button>
        `;

        const addBtn = DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> New Host',
            onClick: () => this._showForm(null)
        });

        setTimeout(() => {
            const btnSearch = DOM.$('#btn-search');
            const filterName = DOM.$('#filter-name');
            const filterHost = DOM.$('#filter-host');

            if (btnSearch) {
                btnSearch.addEventListener('click', () => this._applyFilters());
            }
            if (filterName) {
                filterName.addEventListener('input', () => this._applyFilters());
                filterName.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') this._applyFilters();
                });
            }
            if (filterHost) {
                filterHost.addEventListener('input', () => this._applyFilters());
                filterHost.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') this._applyFilters();
                });
            }
            DOM.createIcons();
        }, 0);

        return [filtersContainer, addBtn];
    },

    _applyFilters() {
        this._filters.name = DOM.$('#filter-name')?.value.trim().toLowerCase() || '';
        this._filters.host = DOM.$('#filter-host')?.value.trim().toLowerCase() || '';

        this.filteredHosts = this.allHosts.filter(h => {
            const matchName = !this._filters.name || h.name.toLowerCase().includes(this._filters.name);
            const matchHost = !this._filters.host || h.host.toLowerCase().includes(this._filters.host);
            return matchName && matchHost;
        });

        this._renderTable();
    },

    _renderTable() {
        const container = DOM.$('#host-table-container');
        if (!container) return;

        container.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>名称</th>
                        <th>主机</th>
                        <th>端口</th>
                        <th>状态</th>
                        <th>CPU</th>
                        <th>内存</th>
                        <th>磁盘</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${this.filteredHosts.map(host => this._renderHostRow(host)).join('')}
                </tbody>
            </table>
        `;
        DOM.createIcons();
    },

    _renderHostRow(host) {
        const statusBadge = this._getStatusBadge(host);
        const cpuColor = this._getMetricColor(host.cpu_usage);
        const memColor = this._getMetricColor(host.memory_usage);
        const diskColor = this._getMetricColor(host.disk_usage);

        return `
            <tr>
                <td><strong>${host.name}</strong></td>
                <td>${host.host}</td>
                <td>${host.port}</td>
                <td>${statusBadge}</td>
                <td class="${cpuColor}">${host.cpu_usage != null ? host.cpu_usage.toFixed(1) + '%' : '-'}</td>
                <td class="${memColor}">${host.memory_usage != null ? host.memory_usage.toFixed(1) + '%' : '-'}</td>
                <td class="${diskColor}">${host.disk_usage != null ? host.disk_usage.toFixed(1) + '%' : '-'}</td>
                <td>
                    <div style="display:flex;gap:4px;">
                        <button class="btn btn-sm btn-secondary" onclick="HostsPage._testHost(${host.id})" title="Test">
                            <i data-lucide="plug"></i>
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="HostsPage._editHost(${host.id})" title="Edit">
                            <i data-lucide="pencil"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="HostsPage._deleteHost(${host.id})" title="Delete">
                            <i data-lucide="trash-2"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    },

    _getStatusBadge(host) {
        const status = host.status || 'offline';
        const message = host.status_message || '';

        const statusMap = {
            normal: { icon: '✓', label: '正常', class: 'badge-success', title: message || '所有指标正常' },
            warning: { icon: '⚠', label: '异常', class: 'badge-warning', title: message || '部分指标接近阈值' },
            error: { icon: '✗', label: '严重', class: 'badge-danger', title: message || '部分指标超过阈值' },
            offline: { icon: '○', label: '离线', class: 'badge-secondary', title: message || '暂无监控数据' },
            unknown: { icon: '○', label: '未知', class: 'badge-secondary', title: message || '暂无监控数据' }
        };

        const s = statusMap[status] || statusMap.unknown;
        return `<span class="badge ${s.class}" title="${s.title}" style="cursor:help">${s.icon} ${s.label}</span>`;
    },

    _getMetricColor(value) {
        if (value == null) return '';
        if (value >= 90) return 'text-danger';
        if (value >= 80) return 'text-warning';
        return '';
    },

    async _testHost(id) {
        const btn = event.target.closest('button');
        btn.innerHTML = '<div class="spinner"></div>';
        btn.disabled = true;
        try {
            const result = await API.testHost(id);
            if (result.success) {
                Toast.success('连接成功!');
            } else {
                Toast.error(`Connection test failed: ${result.message}`);
            }
        } catch (err) {
            Toast.error('Test failed: ' + err.message);
        } finally {
            btn.innerHTML = '<i data-lucide="plug"></i>';
            btn.disabled = false;
            DOM.createIcons();
        }
    },

    _editHost(id) {
        const host = this.allHosts.find(h => h.id === id);
        if (host) this._showForm(host);
    },

    async _deleteHost(id) {
        const host = this.allHosts.find(h => h.id === id);
        if (!host || !confirm(`Delete host "${host.name}"? This cannot be undone.`)) return;
        try {
            await API.deleteHost(id);
            Toast.success('Host deleted');
            this.render();
        } catch (err) {
            Toast.error('Failed to delete: ' + err.message);
        }
    },

    _showForm(host) {
        const isEdit = !!host;
        const form = DOM.el('form');
        form.innerHTML = `
            <div class="form-group"><label>名称</label><input type="text" class="form-input" name="name" required placeholder="生产服务器" value="${host?.name || ''}"></div>
            <div class="form-row">
                <div class="form-group"><label>主机</label><input type="text" class="form-input" name="host" required placeholder="10.0.0.1" value="${host?.host || ''}"></div>
                <div class="form-group"><label>Port</label><input type="number" class="form-input" name="port" value="${host?.port || 22}"></div>
            </div>
            <div class="form-row">
                <div class="form-group"><label>用户名</label><input type="text" class="form-input" name="username" required placeholder="root" value="${host?.username || ''}"></div>
                <div class="form-group"><label>Auth Type</label>
                    <select class="form-select" name="auth_type">
                        <option value="password" ${host?.auth_type === 'password' || !host ? 'selected' : ''}>密码</option>
                        <option value="key" ${host?.auth_type === 'key' ? 'selected' : ''}>Private Key</option>
                    </select>
                </div>
            </div>
            <div class="form-group auth-password"><label>密码</label><input type="password" class="form-input" name="password" placeholder="${isEdit ? '(保持不变)' : ''}"></div>
            <div class="form-group auth-key" style="display:none"><label>私钥</label><textarea class="form-textarea" name="private_key" rows="4" placeholder="-----BEGIN RSA PRIVATE KEY-----"></textarea></div>
        `;

        const authSelect = form.querySelector('[name="auth_type"]');
        const pwdGroup = form.querySelector('.auth-password');
        const keyGroup = form.querySelector('.auth-key');
        const toggleAuth = () => {
            const isKey = authSelect.value === 'key';
            pwdGroup.style.display = isKey ? 'none' : '';
            keyGroup.style.display = isKey ? '' : 'none';
        };
        authSelect.addEventListener('change', toggleAuth);
        if (host?.auth_type === 'key') toggleAuth();

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(form).entries());
            data.port = parseInt(data.port);
            if (!data.password) delete data.password;
            if (!data.private_key) delete data.private_key;
            try {
                if (isEdit) {
                    await API.updateHost(host.id, data);
                    Toast.success('Host updated');
                } else {
                    await API.createHost(data);
                    Toast.success('Host created');
                }
                Modal.hide();
                this.render();
            } catch (err) {
                Toast.error(err.message);
            }
        });

        const footer = DOM.el('div');
        footer.appendChild(DOM.el('button', { className: 'btn btn-secondary', textContent: '取消', type: 'button', onClick: () => Modal.hide() }));
        if (isEdit) {
            footer.appendChild(DOM.el('button', {
                className: 'btn btn-secondary',
                innerHTML: '<i data-lucide="plug"></i> Test',
                type: 'button',
                onClick: async (e) => {
                    const btn = e.currentTarget;
                    btn.innerHTML = '<div class="spinner"></div>';
                    btn.disabled = true;
                    try {
                        const result = await API.testHost(host.id);
                        if (result.success) {
                            Toast.success('连接成功!');
                        } else {
                            Toast.error(`Connection test failed: ${result.message}`);
                        }
                    } catch (err) {
                        Toast.error('Test failed: ' + err.message);
                    } finally {
                        btn.innerHTML = '<i data-lucide="plug"></i> Test';
                        btn.disabled = false;
                        DOM.createIcons();
                    }
                }
            }));
        }
        
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-primary', textContent: isEdit ? '更新' : '创建', type: 'button',
            onClick: () => form.requestSubmit()
        }));
        Modal.show({ title: isEdit ? '编辑主机' : '新建主机', content: form, footer });
    },
};
