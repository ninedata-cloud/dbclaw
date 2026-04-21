/* Alert template management page */
const AlertTemplatesPage = {
    _renderOptions: null,
    _container: null,
    templates: [],
    models: [],

    async render(options = null) {
        if (options) {
            this._renderOptions = options;
            this._container = options.container || DOM.$('#page-content');
        }

        const renderOptions = this._renderOptions || {};
        const container = renderOptions.container || this._container || DOM.$('#page-content');
        this._container = container;

        const currentUser = Store.get('currentUser');
        const actions = [];
        if (currentUser?.is_admin) {
            actions.push(DOM.el('button', {
                className: 'btn btn-primary',
                innerHTML: '<i data-lucide="plus"></i> 新建告警模板',
                onClick: () => this._showForm(null),
            }));
        }
        if (!renderOptions.embedded) {
            Header.render(renderOptions.title || '告警模板', actions);
        }

        container.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            const [templates, models] = await Promise.all([
                API.getAlertTemplates(),
                API.getAIModels(),
            ]);
            this.templates = Array.isArray(templates) ? templates : [];
            this.models = Array.isArray(models) ? models : [];

            container.innerHTML = `
                <div class="system-configs-page alert-ai-page ${renderOptions.embedded ? 'alert-ai-page-embedded' : ''}">
                    ${this._renderToolbar(currentUser, renderOptions)}
                    ${this._renderTemplateSection(currentUser)}
                </div>
            `;
            DOM.createIcons();
        } catch (err) {
            Toast.error('加载告警模板失败：' + err.message);
            container.innerHTML = `
                <div class="error-state">
                    <h3>加载失败</h3>
                    <p>${this._escapeHtml(err.message)}</p>
                </div>
            `;
        }
    },

    cleanup() {
        this._renderOptions = null;
        this._container = null;
    },

    _renderToolbar(currentUser, renderOptions) {
        if (!renderOptions.embedded) {
            return '';
        }

        const createButton = currentUser?.is_admin ? `
            <button class="btn btn-primary" onclick="AlertTemplatesPage._showForm(null)">
                <i data-lucide="plus"></i> 新建告警模板
            </button>
        ` : '';

        return `
            <div class="alert-ai-page-toolbar">
                <div>
                    <h3>告警模板</h3>
                    <div class="text-muted text-sm">统一维护阈值、基线和事件级 AI 诊断策略，实例侧只需要选择模板即可。</div>
                </div>
                ${createButton}
            </div>
        `;
    },

    _renderTemplateSection(currentUser) {
        if (!this.templates.length) {
            return `
                <div class="empty-state">
                    <i data-lucide="layout-template"></i>
                    <h3>暂无告警模板</h3>
                    <p>先创建一个模板，实例配置时即可直接选择使用。</p>
                </div>
            `;
        }

        return `
            <div class="datasource-grid">
                ${this.templates.map((template) => this._renderTemplateCard(template, currentUser)).join('')}
            </div>
        `;
    },

    _renderTemplateCard(template, currentUser) {
        const config = this._normalizeTemplateConfig(template.template_config);
        const adminActions = currentUser?.is_admin ? `
            <button class="btn btn-sm btn-secondary" onclick="AlertTemplatesPage._showForm(${template.id})">
                <i data-lucide="pencil"></i> 编辑
            </button>
            ${template.is_default ? '' : `
                <button class="btn btn-sm btn-secondary" onclick="AlertTemplatesPage._setDefault(${template.id})">
                    <i data-lucide="star"></i> 设为默认
                </button>
            `}
            <button class="btn btn-sm ${template.enabled ? 'btn-danger' : 'btn-success'}" onclick="AlertTemplatesPage._toggleTemplate(${template.id}, ${template.enabled ? 'false' : 'true'})">
                <i data-lucide="${template.enabled ? 'pause' : 'play'}"></i> ${template.enabled ? '停用' : '启用'}
            </button>
        ` : '';

        return `
            <div class="datasource-card ai-model-card">
                <div class="datasource-card-header">
                    <span class="datasource-card-name">${this._escapeHtml(template.name)}</span>
                    <div class="alert-ai-policy-badges">
                        ${template.is_default ? '<span class="badge badge-info">默认模板</span>' : ''}
                        <span class="badge ${template.enabled ? 'badge-success' : 'badge-secondary'}">${template.enabled ? '启用中' : '已停用'}</span>
                    </div>
                </div>
                <div class="datasource-card-info">
                    <span><i data-lucide="message-square-text"></i> ${this._escapeHtml(template.description || '未填写描述')}</span>
                    <span><i data-lucide="siren"></i> ${this._escapeHtml(this._modeLabel(config.alert_engine_mode))}</span>
                    <span><i data-lucide="activity"></i> ${this._escapeHtml(this._thresholdSummary(config.threshold_rules))}</span>
                    <span><i data-lucide="line-chart"></i> ${config.baseline_config?.enabled ? '启用实例基线' : '关闭实例基线'}</span>
                    <span><i data-lucide="brain"></i> ${config.event_ai_config?.enabled !== false ? '事件 AI 诊断开启' : '事件 AI 诊断关闭'}</span>
                    ${config.alert_engine_mode === 'ai' ? `<span><i data-lucide="file-text"></i> ${this._escapeHtml(this._compactRuleText(config.ai_policy_text))}</span>` : ''}
                </div>
                <div class="datasource-card-actions">
                    ${adminActions}
                </div>
            </div>
        `;
    },

    _showForm(templateId) {
        const template = this.templates.find((item) => item.id === templateId) || null;
        const isEdit = Boolean(template);
        const config = this._normalizeTemplateConfig(template?.template_config);
        const thresholdState = this._getThresholdEditorState(config.threshold_rules);
        const form = DOM.el('form');
        form.innerHTML = `
            <div class="form-group">
                <label>模板名称</label>
                <input type="text" name="name" class="form-input" required value="${this._escapeAttr(template?.name || '')}" placeholder="例如：标准生产告警">
            </div>
            <div class="form-group">
                <label>描述</label>
                <input type="text" name="description" class="form-input" value="${this._escapeAttr(template?.description || '')}" placeholder="说明适用实例或场景">
            </div>
            <div class="form-group">
                <label>判警方式</label>
                <select name="alert_engine_mode" id="templateAlertEngineMode" class="form-select">
                    <option value="threshold" ${config.alert_engine_mode !== 'ai' ? 'selected' : ''}>阈值判警</option>
                    <option value="ai" ${config.alert_engine_mode === 'ai' ? 'selected' : ''}>AI 判警</option>
                </select>
                <div class="text-muted text-sm" style="margin-top:6px;">阈值判警更确定、成本更低；AI 判警更适合复杂趋势和上下文判断。</div>
            </div>
            <div class="form-group">
                <label>阈值规则</label>
                <div class="alert-template-threshold-mode">
                    <label class="checkbox-label">
                        <input type="checkbox" name="use_custom_expression" ${thresholdState.useCustomExpression ? 'checked' : ''}>
                        使用自定义表达式
                    </label>
                </div>
                <div id="templatePresetThresholdSection" style="display:${thresholdState.useCustomExpression ? 'none' : 'block'};">
                    <div class="alert-template-threshold-list">
                        ${this._renderMetricLevelEditor('cpu', 'CPU 使用率', '%', thresholdState.cpu)}
                        ${this._renderMetricLevelEditor('disk', '磁盘使用率', '%', thresholdState.disk)}
                        ${this._renderMetricLevelEditor('connections', '活跃连接数', '', thresholdState.connections)}
                    </div>
                    <div class="text-muted text-sm" style="margin-top:6px;">为每个指标配置多个告警等级，不同等级可设置不同的阈值、持续时长和确认次数。</div>
                </div>
                <div id="templateCustomExpressionSection" style="display:${thresholdState.useCustomExpression ? 'block' : 'none'};">
                    <label class="text-muted text-sm">表达式</label>
                    <textarea name="custom_expression_text" class="form-textarea" rows="4" placeholder="例如：cpu_usage > 80 and connections > 120">${this._escapeHtml(thresholdState.customExpression.expression)}</textarea>
                    <div class="alert-ai-advanced-grid" style="margin-top:12px;">
                        <div>
                            <label class="text-muted text-sm">持续时长（秒）</label>
                            <input type="number" name="custom_expression_duration" class="form-input" min="1" value="${this._escapeAttr(thresholdState.customExpression.duration)}">
                        </div>
                    </div>
                    <div style="display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap;">
                        <button type="button" class="btn btn-secondary" id="validateTemplateExpressionBtn">校验表达式</button>
                        <div id="templateExpressionValidation" class="text-muted text-sm">可用指标：cpu_usage、memory_usage、disk_usage、connections、qps、tps</div>
                    </div>
                    <div class="text-muted text-sm" style="margin-top:6px;">适合组合条件或复杂判断，例如 CPU、连接数同时满足时才触发。</div>
                </div>
            </div>
            <div id="templateAIPolicySection" class="form-group" style="display:${config.alert_engine_mode === 'ai' ? 'block' : 'none'};">
                <label>AI 判警规则</label>
                <textarea name="ai_policy_text" class="form-textarea" rows="6" placeholder="例如：当 CPU、磁盘、连接数同时异常且趋势持续恶化时，触发高优先级告警。">${this._escapeHtml(config.ai_policy_text || '')}</textarea>
                <div class="form-group" style="margin-top:12px;">
                    <label>AI 判警模型</label>
                    <select name="alert_ai_model_id" class="form-select">
                        <option value="">继承默认模型</option>
                        ${this.models.map((model) => `<option value="${model.id}" ${String(config.alert_ai_model_id || '') === String(model.id) ? 'selected' : ''}>${this._escapeHtml(model.name)}</option>`).join('')}
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="baseline_enabled" ${config.baseline_config?.enabled ? 'checked' : ''}>
                    启用实例级基线检测
                </label>
                <div class="text-muted text-sm" style="margin-top:6px;">适合识别“相对自身历史明显偏离”的异常，减少固定阈值误报。</div>
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="event_ai_enabled" ${config.event_ai_config?.enabled !== false ? 'checked' : ''}>
                    启用事件级 AI 诊断与通知总结
                </label>
                <div class="text-muted text-sm" style="margin-top:6px;">告警创建或升级后，AI 会总结现象、可能原因和建议动作。</div>
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="enabled" ${template?.enabled !== false ? 'checked' : ''}>
                    启用模板
                </label>
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="is_default" ${template?.is_default ? 'checked' : ''}>
                    设为默认模板
                </label>
            </div>
        `;

        form.querySelector('#templateAlertEngineMode')?.addEventListener('change', (event) => {
            const aiSection = form.querySelector('#templateAIPolicySection');
            if (aiSection) {
                aiSection.style.display = event.target.value === 'ai' ? 'block' : 'none';
            }
        });
        form.querySelector('[name="use_custom_expression"]')?.addEventListener('change', () => {
            this._toggleThresholdEditorMode(form);
        });
        form.querySelector('#validateTemplateExpressionBtn')?.addEventListener('click', async () => {
            await this._validateTemplateExpression(form);
        });

        const submitBtn = DOM.el('button', {
            className: 'btn btn-primary',
            type: 'button',
            textContent: isEdit ? '保存' : '创建',
            onClick: () => form.requestSubmit(),
        });

        DOM.bindAsyncSubmit(form, async () => {
            const formData = new FormData(form);
            const alertEngineMode = String(formData.get('alert_engine_mode') || 'threshold');
            const nextConfig = JSON.parse(JSON.stringify(config || this._defaultTemplateConfig()));
            nextConfig.alert_engine_mode = alertEngineMode;
            const thresholdRules = this._buildThresholdRulesFromForm(form);
            if (!thresholdRules) {
                return;
            }
            nextConfig.threshold_rules = thresholdRules;
            nextConfig.baseline_config = Object.assign({}, nextConfig.baseline_config || {}, {
                enabled: Boolean(form.querySelector('[name="baseline_enabled"]')?.checked),
            });
            nextConfig.event_ai_config = Object.assign({}, nextConfig.event_ai_config || {}, {
                enabled: Boolean(form.querySelector('[name="event_ai_enabled"]')?.checked),
                trigger_on_create: true,
                trigger_on_severity_upgrade: true,
            });
            nextConfig.ai_policy_text = alertEngineMode === 'ai'
                ? String(formData.get('ai_policy_text') || '').trim() || null
                : null;
            nextConfig.alert_ai_model_id = alertEngineMode === 'ai' && formData.get('alert_ai_model_id')
                ? parseInt(String(formData.get('alert_ai_model_id')), 10)
                : null;
            nextConfig.ai_shadow_enabled = false;

            const payload = {
                name: String(formData.get('name') || '').trim(),
                description: String(formData.get('description') || '').trim() || null,
                enabled: Boolean(form.querySelector('[name="enabled"]')?.checked),
                is_default: Boolean(form.querySelector('[name="is_default"]')?.checked),
                template_config: nextConfig,
            };

            if (!payload.name) {
                Toast.error('请填写模板名称');
                return;
            }
            if (!Object.keys(nextConfig.threshold_rules || {}).length) {
                Toast.error('请至少配置一条阈值规则或自定义表达式');
                return;
            }
            if (alertEngineMode === 'ai' && !nextConfig.ai_policy_text) {
                Toast.error('AI 判警模板必须填写自然语言规则');
                return;
            }

            try {
                if (isEdit) {
                    await API.updateAlertTemplate(template.id, payload);
                    Toast.success('告警模板已更新');
                } else {
                    await API.createAlertTemplate(payload);
                    Toast.success('告警模板已创建');
                }
                Modal.hide();
                this.render();
            } catch (err) {
                Toast.error(err.message);
            }
        }, { submitControls: [submitBtn] });

        const footer = DOM.el('div');
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-secondary',
            type: 'button',
            textContent: '取消',
            onClick: () => Modal.hide(),
        }));
        footer.appendChild(submitBtn);

        Modal.show({
            title: isEdit ? '编辑告警模板' : '新建告警模板',
            content: form,
            footer,
            width: '700px',
        });
    },

    async _setDefault(templateId) {
        const template = this.templates.find((item) => item.id === templateId);
        if (!template) return;
        try {
            await API.updateAlertTemplate(templateId, {
                name: template.name,
                description: template.description,
                enabled: template.enabled,
                is_default: true,
                template_config: template.template_config,
            });
            Toast.success('默认模板已更新');
            this.render();
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async _toggleTemplate(templateId, enabled) {
        try {
            await API.toggleAlertTemplate(templateId, enabled);
            Toast.success(enabled ? '模板已启用' : '模板已停用');
            this.render();
        } catch (err) {
            Toast.error(err.message);
        }
    },

    _normalizeTemplateConfig(config = null) {
        const defaults = this._defaultTemplateConfig();
        const payload = config && typeof config === 'object' ? config : {};
        return {
            alert_engine_mode: payload.alert_engine_mode === 'ai' ? 'ai' : 'threshold',
            threshold_rules: this._normalizeThresholdRules(payload.threshold_rules, defaults.threshold_rules),
            baseline_config: Object.assign({}, defaults.baseline_config, payload.baseline_config || {}),
            event_ai_config: Object.assign({}, defaults.event_ai_config, payload.event_ai_config || {}),
            ai_policy_text: payload.ai_policy_text || null,
            alert_ai_model_id: payload.alert_ai_model_id || null,
        };
    },

    _defaultTemplateConfig() {
        return {
            alert_engine_mode: 'threshold',
            threshold_rules: {
                cpu_usage: {
                    levels: [
                        { severity: 'low', threshold: 60, duration: 300 },
                        { severity: 'medium', threshold: 80, duration: 60 },
                        { severity: 'high', threshold: 85, duration: 60 },
                        { severity: 'critical', threshold: 90, duration: 60 },
                    ]
                },
                disk_usage: {
                    levels: [
                        { severity: 'low', threshold: 80, duration: 0 },
                        { severity: 'medium', threshold: 85, duration: 0 },
                        { severity: 'high', threshold: 90, duration: 0 },
                        { severity: 'critical', threshold: 95, duration: 0 },
                    ]
                },
                connections: {
                    levels: [
                        { severity: 'low', threshold: 20, duration: 60 },
                        { severity: 'medium', threshold: 30, duration: 60 },
                        { severity: 'high', threshold: 40, duration: 60 },
                        { severity: 'critical', threshold: 50, duration: 60 },
                    ]
                },
            },
            baseline_config: { enabled: true },
            event_ai_config: { enabled: true, trigger_on_create: true, trigger_on_severity_upgrade: true, trigger_on_recovery: false, stale_recheck_minutes: 30 },
            ai_policy_text: null,
            alert_ai_model_id: null,
        };
    },

    _modeLabel(mode) {
        return mode === 'ai' ? 'AI 判警' : '阈值判警';
    },

    _thresholdSummary(rules = {}) {
        const customExpression = rules?.custom_expression;
        if (customExpression?.expression) {
            const expr = String(customExpression.expression).replace(/\s+/g, ' ').trim();
            const compact = expr.length > 72 ? `${expr.slice(0, 72)}...` : expr;
            return `表达式: ${compact}`;
        }
        const labels = [
            ['cpu_usage', 'CPU'],
            ['disk_usage', '磁盘'],
            ['connections', '连接'],
        ];
        const parts = labels.map(([key, label]) => {
            const rule = rules?.[key];
            // Check if multi-level configuration
            if (rule?.levels && Array.isArray(rule.levels)) {
                return `${label}(${rule.levels.length}级)`;
            }
            return rule?.threshold != null ? `${label}>${rule.threshold}/${rule.duration || '-'}秒` : null;
        }).filter(Boolean);
        return parts.length ? parts.join(' / ') : '未配置阈值';
    },

    _normalizeThresholdRules(rules, defaultRules) {
        if (!rules || typeof rules !== 'object') {
            return JSON.parse(JSON.stringify(defaultRules));
        }
        if (rules.custom_expression && typeof rules.custom_expression === 'object') {
            return {
                custom_expression: {
                    expression: String(rules.custom_expression.expression || '').trim(),
                    duration: parseInt(String(rules.custom_expression.duration || '60'), 10) || 60,
                },
            };
        }
        const normalized = {};
        ['cpu_usage', 'disk_usage', 'connections'].forEach((key) => {
            const rule = rules[key];
            if (!rule || typeof rule !== 'object') {
                return;
            }
            // Check if multi-level configuration
            if (rule.levels && Array.isArray(rule.levels)) {
                normalized[key] = {
                    levels: rule.levels.map(level => ({
                        severity: level.severity,
                        threshold: parseInt(String(level.threshold), 10),
                        duration: parseInt(String(level.duration || '60'), 10) || 60,
                    }))
                };
            }
        });
        return normalized;
    },

    _getThresholdEditorState(rules = {}) {
        const normalized = this._normalizeThresholdRules(rules, this._defaultTemplateConfig().threshold_rules);
        const customRule = normalized.custom_expression;
        return {
            useCustomExpression: Boolean(customRule?.expression),
            customExpression: {
                expression: customRule?.expression || '',
                duration: customRule?.duration || 60,
            },
            cpu: this._metricRuleState(normalized.cpu_usage, 'cpu_usage'),
            disk: this._metricRuleState(normalized.disk_usage, 'disk_usage'),
            connections: this._metricRuleState(normalized.connections, 'connections'),
        };
    },

    _metricRuleState(rule, metricName) {
        const defaults = {
            cpu_usage: {
                levels: [
                    { severity: 'low', threshold: 60, duration: 300 },
                    { severity: 'medium', threshold: 80, duration: 60 },
                    { severity: 'high', threshold: 85, duration: 60 },
                    { severity: 'critical', threshold: 90, duration: 60 },
                ]
            },
            disk_usage: {
                levels: [
                    { severity: 'low', threshold: 80, duration: 0 },
                    { severity: 'medium', threshold: 85, duration: 0 },
                    { severity: 'high', threshold: 90, duration: 0 },
                    { severity: 'critical', threshold: 95, duration: 0 },
                ]
            },
            connections: {
                levels: [
                    { severity: 'low', threshold: 20, duration: 60 },
                    { severity: 'medium', threshold: 30, duration: 60 },
                    { severity: 'high', threshold: 40, duration: 60 },
                    { severity: 'critical', threshold: 50, duration: 60 },
                ]
            },
        };
        const defaultRule = defaults[metricName] || {
            levels: [
                { severity: 'low', threshold: 60, duration: 300 },
                { severity: 'medium', threshold: 80, duration: 60 },
                { severity: 'high', threshold: 85, duration: 60 },
                { severity: 'critical', threshold: 90, duration: 60 },
            ]
        };

        // Check if multi-level configuration
        if (rule?.levels && Array.isArray(rule.levels)) {
            const levelsBySeverity = {};
            rule.levels.forEach(level => {
                levelsBySeverity[level.severity] = level;
            });
            return {
                enabled: true,
                isMultiLevel: true,
                levels: {
                    low: levelsBySeverity.low || { threshold: 80, duration: 60 },
                    medium: levelsBySeverity.medium || { threshold: 80, duration: 60 },
                    high: levelsBySeverity.high || { threshold: 90, duration: 60 },
                    critical: levelsBySeverity.critical || { threshold: 95, duration: 60 },
                }
            };
        }

        // No rule configured
        return {
            enabled: false,
            isMultiLevel: true,
            levels: {
                low: { threshold: 80, duration: 60 },
                medium: { threshold: 80, duration: 120 },
                high: { threshold: 85, duration: 60 },
                critical: { threshold: 90, duration: 120 },
            }
        };
    },

    _toggleThresholdEditorMode(form) {
        const useCustom = Boolean(form.querySelector('[name="use_custom_expression"]')?.checked);
        const presetSection = form.querySelector('#templatePresetThresholdSection');
        const customSection = form.querySelector('#templateCustomExpressionSection');
        if (presetSection) presetSection.style.display = useCustom ? 'none' : 'block';
        if (customSection) customSection.style.display = useCustom ? 'block' : 'none';
    },

    async _validateTemplateExpression(form) {
        const validationEl = form.querySelector('#templateExpressionValidation');
        const expression = String(form.querySelector('[name="custom_expression_text"]')?.value || '').trim();
        if (!expression) {
            if (validationEl) {
                validationEl.innerHTML = '<span style="color:#f59e0b;">请先输入表达式</span>';
            }
            return;
        }
        if (validationEl) {
            validationEl.textContent = '正在校验表达式...';
        }
        try {
            const result = await API.post('/api/inspections/validate-expression', { expression });
            if (validationEl) {
                validationEl.innerHTML = result.valid
                    ? '<span style="color:#22c55e;">表达式语法有效</span>'
                    : `<span style="color:#ef4444;">表达式无效：${this._escapeHtml(result.error || '未知错误')}</span>`;
            }
        } catch (err) {
            if (validationEl) {
                validationEl.innerHTML = `<span style="color:#ef4444;">校验失败：${this._escapeHtml(err.message)}</span>`;
            }
        }
    },

    _buildThresholdRulesFromForm(form) {
        const useCustom = Boolean(form.querySelector('[name="use_custom_expression"]')?.checked);
        if (useCustom) {
            const expression = String(form.querySelector('[name="custom_expression_text"]')?.value || '').trim();
            const duration = parseInt(String(form.querySelector('[name="custom_expression_duration"]')?.value || '60'), 10) || 60;
            if (!expression) {
                Toast.error('请填写自定义表达式');
                return null;
            }
            return {
                custom_expression: {
                    expression,
                    duration,
                },
            };
        }

        const thresholdRules = {};
        const metricFields = [
            ['cpu_usage', 'cpu', 100],
            ['disk_usage', 'disk', 100],
            ['connections', 'connections', null],
        ];

        metricFields.forEach(([metricName, fieldName, max]) => {
            const enabled = Boolean(form.querySelector(`[name="${fieldName}_enabled"]`)?.checked);
            if (!enabled) return;

            // Collect all enabled levels for this metric
            const levels = [];
            const severities = ['low', 'medium', 'high', 'critical'];

            severities.forEach(severity => {
                const levelEnabled = Boolean(form.querySelector(`[name="${fieldName}_${severity}_enabled"]`)?.checked);
                if (!levelEnabled) return;

                const threshold = parseInt(String(form.querySelector(`[name="${fieldName}_${severity}_threshold"]`)?.value || ''), 10);
                const duration = parseInt(String(form.querySelector(`[name="${fieldName}_${severity}_duration"]`)?.value || ''), 10);

                if (!Number.isFinite(threshold) || threshold <= 0) return;
                if (max && threshold > max) return;

                levels.push({
                    severity,
                    threshold,
                    duration: Number.isFinite(duration) && duration > 0 ? duration : 60,
                });
            });

            if (levels.length > 0) {
                // Validate threshold ordering
                const sortedLevels = [...levels].sort((a, b) => {
                    const order = { low: 1, medium: 2, high: 3, critical: 4 };
                    return order[a.severity] - order[b.severity];
                });

                for (let i = 0; i < sortedLevels.length - 1; i++) {
                    if (sortedLevels[i].threshold > sortedLevels[i + 1].threshold) {
                        Toast.error(`${fieldName === 'cpu' ? 'CPU' : fieldName === 'disk' ? '磁盘' : '连接数'}：${sortedLevels[i].severity} 的阈值必须小于 ${sortedLevels[i + 1].severity}`);
                        return null;
                    }
                }

                thresholdRules[metricName] = { levels };
            }
        });

        if (!Object.keys(thresholdRules).length) {
            Toast.error('请至少启用一项基础阈值，或切换为自定义表达式');
            return null;
        }
        return thresholdRules;
    },

    _renderMetricLevelEditor(fieldName, label, unit, state) {
        const severities = [
            { key: 'low', label: 'Low', badge: 'badge-low' },
            { key: 'medium', label: 'Medium', badge: 'badge-medium' },
            { key: 'high', label: 'High', badge: 'badge-high' },
            { key: 'critical', label: 'Critical', badge: 'badge-critical' },
        ];

        const levelsHtml = severities.map(({ key, label: severityLabel, badge }) => {
            const level = state.isMultiLevel ? state.levels[key] : null;
            const enabled = level && level.threshold !== '';
            const threshold = enabled ? level.threshold : '';
            const duration = level ? level.duration : (key === 'critical' ? 60 : key === 'high' ? 180 : 300);

            return `
                <div class="threshold-level-row">
                    <span class="severity-badge ${badge}">${severityLabel}</span>
                    <input type="checkbox" name="${fieldName}_${key}_enabled" ${enabled ? 'checked' : ''}>
                    <input type="number" name="${fieldName}_${key}_threshold" class="form-input" min="1" ${unit === '%' ? 'max="100"' : ''} placeholder="阈值${unit}" value="${this._escapeAttr(threshold)}">
                    <input type="number" name="${fieldName}_${key}_duration" class="form-input" min="0" placeholder="持续秒" value="${this._escapeAttr(duration)}">
                </div>
            `;
        }).join('');

        return `
            <div class="alert-template-threshold-item">
                <label class="checkbox-label alert-template-threshold-toggle">
                    <input type="checkbox" name="${fieldName}_enabled" ${state.enabled ? 'checked' : ''}>
                    ${label}
                </label>
                <div class="alert-template-threshold-levels">
                    ${levelsHtml}
                </div>
            </div>
        `;
    },

    _compactRuleText(text) {
        const compact = String(text || '').replace(/\s+/g, ' ').trim();
        return compact.length > 96 ? `${compact.slice(0, 96)}...` : compact || '未填写规则';
    },

    _escapeHtml(value) {
        return Utils.escapeHtml(String(value ?? ''));
    },

    _escapeAttr(value) {
        return this._escapeHtml(value).replace(/"/g, '&quot;');
    },
};
