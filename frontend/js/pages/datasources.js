/* Datasources management page */
const DatasourcesPage = {
    async render() {
        Header.render('Datasources', DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> New Datasource',
            onClick: () => DatasourceForm.show(null, () => this.render())
        }));

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const datasources = await API.getDatasources();
            Store.set('datasources', datasources);
            content.innerHTML = '';

            if (datasources.length === 0) {
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="database"></i>
                        <h3>No Datasources Yet</h3>
                        <p>Add your first database datasource to start monitoring and diagnosing.</p>
                    </div>
                `;
                DOM.createIcons();
                return;
            }

            // SSH Hosts management link
            const sshBar = DOM.el('div', { className: 'flex-between mb-16' });
            sshBar.appendChild(DOM.el('span', { className: 'text-muted text-sm', textContent: `${datasources.length} datasource(s)` }));
            sshBar.appendChild(DOM.el('button', {
                className: 'btn btn-secondary btn-sm',
                innerHTML: '<i data-lucide="terminal"></i> SSH Hosts',
                onClick: () => this._showSSHHostsModal()
            }));
            content.appendChild(sshBar);

            const grid = DOM.el('div', { className: 'datasource-grid' });
            for (const conn of datasources) {
                grid.appendChild(this._createCard(conn));
            }
            content.appendChild(grid);
            DOM.createIcons();

        } catch (err) {
            Toast.error('Failed to load datasources: ' + err.message);
        }
    },

    _createCard(conn) {
        const card = DOM.el('div', { className: 'datasource-card' });

        const importanceLevels = {
            core: { label: '核心系统', color: '#ef4444' },
            production: { label: '生产系统', color: '#f59e0b' },
            development: { label: '开发测试', color: '#3b82f6' },
            temporary: { label: '临时', color: '#6b7280' }
        };
        const importance = importanceLevels[conn.importance_level] || importanceLevels.production;

        card.innerHTML = `
            <div class="datasource-card-header">
                <span class="datasource-card-name">${conn.name}</span>
                <span class="datasource-card-type type-${conn.db_type}">${conn.db_type}</span>
            </div>
            <div class="datasource-card-info">
                <span><i data-lucide="server"></i> ${conn.host}:${conn.port}</span>
                ${conn.database ? `<span><i data-lucide="hard-drive"></i> ${conn.database}</span>` : ''}
                ${conn.username ? `<span><i data-lucide="user"></i> ${conn.username}</span>` : ''}
                <span><i data-lucide="shield"></i> <span style="color: ${importance.color}; font-weight: 500">${importance.label}</span></span>
                <span><i data-lucide="clock"></i> ${conn.monitoring_interval || 60}s</span>
            </div>
            <div class="datasource-card-actions">
                <button class="btn btn-sm btn-secondary test-btn" data-id="${conn.id}">
                    <i data-lucide="plug"></i> Test
                </button>
                <button class="btn btn-sm btn-secondary edit-btn" data-id="${conn.id}">
                    <i data-lucide="pencil"></i> Edit
                </button>
                <button class="btn btn-sm btn-danger delete-btn" data-id="${conn.id}">
                    <i data-lucide="trash-2"></i>
                </button>
                <div style="flex:1"></div>
                <button class="btn btn-sm btn-primary monitor-btn" data-id="${conn.id}">
                    <i data-lucide="activity"></i> Monitor
                </button>
            </div>
        `;

        // Wire up buttons
        card.querySelector('.test-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this._testDatasource(conn.id, card);
        });
        card.querySelector('.edit-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            DatasourceForm.show(conn, () => this.render());
        });
        card.querySelector('.delete-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            this._deleteDatasource(conn);
        });
        card.querySelector('.monitor-btn').addEventListener('click', (e) => {
            e.stopPropagation();
            Store.set('currentDatasource', conn);
            Router.navigate('monitor');
        });

        return card;
    },

    async _testDatasource(id, card) {
        const btn = card.querySelector('.test-btn');
        btn.innerHTML = '<div class="spinner"></div>';
        btn.disabled = true;
        try {
            const result = await API.testDatasource(id);
            if (result.success) {
                Toast.success(`Datasource successful! ${result.version || ''}`);
            } else {
                Toast.error(`Datasource failed: ${result.message}`);
            }
        } catch (err) {
            Toast.error('Test failed: ' + err.message);
        } finally {
            btn.innerHTML = '<i data-lucide="plug"></i> Test';
            btn.disabled = false;
            DOM.createIcons();
        }
    },

    async _deleteDatasource(conn) {
        if (!confirm(`Delete datasource "${conn.name}"? This cannot be undone.`)) return;
        try {
            await API.deleteDatasource(conn.id);
            Toast.success('Datasource deleted');
            this.render();
        } catch (err) {
            Toast.error('Failed to delete: ' + err.message);
        }
    },

    async _showSSHHostsModal() {
        const container = DOM.el('div');
        container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        const footer = DOM.el('div', { style: { display: 'flex', gap: '8px', justifyContent: 'flex-end' } });
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            textContent: 'Close',
            onClick: () => Modal.hide()
        }));
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> Add SSH Host',
            onClick: () => this._showSSHHostForm()
        }));

        Modal.show({ title: 'SSH Hosts', content: container, footer, width: '600px' });
        DOM.createIcons();

        try {
            const hosts = await API.getSSHHosts();
            container.innerHTML = '';
            if (hosts.length === 0) {
                container.innerHTML = '<p class="text-muted text-center">No SSH hosts configured</p>';
                return;
            }
            for (const host of hosts) {
                const item = DOM.el('div', {
                    className: 'flex-between',
                    style: { padding: '10px 0', borderBottom: '1px solid var(--border-color)' }
                });
                item.innerHTML = `
                    <div>
                        <strong>${host.name}</strong>
                        <span class="text-muted text-sm" style="margin-left:8px">${host.username}@${host.host}:${host.port}</span>
                    </div>
                `;
                const actions = DOM.el('div', { className: 'flex gap-8' });
                actions.appendChild(DOM.el('button', {
                    className: 'btn btn-sm btn-secondary',
                    textContent: 'Test',
                    onClick: async () => {
                        try {
                            const result = await API.testSSHHost(host.id);
                            Toast[result.success ? 'success' : 'error'](result.message);
                        } catch (e) { Toast.error(e.message); }
                    }
                }));
                actions.appendChild(DOM.el('button', {
                    className: 'btn btn-sm btn-danger',
                    textContent: 'Delete',
                    onClick: async () => {
                        if (!confirm('Delete this SSH host?')) return;
                        await API.deleteSSHHost(host.id);
                        Toast.success('Deleted');
                        this._showSSHHostsModal();
                    }
                }));
                item.appendChild(actions);
                container.appendChild(item);
            }
        } catch (err) {
            container.innerHTML = `<p class="text-muted">Error: ${err.message}</p>`;
        }
    },

    _showSSHHostForm() {
        const form = DOM.el('form');
        form.innerHTML = `
            <div class="form-group"><label>Name</label><input type="text" class="form-input" name="name" required placeholder="Production Server"></div>
            <div class="form-row">
                <div class="form-group"><label>Host</label><input type="text" class="form-input" name="host" required placeholder="10.0.0.1"></div>
                <div class="form-group"><label>Port</label><input type="number" class="form-input" name="port" value="22"></div>
            </div>
            <div class="form-group"><label>Username</label><input type="text" class="form-input" name="username" required placeholder="root"></div>
            <div class="form-group"><label>Auth Type</label><select class="form-select" name="auth_type"><option value="password">Password</option><option value="key">Private Key</option></select></div>
            <div class="form-group"><label>Password</label><input type="password" class="form-input" name="password"></div>
        `;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(form).entries());
            data.port = parseInt(data.port);
            try {
                await API.createSSHHost(data);
                Toast.success('SSH host created');
                Modal.hide();
            } catch (err) { Toast.error(err.message); }
        });

        const footer = DOM.el('div', { style: { display: 'flex', gap: '8px', justifyContent: 'flex-end' } });
        footer.appendChild(DOM.el('button', { className: 'btn btn-secondary', textContent: 'Cancel', type: 'button', onClick: () => Modal.hide() }));
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-primary', textContent: 'Create', type: 'button',
            onClick: () => form.requestSubmit()
        }));

        Modal.show({ title: 'New SSH Host', content: form, footer });
    }
};
