/* Alert Management Page */
const AlertsPage = {
    datasources: [],
    alerts: [],
    subscriptions: [],
    currentUser: null,
    filters: {
        datasource_id: null,
        status: 'all',
        severity: null,
        search: '',
        start_time: null,
        end_time: null
    },

    async init() {
        this.currentUser = Store.get('currentUser');
        if (!this.currentUser) {
            Router.navigate('login');
            return;
        }

        await this.loadDatasources();
        await this.loadAlerts();
        await this.loadSubscriptions();
        this.render();
    },

    async loadDatasources() {
        try {
            this.datasources = await API.get('/api/datasources');
        } catch (error) {
            console.error('Failed to load datasources:', error);
            this.datasources = [];
        }
    },

    async loadAlerts() {
        try {
            const params = new URLSearchParams();

            if (this.filters.datasource_id) {
                params.append('datasource_ids', this.filters.datasource_id);
            }
            if (this.filters.status && this.filters.status !== 'all') {
                params.append('status', this.filters.status);
            }
            if (this.filters.severity) {
                params.append('severity', this.filters.severity);
            }
            if (this.filters.search) {
                params.append('search', this.filters.search);
            }
            if (this.filters.start_time) {
                params.append('start_time', this.filters.start_time);
            }
            if (this.filters.end_time) {
                params.append('end_time', this.filters.end_time);
            }

            const response = await API.get(`/api/alerts?${params.toString()}`);
            this.alerts = response.alerts || [];
        } catch (error) {
            console.error('Failed to load alerts:', error);
            this.alerts = [];
        }
    },

    async loadSubscriptions() {
        try {
            this.subscriptions = await API.get(`/api/alerts/subscriptions/list?user_id=${this.currentUser.id}`);
        } catch (error) {
            console.error('Failed to load subscriptions:', error);
            this.subscriptions = [];
        }
    },

    render() {
        // Use standard header component
        const headerActions = DOM.el('div', { className: 'flex gap-8' });
        const addSubBtn = DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i>新建订阅',
            onClick: () => this.showSubscriptionModal()
        });
        headerActions.appendChild(addSubBtn);
        Header.render('告警管理', headerActions);

        const container = DOM.$('#page-content');
        DOM.clear(container);

        // Filters
        const filters = this.renderFilters();
        container.appendChild(filters);

        // Tabs
        const tabs = DOM.el('div', { className: 'tabs' });
        const alertsTab = DOM.el('button', {
            className: 'tab active',
            textContent: '告警列表',
            onClick: (e) => this.switchTab(e.target, 'alerts')
        });
        const subscriptionsTab = DOM.el('button', {
            className: 'tab',
            textContent: '订阅管理',
            onClick: (e) => this.switchTab(e.target, 'subscriptions')
        });
        tabs.appendChild(alertsTab);
        tabs.appendChild(subscriptionsTab);
        container.appendChild(tabs);

        // Tab content
        const tabContent = DOM.el('div', { className: 'tab-content' });
        const alertsContent = DOM.el('div', { className: 'tab-pane active', id: 'alerts-pane' });
        alertsContent.appendChild(this.renderAlertsList());
        const subscriptionsContent = DOM.el('div', { className: 'tab-pane', id: 'subscriptions-pane' });
        subscriptionsContent.appendChild(this.renderSubscriptionsList());
        tabContent.appendChild(alertsContent);
        tabContent.appendChild(subscriptionsContent);
        container.appendChild(tabContent);

        DOM.createIcons();
    },

    renderFilters() {
        const filters = DOM.el('div', { className: 'alert-filters' });

        // Datasource filter (single select)
        const datasourceFilter = DOM.el('div', { className: 'filter-group' });
        datasourceFilter.appendChild(DOM.el('label', { textContent: '数据源' }));
        const datasourceSelect = DOM.el('select', {
            className: 'form-control',
            value: this.filters.datasource_id || '',
            onChange: (e) => {
                this.filters.datasource_id = e.target.value ? parseInt(e.target.value) : null;
                this.loadAlerts().then(() => this.updateAlertsList());
            }
        });
        datasourceSelect.appendChild(DOM.el('option', { value: '', textContent: '全部' }));
        for (const ds of this.datasources) {
            datasourceSelect.appendChild(DOM.el('option', {
                value: ds.id,
                textContent: ds.name,
                selected: this.filters.datasource_id === ds.id
            }));
        }
        datasourceFilter.appendChild(datasourceSelect);
        filters.appendChild(datasourceFilter);

        // Status filter
        const statusFilter = DOM.el('div', { className: 'filter-group' });
        statusFilter.appendChild(DOM.el('label', { textContent: '状态' }));
        const statusSelect = DOM.el('select', {
            className: 'form-control',
            value: this.filters.status,
            onChange: (e) => {
                this.filters.status = e.target.value;
                this.loadAlerts().then(() => this.updateAlertsList());
            }
        });
        statusSelect.appendChild(DOM.el('option', { value: 'all', textContent: '全部' }));
        statusSelect.appendChild(DOM.el('option', { value: 'active', textContent: '活跃' }));
        statusSelect.appendChild(DOM.el('option', { value: 'acknowledged', textContent: '已确认' }));
        statusSelect.appendChild(DOM.el('option', { value: 'resolved', textContent: '已解决' }));
        statusFilter.appendChild(statusSelect);
        filters.appendChild(statusFilter);

        // Severity filter
        const severityFilter = DOM.el('div', { className: 'filter-group' });
        severityFilter.appendChild(DOM.el('label', { textContent: '严重程度' }));
        const severitySelect = DOM.el('select', {
            className: 'form-control',
            onChange: (e) => {
                this.filters.severity = e.target.value || null;
                this.loadAlerts().then(() => this.updateAlertsList());
            }
        });
        severitySelect.appendChild(DOM.el('option', { value: '', textContent: '全部' }));
        severitySelect.appendChild(DOM.el('option', { value: 'critical', textContent: '严重' }));
        severitySelect.appendChild(DOM.el('option', { value: 'high', textContent: '高' }));
        severitySelect.appendChild(DOM.el('option', { value: 'medium', textContent: '中' }));
        severitySelect.appendChild(DOM.el('option', { value: 'low', textContent: '低' }));
        severityFilter.appendChild(severitySelect);
        filters.appendChild(severityFilter);

        // Start time filter
        const startTimeFilter = DOM.el('div', { className: 'filter-group' });
        startTimeFilter.appendChild(DOM.el('label', { textContent: '开始时间' }));
        const startTimeInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'form-control',
            value: this.filters.start_time || '',
            onChange: (e) => {
                this.filters.start_time = e.target.value || null;
                this.loadAlerts().then(() => this.updateAlertsList());
            }
        });
        startTimeFilter.appendChild(startTimeInput);
        filters.appendChild(startTimeFilter);

        // End time filter
        const endTimeFilter = DOM.el('div', { className: 'filter-group' });
        endTimeFilter.appendChild(DOM.el('label', { textContent: '结束时间' }));
        const endTimeInput = DOM.el('input', {
            type: 'datetime-local',
            className: 'form-control',
            value: this.filters.end_time || '',
            onChange: (e) => {
                this.filters.end_time = e.target.value || null;
                this.loadAlerts().then(() => this.updateAlertsList());
            }
        });
        endTimeFilter.appendChild(endTimeInput);
        filters.appendChild(endTimeFilter);

        // Search filter
        const searchFilter = DOM.el('div', { className: 'filter-group' });
        searchFilter.appendChild(DOM.el('label', { textContent: '搜索' }));
        const searchInput = DOM.el('input', {
            type: 'text',
            className: 'form-control',
            placeholder: '搜索标题或内容',
            onInput: (e) => {
                this.filters.search = e.target.value;
                clearTimeout(this.searchTimeout);
                this.searchTimeout = setTimeout(() => {
                    this.loadAlerts().then(() => this.updateAlertsList());
                }, 500);
            }
        });
        searchFilter.appendChild(searchInput);
        filters.appendChild(searchFilter);

        return filters;
    },

    renderAlertsList() {
        const list = DOM.el('div', { className: 'alerts-list', id: 'alerts-list' });

        if (this.alerts.length === 0) {
            list.appendChild(DOM.el('div', {
                className: 'empty-state',
                textContent: '暂无告警'
            }));
            return list;
        }

        const table = DOM.el('table', { className: 'data-table' });
        const thead = DOM.el('thead');
        const headerRow = DOM.el('tr');
        headerRow.appendChild(DOM.el('th', { textContent: '严重程度' }));
        headerRow.appendChild(DOM.el('th', { textContent: '数据源' }));
        headerRow.appendChild(DOM.el('th', { textContent: '类型' }));
        headerRow.appendChild(DOM.el('th', { textContent: '标题' }));
        headerRow.appendChild(DOM.el('th', { textContent: '创建时间' }));
        headerRow.appendChild(DOM.el('th', { textContent: '状态' }));
        headerRow.appendChild(DOM.el('th', { textContent: '操作' }));
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = DOM.el('tbody');
        for (const alert of this.alerts) {
            const row = DOM.el('tr');

            // Severity badge
            const severityCell = DOM.el('td');
            const severityBadge = DOM.el('span', {
                className: `severity-badge severity-${alert.severity}`,
                textContent: this.getSeverityLabel(alert.severity)
            });
            severityCell.appendChild(severityBadge);
            row.appendChild(severityCell);

            // Datasource
            const datasource = this.datasources.find(ds => ds.id === alert.datasource_id);
            row.appendChild(DOM.el('td', { textContent: datasource ? datasource.name : `ID: ${alert.datasource_id}` }));

            // Type
            row.appendChild(DOM.el('td', { textContent: this.getAlertTypeLabel(alert.alert_type) }));

            // Title
            row.appendChild(DOM.el('td', { textContent: alert.title }));

            // Created time
            row.appendChild(DOM.el('td', { textContent: new Date(alert.created_at).toLocaleString('zh-CN') }));

            // Status
            const statusCell = DOM.el('td');
            const statusBadge = DOM.el('span', {
                className: `status-badge status-${alert.status}`,
                textContent: this.getStatusLabel(alert.status)
            });
            statusCell.appendChild(statusBadge);
            row.appendChild(statusCell);

            // Actions
            const actionsCell = DOM.el('td', { className: 'actions-cell' });
            const viewBtn = DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: '<i data-lucide="eye"></i>',
                title: '查看详情',
                onClick: () => this.showAlertDetail(alert)
            });
            actionsCell.appendChild(viewBtn);

            if (alert.status === 'active') {
                const ackBtn = DOM.el('button', {
                    className: 'btn btn-sm btn-primary',
                    innerHTML: '<i data-lucide="check"></i>',
                    title: '确认',
                    onClick: () => this.acknowledgeAlert(alert.id)
                });
                actionsCell.appendChild(ackBtn);
            }

            if (alert.status !== 'resolved') {
                const resolveBtn = DOM.el('button', {
                    className: 'btn btn-sm btn-success',
                    innerHTML: '<i data-lucide="check-check"></i>',
                    title: '解决',
                    onClick: () => this.resolveAlert(alert.id)
                });
                actionsCell.appendChild(resolveBtn);
            }

            row.appendChild(actionsCell);
            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        list.appendChild(table);

        return list;
    },

    renderSubscriptionsList() {
        const list = DOM.el('div', { className: 'subscriptions-list', id: 'subscriptions-list' });

        if (this.subscriptions.length === 0) {
            list.appendChild(DOM.el('div', {
                className: 'empty-state',
                textContent: '暂无订阅'
            }));
            return list;
        }

        const table = DOM.el('table', { className: 'data-table' });
        const thead = DOM.el('thead');
        const headerRow = DOM.el('tr');
        headerRow.appendChild(DOM.el('th', { textContent: '数据源' }));
        headerRow.appendChild(DOM.el('th', { textContent: '严重程度' }));
        headerRow.appendChild(DOM.el('th', { textContent: '通知渠道' }));
        headerRow.appendChild(DOM.el('th', { textContent: '状态' }));
        headerRow.appendChild(DOM.el('th', { textContent: '操作' }));
        thead.appendChild(headerRow);
        table.appendChild(thead);

        const tbody = DOM.el('tbody');
        for (const sub of this.subscriptions) {
            const row = DOM.el('tr');

            // Datasources
            const datasourceNames = sub.datasource_ids.length === 0
                ? '全部'
                : sub.datasource_ids.map(id => {
                    const ds = this.datasources.find(d => d.id === id);
                    return ds ? ds.name : `ID: ${id}`;
                }).join(', ');
            row.appendChild(DOM.el('td', { textContent: datasourceNames }));

            // Severity levels
            const severityText = sub.severity_levels.length === 0
                ? '全部'
                : sub.severity_levels.map(s => this.getSeverityLabel(s)).join(', ');
            row.appendChild(DOM.el('td', { textContent: severityText }));

            // Channels
            row.appendChild(DOM.el('td', { textContent: sub.channels.join(', ') }));

            // Status
            const statusCell = DOM.el('td');
            const statusBadge = DOM.el('span', {
                className: `status-badge ${sub.enabled ? 'status-active' : 'status-disabled'}`,
                textContent: sub.enabled ? '启用' : '禁用'
            });
            statusCell.appendChild(statusBadge);
            row.appendChild(statusCell);

            // Actions
            const actionsCell = DOM.el('td', { className: 'actions-cell' });
            const editBtn = DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: '<i data-lucide="edit"></i>',
                title: '编辑',
                onClick: () => this.showSubscriptionModal(sub)
            });
            const testBtn = DOM.el('button', {
                className: 'btn btn-sm btn-primary',
                innerHTML: '<i data-lucide="send"></i>',
                title: '测试通知',
                onClick: () => this.testNotification(sub.id)
            });
            const deleteBtn = DOM.el('button', {
                className: 'btn btn-sm btn-danger',
                innerHTML: '<i data-lucide="trash-2"></i>',
                title: '删除',
                onClick: () => this.deleteSubscription(sub.id)
            });
            actionsCell.appendChild(editBtn);
            actionsCell.appendChild(testBtn);
            actionsCell.appendChild(deleteBtn);
            row.appendChild(actionsCell);

            tbody.appendChild(row);
        }
        table.appendChild(tbody);
        list.appendChild(table);

        return list;
    },

    switchTab(tabEl, tabName) {
        // Update tab buttons
        DOM.$$('.tab').forEach(t => t.classList.remove('active'));
        tabEl.classList.add('active');

        // Update tab panes
        DOM.$$('.tab-pane').forEach(p => p.classList.remove('active'));
        DOM.$(`#${tabName}-pane`).classList.add('active');
    },

    updateAlertsList() {
        const listContainer = DOM.$('#alerts-list');
        if (listContainer) {
            DOM.clear(listContainer);
            const newList = this.renderAlertsList();
            listContainer.parentNode.replaceChild(newList, listContainer);
            DOM.createIcons();
        }
    },

    updateSubscriptionsList() {
        const listContainer = DOM.$('#subscriptions-list');
        if (listContainer) {
            DOM.clear(listContainer);
            const newList = this.renderSubscriptionsList();
            listContainer.parentNode.replaceChild(newList, listContainer);
            DOM.createIcons();
        }
    },

    async showAlertDetail(alert) {
        Modal.show({
            title: '告警详情',
            content: this.renderAlertDetailContent(alert),
            size: 'large',
            buttons: [
                {
                    text: '关闭',
                    className: 'btn-secondary',
                    onClick: () => modal.close()
                }
            ]
        });
    },

    renderAlertDetailContent(alert) {
        const content = DOM.el('div', { className: 'alert-detail' });

        const datasource = this.datasources.find(ds => ds.id === alert.datasource_id);

        const fields = [
            { label: '严重程度', value: this.getSeverityLabel(alert.severity), className: `severity-${alert.severity}` },
            { label: '数据源', value: datasource ? datasource.name : `ID: ${alert.datasource_id}` },
            { label: '告警类型', value: this.getAlertTypeLabel(alert.alert_type) },
            { label: '状态', value: this.getStatusLabel(alert.status) },
            { label: '标题', value: alert.title },
            { label: '创建时间', value: new Date(alert.created_at).toLocaleString('zh-CN') },
        ];

        if (alert.metric_name) {
            fields.push({ label: '指标名称', value: alert.metric_name });
        }
        if (alert.metric_value !== null) {
            fields.push({ label: '当前值', value: alert.metric_value.toFixed(2) });
        }
        if (alert.threshold_value !== null) {
            fields.push({ label: '阈值', value: alert.threshold_value.toFixed(2) });
        }
        if (alert.trigger_reason) {
            fields.push({ label: '触发原因', value: alert.trigger_reason });
        }
        if (alert.acknowledged_at) {
            fields.push({ label: '确认时间', value: new Date(alert.acknowledged_at).toLocaleString('zh-CN') });
        }
        if (alert.resolved_at) {
            fields.push({ label: '解决时间', value: new Date(alert.resolved_at).toLocaleString('zh-CN') });
        }

        for (const field of fields) {
            const fieldEl = DOM.el('div', { className: 'detail-field' });
            fieldEl.appendChild(DOM.el('label', { textContent: field.label }));
            const valueEl = DOM.el('div', {
                className: field.className ? `detail-value ${field.className}` : 'detail-value',
                textContent: field.value
            });
            fieldEl.appendChild(valueEl);
            content.appendChild(fieldEl);
        }

        // Content
        const contentField = DOM.el('div', { className: 'detail-field' });
        contentField.appendChild(DOM.el('label', { textContent: '详细内容' }));
        const contentValue = DOM.el('pre', {
            className: 'detail-content',
            textContent: alert.content
        });
        contentField.appendChild(contentValue);
        content.appendChild(contentField);

        return content;
    },

    async acknowledgeAlert(alertId) {
        if (!confirm('确认此告警？')) return;

        try {
            await API.post(`/api/alerts/${alertId}/acknowledge`, {
                user_id: this.currentUser.id
            });
            await this.loadAlerts();
            this.updateAlertsList();
            alert('告警已确认');
        } catch (error) {
            console.error('Failed to acknowledge alert:', error);
            alert('确认失败: ' + error.message);
        }
    },

    async resolveAlert(alertId) {
        if (!confirm('解决此告警？')) return;

        try {
            await API.post(`/api/alerts/${alertId}/resolve`, {});
            await this.loadAlerts();
            this.updateAlertsList();
            alert('告警已解决');
        } catch (error) {
            console.error('Failed to resolve alert:', error);
            alert('解决失败: ' + error.message);
        }
    },

    showSubscriptionModal(subscription = null) {
        const isEdit = !!subscription;
        const formData = subscription || {
            datasource_ids: [],
            severity_levels: [],
            time_ranges: [],
            channels: [],
            webhook_url: '',
            enabled: true,
            aggregation_script: ''
        };

        const content = this.renderSubscriptionForm(formData);

        Modal.show({
            title: isEdit ? '编辑订阅' : '新建订阅',
            content,
            size: 'large',
            buttons: [
                {
                    text: '取消',
                    className: 'btn-secondary',
                    onClick: () => modal.close()
                },
                {
                    text: '保存',
                    className: 'btn-primary',
                    onClick: async () => {
                        const data = this.getSubscriptionFormData();
                        if (!data) return;

                        try {
                            if (isEdit) {
                                await API.put(`/api/alerts/subscriptions/${subscription.id}`, data);
                            } else {
                                data.user_id = this.currentUser.id;
                                await API.post('/api/alerts/subscriptions', data);
                            }
                            await this.loadSubscriptions();
                            this.updateSubscriptionsList();
                            modal.close();
                            alert('保存成功');
                        } catch (error) {
                            console.error('Failed to save subscription:', error);
                            alert('保存失败: ' + error.message);
                        }
                    }
                }
            ]
        });
    },

    renderSubscriptionForm(data) {
        const form = DOM.el('div', { className: 'subscription-form', id: 'subscription-form' });

        // Datasource multi-select
        const datasourceGroup = DOM.el('div', { className: 'form-group' });
        datasourceGroup.appendChild(DOM.el('label', { textContent: '数据源（留空表示全部）' }));
        const datasourceSelect = DOM.el('select', {
            multiple: true,
            className: 'form-control',
            id: 'sub-datasources'
        });
        for (const ds of this.datasources) {
            const option = DOM.el('option', {
                value: ds.id,
                textContent: ds.name,
                selected: data.datasource_ids.includes(ds.id)
            });
            datasourceSelect.appendChild(option);
        }
        datasourceGroup.appendChild(datasourceSelect);
        form.appendChild(datasourceGroup);

        // Severity checkboxes
        const severityGroup = DOM.el('div', { className: 'form-group' });
        severityGroup.appendChild(DOM.el('label', { textContent: '严重程度（留空表示全部）' }));
        const severityOptions = DOM.el('div', { className: 'checkbox-group' });
        for (const severity of ['critical', 'high', 'medium', 'low']) {
            const checkbox = DOM.el('label', { className: 'checkbox-label' });
            const input = DOM.el('input', {
                type: 'checkbox',
                value: severity,
                checked: data.severity_levels.includes(severity),
                className: 'severity-checkbox'
            });
            checkbox.appendChild(input);
            checkbox.appendChild(DOM.el('span', { textContent: this.getSeverityLabel(severity) }));
            severityOptions.appendChild(checkbox);
        }
        severityGroup.appendChild(severityOptions);
        form.appendChild(severityGroup);

        // Channels
        const channelsGroup = DOM.el('div', { className: 'form-group' });
        channelsGroup.appendChild(DOM.el('label', { textContent: '通知渠道' }));
        const channelsOptions = DOM.el('div', { className: 'checkbox-group' });
        for (const channel of ['email', 'sms', 'phone', 'webhook']) {
            const checkbox = DOM.el('label', { className: 'checkbox-label' });
            const input = DOM.el('input', {
                type: 'checkbox',
                value: channel,
                checked: data.channels.includes(channel),
                className: 'channel-checkbox'
            });
            checkbox.appendChild(input);
            checkbox.appendChild(DOM.el('span', { textContent: channel.toUpperCase() }));
            channelsOptions.appendChild(checkbox);
        }
        channelsGroup.appendChild(channelsOptions);
        form.appendChild(channelsGroup);

        // Webhook URL
        const webhookGroup = DOM.el('div', { className: 'form-group' });
        webhookGroup.appendChild(DOM.el('label', { textContent: 'Webhook URL（选择webhook渠道时必填）' }));
        const webhookInput = DOM.el('input', {
            type: 'text',
            className: 'form-control',
            id: 'sub-webhook-url',
            value: data.webhook_url || '',
            placeholder: 'https://example.com/webhook'
        });
        webhookGroup.appendChild(webhookInput);
        form.appendChild(webhookGroup);

        // Enabled toggle
        const enabledGroup = DOM.el('div', { className: 'form-group' });
        const enabledLabel = DOM.el('label', { className: 'checkbox-label' });
        const enabledInput = DOM.el('input', {
            type: 'checkbox',
            id: 'sub-enabled',
            checked: data.enabled
        });
        enabledLabel.appendChild(enabledInput);
        enabledLabel.appendChild(DOM.el('span', { textContent: '启用订阅' }));
        enabledGroup.appendChild(enabledLabel);
        form.appendChild(enabledGroup);

        return form;
    },

    getSubscriptionFormData() {
        const datasourceIds = Array.from(DOM.$$('#sub-datasources option:checked')).map(opt => parseInt(opt.value));
        const severityLevels = Array.from(DOM.$$('.severity-checkbox:checked')).map(cb => cb.value);
        const channels = Array.from(DOM.$$('.channel-checkbox:checked')).map(cb => cb.value);
        const webhookUrl = DOM.$('#sub-webhook-url').value.trim();
        const enabled = DOM.$('#sub-enabled').checked;

        if (channels.length === 0) {
            alert('请至少选择一个通知渠道');
            return null;
        }

        if (channels.includes('webhook') && !webhookUrl) {
            alert('选择webhook渠道时必须填写Webhook URL');
            return null;
        }

        return {
            datasource_ids: datasourceIds,
            severity_levels: severityLevels,
            time_ranges: [],  // Simplified for now
            channels,
            webhook_url: webhookUrl || null,
            enabled,
            aggregation_script: null  // Simplified for now
        };
    },

    async testNotification(subscriptionId) {
        if (!confirm('发送测试通知？')) return;

        try {
            const result = await API.post(`/api/alerts/subscriptions/${subscriptionId}/test`, {});
            alert(`测试通知已发送\n${JSON.stringify(result.deliveries, null, 2)}`);
        } catch (error) {
            console.error('Failed to test notification:', error);
            alert('测试失败: ' + error.message);
        }
    },

    async deleteSubscription(subscriptionId) {
        if (!confirm('确认删除此订阅？')) return;

        try {
            await API.delete(`/api/alerts/subscriptions/${subscriptionId}`);
            await this.loadSubscriptions();
            this.updateSubscriptionsList();
            alert('订阅已删除');
        } catch (error) {
            console.error('Failed to delete subscription:', error);
            alert('删除失败: ' + error.message);
        }
    },

    getSeverityLabel(severity) {
        const labels = {
            critical: '严重',
            high: '高',
            medium: '中',
            low: '低'
        };
        return labels[severity] || severity;
    },

    getStatusLabel(status) {
        const labels = {
            active: '活跃',
            acknowledged: '已确认',
            resolved: '已解决'
        };
        return labels[status] || status;
    },

    getAlertTypeLabel(type) {
        const labels = {
            threshold_violation: '超过阈值',
            custom_expression: '自定义表达式',
            system_error: '系统错误'
        };
        return labels[type] || type;
    }
};
