/* SSH Hosts management page */
const SSHHostsPage = {
    async render() {
        Header.render('SSH Hosts', DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> New SSH Host',
            onClick: () => this._showForm(null)
        }));

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const hosts = await API.getSSHHosts();
            Store.set('sshHosts', hosts);
            content.innerHTML = '';

            if (hosts.length === 0) {
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="terminal"></i>
                        <h3>No SSH Hosts</h3>
                        <p>Add your first SSH host to enable SSH tunnel connections to databases.</p>
                    </div>
                `;
                DOM.createIcons();
                return;
            }

            const bar = DOM.el('div', { className: 'flex-between mb-16' });
            bar.appendChild(DOM.el('span', { className: 'text-muted text-sm', textContent: `${hosts.length} host(s) configured` }));
            content.appendChild(bar);

            const grid = DOM.el('div', { className: 'datasource-grid' });
            for (const host of hosts) {
                grid.appendChild(this._createCard(host));
            }
            content.appendChild(grid);
            DOM.createIcons();

        } catch (err) {
            Toast.error('Failed to load SSH hosts: ' + err.message);
        }
    },

    _createCard(host) {
        const card = DOM.el('div', { className: 'datasource-card' });
        card.innerHTML = `
            <div class="datasource-card-header">
                <span class="datasource-card-name">${host.name}</span>
                <span class="badge badge-purple">${host.auth_type}</span>
            </div>
            <div class="datasource-card-info">
                <span><i data-lucide="server"></i> ${host.host}:${host.port}</span>
                <span><i data-lucide="user"></i> ${host.username}</span>
            </div>
            <div class="datasource-card-actions">
                <button class="btn btn-sm btn-secondary test-btn">
                    <i data-lucide="plug"></i> Test
                </button>
                <button class="btn btn-sm btn-secondary edit-btn">
                    <i data-lucide="pencil"></i> Edit
                </button>
                <button class="btn btn-sm btn-danger delete-btn">
                    <i data-lucide="trash-2"></i>
                </button>
            </div>
        `;

        card.querySelector('.test-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this._testHost(host.id, card);
        });
        card.querySelector('.edit-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this._showForm(host);
        });
        card.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this._deleteHost(host);
        });

        return card;
    },

    async _testHost(id, card) {
        const btn = card.querySelector('.test-btn');
        btn.innerHTML = '<div class="spinner"></div>';
        btn.disabled = true;
        try {
            const result = await API.testSSHHost(id);
            if (result.success) {
                Toast.success('SSH connection successful!');
            } else {
                Toast.error(`SSH test failed: ${result.message}`);
            }
        } catch (err) {
            Toast.error('Test failed: ' + err.message);
        } finally {
            btn.innerHTML = '<i data-lucide="plug"></i> Test';
            btn.disabled = false;
            DOM.createIcons();
        }
    },

    _showForm(host) {
        const isEdit = !!host;
        const form = DOM.el('form');
        form.innerHTML = `
            <div class="form-group"><label>Name</label><input type="text" class="form-input" name="name" required placeholder="Production Server" value="${host?.name || ''}"></div>
            <div class="form-row">
                <div class="form-group"><label>Host</label><input type="text" class="form-input" name="host" required placeholder="10.0.0.1" value="${host?.host || ''}"></div>
                <div class="form-group"><label>Port</label><input type="number" class="form-input" name="port" value="${host?.port || 22}"></div>
            </div>
            <div class="form-row">
                <div class="form-group"><label>Username</label><input type="text" class="form-input" name="username" required placeholder="root" value="${host?.username || ''}"></div>
                <div class="form-group"><label>Auth Type</label>
                    <select class="form-select" name="auth_type">
                        <option value="password" ${host?.auth_type === 'password' || !host ? 'selected' : ''}>Password</option>
                        <option value="key" ${host?.auth_type === 'key' ? 'selected' : ''}>Private Key</option>
                    </select>
                </div>
            </div>
            <div class="form-group auth-password"><label>Password</label><input type="password" class="form-input" name="password" placeholder="${isEdit ? '(unchanged)' : ''}"></div>
            <div class="form-group auth-key" style="display:none"><label>Private Key</label><textarea class="form-textarea" name="private_key" rows="4" placeholder="-----BEGIN RSA PRIVATE KEY-----"></textarea></div>
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
                    await API.updateSSHHost(host.id, data);
                    Toast.success('SSH host updated');
                } else {
                    await API.createSSHHost(data);
                    Toast.success('SSH host created');
                }
                Modal.hide();
                this.render();
            } catch (err) {
                Toast.error(err.message);
            }
        });

        const footer = DOM.el('div', { style: { display: 'flex', gap: '8px', justifyContent: 'flex-end' } });
        footer.appendChild(DOM.el('button', { className: 'btn btn-secondary', textContent: 'Cancel', type: 'button', onClick: () => Modal.hide() }));
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
                        const result = await API.testSSHHost(host.id);
                        if (result.success) {
                            Toast.success('SSH connection successful!');
                        } else {
                            Toast.error(`SSH test failed: ${result.message}`);
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
            className: 'btn btn-primary', textContent: isEdit ? 'Update' : 'Create', type: 'button',
            onClick: () => form.requestSubmit()
        }));

        Modal.show({ title: isEdit ? 'Edit SSH Host' : 'New SSH Host', content: form, footer });
    },

    async _deleteHost(host) {
        if (!confirm(`Delete SSH host "${host.name}"? This cannot be undone.`)) return;
        try {
            await API.deleteSSHHost(host.id);
            Toast.success('SSH host deleted');
            this.render();
        } catch (err) {
            Toast.error('Failed to delete: ' + err.message);
        }
    },
};
