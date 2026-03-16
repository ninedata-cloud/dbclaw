/* Hosts management page */
const HostsPage = {
    allHosts: [],
    filteredHosts: [],

    async render() {
        Header.render('主机管理', DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> New Host',
            onClick: () => this._showForm(null)
        }));

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            this.allHosts = await API.getHosts();
            this.filteredHosts = [...this.allHosts];
            Store.set('hosts', this.allHosts);
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

            // Filters
            const filterBar = DOM.el('div', { style: { marginBottom: '20px', display: 'flex', gap: '10px', flexWrap: 'wrap' } });
            filterBar.innerHTML = `
                <div>
                    <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">Name</label>
                    <input type="text" id="filterName" class="form-input" placeholder="按名称搜索..." style="padding:8px;border-radius:4px;min-width:200px;">
                </div>
                <div>
                    <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">Host IP</label>
                    <input type="text" id="filterHost" class="form-input" placeholder="按主机 IP 搜索..." style="padding:8px;border-radius:4px;min-width:200px;">
                </div>
            `;
            content.appendChild(filterBar);

            // Table container
            const tableContainer = DOM.el('div', { id: 'host-table-container' });
            content.appendChild(tableContainer);

            this._renderTable();
            this._setupFilterListeners();
            DOM.createIcons();

        } catch (err) {
            Toast.error('加载失败 hosts: ' + err.message);
        }
    },

    _setupFilterListeners() {
        DOM.$('#filterName')?.addEventListener('input', () => this._applyFilters());
        DOM.$('#filterHost')?.addEventListener('input', () => this._applyFilters());
    },

    _applyFilters() {
        const nameFilter = DOM.$('#filterName')?.value.toLowerCase() || '';
        const hostFilter = DOM.$('#filterHost')?.value.toLowerCase() || '';

        this.filteredHosts = this.allHosts.filter(h => {
            const matchName = !nameFilter || h.name.toLowerCase().includes(nameFilter);
            const matchHost = !hostFilter || h.host.toLowerCase().includes(hostFilter);
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
                        <th>用户名</th>
                        <th>认证方式</th>
                        <th>CPU 使用率</th>
                        <th>操作</th>
                    </tr>
                </thead>
                <tbody>
                    ${this.filteredHosts.map(host => `
                        <tr>
                            <td><strong>${host.name}</strong></td>
                            <td>${host.host}</td>
                            <td>${host.port}</td>
                            <td>${host.username}</td>
                            <td><span class="badge badge-info">${host.auth_type}</span></td>
                            <td>${host.cpu_usage != null ? host.cpu_usage.toFixed(1) + '%' : '-'}</td>
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
                    `).join('')}
                </tbody>
            </table>
        `;
        DOM.createIcons();
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

    async _deleteHost(host) {
        if (!confirm(`Delete host "${host.name}"? This cannot be undone.`)) return;
        try {
            await API.deleteHost(host.id);
            Toast.success('Host deleted');
            this.render();
        } catch (err) {
            Toast.error('Failed to delete: ' + err.message);
        }
    },
};
