/* Alert template management page */
const AlertTemplatesPage = {
    _renderOptions: null,
    _container: null,
    templates: [],
    models: [],

    _t(key, params = {}) {
        return I18n.t(`alerts.templates.${key}`, params);
    },

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
                innerHTML: `<i data-lucide="plus"></i> ${this._t('create')}`,
                onClick: () => this._showForm(null),
            }));
        }
        if (!renderOptions.embedded) {
            Header.render(renderOptions.title || this._t('title'), actions);
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
            Toast.error(this._t('loadFailed', { message: err.message }));
            container.innerHTML = `
                <div class="error-state">
                    <h3>${this._t('loadErrorTitle')}</h3>
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
                <i data-lucide="plus"></i> ${this._t('create')}
            </button>
        ` : '';

        return `
            <div class="alert-ai-page-toolbar">
                <div>
                    <h3>${this._t('title')}</h3>
                    <div class="text-muted text-sm">${this._t('toolbarHint')}</div>
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
                    <h3>${this._t('emptyTitle')}</h3>
                    <p>${this._t('emptyHint')}</p>
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
        const displayName = this._localizedBuiltInText(template.name);
        const displayDescription = this._localizedBuiltInText(template.description || '') || this._t('noDescription');
        const adminActions = currentUser?.is_admin ? `
            <button class="btn btn-sm btn-secondary" onclick="AlertTemplatesPage._showForm(${template.id})">
                <i data-lucide="pencil"></i> ${this._t('edit')}
            </button>
            ${template.is_default ? '' : `
                <button class="btn btn-sm btn-secondary" onclick="AlertTemplatesPage._setDefault(${template.id})">
                    <i data-lucide="star"></i> ${this._t('setDefault')}
                </button>
            `}
            <button class="btn btn-sm ${template.enabled ? 'btn-danger' : 'btn-success'}" onclick="AlertTemplatesPage._toggleTemplate(${template.id}, ${template.enabled ? 'false' : 'true'})">
                <i data-lucide="${template.enabled ? 'pause' : 'play'}"></i> ${template.enabled ? this._t('disable') : this._t('enable')}
            </button>
        ` : '';

        return `
            <div class="datasource-card ai-model-card">
                <div class="datasource-card-header">
                    <span class="datasource-card-name">${this._escapeHtml(displayName)}</span>
                    <div class="alert-ai-policy-badges">
                        ${template.is_default ? `<span class="badge badge-info">${this._t('defaultBadge')}</span>` : ''}
                        <span class="badge ${template.enabled ? 'badge-success' : 'badge-secondary'}">${template.enabled ? this._t('enabledBadge') : this._t('disabledBadge')}</span>
                    </div>
                </div>
                <div class="datasource-card-info">
                    <span><i data-lucide="message-square-text"></i> ${this._escapeHtml(displayDescription)}</span>
                    <span><i data-lucide="siren"></i> ${this._escapeHtml(this._modeLabel(config.alert_engine_mode))}</span>
                    <span><i data-lucide="activity"></i> ${this._escapeHtml(this._thresholdSummary(config.threshold_rules))}</span>
                    <span><i data-lucide="line-chart"></i> ${config.baseline_config?.enabled ? this._t('baselineEnabled') : this._t('baselineDisabled')}</span>
                    <span><i data-lucide="brain"></i> ${config.event_ai_config?.enabled !== false ? this._t('eventAiEnabled') : this._t('eventAiDisabled')}</span>
                    ${config.alert_engine_mode === 'ai' ? `<span><i data-lucide="file-text"></i> ${this._escapeHtml(this._compactRuleText(this._localizedBuiltInText(config.ai_policy_text)))}</span>` : ''}
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
        const displayName = this._localizedBuiltInText(template?.name || '');
        const displayDescription = this._localizedBuiltInText(template?.description || '');
        const displayAiPolicy = this._localizedBuiltInText(config.ai_policy_text || '');
        const form = DOM.el('form');
        form.innerHTML = `
            <div class="form-group">
                <label>${this._t('name')}</label>
                <input type="text" name="name" class="form-input" required value="${this._escapeAttr(displayName)}" placeholder="${I18n.t('placeholders.alertTemplateName')}">
            </div>
            <div class="form-group">
                <label>${this._t('description')}</label>
                <input type="text" name="description" class="form-input" value="${this._escapeAttr(displayDescription)}" placeholder="${I18n.t('placeholders.alertTemplateDescription')}">
            </div>
            <div class="form-group">
                <label>${this._t('evaluationMode')}</label>
                <select name="alert_engine_mode" id="templateAlertEngineMode" class="form-select">
                    <option value="threshold" ${config.alert_engine_mode !== 'ai' ? 'selected' : ''}>${this._t('thresholdMode')}</option>
                    <option value="ai" ${config.alert_engine_mode === 'ai' ? 'selected' : ''}>${this._t('aiMode')}</option>
                </select>
                <div class="text-muted text-sm" style="margin-top:6px;">${this._t('modeHint')}</div>
            </div>
            <div class="form-group">
                <label>${this._t('thresholdRules')}</label>
                <div class="alert-template-threshold-mode">
                    <label class="checkbox-label">
                        <input type="checkbox" name="use_custom_expression" ${thresholdState.useCustomExpression ? 'checked' : ''}>
                        ${this._t('useCustomExpression')}
                    </label>
                </div>
                <div id="templatePresetThresholdSection" style="display:${thresholdState.useCustomExpression ? 'none' : 'block'};">
                    <div class="alert-template-threshold-list">
                        ${this._renderMetricLevelEditor('cpu', this._t('cpuUsage'), '%', thresholdState.cpu)}
                        ${this._renderMetricLevelEditor('disk', this._t('diskUsage'), '%', thresholdState.disk)}
                        ${this._renderMetricLevelEditor('connections_active', this._t('activeConnections'), '', thresholdState.connections_active)}
                    </div>
                    <div class="text-muted text-sm" style="margin-top:6px;">${this._t('thresholdHint')}</div>
                </div>
                <div id="templateCustomExpressionSection" style="display:${thresholdState.useCustomExpression ? 'block' : 'none'};">
                    <label class="text-muted text-sm">${this._t('expression')}</label>
                    <textarea name="custom_expression_text" class="form-textarea" rows="4" placeholder="${I18n.t('placeholders.customExpression')}">${this._escapeHtml(thresholdState.customExpression.expression)}</textarea>
                    <div class="alert-ai-advanced-grid" style="margin-top:12px;">
                        <div>
                            <label class="text-muted text-sm">${this._t('durationSeconds')}</label>
                            <input type="number" name="custom_expression_duration" class="form-input" min="1" value="${this._escapeAttr(thresholdState.customExpression.duration)}">
                        </div>
                    </div>
                    <div style="display:flex;gap:10px;align-items:center;margin-top:12px;flex-wrap:wrap;">
                        <button type="button" class="btn btn-secondary" id="validateTemplateExpressionBtn">${this._t('validateExpression')}</button>
                        <div id="templateExpressionValidation" class="text-muted text-sm">${this._t('availableMetrics')}</div>
                    </div>
                    <div class="text-muted text-sm" style="margin-top:6px;">${this._t('expressionHint')}</div>
                </div>
            </div>
            <div id="templateAIPolicySection" class="form-group" style="display:${config.alert_engine_mode === 'ai' ? 'block' : 'none'};">
                <label>${this._t('aiRule')}</label>
                <textarea name="ai_policy_text" class="form-textarea" rows="6" placeholder="${I18n.t('placeholders.aiPolicy')}">${this._escapeHtml(displayAiPolicy)}</textarea>
                <div class="form-group" style="margin-top:12px;">
                    <label>${this._t('aiModel')}</label>
                    <select name="alert_ai_model_id" class="form-select">
                        <option value="">${this._t('inheritDefaultModel')}</option>
                        ${this.models.map((model) => `<option value="${model.id}" ${String(config.alert_ai_model_id || '') === String(model.id) ? 'selected' : ''}>${this._escapeHtml(model.name)}</option>`).join('')}
                    </select>
                </div>
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="baseline_enabled" ${config.baseline_config?.enabled ? 'checked' : ''}>
                    ${this._t('enableBaseline')}
                </label>
                <div class="text-muted text-sm" style="margin-top:6px;">${this._t('baselineHint')}</div>
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="event_ai_enabled" ${config.event_ai_config?.enabled !== false ? 'checked' : ''}>
                    ${this._t('enableEventAi')}
                </label>
                <div class="text-muted text-sm" style="margin-top:6px;">${this._t('eventAiHint')}</div>
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="enabled" ${template?.enabled !== false ? 'checked' : ''}>
                    ${this._t('enableTemplate')}
                </label>
            </div>
            <div class="form-group">
                <label class="checkbox-label">
                    <input type="checkbox" name="is_default" ${template?.is_default ? 'checked' : ''}>
                    ${this._t('setDefaultTemplate')}
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
            textContent: isEdit ? this._t('saveAction') : this._t('createAction'),
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
                ? this._restoreBuiltInTextIfUnchanged(config.ai_policy_text, String(formData.get('ai_policy_text') || '').trim()) || null
                : null;
            nextConfig.alert_ai_model_id = alertEngineMode === 'ai' && formData.get('alert_ai_model_id')
                ? parseInt(String(formData.get('alert_ai_model_id')), 10)
                : null;
            nextConfig.ai_shadow_enabled = false;

            const payload = {
                name: this._restoreBuiltInTextIfUnchanged(template?.name, String(formData.get('name') || '').trim()),
                description: this._restoreBuiltInTextIfUnchanged(template?.description, String(formData.get('description') || '').trim()) || null,
                enabled: Boolean(form.querySelector('[name="enabled"]')?.checked),
                is_default: Boolean(form.querySelector('[name="is_default"]')?.checked),
                template_config: nextConfig,
            };

            if (!payload.name) {
                Toast.error(this._t('nameRequired'));
                return;
            }
            if (!Object.keys(nextConfig.threshold_rules || {}).length) {
                Toast.error(this._t('thresholdRequired'));
                return;
            }
            if (alertEngineMode === 'ai' && !nextConfig.ai_policy_text) {
                Toast.error(this._t('aiRuleRequired'));
                return;
            }

            try {
                if (isEdit) {
                    await API.updateAlertTemplate(template.id, payload);
                    Toast.success(this._t('updated'));
                } else {
                    await API.createAlertTemplate(payload);
                    Toast.success(this._t('created'));
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
            textContent: this._t('cancelAction'),
            onClick: () => Modal.hide(),
        }));
        footer.appendChild(submitBtn);

        Modal.show({
            title: isEdit ? this._t('editTitle') : this._t('createTitle'),
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
            Toast.success(this._t('defaultUpdated'));
            this.render();
        } catch (err) {
            Toast.error(err.message);
        }
    },

    async _toggleTemplate(templateId, enabled) {
        try {
            await API.toggleAlertTemplate(templateId, enabled);
            Toast.success(enabled ? this._t('templateEnabled') : this._t('templateDisabled'));
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
                connections_active: {
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
        return mode === 'ai' ? this._t('aiMode') : this._t('thresholdMode');
    },

    _thresholdSummary(rules = {}) {
        const customExpression = rules?.custom_expression;
        if (customExpression?.expression) {
            const expr = String(customExpression.expression).replace(/\s+/g, ' ').trim();
            const compact = expr.length > 72 ? `${expr.slice(0, 72)}...` : expr;
            return this._t('expressionPrefix', { expression: compact });
        }
        const labels = [
            ['cpu_usage', 'CPU'],
            ['disk_usage', this._t('diskUsage')],
            ['connections_active', this._t('activeConnections')],
        ];
        const parts = labels.map(([key, label]) => {
            const rule = rules?.[key];
            // Check if multi-level configuration
            if (rule?.levels && Array.isArray(rule.levels)) {
                return this._t('metricLevels', { metric: label, count: rule.levels.length });
            }
            return rule?.threshold != null ? this._t('metricThreshold', { metric: label, threshold: rule.threshold, duration: rule.duration || '-' }) : null;
        }).filter(Boolean);
        return parts.length ? parts.join(' / ') : this._t('noThreshold');
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
        ['cpu_usage', 'disk_usage', 'connections_active'].forEach((key) => {
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
            connections_active: this._metricRuleState(normalized.connections_active, 'connections_active'),
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
            connections_active: {
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
                validationEl.innerHTML = `<span style="color:#f59e0b;">${this._t('enterExpression')}</span>`;
            }
            return;
        }
        if (validationEl) {
            validationEl.textContent = this._t('validatingExpression');
        }
        try {
            const result = await API.post('/api/inspections/validate-expression', { expression });
            if (validationEl) {
                validationEl.innerHTML = result.valid
                    ? `<span style="color:#22c55e;">${this._t('expressionValid')}</span>`
                    : `<span style="color:#ef4444;">${this._t('expressionInvalid', { message: this._escapeHtml(result.error || I18n.t('common.unknown')) })}</span>`;
            }
        } catch (err) {
            if (validationEl) {
                validationEl.innerHTML = `<span style="color:#ef4444;">${this._t('validationFailed', { message: this._escapeHtml(err.message) })}</span>`;
            }
        }
    },

    _buildThresholdRulesFromForm(form) {
        const useCustom = Boolean(form.querySelector('[name="use_custom_expression"]')?.checked);
        if (useCustom) {
            const expression = String(form.querySelector('[name="custom_expression_text"]')?.value || '').trim();
            const duration = parseInt(String(form.querySelector('[name="custom_expression_duration"]')?.value || '60'), 10) || 60;
            if (!expression) {
                Toast.error(this._t('customExpressionRequired'));
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
            ['connections_active', 'connections_active', null],
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
                        const metric = fieldName === 'cpu' ? 'CPU' : fieldName === 'disk' ? this._t('diskUsage') : this._t('activeConnections');
                        Toast.error(this._t('thresholdOrder', {
                            metric,
                            lower: I18n.t(`alerts.severity.${sortedLevels[i].severity}`),
                            upper: I18n.t(`alerts.severity.${sortedLevels[i + 1].severity}`),
                        }));
                        return null;
                    }
                }

                thresholdRules[metricName] = { levels };
            }
        });

        if (!Object.keys(thresholdRules).length) {
            Toast.error(this._t('baseThresholdRequired'));
            return null;
        }
        return thresholdRules;
    },

    _renderMetricLevelEditor(fieldName, label, unit, state) {
        const severities = [
            { key: 'low', label: I18n.t('alerts.severity.low'), badge: 'badge-low' },
            { key: 'medium', label: I18n.t('alerts.severity.medium'), badge: 'badge-medium' },
            { key: 'high', label: I18n.t('alerts.severity.high'), badge: 'badge-high' },
            { key: 'critical', label: I18n.t('alerts.severity.critical'), badge: 'badge-critical' },
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
                    <input type="number" name="${fieldName}_${key}_threshold" class="form-input" min="1" ${unit === '%' ? 'max="100"' : ''} placeholder="${I18n.t('placeholders.threshold', { unit })}" value="${this._escapeAttr(threshold)}">
                    <input type="number" name="${fieldName}_${key}_duration" class="form-input" min="0" placeholder="${I18n.t('placeholders.durationSeconds')}" value="${this._escapeAttr(duration)}">
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
        return compact.length > 96 ? `${compact.slice(0, 96)}...` : compact || this._t('noRule');
    },

    _localizedBuiltInText(value) {
        const source = String(value || '');
        const keys = {
            '\u6807\u51c6\u751f\u4ea7\u544a\u8b66': 'standardName',
            '\u9002\u5408\u5927\u591a\u6570\u751f\u4ea7\u5e93\uff0c\u542f\u7528\u9608\u503c\u544a\u8b66\u3001\u5b9e\u4f8b\u57fa\u7ebf\u548c\u4e8b\u4ef6\u7ea7 AI \u8bca\u65ad\u3002': 'standardDescription',
            'AI \u667a\u80fd\u5224\u8b66': 'aiName',
            '\u9002\u5408\u5e0c\u671b\u51cf\u5c11\u786c\u7f16\u7801\u9608\u503c\u7684\u573a\u666f\uff0c\u7531 AI \u7ed3\u5408\u8d8b\u52bf\u4e0e\u4e0a\u4e0b\u6587\u505a\u6700\u7ec8\u5224\u8b66\u3002': 'aiDescription',
            '\u8f7b\u91cf\u5f00\u53d1\u544a\u8b66': 'devName',
            '\u9002\u5408\u6d4b\u8bd5/\u5f00\u53d1\u73af\u5883\uff0c\u9608\u503c\u66f4\u5bbd\u677e\uff0c\u9ed8\u8ba4\u5173\u95ed\u57fa\u7ebf\u3002': 'devDescription',
            '\u8bf7\u7ed3\u5408 CPU\u3001\u78c1\u76d8\u4f7f\u7528\u7387\u3001\u6d3b\u8dc3\u8fde\u63a5\u6570\u53ca\u6700\u8fd1 15 \u5206\u949f\u8d8b\u52bf\u5224\u65ad\u8be5\u5b9e\u4f8b\u662f\u5426\u5904\u4e8e\u660e\u663e\u5f02\u5e38\u72b6\u6001\u3002\u53ea\u6709\u5728\u5f02\u5e38\u6301\u7eed\u3001\u5f71\u54cd\u6269\u5927\u6216\u98ce\u9669\u8f83\u9ad8\u65f6\u624d\u89e6\u53d1\u544a\u8b66\uff1b\u82e5\u53ea\u662f\u77ed\u65f6\u6296\u52a8\u6216\u63a5\u8fd1\u9608\u503c\u4f46\u8bc1\u636e\u4e0d\u8db3\uff0c\u5219\u4e0d\u89e6\u53d1\u544a\u8b66\u3002': 'aiPolicy',
        };
        const key = keys[source];
        return key ? this._t(`builtIns.${key}`) : source;
    },

    _restoreBuiltInTextIfUnchanged(originalValue, submittedValue) {
        const original = String(originalValue || '');
        const submitted = String(submittedValue || '');
        return original && submitted === this._localizedBuiltInText(original) ? original : submitted;
    },

    _escapeHtml(value) {
        return Utils.escapeHtml(String(value ?? ''));
    },

    _escapeAttr(value) {
        return this._escapeHtml(value).replace(/"/g, '&quot;');
    },
};
