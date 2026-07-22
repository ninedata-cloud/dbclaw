/* User management page (admin only) */
const UsersPage = {
    _maskPhone(phone) {
        if (!phone) return '-';
        const trimmed = String(phone).trim();
        if (trimmed.length < 7) return trimmed;
        return `${trimmed.slice(0, 3)}****${trimmed.slice(-4)}`;
    },

    async render() {
        Header.render(I18n.t('pageCopy.users.userManagement'), DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: `<i data-lucide="plus"></i> ${I18n.t('users.newUser')}`,
            onClick: () => this._showCreateModal()
        }));

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const users = await API.getUsers();
            content.innerHTML = '';

            const info = DOM.el('div', { className: 'flex-between mb-16' });
            info.appendChild(DOM.el('span', { className: 'text-muted text-sm', textContent: I18n.t('pageCopy.users.userCount', { value0: users.length }) }));
            content.appendChild(info);

            const table = DOM.el('table', { className: 'data-table' });
            table.innerHTML = I18n.t('pageCopy.users.usernameDisplayNameEmailPhoneRoleStatus');
            const tbody = DOM.el('tbody');

            for (const user of users) {
                const tr = DOM.el('tr');
                tr.innerHTML = `
                    <td><strong>${Utils.escapeHtml(user.username)}</strong></td>
                    <td>${Utils.escapeHtml(user.display_name || '-')}</td>
                    <td>${Utils.escapeHtml(user.email || '-')}</td>
                    <td>${Utils.escapeHtml(this._maskPhone(user.phone))}</td>
                    <td><span class="badge ${user.is_admin ? 'badge-primary' : 'badge-secondary'}">${user.is_admin ? I18n.t('pageCopy.users.administrator') : I18n.t('pageCopy.users.user')}</span></td>
                    <td><span class="badge ${user.is_active ? 'badge-success' : 'badge-secondary'}">${user.is_active ? I18n.t('pageCopy.users.active') : I18n.t('pageCopy.users.disable')}</span></td>
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
                    title: I18n.t('pageCopy.users.editUser'),
                    onClick: () => this._showEditModal(user)
                });
                actionsCell.appendChild(editBtn);

                // Toggle status button
                if (!isSelf) {
                    const toggleBtn = DOM.el('button', {
                        className: `btn btn-sm ${user.is_active ? 'btn-warning' : 'btn-success'}`,
                        innerHTML: `<i data-lucide="${user.is_active ? 'user-x' : 'user-check'}"></i>`,
                        title: user.is_active ? I18n.t('pageCopy.users.disable') : I18n.t('pageCopy.users.enable'),
                        onClick: () => this._toggleStatus(user)
                    });
                    actionsCell.appendChild(toggleBtn);
                }

                // Reset password button
                if (canResetPassword) {
                    const resetBtn = DOM.el('button', {
                        className: 'btn btn-sm btn-secondary',
                        innerHTML: '<i data-lucide="key"></i>',
                        title: I18n.t('pageCopy.users.resetPassword'),
                        onClick: () => this._showResetPasswordModal(user)
                    });
                    actionsCell.appendChild(resetBtn);
                }

                // Login logs button
                const logsBtn = DOM.el('button', {
                    className: 'btn btn-sm btn-secondary',
                    innerHTML: '<i data-lucide="scroll-text"></i>',
                    title: I18n.t('pageCopy.users.signInHistory'),
                    onClick: () => this._showLoginLogs(user)
                });
                actionsCell.appendChild(logsBtn);

                // Delete button
                if (!isSelf) {
                    const deleteBtn = DOM.el('button', {
                        className: 'btn btn-sm btn-danger',
                        innerHTML: '<i data-lucide="trash-2"></i>',
                        title: I18n.t('pageCopy.users.delete'),
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
            Toast.error(I18n.t('pageCopy.users.loadFailed') + ': ' + err.message);
        }
    },

    _showCreateModal() {
        const form = DOM.el('div');
        form.innerHTML = I18n.t('pageCopy.users.usernamePasswordDisplayNameEmailPhoneAdministrator', { value0: I18n.t('placeholders.username'), value1: I18n.t('placeholders.passwordMin'), value2: I18n.t('placeholders.displayNameOptional'), value3: I18n.t('placeholders.emailOptional'), value4: I18n.t('placeholders.phoneOptional') });

        Modal.show({
            title: I18n.t('pageCopy.users.newUser'),
            content: form,
            buttons: [
                { text: I18n.t('pageCopy.users.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('pageCopy.users.create'), variant: 'primary', onClick: () => this._createUser() },
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
            Toast.error(I18n.t('users.credentialsRequired'));
            return;
        }
        if (password.length < 6) {
            Toast.error(I18n.t('pageCopy.users.passwordMustBeAtLeast6Characters'));
            return;
        }

        try {
            await API.createUser({ username, password, display_name: display_name || null, email: email || null, phone: phone || null, is_admin });
            Modal.hide();
            Toast.success(I18n.t('pageCopy.users.userCreated'));
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
        form.innerHTML = I18n.t('pageCopy.users.displayNameEmailPhoneAdministrator', { value0: I18n.t('placeholders.displayNameOptional'), value1: Utils.escapeHtml(user.display_name || ''), value2: I18n.t('placeholders.emailOptional'), value3: Utils.escapeHtml(user.email || ''), value4: I18n.t('placeholders.phoneOptional'), value5: Utils.escapeHtml(user.phone || ''), value6: user.is_admin ? 'checked' : '' });

        Modal.show({
            title: I18n.t('pageCopy.users.editUserValue', { value0: Utils.escapeHtml(user.username) }),
            content: form,
            buttons: [
                { text: I18n.t('pageCopy.users.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('pageCopy.users.save'), variant: 'primary', onClick: async () => {
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
                        Toast.success(I18n.t('pageCopy.users.userUpdated'));
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
            <p style="margin-bottom:12px;color:var(--text-secondary)">${I18n.t('users.resetFor', { username: `<strong>${Utils.escapeHtml(user.username)}</strong>` })}</p>
            <div class="form-group">
                <label>${I18n.t('pageCopy.users.newPassword')}</label>
                <input type="password" id="reset-password" class="form-input" placeholder="${I18n.t('placeholders.newPasswordMin')}">
            </div>
        `;

        Modal.show({
            title: I18n.t('pageCopy.users.resetPassword'),
            content: form,
            size: 'small',
            buttons: [
                { text: I18n.t('common.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('pageCopy.users.reset'), variant: 'primary', onClick: async () => {
                    const pw = DOM.$('#reset-password').value;
                    if (!pw || pw.length < 6) {
                        Toast.error(I18n.t('pageCopy.users.passwordMustBeAtLeast6Characters'));
                        return;
                    }
                    try {
                        await API.resetUserPassword(user.id, pw);
                        Modal.hide();
                        Toast.success(I18n.t('users.passwordReset'));
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
                container.innerHTML = `<p style="text-align:center;color:var(--text-muted);padding:24px;">${I18n.t('users.noLoginLogs')}</p>`;
            } else {
                const table = DOM.el('table', { className: 'data-table' });
                table.innerHTML = I18n.t('pageCopy.users.timeIpAddressUserAgentResult');
                const tbody = DOM.el('tbody');
                for (const log of logs) {
                    const loginTime = log.login_time || log.logged_in_at;
                    const isSuccess = log.success ?? log.is_success;
                    const tr = DOM.el('tr');
                    tr.innerHTML = `
                        <td style="white-space:nowrap">${Format.datetime(loginTime)}</td>
                        <td>${Utils.escapeHtml(log.ip_address || '-')}</td>
                        <td style="max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${Utils.escapeHtml(log.user_agent || '')}">${Utils.escapeHtml(log.user_agent || '-')}</td>
                        <td><span class="badge ${isSuccess ? 'badge-success' : 'badge-danger'}">${I18n.t(isSuccess ? 'common.success' : 'common.failed')}</span></td>
                    `;
                    tbody.appendChild(tr);
                }
                table.appendChild(tbody);
                const tableContainer = DOM.el('div', { className: 'data-table-container', style: { maxHeight: '400px', overflow: 'auto' } });
                tableContainer.appendChild(table);
                container.appendChild(tableContainer);
            }

            Modal.show({
                title: I18n.t('users.loginLogsTitle', { username: user.username }),
                content: container,
                size: 'large',
                buttons: [
                    { text: I18n.t('common.close'), variant: 'secondary', onClick: () => Modal.hide() },
                ]
            });
        } catch (err) {
            Toast.error(I18n.t('users.loadLoginLogsFailed', { message: err.message }));
        }
    },

    async _deleteUser(user) {
        Modal.show({
            title: I18n.t('users.deleteTitle'),
            content: `<p>${I18n.t('users.deleteConfirm', { username: Utils.escapeHtml(user.username) })}</p>`,
            size: 'small',
            buttons: [
                { text: I18n.t('common.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('common.delete'), variant: 'danger', onClick: async () => {
                    try {
                        await API.deleteUser(user.id);
                        Modal.hide();
                        Toast.success(I18n.t('users.deleted'));
                        this.render();
                    } catch (err) {
                        Toast.error(err.message);
                    }
                }},
            ]
        });
    }
};
