/* Datasource form component */
const DatasourceForm = {
    show(datasource = null, onSave) {
        const isEdit = !!datasource;
        const form = DOM.el('form', { id: 'datasource-form' });

        form.innerHTML = `
            <div class="form-group">
                <label>数据源名称</label>
                <input type="text" class="form-input" name="name" value="${datasource?.name || ''}" required placeholder="我的数据库">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>数据库类型</label>
                    <select class="form-select" name="db_type" required>
                        <option value="mysql" ${datasource?.db_type === 'mysql' ? 'selected' : ''}>MySQL</option>
                        <option value="postgresql" ${datasource?.db_type === 'postgresql' ? 'selected' : ''}>PostgreSQL</option>
                        <option value="oracle" ${datasource?.db_type === 'oracle' ? 'selected' : ''}>Oracle</option>
                        <option value="sqlserver" ${datasource?.db_type === 'sqlserver' ? 'selected' : ''}>SQL Server</option>
                        <option value="tidb" ${datasource?.db_type === 'tidb' ? 'selected' : ''}>TiDB</option>
                        <option value="dm" ${datasource?.db_type === 'dm' ? 'selected' : ''}>DM (达梦)</option>
                        <option value="oceanbase" ${datasource?.db_type === 'oceanbase' ? 'selected' : ''}>OceanBase</option>
                        <option value="opengauss" ${datasource?.db_type === 'opengauss' ? 'selected' : ''}>openGauss</option>
                        <option value="mongodb" ${datasource?.db_type === 'mongodb' ? 'selected' : ''}>MongoDB</option>
                        <option value="redis" ${datasource?.db_type === 'redis' ? 'selected' : ''}>Redis</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Port</label>
                    <input type="number" class="form-input" name="port" value="${datasource?.port || this._defaultPort('mysql')}" required>
                </div>
            </div>
            <div class="form-group">
                <label>Host</label>
                <input type="text" class="form-input" name="host" value="${datasource?.host || 'localhost'}" required placeholder="localhost">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Username</label>
                    <input type="text" class="form-input" name="username" value="${datasource?.username || ''}" placeholder="root">
                </div>
                <div class="form-group">
                    <label>Password</label>
                    <input type="password" class="form-input" name="password" value="" placeholder="${isEdit ? '(保持不变)' : ''}">
                </div>
            </div>
            <div class="form-group">
                <label>Database</label>
                <input type="text" class="form-input" name="database" value="${datasource?.database || ''}" placeholder="mydb">
            </div>
            <div class="form-group">
                <label>Host (可选)</label>
                <select class="form-select" name="host_id">
                    <option value="">无</option>
                </select>
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>重要性级别</label>
                    <select class="form-select" name="importance_level" required>
                        <option value="core" ${datasource?.importance_level === 'core' ? 'selected' : ''}>核心系统 (Core)</option>
                        <option value="production" ${datasource?.importance_level === 'production' || !datasource ? 'selected' : ''}>生产系统 (Production)</option>
                        <option value="development" ${datasource?.importance_level === 'development' ? 'selected' : ''}>开发测试 (Development)</option>
                        <option value="temporary" ${datasource?.importance_level === 'temporary' ? 'selected' : ''}>临时 (Temporary)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>监控间隔（秒）</label>
                    <input type="number" class="form-input" name="monitoring_interval" value="${datasource?.monitoring_interval || 60}" min="5" max="3600" required>
                </div>
            </div>
        `;

        // Update port when db_type changes
        const dbTypeSelect = form.querySelector('[name="db_type"]');
        const portInput = form.querySelector('[name="port"]');
        dbTypeSelect.addEventListener('change', () => {
            if (!datasource) portInput.value = this._defaultPort(dbTypeSelect.value);
        });

        // Load hosts
        this._loadHosts(form.querySelector('[name="host_id"]'), datasource?.host_id);

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const data = Object.fromEntries(formData.entries());
            data.port = parseInt(data.port);
            data.monitoring_interval = parseInt(data.monitoring_interval);
            if (!data.password) delete data.password;
            if (!data.host_id) data.host_id = null;
            else data.host_id = parseInt(data.host_id);
            if (!data.database) data.database = null;

            try {
                if (isEdit) {
                    await API.updateDatasource(datasource.id, data);
                    Toast.success('数据源已更新');
                } else {
                    await API.createDatasource(data);
                    Toast.success('数据源已创建');
                }
                Modal.hide();
                if (onSave) onSave();
            } catch (err) {
                Toast.error(err.message);
            }
        });

        const footer = DOM.el('div');
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            textContent: 'Cancel',
            type: 'button',
            onClick: () => Modal.hide()
        }));

        // Add test button for both create and edit modes
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: '<i data-lucide="plug"></i> Test',
            type: 'button',
            onClick: async (e) => {
                const btn = e.currentTarget;
                btn.innerHTML = '<div class="spinner"></div>';
                btn.disabled = true;
                try {
                    // Get current form values
                    const formData = new FormData(form);
                    const data = {
                        db_type: formData.get('db_type'),
                        host: formData.get('host'),
                        port: parseInt(formData.get('port')),
                        username: formData.get('username') || null,
                        password: formData.get('password') || null,
                        database: formData.get('database') || null
                    };

                    // If editing, include datasource_id so backend can use saved password if needed
                    if (isEdit) {
                        data.datasource_id = datasource.id;
                    }

                    const result = await API.testDatasourceConnection(data);
                    if (result.success) {
                        Toast.success(`连接成功! ${result.version || ''}`);
                    } else {
                        Toast.error(`连接失败: ${result.message}`);
                    }
                } catch (err) {
                    Toast.error('测试失败: ' + err.message);
                } finally {
                    btn.innerHTML = '<i data-lucide="plug"></i> Test';
                    btn.disabled = false;
                    DOM.createIcons();
                }
            }
        }));

        footer.appendChild(DOM.el('button', {
            className: 'btn btn-primary',
            textContent: isEdit ? 'Update' : 'Create',
            type: 'button',
            onClick: () => form.requestSubmit()
        }));

        Modal.show({
            title: isEdit ? 'Edit Datasource' : 'New Datasource',
            content: form,
            footer: footer,
        });
    },

    _defaultPort(dbType) {
        const ports = {
            mysql: 3306,
            postgresql: 5432,
            oracle: 1521,
            sqlserver: 1433,
            tidb: 4000,
            dm: 5236,
            oceanbase: 2881,
            opengauss: 5432,
            mongodb: 27017,
            redis: 6379
        };
        return ports[dbType] || 3306;
    },

    async _loadHosts(select, selectedId) {
        try {
            const hosts = await API.getHosts();
            Store.set('hosts', hosts);
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
