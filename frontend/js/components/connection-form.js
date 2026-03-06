/* Connection form component */
const ConnectionForm = {
    show(connection = null, onSave) {
        const isEdit = !!connection;
        const form = DOM.el('form', { id: 'connection-form' });

        form.innerHTML = `
            <div class="form-group">
                <label>Connection Name</label>
                <input type="text" class="form-input" name="name" value="${connection?.name || ''}" required placeholder="My Database">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Database Type</label>
                    <select class="form-select" name="db_type" required>
                        <option value="mysql" ${connection?.db_type === 'mysql' ? 'selected' : ''}>MySQL</option>
                        <option value="postgresql" ${connection?.db_type === 'postgresql' ? 'selected' : ''}>PostgreSQL</option>
                        <option value="oracle" ${connection?.db_type === 'oracle' ? 'selected' : ''}>Oracle</option>
                        <option value="mongodb" ${connection?.db_type === 'mongodb' ? 'selected' : ''}>MongoDB</option>
                        <option value="redis" ${connection?.db_type === 'redis' ? 'selected' : ''}>Redis</option>
                        <option value="sqlserver" ${connection?.db_type === 'sqlserver' ? 'selected' : ''}>SQL Server</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Port</label>
                    <input type="number" class="form-input" name="port" value="${connection?.port || this._defaultPort('mysql')}" required>
                </div>
            </div>
            <div class="form-group">
                <label>Host</label>
                <input type="text" class="form-input" name="host" value="${connection?.host || 'localhost'}" required placeholder="localhost">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" class="form-input" name="username" value="${connection?.username || ''}" placeholder="root">
                </div>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" class="form-input" name="password" value="" placeholder="${isEdit ? '(unchanged)' : ''}">
                </div>
            </div>
            <div class="form-group">
                <label>Database</label>
                <input type="text" class="form-input" name="database" value="${connection?.database || ''}" placeholder="mydb">
            </div>
            <div class="form-group">
                <label>SSH Host (Optional)</label>
                <select class="form-select" name="ssh_host_id">
                    <option value="">None</option>
                </select>
            </div>
        `;

        // Update port when db_type changes
        const dbTypeSelect = form.querySelector('[name="db_type"]');
        const portInput = form.querySelector('[name="port"]');
        dbTypeSelect.addEventListener('change', () => {
            if (!connection) portInput.value = this._defaultPort(dbTypeSelect.value);
        });

        // Load SSH hosts
        this._loadSSHHosts(form.querySelector('[name="ssh_host_id"]'), connection?.ssh_host_id);

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());
            data.port = parseInt(data.port);
            if (!data.password) delete data.password;
            if (!data.ssh_host_id) data.ssh_host_id = null;
            else data.ssh_host_id = parseInt(data.ssh_host_id);
            if (!data.database) data.database = null;

            try {
                if (isEdit) {
                    await API.updateConnection(connection.id, data);
                    Toast.success('Connection updated');
                } else {
                    await API.createConnection(data);
                    Toast.success('Connection created');
                }
                Modal.hide();
                if (onSave) onSave();
            } catch (err) {
                Toast.error(err.message);
            }
        });

        const footer = DOM.el('div', { style: { display: 'flex', gap: '8px' } });
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            textContent: 'Cancel',
            type: 'button',
            onClick: () => Modal.hide()
        }));
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
                        const result = await API.testConnection(connection.id);
                        if (result.success) {
                            Toast.success(`Connection successful! ${result.version || ''}`);
                        } else {
                            Toast.error(`Connection failed: ${result.message}`);
                        }
                    } catch (err) {
                        Toast.error('Test failed: ' + err.message);
                    } finally {
                        btn.innerHTML = '<i data-lucide="plug"></i> Test';
                        btn.disabled = false;
                        lucide.createIcons();
                    }
                }
            }));
        }
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-primary',
            textContent: isEdit ? 'Update' : 'Create',
            type: 'button',
            onClick: () => form.requestSubmit()
        }));

        Modal.show({
            title: isEdit ? 'Edit Connection' : 'New Connection',
            content: form,
            footer: footer,
        });
    },

    _defaultPort(dbType) {
        const ports = { mysql: 3306, postgresql: 5432, oracle: 1521, mongodb: 27017, redis: 6379, sqlserver: 1433 };
        return ports[dbType] || 3306;
    },

    async _loadSSHHosts(select, selectedId) {
        try {
            const hosts = await API.getSSHHosts();
            Store.set('sshHosts', hosts);
            for (const host of hosts) {
                const opt = DOM.el('option', { value: host.id, textContent: `${host.name} (${host.host})` });
                if (selectedId && host.id === selectedId) opt.selected = true;
                select.appendChild(opt);
            }
        } catch (e) {
            // Ignore
        }
    }
};
