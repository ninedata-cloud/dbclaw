/* User management page (admin only) */
const UsersPage = {
    _maskPhone(phone) {
        if (!phone) return '-';
        const trimmed = String(phone).trim();
        if (trimmed.length < 7) return trimmed;
        return `${trimmed.slice(0, 3)}****${trimmed.slice(-4)}`;
    },

    async render() {
        Header.render('用户管理', DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> New 用户',
            onClick: () => this._showCreateModal()
        }));

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const users = await API.getUsers();
            content.innerHTML = '';

            const info = DOM.el('div', { className: 'flex-between mb-16' });
            info.appendChild(DOM.el('span', { className: 'text-muted text-sm', textContent: `${users.length} 个用户` }));
            content.appendChild(info);

            const table = DOM.el('table', { className: 'data-table' });
            table.innerHTML = `
                <thead>
                    <tr>
                        <th>用户名</th>
                        <th>显示名称</th>
                        <th>邮箱</th>
                        <th>电话</th>
                        <th>角色</th>
                        <th>状态</th>
                        <th>创建时间</th>
                        <th>操作</th>
                    </tr>
                </thead>
            `;
            const tbody = DOM.el('tbody');

            for (const user of users) {
                const tr = DOM.el('tr');
                tr.innerHTML = `
                    <td><strong>${Utils.escapeHtml(user.username)}</strong></td>
                    <td>${Utils.escapeHtml(user.display_name || '-')}</td>
                    <td>${Utils.escapeHtml(user.email || '-')}</td>
                    <td>${Utils.escapeHtml(this._maskPhone(user.phone))}</td>
                    <td><span class="badge ${user.is_admin ? 'badge-primary' : 'badge-secondary'}">${user.is_admin ? '管理员' : '用户'}</span></td>
                    <td><span class="badge ${user.is_active ? 'badge-success' : 'badge-secondary'}">${user.is_active ? '活跃' : '禁用'}</span></td>
                    <td>${Format.datetime(user.created_at)}</td>
                    <td class="actions-cell"></td>
                `;

                const actionsCell = tr.querySelector('.actions-cell');
                const currentUser = Store.get('currentUser');
                const isSelf = currentUser && currentUser.id === user.id;
                const canResetPassword = user.username !== 'admin' || isSelf;

                // Edit button
                const editBtn = DOM.el('button', {
                    className: 'btn btn-sm btn-secondary',
                    innerHTML: '<i data-lucide="pencil"></i>',
                    title: '编辑用户',
                    onClick: () => this._showEditModal(user)
                });
                actionsCell.appendChild(editBtn);

                // Toggle status button
                if (!isSelf) {
                    const toggleBtn = DOM.el('button', {
                        className: `btn btn-sm ${user.is_active ? 'btn-warning' : 'btn-success'}`,
                        innerHTML: `<i data-lucide="${user.is_active ? 'user-x' : 'user-check'}"></i>`,
                        title: user.is_active ? 'Disable' : 'Enable',
                        onClick: () => this._toggleStatus(user)
                    });
                    actionsCell.appendChild(toggleBtn);
                }

                // Reset password button
                if (canResetPassword) {
                    const resetBtn = DOM.el('button', {
                        className: 'btn btn-sm btn-secondary',
                        innerHTML: '<i data-lucide="key"></i>',
                        title: '重置密码',
                        onClick: () => this._showResetPasswordModal(user)
                    });
                    actionsCell.appendChild(resetBtn);
                }

                // Login logs button
                const logsBtn = DOM.el('button', {
                    className: 'btn btn-sm btn-secondary',
                    innerHTML: '<i data-lucide="scroll-text"></i>',
                    title: 'Login Logs',
                    onClick: () => this._showLoginLogs(user)
                });
                actionsCell.appendChild(logsBtn);

                // Delete button
                if (!isSelf) {
                    const deleteBtn = DOM.el('button', {
                        className: 'btn btn-sm btn-danger',
                        innerHTML: '<i data-lucide="trash-2"></i>',
                        title: 'Delete',
                        onClick: () => this._deleteUser(user)
                    });
                    actionsCell.appendChild(deleteBtn);
                }

                tbody.appendChild(tr);
            }

            table.appendChild(tbody);
            const container = DOM.el('div', { className: 'data-table-container' });
            container.appendChild(table);
            content.appendChild(container);
            DOM.createIcons();
        } catch (err) {
            Toast.error('加载失败 users: ' + err.message);
        }
    },

    _showCreateModal() {
        const form = DOM.el('div');
        form.innerHTML = `
            <div class="form-group">
                <label>用户名</label>
                <input type="text" id="new-username" class="form-input" placeholder="用户名" required>
            </div>
            <div class="form-group">
                <label>密码</label>
                <input type="password" id="new-password" class="form-input" placeholder="密码（至少 6 位）">
            </div>
            <div class="form-group">
                <label>显示名称</label>
                <input type="text" id="new-display-name" class="form-input" placeholder="显示名称（可选）">
            </div>
            <div class="form-group">
                <label>邮箱</label>
                <input type="email" id="new-email" class="form-input" placeholder="邮箱（可选）">
            </div>
            <div class="form-group">
                <label>电话</label>
                <input type="text" id="new-phone" class="form-input" placeholder="电话（可选）">
            </div>
            <div class="form-group" style="display:flex;align-items:center;gap:8px;">
                <input type="checkbox" id="new-is-admin">
                <label for="new-is-admin" style="margin:0">管理员</label>
            </div>
        `;

        Modal.show({
            title: '新建用户',
            content: form,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '创建', variant: 'primary', onClick: () => this._createUser() },
            ]
        });
    },

    async _createUser() {
        const username = DOM.$('#new-username').value.trim();
        const password = DOM.$('#new-password').value;
        const display_name = DOM.$('#new-display-name').value.trim();
        const email = DOM.$('#new-email').value.trim();
        const phone = DOM.$('#new-phone').value.trim();
        const is_admin = DOM.$('#new-is-admin').checked;

        if (!username || !password) {
            Toast.error('用户名和密码不能为空');
            return;
        }
        if (password.length < 6) {
            Toast.error('密码不能少于 6 位');
            return;
        }

        try {
            await API.createUser({ username, password, display_name: display_name || null, email: email || null, phone: phone || null, is_admin });
            Modal.hide();
            Toast.success('用户创建成功');
            this.render();
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async _toggleStatus(user) {
        try {
            const result = await API.toggleUserStatus(user.id);
            Toast.success(result.message);
            this.render();
        } catch (err) {
            Toast.error(err.message);
        }
    },

    _showEditModal(user) {
        const form = DOM.el('div');
        form.innerHTML = `
            <div class="form-group">
                <label>显示名称</label>
                <input type="text" id="edit-display-name" class="form-input" placeholder="显示名称（可选）" value="${Utils.escapeHtml(user.display_name || '')}">
            </div>
            <div class="form-group">
                <label>邮箱</label>
                <input type="email" id="edit-email" class="form-input" placeholder="邮箱（可选）" value="${Utils.escapeHtml(user.email || '')}">
            </div>
            <div class="form-group">
                <label>电话</label>
                <input type="text" id="edit-phone" class="form-input" placeholder="电话（可选）" value="${Utils.escapeHtml(user.phone || '')}">
            </div>
            <div class="form-group" style="display:flex;align-items:center;gap:8px;">
                <input type="checkbox" id="edit-is-admin" ${user.is_admin ? 'checked' : ''}>
                <label for="edit-is-admin" style="margin:0">管理员</label>
            </div>
        `;

        Modal.show({
            title: `编辑用户 - ${Utils.escapeHtml(user.username)}`,
            content: form,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '保存', variant: 'primary', onClick: async () => {
                    const display_name = DOM.$('#edit-display-name').value.trim();
                    const email = DOM.$('#edit-email').value.trim();
                    const phone = DOM.$('#edit-phone').value.trim();
                    const is_admin = DOM.$('#edit-is-admin').checked;
                    try {
                        await API.updateUser(user.id, {
                            display_name: display_name || null,
                            email: email || null,
                            phone: phone || null,
                            is_admin
                        });
                        Modal.hide();
                        Toast.success('用户信息已更新');
                        this.render();
                    } catch (err) {
                        Toast.error(err.message);
                    }
                }},
            ]
        });
    },

    _showResetPasswordModal(user) {
        const form = DOM.el('div');
        form.innerHTML = `
            <p style="margin-bottom:12px;color:var(--text-secondary)">Reset password for <strong>${Utils.escapeHtml(user.username)}</strong></p>
            <div class="form-group">
                <label>New Password</label>
                <input type="password" id="reset-password" class="form-input" placeholder="新密码（至少 6 位）">
            </div>
        `;

        Modal.show({
            title: '重置密码',
            content: form,
            size: 'small',
            buttons: [
                { text: 'Cancel', variant: 'secondary', onClick: () => Modal.hide() },
                { text: 'Reset', variant: 'primary', onClick: async () => {
                    const pw = DOM.$('#reset-password').value;
                    if (!pw || pw.length < 6) {
                        Toast.error('Password must be at least 6 characters');
                        return;
                    }
                    try {
                        await API.resetUserPassword(user.id, pw);
                        Modal.hide();
                        Toast.success('Password reset successfully');
                    } catch (err) {
                        Toast.error(err.message);
                    }
                }},
            ]
        });
    },

    async _showLoginLogs(user) {
        try {
            const logs = await API.getUserLoginLogs(user.id);

            const container = DOM.el('div');
            if (logs.length === 0) {
                container.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:24px;">No login logs</p>';
            } else {
                const table = DOM.el('table', { className: 'data-table' });
                table.innerHTML = `
                    <thead>
                        <tr>
                            <th>时间</th>
                            <th>IP 地址</th>
                            <th>用户 Agent</th>
                            <th>结果</th>
                        </tr>
                    </thead>
                `;
                const tbody = DOM.el('tbody');
                for (const log of logs) {
                    const loginTime = log.login_time || log.logged_in_at;
                    const isSuccess = log.success ?? log.is_success;
                    const tr = DOM.el('tr');
                    tr.innerHTML = `
                        <td style="white-space:nowrap">${Format.datetime(loginTime)}</td>
                        <td>${Utils.escapeHtml(log.ip_address || '-')}</td>
                        <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${Utils.escapeHtml(log.user_agent || '')}">${Utils.escapeHtml(log.user_agent || '-')}</td>
                        <td><span class="badge ${isSuccess ? 'badge-success' : 'badge-danger'}">${isSuccess ? 'Success' : 'Failed'}</span></td>
                    `;
                    tbody.appendChild(tr);
                }
                table.appendChild(tbody);
                const tableContainer = DOM.el('div', { className: 'data-table-container', style: { maxHeight: '400px', overflow: 'auto' } });
                tableContainer.appendChild(table);
                container.appendChild(tableContainer);
            }

            Modal.show({
                title: `Login Logs - ${user.username}`,
                content: container,
                size: 'large',
                buttons: [
                    { text: 'Close', variant: 'secondary', onClick: () => Modal.hide() },
                ]
            });
        } catch (err) {
            Toast.error('加载失败 login logs: ' + err.message);
        }
    },

    async _deleteUser(user) {
        Modal.show({
            title: 'Delete 用户',
            content: `<p>确认操作 you want to delete user <strong>${Utils.escapeHtml(user.username)}</strong>? This action cannot be undone.</p>`,
            size: 'small',
            buttons: [
                { text: 'Cancel', variant: 'secondary', onClick: () => Modal.hide() },
                { text: 'Delete', variant: 'danger', onClick: async () => {
                    try {
                        await API.deleteUser(user.id);
                        Modal.hide();
                        Toast.success('用户 deleted');
                        this.render();
                    } catch (err) {
                        Toast.error(err.message);
                    }
                }},
            ]
        });
    }
};
