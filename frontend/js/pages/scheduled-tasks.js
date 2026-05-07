/* Scheduled task management page */
const ScheduledTasksPage = {
    tasks: [],
    notificationIntegrations: [],
    currentEditingTask: null,

    render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading">正在加载任务调度配置...</div>';
        Header.render('任务调度管理', this._buildHeaderActions());
        this.loadTasks();
    },

    _buildHeaderActions() {
        const filters = DOM.el('div', { className: 'dashboard-filters' });
        filters.innerHTML = `
            <input type="text" id="scheduled-task-keyword" class="filter-input" placeholder="搜索任务..." style="min-width:180px;">
            <select id="scheduled-task-enabled" class="filter-select">
                <option value="">全部状态</option>
                <option value="true">已启用</option>
                <option value="false">已停用</option>
            </select>
            <select id="scheduled-task-last-status" class="filter-select">
                <option value="">全部结果</option>
                <option value="success">成功</option>
                <option value="failed">失败</option>
                <option value="skipped">跳过</option>
                <option value="running">运行中</option>
            </select>
        `;

        const addBtn = DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> 新建任务',
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
            content.innerHTML = `
                <div class="scheduled-tasks-page">
                    <div class="scheduled-task-table-card">
                        <table class="scheduled-task-table">
                            <thead>
                                <tr>
                                    <th>任务</th>
                                    <th>调度</th>
                                    <th>启用</th>
                                    <th>上次运行</th>
                                    <th>下次运行</th>
                                    <th>最近结果</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody>${this.renderRows()}</tbody>
                        </table>
                    </div>
                </div>
            `;
            DOM.createIcons();
        } catch (error) {
            console.error('Failed to load scheduled tasks:', error);
            Toast.error('加载任务失败: ' + error.message);
            content.innerHTML = `
                <div class="error-state">
                    <h3>加载任务失败</h3>
                    <p>${Utils.escapeHtml(error.message)}</p>
                    <button class="btn btn-primary" onclick="ScheduledTasksPage.loadTasks()">重试</button>
                </div>
            `;
        }
    },

    renderRows() {
        if (!this.tasks.length) {
            return '<tr><td colspan="7" class="empty-state">暂无任务调度配置</td></tr>';
        }
        return this.tasks.map(task => `
            <tr>
                <td>
                    <div class="scheduled-task-name">${Utils.escapeHtml(task.name)}</div>
                    <div class="scheduled-task-desc">${Utils.escapeHtml(task.description || '暂无描述')}</div>
                </td>
                <td>${this.formatSchedule(task)}</td>
                <td>${task.enabled ? '<span class="task-chip enabled">已启用</span>' : '<span class="task-chip disabled">已停用</span>'}</td>
                <td>${this.formatDate(task.last_run_at)}</td>
                <td>${this.formatDate(task.next_run_at)}</td>
                <td>${this.renderStatus(task.last_status, task.last_error)}</td>
                <td class="actions scheduled-task-actions">
                    <button class="btn btn-sm" onclick="ScheduledTasksPage.runTask(${task.id})" title="立即执行">
                        <i data-lucide="play"></i>
                    </button>
                    <button class="btn btn-sm" onclick="ScheduledTasksPage.showRuns(${task.id})" title="运行历史">
                        <i data-lucide="history"></i>
                    </button>
                    <button class="btn btn-sm" onclick="ScheduledTasksPage.showTaskModal(${task.id})" title="编辑">
                        <i data-lucide="edit"></i>
                    </button>
                    <button class="btn btn-sm" onclick="ScheduledTasksPage.toggleTask(${task.id})" title="${task.enabled ? '停用' : '启用'}">
                        <i data-lucide="${task.enabled ? 'pause' : 'power'}"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="ScheduledTasksPage.deleteTask(${task.id})" title="删除">
                        <i data-lucide="trash-2"></i>
                    </button>
                </td>
            </tr>
        `).join('');
    },

    formatSchedule(task) {
        const config = task.schedule_config || {};
        if (task.schedule_type === 'interval') {
            const seconds = Number(config.interval_seconds || 0);
            const expression = this.intervalSecondsToCronExpression(seconds || 60);
            return `<span class="task-mono">cron: ${Utils.escapeHtml(expression)}</span> <span class="task-chip disabled">原间隔</span>`;
        }
        if (config.preset === 'hourly') {
            return `<span class="task-mono">每小时 ${String(config.minute ?? 0).padStart(2, '0')}分${String(config.second ?? 0).padStart(2, '0')}秒</span>`;
        }
        if (config.preset === 'daily') {
            return `<span class="task-mono">每天 ${Utils.escapeHtml(config.time || '00:00:00')}</span>`;
        }
        if (config.preset === 'weekly') {
            return `<span class="task-mono">每周${this.weekdayLabel(config.day_of_week)} ${Utils.escapeHtml(config.time || '00:00:00')}</span>`;
        }
        if (config.preset === 'monthly') {
            return `<span class="task-mono">每月${config.day ?? 1}日 ${Utils.escapeHtml(config.time || '00:00:00')}</span>`;
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
        const labels = { success: '成功', failed: '失败', skipped: '跳过', running: '运行中', pending: '等待中' };
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
            '    print("任务开始执行")',
            '    return {"success": True}',
            ''
        ].join('\n');

        Modal.show({
            title: isEdit ? '编辑任务' : '新建任务',
            size: 'xlarge',
            containerClassName: 'scheduled-task-editor-modal',
            bodyClassName: 'scheduled-task-modal-body',
            content: `
                <form id="scheduled-task-form" class="scheduled-task-form">
                    <div class="scheduled-task-form-intro">
                        <div>
                            <span class="scheduled-task-eyebrow">${isEdit ? 'TASK CONFIGURATION' : 'NEW SCHEDULED TASK'}</span>
                            <p>配置任务的基础信息、触发方式和执行脚本。脚本入口必须定义 <code>run(context)</code>。</p>
                        </div>
                    </div>

                    <section class="scheduled-task-form-section">
                        <div class="scheduled-task-section-heading">
                            <h4>基础信息</h4>
                            <p>名称用于列表识别，启用状态控制任务是否进入调度器。</p>
                        </div>
                        <div class="scheduled-task-form-grid scheduled-task-basic-grid">
                            <div class="form-group scheduled-task-name-field">
                                <label>任务名称 *</label>
                                <input id="task-name" class="form-input" value="${this.escapeAttr(task?.name || '')}" required>
                            </div>
                            <div class="form-group scheduled-task-enabled-field">
                                <label>启用状态</label>
                                <label class="scheduled-task-checkbox scheduled-task-switch-card">
                                    <input type="checkbox" id="task-enabled" ${task?.enabled === false ? '' : 'checked'}>
                                    <span>启用任务</span>
                                </label>
                            </div>
                            <div class="form-group">
                                <label>超时时间（秒）</label>
                                <input id="task-timeout" type="number" min="1" max="3600" class="form-input" value="${task?.timeout_seconds || 60}">
                            </div>
                            <div class="form-group scheduled-task-full">
                                <label>任务描述</label>
                                <textarea id="task-description" class="form-textarea scheduled-task-description-input" rows="2" placeholder="例如：每天凌晨执行巡检脚本，检查实例状态并输出摘要。">${Utils.escapeHtml(task?.description || '')}</textarea>
                            </div>
                        </div>
                    </section>

                    <section class="scheduled-task-form-section">
                        <div class="scheduled-task-section-heading">
                            <h4>Cron 调度</h4>
                            <p>先选常用周期（底层均为 Cron）；最后一项可手写表达式。短周期请设置合理超时，避免任务堆积。</p>
                        </div>
                        <div class="scheduled-task-schedule-layout">
                            <div id="task-cron-fields" class="scheduled-task-schedule-row">
                                <div class="form-group scheduled-task-compact-field">
                                    <label>执行周期 *</label>
                                    <select id="task-cron-preset" class="form-select">
                                        <option value="hourly" ${config.preset === 'hourly' ? 'selected' : ''}>每小时</option>
                                        <option value="daily" ${config.preset === 'daily' ? 'selected' : ''}>每天</option>
                                        <option value="weekly" ${config.preset === 'weekly' ? 'selected' : ''}>每周</option>
                                        <option value="monthly" ${config.preset === 'monthly' ? 'selected' : ''}>每月</option>
                                        <option value="custom" ${config.preset === 'custom' ? 'selected' : ''}>自定义 Cron 表达式</option>
                                    </select>
                                </div>
                                <div id="task-cron-hourly-fields" class="form-group scheduled-task-compact-field">
                                    <label>分钟 / 秒</label>
                                    <div class="scheduled-task-inline-fields">
                                        <input id="task-cron-hourly-minute" type="number" min="0" max="59" class="form-input" value="${config.minute}" title="每小时内的第几分">
                                        <input id="task-cron-hourly-second" type="number" min="0" max="59" class="form-input" value="${config.second}" title="该分钟内的第几秒">
                                    </div>
                                </div>
                                <div id="task-cron-time-fields" class="form-group scheduled-task-compact-field">
                                    <label>时间 (HH:MM:SS)</label>
                                    <input id="task-cron-time" class="form-input task-mono" value="${this.escapeAttr(config.time)}" placeholder="02:30:00">
                                </div>
                                <div id="task-cron-weekly-fields" class="form-group scheduled-task-compact-field">
                                    <label>星期</label>
                                    <select id="task-cron-weekday" class="form-select">
                                        ${[0, 1, 2, 3, 4, 5, 6].map(day => `
                                            <option value="${day}" ${Number(config.day_of_week) === day ? 'selected' : ''}>周${this.weekdayLabel(day)}</option>
                                        `).join('')}
                                    </select>
                                </div>
                                <div id="task-cron-monthly-fields" class="form-group scheduled-task-compact-field">
                                    <label>每月几号</label>
                                    <input id="task-cron-month-day" type="number" min="1" max="31" class="form-input" value="${config.day}">
                                </div>
                                <div id="task-cron-custom-fields" class="form-group scheduled-task-cron-field scheduled-task-full">
                                    <label>Cron 表达式</label>
                                    <input id="task-cron-expression" class="form-input task-mono" placeholder="0 */5 * * * *" value="${this.escapeAttr(config.expression)}">
                                    <p class="form-hint">支持 5 段（分 时 日 月 周）或 6 段（秒 分 时 日 月 周）。</p>
                                </div>
                            </div>
                        </div>
                    </section>

                    <section class="scheduled-task-form-section">
                        <div class="scheduled-task-section-heading">
                            <h4>结果通知</h4>
                            <p>任务执行完成后，可复用外部集成管理中的出站通知模板发送结果。</p>
                        </div>
                        <div class="scheduled-task-notification-layout">
                            <div class="form-group scheduled-task-policy-field">
                                <label>发送策略</label>
                                <select id="task-notification-policy" class="form-select">
                                    ${[
                                        ['never', '不发送'],
                                        ['on_failure', '失败发送'],
                                        ['on_success', '成功发送'],
                                        ['always', '全部发送']
                                    ].map(([value, label]) => `
                                        <option value="${value}" ${(task?.notification_policy || 'never') === value ? 'selected' : ''}>${label}</option>
                                    `).join('')}
                                </select>
                            </div>
                            <div id="scheduled-task-notification-targets" class="scheduled-task-notification-targets">
                                <div class="scheduled-task-targets-header">
                                    <div>
                                        <strong>通知接口</strong>
                                        <span>选择已启用的出站通知，并填写 webhook、email 等运行参数。</span>
                                    </div>
                                    <button type="button" class="btn btn-sm btn-secondary" onclick="ScheduledTasksPage.addNotificationTargetRow()">新增接口</button>
                                </div>
                                <div id="scheduled-task-target-list" class="scheduled-task-target-list"></div>
                            </div>
                        </div>
                    </section>

                    <section class="scheduled-task-form-section scheduled-task-execution-section">
                        <div class="scheduled-task-section-heading">
                            <h4>执行内容</h4>
                            <p>脚本区域保留更宽空间，便于阅读和编辑多行代码。需要动态数据时可通过 <code>context</code> 读取系统配置或数据库会话。</p>
                        </div>
                        <div class="form-group scheduled-task-script-panel">
                            <label>Python 脚本 *</label>
                            <textarea id="task-script-code" class="form-textarea task-mono scheduled-task-code" rows="16" spellcheck="false" required>${Utils.escapeHtml(code)}</textarea>
                        </div>
                    </section>
                </form>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: isEdit ? '保存' : '创建', variant: 'primary', onClick: () => this.saveTask(task?.id || null) }
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

        wrapper.innerHTML = `
            <div class="scheduled-task-target-top">
                <div class="form-group">
                    <label>出站通知</label>
                    <select class="scheduled-task-target-integration form-select">
                        <option value="">请选择</option>
                        ${integrationOptions}
                    </select>
                </div>
                <div class="scheduled-task-target-actions">
                    <label class="scheduled-task-checkbox">
                        <input type="checkbox" class="scheduled-task-target-enabled" ${target.enabled !== false ? 'checked' : ''}>
                        <span>启用</span>
                    </label>
                    <button type="button" class="btn-icon scheduled-task-remove-target" title="删除接口" aria-label="删除接口">
                        <i data-lucide="trash-2"></i>
                    </button>
                </div>
            </div>
            <div class="scheduled-task-target-params"></div>
        `;

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
                : '<div class="scheduled-task-target-empty">暂无可用出站通知，请先在外部集成管理中启用出站通知模板。</div>';
            return;
        }
        if (!integration.config_schema?.properties) {
            container.innerHTML = '<div class="scheduled-task-target-empty">此出站通知不需要额外参数。</div>';
            return;
        }

        let html = '<div class="scheduled-task-target-param-title">接口参数</div>';
        for (const [key, prop] of Object.entries(integration.config_schema.properties)) {
            const required = integration.config_schema.required?.includes(key) ? '<span class="scheduled-task-param-required">*</span>' : '';
            const isPassword = prop.format === 'password';
            const currentValue = existingParams[key];
            const value = isPassword ? '' : (currentValue || prop.default || '');
            const placeholder = isPassword && currentValue ? '已配置，留空则保持不变' : (prop.description || '');
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
        return ['一', '二', '三', '四', '五', '六', '日'][Number(day) || 0] || '一';
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
            throw new Error('请选择至少一个通知接口');
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
        if (!expression) throw new Error('自定义模式下 Cron 表达式不能为空');
        return { expression };
    },

    getIntegrationName(integrationId) {
        const integration = this.notificationIntegrations.find(item => item.id === integrationId);
        return integration ? integration.name : `通知接口 ${integrationId || ''}`.trim();
    },

    async saveTask(taskId) {
        try {
            const data = this.collectFormData();
            if (!data.name) throw new Error('任务名称不能为空');
            if (!data.script_code.trim()) throw new Error('Python 脚本不能为空');
            if (taskId) {
                await API.updateScheduledTask(taskId, data);
                Toast.success('任务已更新');
            } else {
                await API.createScheduledTask(data);
                Toast.success('任务已创建');
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
            Toast.success(task.enabled ? '任务已停用' : '任务已启用');
            await this.loadTasks();
        } catch (error) {
            Toast.error('更新任务状态失败: ' + error.message);
        }
    },

    async runTask(taskId) {
        const task = this.tasks.find(item => item.id === taskId);
        const taskName = task?.name || `#${taskId}`;
        if (!confirm(`确认立即手工执行任务「${taskName}」吗？`)) return;

        try {
            const run = await API.runScheduledTask(taskId);
            Toast.success(run.status === 'success' ? '任务执行成功' : `任务执行完成：${run.status}`);
            await this.loadTasks();
            this.showRunDetail(run);
        } catch (error) {
            Toast.error('执行任务失败: ' + error.message);
        }
    },

    async deleteTask(taskId) {
        const task = this.tasks.find(item => item.id === taskId);
        if (!task) return;
        if (!confirm(`确定删除任务「${task.name}」吗？运行历史将保留。`)) return;
        try {
            await API.deleteScheduledTask(taskId);
            Toast.success('任务已删除');
            await this.loadTasks();
        } catch (error) {
            Toast.error('删除任务失败: ' + error.message);
        }
    },

    async showRuns(taskId) {
        const task = this.tasks.find(item => item.id === taskId);
        try {
            const runs = await API.getScheduledTaskRuns(taskId, { limit: 100 });
            Modal.show({
                title: `运行历史 - ${task ? task.name : taskId}`,
                size: 'xlarge',
                bodyClassName: 'scheduled-task-modal-body',
                content: `
                    <div class="scheduled-task-runs">
                        <table class="scheduled-task-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>触发来源</th>
                                    <th>状态</th>
                                    <th>开始时间</th>
                                    <th>耗时</th>
                                    <th>操作</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${runs.length ? runs.map(run => `
                                    <tr>
                                        <td>${run.id}</td>
                                        <td>${run.trigger_source === 'scheduler' ? '调度器' : '手动'}</td>
                                        <td>${this.renderStatus(run.status, run.error_message)}</td>
                                        <td>${this.formatDate(run.started_at || run.created_at)}</td>
                                        <td>${run.duration_ms === null || run.duration_ms === undefined ? '-' : Format.duration(run.duration_ms)}</td>
                                        <td>
                                            <button class="btn btn-sm" onclick="ScheduledTasksPage.loadRunDetail(${run.id})">
                                                <i data-lucide="file-text"></i> 详情
                                            </button>
                                        </td>
                                    </tr>
                                `).join('') : '<tr><td colspan="6" class="empty-state">暂无运行记录</td></tr>'}
                            </tbody>
                        </table>
                    </div>
                `,
                buttons: [{ text: '关闭', variant: 'secondary', onClick: () => Modal.hide() }]
            });
        } catch (error) {
            Toast.error('加载运行历史失败: ' + error.message);
        }
    },

    async loadRunDetail(runId) {
        try {
            const run = await API.getScheduledTaskRun(runId);
            this.showRunDetail(run);
        } catch (error) {
            Toast.error('加载运行详情失败: ' + error.message);
        }
    },

    showRunDetail(run) {
        Modal.show({
            title: `运行详情 #${run.id}`,
            size: 'xlarge',
            bodyClassName: 'scheduled-task-modal-body',
            content: `
                <div class="scheduled-task-run-detail">
                    <div class="scheduled-task-run-meta">
                        <span>${this.renderStatus(run.status, run.error_message)}</span>
                        <span>触发：${run.trigger_source === 'scheduler' ? '调度器' : '手动'}</span>
                        <span>开始：${this.formatDate(run.started_at || run.created_at)}</span>
                        <span>耗时：${run.duration_ms === null || run.duration_ms === undefined ? '-' : Format.duration(run.duration_ms)}</span>
                    </div>
                    ${run.error_message ? `<div class="scheduled-task-error">${Utils.escapeHtml(run.error_message)}</div>` : ''}
                    <h4>返回结果</h4>
                    <pre>${Utils.escapeHtml(JSON.stringify(run.result || {}, null, 2))}</pre>
                    <h4>stdout</h4>
                    <pre>${Utils.escapeHtml(run.stdout || '')}</pre>
                    <h4>stderr</h4>
                    <pre>${Utils.escapeHtml(run.stderr || '')}</pre>
                </div>
            `,
            buttons: [{ text: '关闭', variant: 'secondary', onClick: () => Modal.hide() }]
        });
    },

    escapeAttr(value) {
        return Utils.escapeHtml(String(value || '')).replace(/"/g, '&quot;');
    }
};
