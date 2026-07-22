/* Datasources management page */
const DatasourcesPage = {
    allDatasources: [],
    filteredDatasources: [],
    latestMetrics: {},
    _sort: {
        field: 'name',
        direction: 'asc'
    },

    async render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        try {
            this.allDatasources = await API.getDatasources();
            this.filteredDatasources = [...this.allDatasources];
            this._applySort();
            Store.set('datasources', this.allDatasources);

            Header.render(I18n.t('pageCopy.datasources.datasourceManagement'), this._buildHeaderActions());

            content.innerHTML = '';

            if (this.allDatasources.length === 0) {
                content.innerHTML = I18n.t('pageCopy.datasources.noDatasourcesAddYourFirstDatabaseConnection');
                DOM.createIcons();
                return;
            }

            // Table container
            const tableContainer = DOM.el('div', { id: 'datasource-table-container' });
            content.appendChild(tableContainer);

            this._renderTable();
            DOM.createIcons();

            // Fetch latest metrics separately (after table renders for fast initial load)
            this._loadLatestMetrics();

        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        }
    },

    _escapeHtml(value) {
        return Utils.escapeHtml(String(value ?? ''));
    },

    _escapeAttr(value) {
        return this._escapeHtml(value).replace(/"/g, '&quot;');
    },

    _getDbTypeLabel(dbType) {
        const labels = {
            mysql: 'MySQL',
            postgresql: 'PostgreSQL',
            sqlserver: 'SQL Server',
            oracle: 'Oracle',
            'tdsql-c-mysql': 'TDSQL-C MySQL',
            'oceanbase-mysql': 'OceanBase MySQL',
            opengauss: 'openGauss',
            hana: 'SAP HANA',
        };
        return labels[dbType] || dbType || '-';
    },

    _formatHourValue(hours) {
        const value = Number(hours);
        if (!Number.isFinite(value)) return '-';
        return String(parseFloat(value.toFixed(2)));
    },

    _getSilenceState(datasource) {
        if (!datasource?.silence_until) {
            return {
                isSilenced: false,
                remainingHours: null,
                silenceUntil: null,
                reason: datasource?.silence_reason || null,
            };
        }

        const silenceUntil = new Date(datasource.silence_until);
        if (Number.isNaN(silenceUntil.getTime())) {
            return {
                isSilenced: false,
                remainingHours: null,
                silenceUntil: null,
                reason: datasource?.silence_reason || null,
            };
        }

        const remainingMs = silenceUntil.getTime() - Date.now();
        if (remainingMs <= 0) {
            return {
                isSilenced: false,
                remainingHours: null,
                silenceUntil,
                reason: datasource?.silence_reason || null,
            };
        }

        return {
            isSilenced: true,
            remainingHours: Math.round((remainingMs / 3600000) * 100) / 100,
            silenceUntil,
            reason: datasource?.silence_reason || null,
        };
    },

    _renderSilenceBadge(datasource) {
        const state = this._getSilenceState(datasource);
        if (!state.isSilenced) return '';

        const titleParts = [
            I18n.t('pageCopy.datasources.silenceUntilValue', { value0: Format.datetime(datasource.silence_until) }),
            I18n.t('pageCopy.datasources.remainingValueHours', { value0: this._formatHourValue(state.remainingHours) }),
        ];
        if (state.reason) {
            titleParts.push(I18n.t('pageCopy.datasources.reasonValue', { value0: state.reason }));
        }

        return I18n.t('pageCopy.datasources.theAlarmIsSilentValueH', { value0: this._escapeAttr(titleParts.join('\n')), value1: this._escapeHtml(this._formatHourValue(state.remainingHours)) });
    },

    async _loadLatestMetrics() {
        try {
            this.latestMetrics = await API.getDatasourcesLatestMetrics();
            this._renderTable();
        } catch (err) {
            console.warn('Failed to load latest metrics:', err);
        }
    },

    _buildHeaderActions() {
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters' });
        filtersContainer.innerHTML = I18n.t('pageCopy.datasources.allTypesMysqlPostgresqlOracleSqlServer', { value0: I18n.t('placeholders.searchDatasource'), value1: I18n.t('placeholders.filterTags') });

        const newBtn = DOM.el('button', { className: 'btn btn-primary' });
        newBtn.innerHTML = I18n.t('pageCopy.datasources.createANewDatasource');
        newBtn.onclick = () => DatasourceForm.show(null, () => this.render());

        setTimeout(() => {
            this._setupFilterListeners();
            DOM.createIcons();
        }, 0);

        return [filtersContainer, newBtn];
    },

    _setupFilterListeners() {
        DOM.$('#filterName')?.addEventListener('input', () => this._applyFilters());
        DOM.$('#filterTags')?.addEventListener('input', () => this._applyFilters());
        DOM.$('#filterType')?.addEventListener('change', () => this._applyFilters());
    },

    _applyFilters() {
        clearTimeout(this._filterDebounce);
        this._filterDebounce = setTimeout(() => this._reloadWithFilters(), 250);
    },

    async _reloadWithFilters() {
        const q = DOM.$('#filterName')?.value.trim() || '';
        const tagsRaw = DOM.$('#filterTags')?.value.trim() || '';
        const db_type = DOM.$('#filterType')?.value || '';

        const params = {};
        if (q) params.q = q;
        if (tagsRaw) params.tags = tagsRaw;
        if (db_type) params.db_type = db_type;

        try {
            this.allDatasources = await API.getDatasources(params);
            this.filteredDatasources = [...this.allDatasources];
            this._applySort();
            Store.set('datasources', this.allDatasources);
            this._renderTable();
            this._loadLatestMetrics();
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        }
    },

    _getStatusBadge(conn) {
        const status = conn.connection_status || 'unknown';
        const message = conn.connection_error || '';

        const statusMap = {
            normal: { icon: '✓', label: I18n.t('pageCopy.datasources.healthy'), class: 'badge-success', title: message || I18n.t('pageCopy.datasources.connectionHealthy') },
            failed: { icon: '✗', label: I18n.t('pageCopy.datasources.failed'), class: 'badge-danger', title: message || I18n.t('pageCopy.datasources.connectionFailed') },
            warning: { icon: '⚠', label: I18n.t('pageCopy.datasources.warning'), class: 'badge-warning', title: message || I18n.t('pageCopy.datasources.connectionWarning') },
            unknown: { icon: '○', label: I18n.t('pageCopy.datasources.unknown'), class: 'badge-secondary', title: message || I18n.t('pageCopy.datasources.noMonitoringData') }
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
        this.filteredDatasources.sort((a, b) => {
            let va, vb;
            // For CPU, QPS, connections - get from latestMetrics
            if (field === 'cpu_usage' || field === 'qps' || field === 'connections_active') {
                const metricsA = this.latestMetrics[a.id] || {};
                const metricsB = this.latestMetrics[b.id] || {};
                va = metricsA[field];
                vb = metricsB[field];
            } else {
                va = a[field];
                vb = b[field];
            }
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

    _renderTags(tags = []) {
        if (!tags.length) {
            return '<span style="color:var(--text-tertiary);">-</span>';
        }

        return `
            <div style="display:flex;flex-wrap:wrap;gap:6px;">
                ${tags.map(tag => `
                    <span style="display:inline-flex;align-items:center;padding:2px 8px;border-radius:999px;background:var(--bg-tertiary);color:var(--text-secondary);font-size:12px;line-height:1.5;">
                        ${tag}
                    </span>
                `).join('')}
            </div>
        `;
    },

    _renderMetricsCell(conn) {
        const metrics = this.latestMetrics[conn.id] || {};
        const cpu = metrics.cpu_usage;
        const qps = metrics.qps;
        const connections = metrics.connections_active;
        const cpuColor = this._getMetricColor(cpu);

        return `
            <td class="${cpuColor}">${cpu != null ? cpu.toFixed(1) + '%' : '-'}</td>
            <td>${qps != null ? qps.toFixed(1) : '-'}</td>
            <td>${connections != null ? connections : '-'}</td>
        `;
    },

    _renderActionMenuItem({ label, icon, onClick, danger = false, dividerBefore = false }) {
        return `
            ${dividerBefore ? '<div class="datasource-more-menu-divider"></div>' : ''}
            <button
                type="button"
                class="ds-more-menu-item datasource-more-menu-item${danger ? ' danger' : ''}"
                onclick="${onClick}"
            >
                <i data-lucide="${icon}" class="datasource-more-menu-icon"></i>
                <span>${this._escapeHtml(label)}</span>
            </button>
        `;
    },

    _renderTable() {
        const container = DOM.$('#datasource-table-container');
        if (!container) return;

        container.innerHTML = I18n.t('pageCopy.datasources.idNameTypeTagsHostDatabaseConnection', { value0: this.filteredDatasources.map(conn => {
                            const silenceState = this._getSilenceState(conn);
                            const hostDisplay = `${conn.host}:${conn.port}`;
                            const silenceMenuItems = silenceState.isSilenced
                                ? [
                                    this._renderActionMenuItem({
                                        label: I18n.t('pageCopy.datasources.adjustAlarmSilence'),
                                        icon: 'bell-ring',
                                        onClick: `DatasourcesPage._showSilenceModal(${conn.id})`
                                    }),
                                    this._renderActionMenuItem({
                                        label: I18n.t('pageCopy.datasources.cancelAlarmSilence'),
                                        icon: 'bell-off',
                                        onClick: `DatasourcesPage._cancelDatasourceSilence(${conn.id})`,
                                        danger: true
                                    })
                                ].join('')
                                : this._renderActionMenuItem({
                                    label: I18n.t('pageCopy.datasources.silenceAlerts'),
                                    icon: 'bell-off',
                                    onClick: `DatasourcesPage._showSilenceModal(${conn.id})`
                                });

                            return I18n.t('pageCopy.datasources.datasourceRow', { value0: conn.id, value1: this._escapeHtml(conn.name), value2: this._renderSilenceBadge(conn), value3: this._escapeHtml(this._getDbTypeLabel(conn.db_type)), value4: this._renderTags(conn.tags || []), value5: this._escapeAttr(hostDisplay), value6: this._escapeHtml(hostDisplay), value7: this._escapeAttr(conn.database || '-'), value8: this._escapeHtml(conn.database || '-'), value9: this._getStatusBadge(conn), value10: this._renderMetricsCell(conn), value11: conn.id, value12: conn.id, value13: this._renderActionMenuItem({
                                                    label: I18n.t('pageCopy.datasources.instanceDetails'),
                                                    icon: 'panel-left',
                                                    onClick: `DatasourcesPage._openInstanceDetail(${conn.id})`
                                                }), value14: this._renderActionMenuItem({
                                                    label: I18n.t('pageCopy.datasources.editDatasource'),
                                                    icon: 'pencil',
                                                    onClick: `DatasourcesPage._editDatasource(${conn.id})`
                                                }), value15: this._renderActionMenuItem({
                                                    label: I18n.t('pageCopy.datasources.runInspectionNow'),
                                                    icon: 'zap',
                                                    onClick: `DatasourcesPage._triggerInspection(${conn.id}, event)`
                                                }), value16: this._renderActionMenuItem({
                                                    label: I18n.t('pageCopy.datasources.testConnection'),
                                                    icon: 'plug',
                                                    onClick: `DatasourcesPage._testDatasource(${conn.id})`
                                                }), value17: this._renderActionMenuItem({
                                                    label: I18n.t('pageCopy.datasources.inspectionAndAlarmConfiguration'),
                                                    icon: 'settings',
                                                    onClick: `DatasourcesPage._showInspectionConfig(${conn.id})`
                                                }), value18: silenceMenuItems, value19: this._renderActionMenuItem({
                                                    label: I18n.t('pageCopy.datasources.deleteDatasource'),
                                                    icon: 'trash-2',
                                                    onClick: `DatasourcesPage._deleteDatasource(${conn.id})`,
                                                    danger: true,
                                                    dividerBefore: true
                                                }) });
                        }).join('') });
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

    _toggleMoreMenu(event, id) {
        event.stopPropagation();
        const menu = document.getElementById(`more-menu-${id}`);
        if (!menu) return;
        const isOpen = menu.style.display !== 'none';
        // close all open menus first
        document.querySelectorAll('.ds-more-menu').forEach(m => m.style.display = 'none');
        if (!isOpen) {
            // use fixed positioning to escape table overflow clipping
            const btn = event.currentTarget;
            const rect = btn.getBoundingClientRect();
            menu.style.position = 'fixed';
            menu.style.top = '0px';
            menu.style.left = '';
            menu.style.right = '';
            menu.style.display = 'block';
            const menuWidth = menu.offsetWidth || 180;
            const menuHeight = menu.offsetHeight || 260;
            const viewportPadding = 8;
            const preferredLeft = rect.right - menuWidth;
            const preferredTop = rect.bottom + 4;
            const fitsBelow = preferredTop + menuHeight <= window.innerHeight - viewportPadding;
            const resolvedTop = fitsBelow
                ? preferredTop
                : Math.max(viewportPadding, rect.top - menuHeight - 4);
            const resolvedLeft = Math.min(
                window.innerWidth - menuWidth - viewportPadding,
                Math.max(viewportPadding, preferredLeft)
            );
            menu.style.top = `${resolvedTop}px`;
            menu.style.left = `${resolvedLeft}px`;
            DOM.createIcons();
            // close on next outside click
            const handler = () => {
                menu.style.display = 'none';
                document.removeEventListener('click', handler, true);
            };
            document.addEventListener('click', handler, true);
        }
    },

    async _testDatasource(id) {
        try {
            const datasource = this.allDatasources.find(d => d.id === id);
            const result = await API.testDatasource(id);
            if (result.success) {
                const versionDisplay = result.version && datasource
                    ? this._simplifyVersion(result.version, datasource.db_type).short
                    : result.version || '';
                Toast.success(I18n.t('pageCopy.datasources.connectedValue', { value0: versionDisplay }));
            } else {
                Toast.error(result.message || I18n.t('common.failed'));
            }
            // 重新加载数据源列表以更新连接状态
            await this._reloadWithFilters();
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        }
    },

    _editDatasource(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (conn) DatasourceForm.show(conn, () => this.render());
    },

    _openInstanceDetail(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (!conn) return;
        Store.set('currentInstance', conn);
        Store.set('currentInstanceId', conn.id);
        Store.set('currentConnection', conn);
        Store.set('currentDatasource', conn);
        Router.navigate(`instance-detail?datasource=${conn.id}&tab=monitor`);
    },

    _showSilenceModal(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (!conn) return;

        const state = this._getSilenceState(conn);
        const defaultHours = state.isSilenced ? this._formatHourValue(state.remainingHours) : '1';
        const currentStatusHtml = state.isSilenced ? I18n.t('pageCopy.datasources.currentlyInAlarmSilenceDeadlineValueRemaining', { value0: this._escapeHtml(Format.datetime(conn.silence_until)), value1: this._escapeHtml(this._formatHourValue(state.remainingHours)), value2: state.reason ? I18n.t('pageCopy.datasources.reasonForSilenceValue', { value0: this._escapeHtml(state.reason) }) : '' }) : '';

        Modal.show({
            title: I18n.t('pageCopy.datasources.silenceAlerts'),
            content: I18n.t("pageCopy.datasources._showSilenceModalContent", { value0: this._escapeHtml(conn.name), value1: currentStatusHtml, value2: this._escapeAttr(defaultHours), value3: I18n.t('placeholders.silenceReason'), value4: this._escapeHtml(state.reason || '') }),
            buttons: [
                { text: I18n.t('pageCopy.datasources.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: state.isSilenced ? I18n.t('pageCopy.datasources.updateSilently') : I18n.t('pageCopy.datasources.startSilence'),
                    variant: 'primary',
                    onClick: () => this._setDatasourceSilence(id)
                }
            ]
        });
    },

    async _setDatasourceSilence(id) {
        const hoursValue = DOM.$('#datasource-silence-hours')?.value;
        const reasonValue = DOM.$('#datasource-silence-reason')?.value?.trim() || '';
        const hours = parseFloat(hoursValue);

        if (!Number.isFinite(hours)) {
            Toast.error(I18n.t('alerts.silence.invalidDuration'));
            return;
        }
        if (hours < 0.5 || hours > 240) {
            Toast.error(I18n.t('alerts.silence.outOfRange'));
            return;
        }

        try {
            const result = await API.setDatasourceSilence(id, {
                hours,
                reason: reasonValue || null,
            });
            Modal.hide();
            Toast.success(I18n.t('pageCopy.datasources.alertSilenceEnabledValueHours', { value0: this._formatHourValue(result.remaining_hours ?? hours) }));
            await this.render();
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        }
    },

    async _cancelDatasourceSilence(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (!conn) return;

        Modal.show({
            title: I18n.t('pageCopy.datasources.cancelAlarmSilence'),
            content: I18n.t("pageCopy.datasources._cancelDatasourceSilenceContent", { value0: this._escapeHtml(conn.name) }),
            buttons: [
                { text: I18n.t('pageCopy.datasources.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                {
                    text: I18n.t('pageCopy.datasources.confirmCancellation'),
                    variant: 'danger',
                    onClick: async () => {
                        try {
                            await API.cancelDatasourceSilence(id);
                            Modal.hide();
                            Toast.success(I18n.t('pageCopy.datasources.alarmSilenceHasBeenCanceled'));
                            await this.render();
                        } catch (err) {
                            Toast.error(err.message || I18n.t('common.requestFailed'));
                        }
                    }
                }
            ]
        });
    },

    async _deleteDatasource(id) {
        const conn = this.allDatasources.find(c => c.id === id);
        if (!conn || !confirm(I18n.t('pageCopy.datasources.deleteDatasourceValueThisActionCannotBe', { value0: conn.name }))) return;
        try {
            await API.deleteDatasource(id);
            Toast.success(I18n.t('pageCopy.datasources.datasourceDeleted'));
            this.render();
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        }
    },

    async _triggerInspection(datasourceId, triggerEvent = null) {
        if (!confirm(I18n.t('pageCopy.datasources.triggerManualInspectionThisWillGenerateA'))) {
            return;
        }
        const trigger = triggerEvent?.target?.closest('button');
        if (trigger) {
            trigger.innerHTML = '<div class="spinner"></div>';
            trigger.disabled = true;
        }
        try {
            await API.post(`/api/inspections/trigger/${datasourceId}`);
            Toast.success(I18n.t('pageCopy.datasources.inspectionHasBeenSuccessfullyTriggered'));
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        } finally {
            if (trigger) {
                trigger.innerHTML = '<i data-lucide="more-horizontal"></i>';
                trigger.disabled = false;
                DOM.createIcons();
            }
        }
    },

    async _showInspectionConfig(datasourceId, draft = null) {
        try {
            const [config, templates, baselineSummary] = await Promise.all([
                API.get(`/api/inspections/config/${datasourceId}`),
                API.getAlertTemplates(),
                API.get(`/api/inspections/baseline/${datasourceId}`),
            ]);
            this._inspectionConfigSnapshot = config;
            this._inspectionTemplates = Array.isArray(templates) ? templates : [];
            this._inspectionBaselineSummary = baselineSummary || null;
            const effectiveConfig = {
                ...config,
                ...(draft && typeof draft === 'object' ? draft : {}),
            };
            const selectedTemplateId = effectiveConfig?.alert_template_id || this._inspectionTemplates.find((item) => item.is_default)?.id || '';

            Modal.show({
                title: I18n.t('pageCopy.datasources.inspectionAndAlarmConfiguration'),
                content: I18n.t("pageCopy.datasources._showInspectionConfigContent", { value0: effectiveConfig?.enabled ? 'checked' : '', value1: this._buildScheduleIntervalOptions(effectiveConfig?.schedule_interval || 86400), value2: effectiveConfig?.use_ai_analysis !== false ? 'checked' : '', value3: this._inspectionTemplates.filter((item) => item.enabled || item.id === selectedTemplateId).map((item) => `
                                        <option value="${item.id}" ${String(selectedTemplateId) === String(item.id) ? 'selected' : ''}>
                                            ${this._escapeHtml(item.name)}${item.is_default ? I18n.t('pageCopy.datasources._showInspectionConfigContent2') : ''}
                                        </option>
                                    `).join(''), value4: this._renderAlertTemplatePreview(selectedTemplateId, baselineSummary), value5: this._escapeHtml(config?.alert_template_name || I18n.t('pageCopy.datasources._showInspectionConfigContent3')), value6: this._escapeHtml(config?.next_scheduled_at ? Format.datetime(config.next_scheduled_at) : '-'), value7: this._escapeHtml(config?.last_scheduled_at ? Format.datetime(config.last_scheduled_at) : '-'), value8: baselineSummary?.profile_count || 0 }),
                buttons: [
                    { text: I18n.t('pageCopy.datasources.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                    { text: I18n.t('pageCopy.datasources.save'), variant: 'primary', onClick: () => this._saveInspectionConfig(datasourceId) }
                ]
            });

            this._setupInspectionConfigListeners(datasourceId);
        } catch (error) {
            Toast.error(error.message || I18n.t('common.requestFailed'));
        }
    },

    _buildScheduleIntervalOptions(currentValue) {
        const presets = [
            { value: 3600, label: I18n.t('pageCopy.datasources.hourly') },
            { value: 21600, label: I18n.t('pageCopy.datasources.every6Hours') },
            { value: 86400, label: I18n.t('pageCopy.datasources.everyDay') },
            { value: 604800, label: I18n.t('pageCopy.datasources.weekly') },
            { value: 2592000, label: I18n.t('pageCopy.datasources.monthly') },
        ];
        const numericCurrent = parseInt(currentValue, 10) || 86400;
        const hasCurrent = presets.some((item) => item.value === numericCurrent);
        const items = hasCurrent ? presets : presets.concat([{ value: numericCurrent, label: I18n.t('pageCopy.datasources.customValueSeconds', { value0: numericCurrent }) }]);
        return items.map((item) => `<option value="${item.value}" ${item.value === numericCurrent ? 'selected' : ''}>${item.label}</option>`).join('');
    },

    _normalizeAlertTemplateConfig(config) {
        const payload = config && typeof config === 'object' ? config : {};
        const thresholdRules = payload.threshold_rules && typeof payload.threshold_rules === 'object' ? payload.threshold_rules : {};
        return {
            alert_engine_mode: payload.alert_engine_mode === 'ai' ? 'ai' : 'threshold',
            threshold_rules: thresholdRules,
            baseline_config: payload.baseline_config || {},
            event_ai_config: payload.event_ai_config || {},
            ai_policy_text: payload.ai_policy_text || null,
        };
    },

    _renderAlertTemplatePreview(templateId, baselineSummary = null) {
        const template = (this._inspectionTemplates || []).find((item) => String(item.id) === String(templateId));
        if (!template) {
            return I18n.t('pageCopy.datasources.afterSelectingATemplateASummaryOf');
        }

        const config = this._normalizeAlertTemplateConfig(template.template_config);
        const customExpression = config.threshold_rules?.custom_expression;
        const thresholdSummary = customExpression?.expression
            ? I18n.t('pageCopy.datasources.customExpressionValue', { value0: customExpression.expression })
            : [
                ['cpu_usage', 'CPU'],
                ['disk_usage', I18n.t('pageCopy.datasources.disk')],
                ['connections_active', I18n.t('pageCopy.datasources.connection')],
            ].map(([key, label]) => {
                const rule = config.threshold_rules?.[key];
                return rule?.threshold != null ? I18n.t('pageCopy.datasources.conditionDuration', { value0: label, value1: rule.threshold, value2: rule.duration || '-' }) : null;
            }).filter(Boolean).join(' / ');
        const baselineText = config.baseline_config?.enabled
            ? I18n.t('pageCopy.datasources.enabledValue', { value0: baselineSummary ? I18n.t('pageCopy.datasources.currentinstanceValueTimeSlotPortrait', { value0: baselineSummary.profile_count || 0 }) : '' })
            : I18n.t('pageCopy.datasources.notEnabled');
        const eventAIText = config.event_ai_config?.enabled !== false ? I18n.t('pageCopy.datasources.enabled') : I18n.t('pageCopy.datasources.close');
        return I18n.t('pageCopy.datasources.alertTemplatePreview', { value0: this._escapeHtml(template.name), value1: template.is_default ? I18n.t('pageCopy.datasources.defaultTemplate') : '', value2: template.enabled ? 'badge-success' : 'badge-secondary', value3: template.enabled ? I18n.t('pageCopy.datasources.enable') : I18n.t('pageCopy.datasources.disabled'), value4: this._escapeHtml(config.alert_engine_mode === 'ai' ? I18n.t('pageCopy.datasources.aiAlertEvaluation') : I18n.t('pageCopy.datasources.thresholdEvaluation')), value5: this._escapeHtml(thresholdSummary || I18n.t('pageCopy.datasources.notConfigured')), value6: this._escapeHtml(baselineText), value7: this._escapeHtml(eventAIText), value8: config.alert_engine_mode === 'ai' && config.ai_policy_text ? I18n.t('pageCopy.datasources.aiValue', { value0: this._escapeHtml(config.ai_policy_text) }) : '', value9: template.summary ? I18n.t('pageCopy.datasources.summaryLabel', { value0: this._escapeHtml(template.summary) }) : '' });
    },

    _syncInspectionTemplatePreview(selectedTemplateId = null) {
        const templateId = selectedTemplateId ?? DOM.$('#alertTemplateId')?.value;
        const preview = DOM.$('#alertTemplatePreview');
        if (preview) {
            preview.innerHTML = this._renderAlertTemplatePreview(templateId, this._inspectionBaselineSummary);
        }
        const template = (this._inspectionTemplates || []).find((item) => String(item.id) === String(templateId));
        const config = this._normalizeAlertTemplateConfig(template?.template_config);
        const rebuildBtn = DOM.$('#rebuildBaselineBtn');
        const detailBtn = DOM.$('#viewBaselineDetailBtn');
        if (rebuildBtn) {
            rebuildBtn.style.display = config.baseline_config?.enabled ? 'inline-flex' : 'none';
        }
        if (detailBtn) {
            detailBtn.style.display = config.baseline_config?.enabled ? 'inline-flex' : 'none';
        }
    },

    _setupInspectionConfigListeners(datasourceId) {
        DOM.$('#alertTemplateId')?.addEventListener('change', (event) => {
            this._syncInspectionTemplatePreview(event.target.value);
        });

        DOM.$('#openAlertTemplatesBtn')?.addEventListener('click', () => {
            Modal.hide();
            Router.navigate('alerts?tab=templates');
        });

        DOM.$('#viewBaselineDetailBtn')?.addEventListener('click', async () => {
            await this._showBaselineDetail(datasourceId, this._captureInspectionConfigDraft());
        });

        DOM.$('#rebuildBaselineBtn')?.addEventListener('click', async () => {
            const btn = DOM.$('#rebuildBaselineBtn');
            btn.disabled = true;
            btn.textContent = I18n.t('pageCopy.datasources.rebuilding');
            try {
                const result = await API.post(`/api/inspections/baseline/${datasourceId}/rebuild`);
                this._inspectionBaselineSummary = result;
                this._syncInspectionTemplatePreview();
                Toast.success(I18n.t('pageCopy.datasources.historicalBaselineReconstructionCompleted'));
            } catch (err) {
                Toast.error(err.message || I18n.t('common.requestFailed'));
            } finally {
                btn.disabled = false;
                btn.textContent = I18n.t('pageCopy.datasources.rebuildTheCurrentInstanceBaseline');
            }
        });

        this._syncInspectionTemplatePreview();
    },

    _captureInspectionConfigDraft() {
        return {
            enabled: Boolean(DOM.$('#enableAuto')?.checked),
            schedule_interval: parseInt(DOM.$('#scheduleInterval')?.value, 10) || 86400,
            use_ai_analysis: Boolean(DOM.$('#useAI')?.checked),
            alert_template_id: DOM.$('#alertTemplateId')?.value ? parseInt(DOM.$('#alertTemplateId')?.value, 10) : null,
        };
    },

    async _showBaselineDetail(datasourceId, draft = null) {
        try {
            const summary = await API.get(`/api/inspections/baseline/${datasourceId}?limit=500`);
            const content = this._renderBaselineDetailContent(summary || {});
            Modal.show({
                title: I18n.t('pageCopy.datasources.instanceBaselineDetails'),
                content,
                size: 'xlarge',
                width: '1080px',
                bodyClassName: 'baseline-detail-modal-body',
                onHide: () => this._showInspectionConfig(datasourceId, draft),
                buttons: [
                    { text: I18n.t('pageCopy.datasources.close'), variant: 'secondary', onClick: () => Modal.hide() },
                ],
            });
        } catch (error) {
            Toast.error(error.message || I18n.t('common.requestFailed'));
        }
    },

    _renderBaselineDetailContent(summary) {
        const wrapper = DOM.el('div', { className: 'baseline-detail-modal' });
        const enabled = Boolean(summary?.enabled);
        const profiles = Array.isArray(summary?.profiles) ? summary.profiles : [];
        const groupedProfiles = this._groupBaselineProfiles(profiles);

        const summaryCard = DOM.el('div', { className: 'baseline-detail-summary' });
        summaryCard.innerHTML = I18n.t('pageCopy.datasources.baselineStatusValueNumberOfPortraitsValue', { value0: enabled ? I18n.t('pageCopy.datasources.enabled2') : I18n.t('pageCopy.datasources.notEnabled'), value1: summary?.profile_count || 0, value2: summary?.diagnostics?.learning_days || '-', value3: summary?.diagnostics?.min_samples || '-', value4: Array.isArray(summary?.diagnostics?.default_metrics) && summary.diagnostics.default_metrics.length
                    ? summary.diagnostics.default_metrics.map((metric) => this._escapeHtml(this._getBaselineMetricLabel(metric))).join(' / ')
                    : '-', value5: summary?.last_profile_updated_at ? this._escapeHtml(Format.datetime(summary.last_profile_updated_at)) : '-' });
        wrapper.appendChild(summaryCard);

        if (!enabled) {
            wrapper.appendChild(DOM.el('div', {
                className: 'empty-state',
                innerHTML: I18n.t('pageCopy.datasources.instanceBaselinesAreNotEnabledForThe'),
            }));
            return wrapper;
        }

        if (!profiles.length) {
            wrapper.appendChild(DOM.el('div', {
                className: 'empty-state',
                innerHTML: I18n.t('pageCopy.datasources.noBaselineImageYetYouCanWait'),
            }));
            return wrapper;
        }

        const metricsBoard = DOM.el('div', { className: 'baseline-detail-metrics-board' });
        const metricConfigs = summary?.baseline_config?.metrics || {};
        this._getOrderedBaselineMetricGroups(groupedProfiles).forEach(([metricName, items]) => {
            metricsBoard.appendChild(this._renderBaselineMetricCard(metricName, items, metricConfigs[metricName] || {}));
        });
        wrapper.appendChild(metricsBoard);

        return wrapper;
    },

    _getOrderedBaselineMetricGroups(groupedProfiles) {
        const preferredOrder = ['cpu_usage', 'disk_usage', 'connections_active', 'qps', 'tps'];
        const keys = Object.keys(groupedProfiles || {});
        return keys
            .sort((left, right) => {
                const leftIndex = preferredOrder.indexOf(left);
                const rightIndex = preferredOrder.indexOf(right);
                if (leftIndex === -1 && rightIndex === -1) return left.localeCompare(right, I18n.getLocale());
                if (leftIndex === -1) return 1;
                if (rightIndex === -1) return -1;
                return leftIndex - rightIndex;
            })
            .map((key) => [key, groupedProfiles[key]]);
    },

    _renderBaselineMetricCard(metricName, items, metricConfig = {}) {
        const card = DOM.el('div', {
            className: `baseline-metric-card baseline-metric-card-${this._escapeHtml(metricName)}`,
        });
        const slotMap = this._buildBaselineSlotMap(items);
        const latestItem = [...items].sort((left, right) => {
            const leftTime = left?.updated_at ? new Date(left.updated_at).getTime() : 0;
            const rightTime = right?.updated_at ? new Date(right.updated_at).getTime() : 0;
            return rightTime - leftTime;
        })[0];

        const hoursHeader = [0, 6, 12, 18, 23].map((hour) => `
            <span style="grid-column:${hour + 1};">${String(hour).padStart(2, '0')}</span>
        `).join('');

        const rows = Array.from({ length: 7 }, (_, weekday) => {
            const cells = Array.from({ length: 24 }, (_, hour) => {
                const item = slotMap[`${weekday}-${hour}`];
                if (!item) {
                    return '<span class="baseline-heatmap-cell is-empty"></span>';
                }
                const levelClass = this._getBaselineCellLevel(metricName, item, metricConfig);
                const sampleCount = item.sample_count ?? '-';
                const label = I18n.t('pageCopy.datasources.baselineSlotSummary', { value0: this._getWeekdayLabel(weekday), value1: String(hour).padStart(2, '0'), value2: this._formatBaselineNumber(item.avg_value), value3: this._getBaselineMetricUnit(metricName), value4: this._formatBaselineNumber(item.p95_value), value5: this._getBaselineMetricUnit(metricName), value6: sampleCount });
                return `<span class="baseline-heatmap-cell ${levelClass}" title="${this._escapeAttr(label)}"></span>`;
            }).join('');
            return `
                <div class="baseline-heatmap-row">
                    <div class="baseline-heatmap-row-label">${this._escapeHtml(this._getWeekdayLabel(weekday).replace(I18n.t('pageCopy.datasources.weekLabel'), ''))}</div>
                    <div class="baseline-heatmap-row-cells">${cells}</div>
                </div>
            `;
        }).join('');

        const avgRange = this._buildBaselineRangeText(items, 'avg_value', metricName);
        const p95Range = this._buildBaselineRangeText(items, 'p95_value', metricName);

        card.innerHTML = I18n.t('pageCopy.datasources.baselineProfileSummary', { value0: this._escapeHtml(this._getBaselineMetricLabel(metricName)), value1: items.length, value2: latestItem?.updated_at ? I18n.t('pageCopy.datasources.updateValue', { value0: this._escapeHtml(Format.datetime(latestItem.updated_at)) }) : '', value3: this._escapeHtml(avgRange), value4: this._escapeHtml(p95Range), value5: hoursHeader, value6: rows });
        return card;
    },

    _groupBaselineProfiles(profiles) {
        const groups = {};
        (profiles || []).forEach((item) => {
            const metricName = item.metric_name || 'unknown';
            if (!groups[metricName]) {
                groups[metricName] = [];
            }
            groups[metricName].push(item);
        });
        Object.values(groups).forEach((items) => {
            items.sort((a, b) => {
                const weekdayDiff = Number(a.weekday || 0) - Number(b.weekday || 0);
                if (weekdayDiff !== 0) return weekdayDiff;
                return Number(a.hour || 0) - Number(b.hour || 0);
            });
        });
        return groups;
    },

    _buildBaselineSlotMap(items) {
        return (items || []).reduce((acc, item) => {
            acc[`${Number(item.weekday || 0)}-${Number(item.hour || 0)}`] = item;
            return acc;
        }, {});
    },

    _getBaselineCellLevel(metricName, item, metricConfig = {}) {
        const representativeValue = Number(item?.p95_value ?? item?.avg_value ?? item?.max_value ?? 0);
        if (!Number.isFinite(representativeValue)) {
            return 'baseline-level-low';
        }

        if (metricName === 'cpu_usage' || metricName === 'disk_usage') {
            if (representativeValue < 20) return 'baseline-level-low';
            if (representativeValue <= 80) return 'baseline-level-medium';
            return 'baseline-level-high';
        }

        if (metricName === 'connections_active') {
            if (representativeValue < 5) return 'baseline-level-low';
            if (representativeValue <= 20) return 'baseline-level-medium';
            return 'baseline-level-high';
        }

        const minimum = Number(metricConfig?.minimum);
        if (Number.isFinite(minimum) && minimum > 0) {
            if (representativeValue < minimum) return 'baseline-level-low';
            if (representativeValue <= minimum * 2) return 'baseline-level-medium';
            return 'baseline-level-high';
        }

        if (representativeValue < 20) return 'baseline-level-low';
        if (representativeValue <= 80) return 'baseline-level-medium';
        return 'baseline-level-high';
    },

    _buildBaselineRangeText(items, fieldName, metricName) {
        const values = (items || [])
            .map((item) => Number(item?.[fieldName]))
            .filter((value) => Number.isFinite(value));
        if (!values.length) {
            return '-';
        }
        const minValue = Math.min(...values);
        const maxValue = Math.max(...values);
        const unit = this._getBaselineMetricUnit(metricName);
        return `${this._formatBaselineNumber(minValue)}${unit} - ${this._formatBaselineNumber(maxValue)}${unit}`;
    },

    _getWeekdayLabel(weekday) {
        return [I18n.t('pageCopy.datasources.monday'), I18n.t('pageCopy.datasources.tuesday'), I18n.t('pageCopy.datasources.wednesday'), I18n.t('pageCopy.datasources.thursday'), I18n.t('pageCopy.datasources.friday'), I18n.t('pageCopy.datasources.saturday'), I18n.t('pageCopy.datasources.sunday')][Number(weekday) || 0] || I18n.t('pageCopy.datasources.weekValue', { value0: weekday });
    },

    _getBaselineMetricLabel(metricName) {
        return {
            cpu_usage: I18n.t('pageCopy.datasources.cpuUsage'),
            disk_usage: I18n.t('pageCopy.datasources.diskUsage'),
            connections_active: I18n.t('pageCopy.datasources.activeConnections'),
            qps: 'QPS',
            tps: 'TPS',
        }[metricName] || metricName || '-';
    },

    _getBaselineMetricUnit(metricName) {
        if (metricName === 'cpu_usage' || metricName === 'disk_usage') return '%';
        return '';
    },

    _formatBaselineNumber(value) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
        const numericValue = Number(value);
        if (Math.abs(numericValue) >= 100) return numericValue.toFixed(0);
        if (Math.abs(numericValue) >= 10) return numericValue.toFixed(1);
        return numericValue.toFixed(2);
    },

    async _saveInspectionConfig(datasourceId) {
        const baseConfig = this._inspectionConfigSnapshot || await API.get(`/api/inspections/config/${datasourceId}`);
        const enabled = DOM.$('#enableAuto')?.checked;
        const schedule_interval = parseInt(DOM.$('#scheduleInterval')?.value) || 86400;
        const use_ai_analysis = DOM.$('#useAI')?.checked;
        const alert_template_id = DOM.$('#alertTemplateId')?.value ? parseInt(DOM.$('#alertTemplateId')?.value, 10) : null;

        if (!alert_template_id) {
            Toast.error(I18n.t('alerts.templates.selectRequired'));
            return;
        }

        try {
            await API.post(`/api/inspections/config/${datasourceId}`, {
                enabled,
                schedule_interval,
                use_ai_analysis,
                ai_model_id: baseConfig?.ai_model_id || null,
                kb_ids: Array.isArray(baseConfig?.kb_ids) ? baseConfig.kb_ids : [],
                alert_template_id,
                threshold_rules: baseConfig?.threshold_rules || {},
                alert_engine_mode: baseConfig?.alert_engine_mode || 'inherit',
                ai_policy_source: baseConfig?.ai_policy_source || 'inline',
                ai_policy_text: baseConfig?.ai_policy_text || null,
                ai_policy_id: baseConfig?.ai_policy_id || null,
                alert_ai_model_id: baseConfig?.alert_ai_model_id || null,
                ai_shadow_enabled: Boolean(baseConfig?.ai_shadow_enabled),
                baseline_config: baseConfig?.baseline_config || {},
                event_ai_config: baseConfig?.event_ai_config || {},
            });
            Modal.hide();
            Toast.success(I18n.t('pageCopy.datasources.inspectionAndAlarmConfigurationHasBeenSaved'));
        } catch (error) {
            Toast.error(error.message || I18n.t('common.requestFailed'));
        }
    },

    _simplifyVersion(fullVersion, dbType) {
        if (!fullVersion) return { short: I18n.t('pageCopy.datasources.unknownVersion'), full: '', details: '' };

        const patterns = {
            'postgresql': /PostgreSQL\s+([\d.]+)/i,
            'mysql': /([\d.]+)/,
            'oracle': /Oracle Database ([\d.]+)/i,
            'sqlserver': /Microsoft SQL Server\s+([\d.]+)/i,
            'opengauss': /openGauss\s+([\d.]+)/i,
            'hana': /HDB\s+([\d.]+)/i,
            'tdsql': /([\d.]+)/,
            'oceanbasemysql': /([\d.]+)/
        };

        const dbTypeNormalized = (dbType || '').toLowerCase().replace(/[_-]/g, '');
        const pattern = patterns[dbTypeNormalized];

        if (pattern) {
            const match = fullVersion.match(pattern);
            if (match) {
                const versionNum = match[1];
                const dbDisplayNames = {
                    'postgresql': 'PostgreSQL',
                    'mysql': 'MySQL',
                    'oracle': 'Oracle',
                    'sqlserver': 'SQL Server',
                    'opengauss': 'openGauss',
                    'hana': 'SAP HANA',
                    'tdsql': 'TDSQL-C',
                    'oceanbasemysql': 'OceanBase MySQL'
                };
                const displayName = dbDisplayNames[dbTypeNormalized] || dbType.toUpperCase();
                const short = `${displayName} ${versionNum}`;
                const details = fullVersion.substring(match.index + match[0].length).trim().replace(/^[,\s]+/, '');

                return { short, full: fullVersion, details };
            }
        }

        if (fullVersion.length > 50) {
            return {
                short: fullVersion.substring(0, 50) + '...',
                full: fullVersion,
                details: fullVersion.substring(50)
            };
        }

        return { short: fullVersion, full: fullVersion, details: '' };
    }
};
