/* Hosts management page */
const HostsPage = {
    allHosts: [],
    filteredHosts: [],
    _filters: {
        search: ''
    },
    _sort: {
        field: 'name',
        direction: 'asc'
    },

    async render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            this.allHosts = await API.getHosts();
            this.filteredHosts = [...this.allHosts];
            this._applySort();
            Store.set('hosts', this.allHosts);

            Header.render(I18n.t('pageCopy.hosts.hostManagement'), this._buildHeaderActions());
            content.innerHTML = '';

            if (this.allHosts.length === 0) {
                content.innerHTML = I18n.t('pageCopy.hosts.noHostsAddYourFirstHostTo');
                DOM.createIcons();
                return;
            }

            // Table container
            const tableContainer = DOM.el('div', { id: 'host-table-container' });
            content.appendChild(tableContainer);

            this._renderTable();
            DOM.createIcons();

        } catch (err) {
            Toast.error(I18n.t('pageCopy.hosts.loadFailed') + ': ' + err.message);
        }
    },

    _buildHeaderActions() {
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters' });
        filtersContainer.innerHTML = I18n.t('pageCopy.hosts.search', { value0: I18n.t('placeholders.searchHost') });

        const addBtn = DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: I18n.t('pageCopy.hosts.newHost'),
            onClick: () => this._showForm(null)
        });

        setTimeout(() => {
            const btnSearch = DOM.$('#btn-search');
            const filterSearch = DOM.$('#filter-search');

            if (btnSearch) {
                btnSearch.addEventListener('click', () => this._applyFilters());
            }
            if (filterSearch) {
                filterSearch.addEventListener('input', () => this._applyFilters());
                filterSearch.addEventListener('keypress', (e) => {
                    if (e.key === 'Enter') this._applyFilters();
                });
            }
            DOM.createIcons();
        }, 0);

        return [filtersContainer, addBtn];
    },

    _applyFilters() {
        this._filters.search = DOM.$('#filter-search')?.value.trim().toLowerCase() || '';

        this.filteredHosts = this.allHosts.filter(h => {
            if (!this._filters.search) return true;
            return h.name.toLowerCase().includes(this._filters.search) ||
                   h.host.toLowerCase().includes(this._filters.search);
        });

        this._applySort();
        this._renderTable();
    },

    _toggleSort(field) {
        if (this._sort.field === field) {
            this._sort.direction = this._sort.direction === 'asc' ? 'desc' : 'asc';
        } else {
            this._sort.field = field;
            this._sort.direction = 'asc';
        }
        this._applySort();
    },

    _applySort() {
        const { field, direction } = this._sort;
        this.filteredHosts.sort((a, b) => {
            let va = a[field];
            let vb = b[field];
            const vaNull = va == null;
            const vbNull = vb == null;
            if (vaNull) va = direction === 'asc' ? Infinity : -Infinity;
            if (vbNull) vb = direction === 'asc' ? Infinity : -Infinity;
            if (typeof va === 'string') va = va.toLowerCase();
            if (typeof vb === 'string') vb = vb.toLowerCase();
            if (vaNull && vbNull) return 0;
            if (vaNull) return 1;
            if (vbNull) return -1;
            if (va < vb) return direction === 'asc' ? -1 : 1;
            if (va > vb) return direction === 'asc' ? 1 : -1;
            return 0;
        });
    },

    _updateSortIcons() {
        document.querySelectorAll('.sort-icon').forEach(icon => {
            const field = icon.dataset.field;
            if (field === this._sort.field) {
                icon.textContent = this._sort.direction === 'asc' ? '▲' : '▼';
            } else {
                icon.textContent = '';
            }
        });
    },

    _renderTable() {
        const container = DOM.$('#host-table-container');
        if (!container) return;

        container.innerHTML = I18n.t('pageCopy.hosts.idNameHostPortStatusCpuMemory', { value0: this.filteredHosts.map(host => this._renderHostRow(host)).join('') });
        this._updateSortIcons();
        container.querySelectorAll('th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const field = th.dataset.sort;
                this._toggleSort(field);
                this._renderTable();
            });
        });
        DOM.createIcons();
    },

    _renderHostRow(host) {
        const statusBadge = this._getStatusBadge(host);
        const cpuColor = this._getMetricColor(host.cpu_usage);
        const memColor = this._getMetricColor(host.memory_usage);
        const diskColor = this._getMetricColor(host.disk_usage);

        return I18n.t('pageCopy.hosts.hostRow', { value0: host.id, value1: host.name, value2: host.host, value3: host.port, value4: statusBadge, value5: cpuColor, value6: host.cpu_usage != null ? host.cpu_usage.toFixed(1) + '%' : '-', value7: memColor, value8: host.memory_usage != null ? host.memory_usage.toFixed(1) + '%' : '-', value9: diskColor, value10: host.disk_usage != null ? host.disk_usage.toFixed(1) + '%' : '-', value11: host.id, value12: host.id, value13: host.id, value14: host.id });
    },

    _getStatusBadge(host) {
        const status = host.status || 'offline';
        const message = host.status_message || '';

        const statusMap = {
            normal: { icon: '✓', label: I18n.t('pageCopy.hosts.healthy'), class: 'badge-success', title: message || I18n.t('pageCopy.hosts.allMetricsAreHealthy') },
            warning: { icon: '⚠', label: I18n.t('pageCopy.hosts.abnormal'), class: 'badge-warning', title: message || I18n.t('pageCopy.hosts.someMetricsAreNearThresholds') },
            error: { icon: '✗', label: I18n.t('pageCopy.hosts.critical'), class: 'badge-danger', title: message || I18n.t('pageCopy.hosts.someMetricsExceededThresholds') },
            offline: { icon: '○', label: I18n.t('pageCopy.hosts.offline'), class: 'badge-secondary', title: message || I18n.t('pageCopy.hosts.noMonitoringData') },
            unknown: { icon: '○', label: I18n.t('pageCopy.hosts.unknown'), class: 'badge-secondary', title: message || I18n.t('pageCopy.hosts.noMonitoringData') }
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
                Toast.success(I18n.t('pageCopy.hosts.connected'));
            } else {
                Toast.error(result.message || I18n.t('common.failed'));
            }
            // 重新加载主机列表以更新状态和指标
            await this.render();
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        } finally {
            btn.innerHTML = '<i data-lucide="plug"></i>';
            btn.disabled = false;
            DOM.createIcons();
        }
    },

    _viewDetail(id) {
        Router.navigate(`host-detail?host=${id}`);
    },

    _editHost(id) {
        const host = this.allHosts.find(h => h.id === id);
        if (host) this._showForm(host);
    },

    async _deleteHost(id) {
        const host = this.allHosts.find(h => h.id === id);
        if (!host || !confirm(I18n.t('pageCopy.hosts.confirmHostDeletionValueThisActionCannot', { value0: host.name }))) return;
        try {
            await API.deleteHost(id);
            Toast.success(I18n.t('pageCopy.hosts.hostDeleted'));
            this.render();
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        }
    },

    _showForm(host) {
        const isEdit = !!host;
        const form = DOM.el('form');
        form.innerHTML = I18n.t('pageCopy.hosts.nameHostPortUsernameAuthenticationMethodPassword', { value0: I18n.t('placeholders.hostName'), value1: host?.name || '', value2: host?.host || '', value3: host?.port || 22, value4: host?.username || '', value5: host?.auth_type === 'password' || !host ? 'selected' : '', value6: host?.auth_type === 'key' ? 'selected' : '', value7: isEdit ? I18n.t('placeholders.keepUnchanged') : '' });

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

        const submitBtn = DOM.el('button', {
            className: 'btn btn-primary',
            textContent: isEdit ? I18n.t('pageCopy.hosts.update') : I18n.t('pageCopy.hosts.create'),
            type: 'button',
            onClick: () => form.requestSubmit()
        });

        const getFormData = () => {
            const data = Object.fromEntries(new FormData(form).entries());
            data.port = parseInt(data.port, 10);
            if (!data.password) delete data.password;
            if (!data.private_key) delete data.private_key;
            return data;
        };

        const testBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            innerHTML: I18n.t('pageCopy.hosts.testConnection'),
            type: 'button',
            onClick: async (e) => {
                const btn = e.currentTarget;
                const rawText = btn.textContent;
                btn.innerHTML = '<div class="spinner"></div>';
                btn.disabled = true;
                try {
                    const result = await API.testHostConnection(getFormData());
                    if (result.success) {
                        Toast.success(I18n.t('pageCopy.hosts.connected'));
                    } else {
                        Toast.error(result.message || I18n.t('common.failed'));
                    }
                } catch (err) {
                    Toast.error(err.message || I18n.t('common.requestFailed'));
                } finally {
                    btn.innerHTML = `<i data-lucide="plug"></i> ${rawText}`;
                    btn.disabled = false;
                    DOM.createIcons();
                }
            }
        });

        DOM.bindAsyncSubmit(form, async () => {
            const data = getFormData();
            try {
                if (isEdit) {
                    await API.updateHost(host.id, data);
                    Toast.success(I18n.t('pageCopy.hosts.hostUpdated'));
                } else {
                    await API.createHost(data);
                    Toast.success(I18n.t('pageCopy.hosts.hostCreated'));
                }
                Modal.hide();
                this.render();
            } catch (err) {
                Toast.error(err.message);
            }
        }, { submitControls: [submitBtn] });

        const footer = DOM.el('div');
        footer.style.width = '100%';
        footer.style.justifyContent = 'space-between';

        const footerLeft = DOM.el('div');
        const footerRight = DOM.el('div', { style: 'display:flex;gap:8px;' });
        footerLeft.appendChild(testBtn);
        footerRight.appendChild(DOM.el('button', { className: 'btn btn-secondary', textContent: I18n.t('pageCopy.hosts.cancel'), type: 'button', onClick: () => Modal.hide() }));
        footerRight.appendChild(submitBtn);
        footer.appendChild(footerLeft);
        footer.appendChild(footerRight);

        Modal.show({ title: isEdit ? I18n.t('pageCopy.hosts.editHost') : I18n.t('pageCopy.hosts.newHost2'), content: form, footer });
    },
};
