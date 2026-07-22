/* Scheduled task management page */
const ScheduledTasksPage = {
    tasks: [],
    notificationIntegrations: [],
    currentEditingTask: null,

    render() {
        const content = DOM.$('#page-content');
        content.innerHTML = I18n.t('pageCopy.scheduledTasks.loadingTaskSchedulingConfiguration');
        Header.render(I18n.t('pageCopy.scheduledTasks.taskScheduling'), this._buildHeaderActions());
        this.loadTasks();
    },

    _buildHeaderActions() {
        const filters = DOM.el('div', { className: 'dashboard-filters' });
        filters.innerHTML = I18n.t('pageCopy.scheduledTasks.allStatusesEnabledDisabledAllResultsSuccess', { value0: I18n.t('placeholders.searchTasks') });

        const addBtn = DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: I18n.t('pageCopy.scheduledTasks.newTask'),
            onClick: () => this.showTaskModal()
        });

        setTimeout(() => {
            DOM.$('#scheduled-task-keyword')?.addEventListener('keypress', (event) => {
                if (event.key === 'Enter') this.loadTasks();
            });
            DOM.$('#scheduled-task-enabled')?.addEventListener('change', () => this.loadTasks());
            DOM.$('#scheduled-task-last-status')?.addEventListener('change', () => this.loadTasks());
        }, 0);

        return [filters, addBtn];
    },

    async loadTasks() {
        const content = DOM.$('#page-content');
        try {
            await this.loadNotificationIntegrations();
            const params = {};
            const keyword = DOM.$('#scheduled-task-keyword')?.value.trim();
            const enabled = DOM.$('#scheduled-task-enabled')?.value;
            const lastStatus = DOM.$('#scheduled-task-last-status')?.value;
            if (keyword) params.keyword = keyword;
            if (enabled) params.enabled = enabled;
            if (lastStatus) params.last_status = lastStatus;

            this.tasks = await API.getScheduledTasks(Object.keys(params).length ? params : null);
            content.innerHTML = I18n.t('pageCopy.scheduledTasks.taskScheduleEnableLastRunNextRun', { value0: this.renderRows() });
            DOM.createIcons();
        } catch (error) {
            console.error('Failed to load scheduled tasks:', error);
            Toast.error(I18n.t('pageCopy.scheduledTasks.loadingTaskFailedValueRetry', { value0: Utils.escapeHtml(error.message) }));
            content.innerHTML = I18n.t('pageCopy.scheduledTasks.loadingTaskFailedValueRetry', { value0: Utils.escapeHtml(error.message) });
        }
    },

    renderRows() {
        if (!this.tasks.length) {
            return I18n.t('pageCopy.scheduledTasks.noScheduledTasks');
        }
        return this.tasks.map(task => I18n.t('pageCopy.scheduledTasks.taskRow', { value0: Utils.escapeHtml(task.name), value1: Utils.escapeHtml(task.description || I18n.t('pageCopy.scheduledTasks.noDescriptionYet')), value2: this.formatSchedule(task), value3: task.enabled ? I18n.t('pageCopy.scheduledTasks.enabled') : I18n.t('pageCopy.scheduledTasks.disabled'), value4: this.formatDate(task.last_run_at), value5: this.formatDate(task.next_run_at), value6: this.renderStatus(task.last_status, task.last_error), value7: task.id, value8: task.id, value9: task.id, value10: task.id, value11: task.enabled ? I18n.t('pageCopy.scheduledTasks.disabledLabel') : I18n.t('pageCopy.scheduledTasks.enable'), value12: task.enabled ? 'pause' : 'power', value13: task.id })).join('');
    },

    formatSchedule(task) {
        const config = task.schedule_config || {};
        if (task.schedule_type === 'interval') {
            const seconds = Number(config.interval_seconds || 0);
            const expression = this.intervalSecondsToCronExpression(seconds || 60);
            return I18n.t('pageCopy.scheduledTasks.cronValueOriginalInterval', { value0: Utils.escapeHtml(expression) });
        }
        if (config.preset === 'hourly') {
            return I18n.t('pageCopy.scheduledTasks.hourlyValueValue', { value0: String(config.minute ?? 0).padStart(2, '0'), value1: String(config.second ?? 0).padStart(2, '0') });
        }
        if (config.preset === 'daily') {
            return I18n.t('pageCopy.scheduledTasks.everyDayValue', { value0: Utils.escapeHtml(config.time || '00:00:00') });
        }
        if (config.preset === 'weekly') {
            return I18n.t('pageCopy.scheduledTasks.weeklyValueValue', { value0: this.weekdayLabel(config.day_of_week), value1: Utils.escapeHtml(config.time || '00:00:00') });
        }
        if (config.preset === 'monthly') {
            return I18n.t('pageCopy.scheduledTasks.monthlyValueValue', { value0: config.day ?? 1, value1: Utils.escapeHtml(config.time || '00:00:00') });
        }
        const expression = (config.expression || '').trim() || '-';
        return `<span class="task-mono">cron: ${Utils.escapeHtml(expression)}</span>`;
    },

    /** 将历史「间隔秒」近似为 5/6 段 Cron，便于迁移为纯 Cron 任务。 */
    intervalSecondsToCronExpression(seconds) {
        const sec = Math.max(1, Math.floor(Number(seconds) || 60));
        if (sec <= 59) return `*/${sec} * * * * *`;
        if (sec % 60 === 0) {
            const m = sec / 60;
            if (m > 0 && m < 1440) return `0 */${m} * * * *`;
        }
        if (sec % 3600 === 0) {
            const h = sec / 3600;
            if (h > 0 && h <= 23) return `0 0 */${h} * * *`;
        }
        if (sec % 86400 === 0) {
            const d = sec / 86400;
            if (d > 0) return `0 0 0 */${d} * *`;
        }
        return '0 * * * * *';
    },

    formatDate(value) {
        return value ? Format.datetime(value) : '-';
    },

    renderStatus(status, error) {
        if (!status) return '-';
        const labels = { success: I18n.t('pageCopy.scheduledTasks.success'), failed: I18n.t('pageCopy.scheduledTasks.failed'), skipped: I18n.t('pageCopy.scheduledTasks.skip'), running: I18n.t('pageCopy.scheduledTasks.running'), pending: I18n.t('pageCopy.scheduledTasks.waiting') };
        const title = error ? ` title="${this.escapeAttr(error)}"` : '';
        return `<span class="task-chip ${status}"${title}>${labels[status] || status}</span>`;
    },

    async loadNotificationIntegrations() {
        try {
            const items = await API.get('/api/integrations');
            this.notificationIntegrations = (items || []).filter(item => item.integration_type === 'outbound_notification' && item.enabled);
        } catch (error) {
            console.error('Failed to load notification integrations:', error);
            this.notificationIntegrations = [];
        }
    },

    showTaskModal(taskId = null) {
        const task = taskId ? this.tasks.find(item => item.id === taskId) : null;
        const isEdit = Boolean(task);
        this.currentEditingTask = task;
        const config = this.denormalizeSchedule(task);
        const code = task?.script_code || [
            'async def run(context):',
            '    print("Task initiated")',
            '    return {"success": True}',
            ''
        ].join('\n');

        Modal.show({
            title: isEdit ? I18n.t('pageCopy.scheduledTasks.editTask') : I18n.t('pageCopy.scheduledTasks.newTask2'),
            size: 'xlarge',
            containerClassName: 'scheduled-task-editor-modal',
            bodyClassName: 'scheduled-task-modal-body',
            content: I18n.t("pageCopy.scheduledTasks.showTaskModalContent", { value0: isEdit ? 'TASK CONFIGURATION' : 'NEW SCHEDULED TASK', value1: this.escapeAttr(task?.name || ''), value2: task?.enabled === false ? '' : 'checked', value3: task?.timeout_seconds || 60, value4: I18n.t('scheduledTasks.descriptionPlaceholder'), value5: Utils.escapeHtml(task?.description || ''), value6: config.preset === 'hourly' ? 'selected' : '', value7: config.preset === 'daily' ? 'selected' : '', value8: config.preset === 'weekly' ? 'selected' : '', value9: config.preset === 'monthly' ? 'selected' : '', value10: config.preset === 'custom' ? 'selected' : '', value11: config.minute, value12: I18n.t('scheduledTasks.hourlyMinuteTitle'), value13: config.second, value14: I18n.t('scheduledTasks.minuteSecondTitle'), value15: this.escapeAttr(config.time), value16: [0, 1, 2, 3, 4, 5, 6].map(day => I18n.t('pageCopy.scheduledTasks.showTaskModalContent2', {
                                            value0: day,
                                            value1: Number(config.day_of_week) === day ? 'selected' : '',
                                            value2: this.weekdayLabel(day)
                                        })).join(''), value17: config.day, value18: this.escapeAttr(config.expression), value19: [
                                        ['never', I18n.t('pageCopy.scheduledTasks.showTaskModalContent3')],
                                        ['on_failure', I18n.t('pageCopy.scheduledTasks.showTaskModalContent4')],
                                        ['on_success', I18n.t('pageCopy.scheduledTasks.showTaskModalContent5')],
                                        ['always', I18n.t('pageCopy.scheduledTasks.showTaskModalContent6')]
                                    ].map(([value, label]) => `
                                        <option value="${value}" ${(task?.notification_policy || 'never') === value ? 'selected' : ''}>${label}</option>
                                    `).join(''), value20: Utils.escapeHtml(code) }),
            buttons: [
                { text: I18n.t('pageCopy.scheduledTasks.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: isEdit ? I18n.t('pageCopy.scheduledTasks.save') : I18n.t('pageCopy.scheduledTasks.create'), variant: 'primary', onClick: () => this.saveTask(task?.id || null) }
            ]
        });
        this.updateCronPresetFieldsVisibility();
        DOM.$('#task-cron-preset')?.addEventListener('change', () => this.updateCronPresetFieldsVisibility());
        this.renderNotificationTargets(task?.notification_targets || []);
        this.updateNotificationFieldsVisibility();
        DOM.$('#task-notification-policy')?.addEventListener('change', () => this.updateNotificationFieldsVisibility());
    },

    renderNotificationTargets(targets = []) {
        const list = DOM.$('#scheduled-task-target-list');
        if (!list) return;
        list.innerHTML = '';
        const initialTargets = targets.length ? targets : [this.createEmptyNotificationTarget()];
        initialTargets.forEach(target => list.appendChild(this.renderNotificationTargetRow(target)));
    },

    createEmptyNotificationTarget() {
        const integration = this.notificationIntegrations[0] || null;
        return {
            target_id: `target_${Date.now()}`,
            integration_id: integration ? integration.id : null,
            name: integration ? integration.name : '',
            enabled: true,
            params: {}
        };
    },

    renderNotificationTargetRow(target) {
        const wrapper = DOM.el('div', { className: 'scheduled-task-target-row' });
        const integrationOptions = this.notificationIntegrations.map(item => {
            const selected = String(target.integration_id) === String(item.id) ? 'selected' : '';
            return `<option value="${item.id}" ${selected}>${Utils.escapeHtml(item.name)}</option>`;
        }).join('');

        wrapper.innerHTML = I18n.t('pageCopy.scheduledTasks.outboundNotificationSelectValueEnable', { value0: integrationOptions, value1: target.enabled !== false ? 'checked' : '', value2: I18n.t('scheduledTasks.removeTarget'), value3: I18n.t('scheduledTasks.removeTarget') });

        wrapper.querySelector('.scheduled-task-target-integration')?.addEventListener('change', () => {
            this.renderNotificationTargetParams(wrapper, {});
        });
        wrapper.querySelector('.scheduled-task-remove-target')?.addEventListener('click', () => {
            const list = DOM.$('#scheduled-task-target-list');
            wrapper.remove();
            if (list && !list.children.length) {
                list.appendChild(this.renderNotificationTargetRow(this.createEmptyNotificationTarget()));
            }
            DOM.createIcons();
        });

        this.renderNotificationTargetParams(wrapper, target.params || {});
        DOM.createIcons();
        return wrapper;
    },

    renderNotificationTargetParams(wrapper, existingParams = {}) {
        const integrationId = parseInt(wrapper.querySelector('.scheduled-task-target-integration')?.value, 10);
        const integration = this.notificationIntegrations.find(item => item.id === integrationId);
        const container = wrapper.querySelector('.scheduled-task-target-params');
        if (!container) return;
        if (!integration) {
            container.innerHTML = this.notificationIntegrations.length
                ? ''
                : I18n.t('pageCopy.scheduledTasks.thereAreNoOutboundNotificationsAvailableYet');
            return;
        }
        if (!integration.config_schema?.properties) {
            container.innerHTML = I18n.t('pageCopy.scheduledTasks.noAdditionalParametersAreRequiredForThis');
            return;
        }

        let html = I18n.t('pageCopy.scheduledTasks.interfaceParameters');
        for (const [key, prop] of Object.entries(integration.config_schema.properties)) {
            const required = integration.config_schema.required?.includes(key) ? '<span class="scheduled-task-param-required">*</span>' : '';
            const isPassword = prop.format === 'password';
            const currentValue = existingParams[key];
            const value = isPassword ? '' : (currentValue || prop.default || '');
            const placeholder = isPassword && currentValue
                ? I18n.t('placeholders.configuredKeep')
                : (prop.description || '');
            html += `
                <div class="scheduled-task-target-param-row">
                    <label>${Utils.escapeHtml(prop.title || key)}${required}</label>
                    <input
                        type="${isPassword ? 'password' : 'text'}"
                        class="form-input scheduled-task-target-param"
                        data-key="${this.escapeAttr(key)}"
                        data-format="${this.escapeAttr(prop.format || '')}"
                        value="${this.escapeAttr(value)}"
                        placeholder="${this.escapeAttr(placeholder)}"
                    >
                </div>
            `;
        }
        container.innerHTML = html;
    },

    addNotificationTargetRow() {
        const list = DOM.$('#scheduled-task-target-list');
        if (!list) return;
        list.appendChild(this.renderNotificationTargetRow(this.createEmptyNotificationTarget()));
    },

    denormalizeSchedule(task) {
        const defaultExpr = '0 */5 * * * *';
        const base = {
            preset: 'custom',
            expression: defaultExpr,
            minute: 0,
            second: 0,
            time: '00:00:00',
            day_of_week: 0,
            day: 1,
        };
        if (!task) {
            return { ...base, preset: 'hourly', minute: 0, second: 0 };
        }

        const config = task.schedule_config || {};
        if (task.schedule_type === 'interval') {
            const seconds = Number(config.interval_seconds || 300);
            return { ...base, preset: 'custom', expression: this.intervalSecondsToCronExpression(seconds) };
        }

        const preset = config.preset && ['hourly', 'daily', 'weekly', 'monthly', 'custom'].includes(config.preset)
            ? config.preset
            : 'custom';

        if (preset !== 'custom') {
            return {
                preset,
                expression: String(config.expression || defaultExpr).trim(),
                minute: Number(config.minute ?? 0),
                second: Number(config.second ?? 0),
                time: config.time || '00:00:00',
                day_of_week: Number(config.day_of_week ?? 0),
                day: Number(config.day ?? 1),
            };
        }

        const expr = String(config.expression || defaultExpr).trim();
        const fields = expr.split(/\s+/).filter(Boolean);
        let parsedMinute = 0;
        let parsedSecond = 0;
        let parsedTime = '00:00:00';
        let parsedDayOfWeek = 0;
        let parsedDay = 1;
        if (fields.length === 6) {
            parsedSecond = Number(fields[0]) || 0;
            parsedMinute = Number(fields[1]) || 0;
            const hour = Number(fields[2]) || 0;
            parsedDay = Number(fields[3]) || 1;
            parsedDayOfWeek = Number(fields[5]) || 0;
            parsedTime = `${String(hour).padStart(2, '0')}:${String(parsedMinute).padStart(2, '0')}:${String(parsedSecond).padStart(2, '0')}`;
        }
        return {
            preset: 'custom',
            expression: expr,
            minute: parsedMinute,
            second: parsedSecond,
            time: parsedTime,
            day_of_week: parsedDayOfWeek,
            day: parsedDay,
        };
    },

    updateCronPresetFieldsVisibility() {
        const preset = DOM.$('#task-cron-preset')?.value || 'hourly';
        const hourlyFields = DOM.$('#task-cron-hourly-fields');
        const timeFields = DOM.$('#task-cron-time-fields');
        const weeklyFields = DOM.$('#task-cron-weekly-fields');
        const monthlyFields = DOM.$('#task-cron-monthly-fields');
        const customFields = DOM.$('#task-cron-custom-fields');
        if (hourlyFields) hourlyFields.style.display = preset === 'hourly' ? 'block' : 'none';
        if (timeFields) timeFields.style.display = ['daily', 'weekly', 'monthly'].includes(preset) ? 'block' : 'none';
        if (weeklyFields) weeklyFields.style.display = preset === 'weekly' ? 'block' : 'none';
        if (monthlyFields) monthlyFields.style.display = preset === 'monthly' ? 'block' : 'none';
        if (customFields) customFields.style.display = preset === 'custom' ? 'block' : 'none';
    },

    weekdayLabel(day) {
        return [I18n.t('pageCopy.scheduledTasks.mondayShort'), I18n.t('pageCopy.scheduledTasks.tuesdayShort'), I18n.t('pageCopy.scheduledTasks.wednesdayShort'), I18n.t('pageCopy.scheduledTasks.thursdayShort'), I18n.t('pageCopy.scheduledTasks.fridayShort'), I18n.t('pageCopy.scheduledTasks.saturdayShort'), I18n.t('pageCopy.scheduledTasks.sundayShort')][Number(day) || 0] || I18n.t('pageCopy.scheduledTasks.mondayShort');
    },

    updateNotificationFieldsVisibility() {
        const policy = DOM.$('#task-notification-policy')?.value || 'never';
        const targets = DOM.$('#scheduled-task-notification-targets');
        if (targets) targets.style.display = policy === 'never' ? 'none' : 'block';
    },

    collectFormData() {
        const notificationPolicy = DOM.$('#task-notification-policy')?.value || 'never';

        const scheduleConfig = this.collectCronScheduleConfig();

        const notificationTargets = Array.from(DOM.$$('.scheduled-task-target-row')).map((row, index) => {
            const integrationId = parseInt(row.querySelector('.scheduled-task-target-integration')?.value, 10);
            const existingTarget = this.currentEditingTask?.notification_targets?.[index];
            const integrationName = this.getIntegrationName(integrationId);
            const targetParams = {};
            row.querySelectorAll('.scheduled-task-target-param').forEach(input => {
                const key = input.dataset.key;
                const format = input.dataset.format;
                if (!key) return;
                if (format === 'password') {
                    if (input.value) {
                        targetParams[key] = `ENCRYPT:${input.value}`;
                    } else if (existingTarget?.params && existingTarget.params[key]) {
                        targetParams[key] = existingTarget.params[key];
                    }
                } else {
                    targetParams[key] = input.value;
                }
            });

            return {
                target_id: existingTarget?.target_id || `target_${Date.now()}_${index}`,
                integration_id: integrationId,
                name: existingTarget?.name || `${integrationName} #${index + 1}`,
                enabled: row.querySelector('.scheduled-task-target-enabled')?.checked !== false,
                params: targetParams
            };
        }).filter(target => Number.isFinite(target.integration_id));

        if (notificationPolicy !== 'never' && notificationTargets.length === 0) {
            throw new Error(I18n.t('pageCopy.scheduledTasks.pleaseSelectAtLeastOneNotificationInterface'));
        }

        return {
            name: DOM.$('#task-name').value.trim(),
            description: DOM.$('#task-description').value.trim() || null,
            script_code: DOM.$('#task-script-code').value,
            schedule_type: 'cron',
            schedule_config: scheduleConfig,
            enabled: DOM.$('#task-enabled').checked,
            timeout_seconds: Number(DOM.$('#task-timeout').value || 60),
            max_concurrent_runs: 1,
            notification_policy: notificationPolicy,
            notification_targets: notificationTargets
        };
    },

    collectCronScheduleConfig() {
        const preset = DOM.$('#task-cron-preset')?.value || 'hourly';
        if (preset === 'hourly') {
            return {
                preset: 'hourly',
                minute: Number(DOM.$('#task-cron-hourly-minute')?.value || 0),
                second: Number(DOM.$('#task-cron-hourly-second')?.value || 0),
            };
        }
        if (preset === 'daily') {
            return {
                preset: 'daily',
                time: (DOM.$('#task-cron-time')?.value || '00:00:00').trim(),
            };
        }
        if (preset === 'weekly') {
            return {
                preset: 'weekly',
                time: (DOM.$('#task-cron-time')?.value || '00:00:00').trim(),
                day_of_week: Number(DOM.$('#task-cron-weekday')?.value || 0),
            };
        }
        if (preset === 'monthly') {
            return {
                preset: 'monthly',
                time: (DOM.$('#task-cron-time')?.value || '00:00:00').trim(),
                day: Number(DOM.$('#task-cron-month-day')?.value || 1),
            };
        }
        const expression = (DOM.$('#task-cron-expression')?.value || '').trim();
        if (!expression) throw new Error(I18n.t('pageCopy.scheduledTasks.cronExpressionCannotBeEmptyInCustom'));
        return { expression };
    },

    getIntegrationName(integrationId) {
        const integration = this.notificationIntegrations.find(item => item.id === integrationId);
        return integration ? integration.name : I18n.t('pageCopy.scheduledTasks.notificationEndpointValue', { value0: integrationId || '' }).trim();
    },

    async saveTask(taskId) {
        try {
            const data = this.collectFormData();
            if (!data.name) throw new Error(I18n.t('pageCopy.scheduledTasks.taskNameCannotBeEmpty'));
            if (!data.script_code.trim()) throw new Error(I18n.t('pageCopy.scheduledTasks.pythonScriptCannotBeEmpty'));
            if (taskId) {
                await API.updateScheduledTask(taskId, data);
                Toast.success(I18n.t('pageCopy.scheduledTasks.taskUpdated'));
            } else {
                await API.createScheduledTask(data);
                Toast.success(I18n.t('pageCopy.scheduledTasks.taskHasBeenCreated'));
            }
            Modal.hide();
            await this.loadTasks();
        } catch (error) {
            Toast.error(error.message);
            throw error;
        }
    },

    async toggleTask(taskId) {
        const task = this.tasks.find(item => item.id === taskId);
        if (!task) return;
        try {
            await API.updateScheduledTask(taskId, { enabled: !task.enabled });
            Toast.success(task.enabled ? I18n.t('pageCopy.scheduledTasks.taskIsDeactivated') : I18n.t('pageCopy.scheduledTasks.taskIsEnabled'));
            await this.loadTasks();
        } catch (error) {
            Toast.error(error.message || I18n.t('common.requestFailed'));
        }
    },

    async runTask(taskId) {
        const task = this.tasks.find(item => item.id === taskId);
        const taskName = task?.name || `#${taskId}`;
        if (!confirm(I18n.t('pageCopy.scheduledTasks.confirmToExecuteTheTaskManuallyImmediately', { value0: taskName }))) return;

        try {
            const run = await API.runScheduledTask(taskId);
            Toast.success(run.status === 'success' ? I18n.t('pageCopy.scheduledTasks.taskExecutionSuccessful') : I18n.t('pageCopy.scheduledTasks.taskExecutionCompletedValue', { value0: run.status }));
            await this.loadTasks();
            this.showRunDetail(run);
        } catch (error) {
            Toast.error(error.message || I18n.t('common.requestFailed'));
        }
    },

    async deleteTask(taskId) {
        const task = this.tasks.find(item => item.id === taskId);
        if (!task) return;
        if (!confirm(I18n.t('pageCopy.scheduledTasks.confirmToDeleteTaskValueRunHistory', { value0: task.name }))) return;
        try {
            await API.deleteScheduledTask(taskId);
            Toast.success(I18n.t('pageCopy.scheduledTasks.taskDeleted'));
            await this.loadTasks();
        } catch (error) {
            Toast.error(error.message || I18n.t('common.requestFailed'));
        }
    },

    async showRuns(taskId) {
        const task = this.tasks.find(item => item.id === taskId);
        try {
            const runs = await API.getScheduledTaskRuns(taskId, { limit: 100 });
            Modal.show({
                title: I18n.t('pageCopy.scheduledTasks.operationHistoryValue', { value0: task ? task.name : taskId }),
                size: 'xlarge',
                bodyClassName: 'scheduled-task-modal-body',
                content: I18n.t('pageCopy.scheduledTasks.showRunsContent', {
                    value0: runs.length
                        ? runs.map(run => I18n.t('pageCopy.scheduledTasks.showRunsContent2', {
                            value0: run.id,
                            value1: I18n.t(run.trigger_source === 'scheduler'
                                ? 'pageCopy.scheduledTasks.showRunsContent3'
                                : 'pageCopy.scheduledTasks.showRunsContent4'),
                            value2: this.renderStatus(run.status, run.error_message),
                            value3: this.formatDate(run.started_at || run.created_at),
                            value4: run.duration_ms === null || run.duration_ms === undefined ? '-' : Format.duration(run.duration_ms),
                            value5: run.id
                        })).join('')
                        : I18n.t('pageCopy.scheduledTasks.showRunsContent5')
                }),
                buttons: [{ text: I18n.t('pageCopy.scheduledTasks.close'), variant: 'secondary', onClick: () => Modal.hide() }]
            });
        } catch (error) {
            Toast.error(I18n.t('pageCopy.scheduledTasks.loadHistoryFailed', { message: error.message }));
        }
    },

    async loadRunDetail(runId) {
        try {
            const run = await API.getScheduledTaskRun(runId);
            this.showRunDetail(run);
        } catch (error) {
            Toast.error(I18n.t('pageCopy.scheduledTasks.loadDetailFailed', { message: error.message }));
        }
    },

    showRunDetail(run) {
        Modal.show({
            title: I18n.t('pageCopy.scheduledTasks.runDetailsValue', { value0: run.id }),
            size: 'xlarge',
            bodyClassName: 'scheduled-task-modal-body',
            content: I18n.t('pageCopy.scheduledTasks.showRunDetailContent', {
                value0: this.renderStatus(run.status, run.error_message),
                value1: I18n.t(run.trigger_source === 'scheduler'
                    ? 'pageCopy.scheduledTasks.showRunDetailContent2'
                    : 'pageCopy.scheduledTasks.showRunDetailContent3'),
                value2: this.formatDate(run.started_at || run.created_at),
                value3: run.duration_ms === null || run.duration_ms === undefined ? '-' : Format.duration(run.duration_ms),
                value4: run.error_message ? `<div class="scheduled-task-error">${Utils.escapeHtml(run.error_message)}</div>` : '',
                value5: Utils.escapeHtml(JSON.stringify(run.result || {}, null, 2)),
                value6: Utils.escapeHtml(run.stdout || ''),
                value7: Utils.escapeHtml(run.stderr || '')
            }),
            buttons: [{ text: I18n.t('pageCopy.scheduledTasks.close'), variant: 'secondary', onClick: () => Modal.hide() }]
        });
    },

    escapeAttr(value) {
        return Utils.escapeHtml(String(value || '')).replace(/"/g, '&quot;');
    }
};
