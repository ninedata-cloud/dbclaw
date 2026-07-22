/* Inspection Dashboard Page */
const InspectionPage = {
    currentPage: 1,
    pageSize: 10,
    totalReports: 0,
    pollInterval: null,
    datasourceSelector: null,
    _renderOptions: null,
    _container: null,
    filters: {
        datasource_id: null,
        status: null,
        trigger_type: null,
        start_date: null,
        end_date: null
    },
    currentReportDetail: null,
    _errorTooltipEl: null,
    _errorTooltipHideHandler: null,

    _escapeHtml(value) {
        return Utils.escapeHtml(String(value ?? ''));
    },

    _escapeAttr(value) {
        return this._escapeHtml(value).replace(/"/g, '&quot;');
    },

    _formatDurationSeconds(totalSeconds) {
        if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return null;

        const seconds = Math.floor(totalSeconds);
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const remainSeconds = seconds % 60;

        if (days > 0) return I18n.t('pageCopy.inspection.durationDaysHours', { value0: days, value1: hours });
        if (hours > 0) return I18n.t('pageCopy.inspection.durationHoursMinutes', { value0: hours, value1: minutes });
        if (minutes > 0) return I18n.t('pageCopy.inspection.durationMinutesSeconds', { value0: minutes, value1: remainSeconds });
        return I18n.t('pageCopy.inspection.durationSeconds', { value0: remainSeconds });
    },

    async render() {
        return this.renderWithOptions({});
    },

    async renderFromRoute(routeParam = '') {
        const params = new URLSearchParams(routeParam || '');
        const datasourceId = parseInt(params.get('datasource'), 10);
        const reportId = parseInt(params.get('report'), 10);
        return this.renderWithOptions({
            fixedDatasourceId: Number.isFinite(datasourceId) ? datasourceId : null,
            initialReportId: Number.isFinite(reportId) ? reportId : null,
        });
    },

    async renderWithOptions(options = {}) {
        this._renderOptions = options || {};
        this._container = options.container || DOM.$('#page-content');
        if (options.fixedDatasourceId) {
            this.filters.datasource_id = options.fixedDatasourceId;
        }

        const content = this._container;
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        // Build header with filters (like dashboard layout)
        const headerActions = this._buildHeaderActions();

        content.innerHTML = I18n.t('pageCopy.inspection.loadingLatestReports');
        if (options.embedded) {
            const page = content.querySelector('.inspection-page');
            const embeddedToolbar = DOM.el('div', {
                className: 'instance-embedded-toolbar',
                style: {
                    display: 'flex',
                    gap: '12px',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    marginBottom: '16px',
                    flexWrap: 'wrap'
                }
            });
            embeddedToolbar.appendChild(DOM.el('div', {
                className: 'instance-embedded-title',
                textContent: I18n.t('pageCopy.inspection.inspectionManagement')
            }));
            embeddedToolbar.appendChild(headerActions);
            content.insertBefore(embeddedToolbar, page);
        } else {
            Header.render(I18n.t('pageCopy.inspection.intelligentDatabaseInspection'), headerActions);
        }

        await this.loadReports();
        if (options.initialReportId) {
            await this.viewReport(options.initialReportId);
        }
        this.startPolling();

        // Return cleanup function for Router
        return () => this.cleanup();
    },

    _buildHeaderActions() {
        // Build filters container
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters inspection-header-filters' });
        filtersContainer.innerHTML = I18n.t('pageCopy.inspection.filterControls', { value0: this._renderOptions?.fixedDatasourceId ? '' : '<div id="filterDatasource" class="inspection-filter-datasource"></div>', value1: I18n.t('placeholders.startDate'), value2: I18n.t('placeholders.endDate') });

        // Bind events after render
        setTimeout(() => {
            if (!this._renderOptions?.fixedDatasourceId) {
                this.initDatasourceSelector();
            }
            this._bindFilterEvents();
            DatePicker.enhanceAll(filtersContainer);
            DOM.createIcons();
        }, 0);

        return filtersContainer;
    },

    _bindFilterEvents() {
        const bind = (selector, eventName = 'change') => {
            const el = DOM.$(selector);
            if (!el) return;
            el.addEventListener(eventName, () => this.applyFilters());
        };

        bind('#filterStatus');
        bind('#filterTriggerType');
        bind('#filterStartDate', 'input');
        bind('#filterEndDate', 'input');
    },

    initDatasourceSelector() {
        this.datasourceSelector = new DatasourceSelector({
            container: DOM.$('#filterDatasource'),
            allowEmpty: true,
            emptyText: I18n.t('pageCopy.inspection.allDatasources'),
            minWidth: '280px',
            maxWidth: '320px',
            showStatus: true,
            showDetails: true,
            onChange: (datasource) => {
                this.filters.datasource_id = datasource ? datasource.id : null;
                this.applyFilters();
            }
        });
    },

    applyFilters() {
        this.filters.status = DOM.$('#filterStatus')?.value || null;
        this.filters.trigger_type = DOM.$('#filterTriggerType')?.value || null;
        this.filters.start_date = DOM.$('#filterStartDate')?.value || null;
        this.filters.end_date = DOM.$('#filterEndDate')?.value || null;
        this.currentPage = 1;
        this.loadReports();
    },

    async loadReports() {
        const offset = (this.currentPage - 1) * this.pageSize;
        const params = new URLSearchParams({
            limit: this.pageSize,
            offset: offset
        });

        if (this.filters.datasource_id) params.append('datasource_id', this.filters.datasource_id);
        if (this.filters.status) params.append('status', this.filters.status);
        if (this.filters.trigger_type) params.append('trigger_type', this.filters.trigger_type);
        if (this.filters.start_date) params.append('start_date', this.filters.start_date);
        if (this.filters.end_date) params.append('end_date', this.filters.end_date);

        const container = DOM.$('#reports');

        // If container doesn't exist (user navigated away), stop polling
        if (!container) {
            if (this.pollInterval) {
                clearInterval(this.pollInterval);
                this.pollInterval = null;
            }
            return;
        }

        this._removeErrorTooltip();

        // Show loading indicator only on initial load or filter change
        if (!this.pollInterval || container.innerHTML === '') {
            container.innerHTML = I18n.t('pageCopy.inspection.loadingInspectionReport');
        }

        try {
            const response = await API.get(`/api/inspections/reports?${params.toString()}`);
            const reports = Array.isArray(response)
                ? response
                : (response.reports || response.report || []);
            const showDatasourceColumn = !this._renderOptions?.fixedDatasourceId;
            this.totalReports = response.total || reports.length;
            const meta = DOM.$('#inspection-list-meta');
            if (meta) {
                meta.textContent = I18n.t('inspection.listMeta', {
                    total: I18n.formatNumber(this.totalReports),
                    page: I18n.formatNumber(this.currentPage)
                });
            }

            if (reports.length === 0) {
                container.innerHTML = I18n.t('pageCopy.inspection.noReportsFoundNoInspectionRecordsMatch');
                DOM.$('#pagination').innerHTML = '';
                DOM.createIcons();
                return;
            }

            const renderTriggerBadge = (triggerType) => {
                const map = {
                    anomaly: { label: I18n.t('pageCopy.inspection.exceptionTrigger'), className: 'danger' },
                    connection_failure: { label: I18n.t('pageCopy.inspection.connectionFailureTrigger'), className: 'danger' },
                    baseline: { label: I18n.t('pageCopy.inspection.baselineTrigger'), className: 'warning' },
                    scheduled: { label: I18n.t('pageCopy.inspection.timingTrigger'), className: 'success' },
                    manual: { label: I18n.t('pageCopy.inspection.manualTrigger'), className: 'info' },
                    threshold: { label: I18n.t('pageCopy.inspection.thresholdTrigger'), className: 'warning' }
                };
                const meta = map[triggerType] || { label: this.formatTriggerType(triggerType), className: 'muted' };
                return `<span class="inspection-pill ${meta.className}">${this._escapeHtml(meta.label)}</span>`;
            };

	            container.innerHTML = I18n.t('pageCopy.inspection.idValueTriggerTypeReportStatusTitle', { value0: showDatasourceColumn ? '' : 'inspection-table-instance', value1: showDatasourceColumn ? I18n.t('pageCopy.inspection.datasource') : '', value2: reports.map(r => {
                                const statusMeta = InspectionPage.formatReportStatus(r.status);
	                            const reportTitle = InspectionPage.formatReportTitle(r);
	                            const triggerReason = InspectionPage.formatTriggerReason(r);
	                                return I18n.t('pageCopy.inspection.reportRow', { value0: InspectionPage._escapeHtml(r.report_id), value1: showDatasourceColumn ? `
	                                        <td class="inspection-col-source">
	                                            <div class="inspection-cell-stack">
	                                                <div class="inspection-primary-text inspection-nowrap-text" title="${InspectionPage._escapeAttr(r.datasource_name || 'N/A')}">${InspectionPage._escapeHtml(r.datasource_name || 'N/A')}</div>
	                                            </div>
	                                        </td>
	                                        ` : '', value2: renderTriggerBadge(r.trigger_type), value3: statusMeta.badge, value4: InspectionPage._escapeHtml(statusMeta.text), value5: r.status !== 'completed' && r.error_message ? `
                                                    <span class="error-icon" data-error="${InspectionPage._escapeAttr(r.error_message)}">⚠</span>
                                                ` : '', value6: InspectionPage._escapeAttr(reportTitle), value7: InspectionPage._escapeHtml(reportTitle), value8: InspectionPage._escapeHtml(Format.datetime(r.created_at)), value9: InspectionPage._escapeAttr(triggerReason), value10: InspectionPage._escapeHtml(triggerReason), value11: r.report_id, value12: r.report_id });
                            }).join('') });

            // Setup error icon tooltips
            this.setupErrorTooltips();

            this.renderPagination();
            DOM.createIcons();

            // Stop polling if no reports are generating
            const hasGeneratingReports = reports.some(r =>
                r.status !== 'completed' && r.status !== 'failed'
            );

            if (!hasGeneratingReports && this.pollInterval) {
                clearInterval(this.pollInterval);
                this.pollInterval = null;
            } else if (hasGeneratingReports && !this.pollInterval) {
                // Restart polling if there are generating reports but polling stopped
                this.startPolling();
            }
        } catch (error) {
            console.error('Failed to load reports:', error);
            container.innerHTML = I18n.t('pageCopy.inspection.loadFailedFailedToObtainTheInspection');
            Toast.show(I18n.t('pageCopy.inspection.failedToLoadReport'), 'error');
        }
    },

    renderPagination() {
        const pagination = DOM.$('#pagination');
        if (!pagination) return;

        const totalPages = Math.ceil(this.totalReports / this.pageSize);
        if (totalPages <= 1) {
            pagination.innerHTML = '';
            return;
        }

        const buttons = [];

        // Previous button
        buttons.push(I18n.t('pageCopy.inspection.previous', { value0: this.currentPage === 1 ? 'disabled' : '', value1: this.currentPage - 1 }));

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                buttons.push(`<button class="btn btn-sm ${i === this.currentPage ? 'btn-primary' : 'btn-secondary'} inspection-pagination-btn" onclick="InspectionPage.goToPage(${i})">${i}</button>`);
            } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                buttons.push('<span class="inspection-pagination-ellipsis">...</span>');
            }
        }

        // Next button
        buttons.push(I18n.t('pageCopy.inspection.next', { value0: this.currentPage === totalPages ? 'disabled' : '', value1: this.currentPage + 1 }));

        pagination.innerHTML = buttons.join('');
    },

    async goToPage(page) {
        this.currentPage = page;
        await this.loadReports();
    },

    formatReportStatus(status) {
        const map = {
            completed: { text: I18n.t('pageCopy.inspection.completed'), badge: 'success' },
            partial: { text: I18n.t('pageCopy.inspection.partialResults'), badge: 'warning' },
            timed_out: { text: I18n.t('pageCopy.inspection.timedOut'), badge: 'warning' },
            awaiting_confirm: { text: I18n.t('pageCopy.inspection.toBeConfirmed'), badge: 'warning' },
            failed: { text: I18n.t('pageCopy.inspection.failed'), badge: 'danger' },
            generating: { text: I18n.t('pageCopy.inspection.generating'), badge: 'info' }
        };
        return map[status] || { text: status || I18n.t('pageCopy.inspection.unknown'), badge: 'warning' };
    },

    formatTriggerType(triggerType) {
        const map = {
            anomaly: I18n.t('pageCopy.inspection.exceptionTrigger'),
            scheduled: I18n.t('pageCopy.inspection.timingTrigger'),
            threshold: I18n.t('pageCopy.inspection.thresholdTrigger'),
            baseline: I18n.t('pageCopy.inspection.baselineTrigger'),
            manual: I18n.t('pageCopy.inspection.manualTrigger'),
            connection_failure: I18n.t('pageCopy.inspection.connectionFailureTrigger')
        };
        return map[triggerType] || triggerType || I18n.t('pageCopy.inspection.unknownType');
    },

    formatReportTitle(report) {
        const titleKeys = {
            anomaly: 'pageCopy.inspection.anomalyInspectionTitle',
            connection_failure: 'pageCopy.inspection.connectionFailureInspectionTitle',
            baseline: 'pageCopy.inspection.baselineInspectionTitle',
            scheduled: 'pageCopy.inspection.scheduledInspectionTitle',
            manual: 'pageCopy.inspection.manualInspectionTitle',
            threshold: 'pageCopy.inspection.thresholdInspectionTitle'
        };
        const titleKey = titleKeys[report?.trigger_type];
        if (!titleKey || !report?.datasource_name) {
            return report?.title || I18n.t('pageCopy.inspection.untitledReport');
        }
        return I18n.t('pageCopy.inspection.reportTitle', {
            value0: I18n.t(titleKey),
            value1: report.datasource_name
        });
    },

    formatTriggerReason(report) {
        const reason = String(report?.trigger_reason || '').trim();
        if (!reason) return '-';

        if (report?.trigger_type === 'manual'
            && /^(?:manual inspection|inspection requested|\u4eba\u5de5(?:\u89e6\u53d1)?\u5de1\u68c0|\u624b\u52a8\u5de1\u68c0)$/i.test(reason)) {
            return I18n.t('pageCopy.inspection.manualInspectionReason');
        }
        if (report?.trigger_type === 'scheduled'
            && /^(?:scheduled inspection|\u5b9a\u65f6\u5de1\u68c0|\u8ba1\u5212\u5de1\u68c0)$/i.test(reason)) {
            return I18n.t('pageCopy.inspection.scheduledInspectionReason');
        }
        if (report?.trigger_type === 'connection_failure') {
            const match = reason.match(/^(?:database connection failed|数据库连接失败)\s*[:：]?\s*(.*)$/i);
            if (match) {
                return match[1]
                    ? I18n.t('pageCopy.inspection.connectionFailureReasonDetail', { value0: match[1] })
                    : I18n.t('pageCopy.inspection.connectionFailureReason');
            }
        }
        return reason;
    },

    async viewReport(reportId) {
        try {
            const report = await API.get(`/api/inspections/reports/detail/${reportId}`);
            this.currentReportDetail = report;
            const content = this._container || DOM.$('#page-content');
            const safe = (value) => this._escapeHtml(value);
            const safeAttr = (value) => this._escapeAttr(value);

            const statusMeta = this.formatReportStatus(report.status);
            const triggerTypeLabel = this.formatTriggerType(report.trigger_type || 'manual');
            const datasourceLabel = report.datasource_name || (report.datasource_id ? I18n.t('pageCopy.inspection.datasourceValue', { value0: report.datasource_id }) : I18n.t('pageCopy.inspection.datasourceNotAssociated'));
            const reportTitle = this.formatReportTitle(report);
            const triggerReason = this.formatTriggerReason(report);
            const createdAtLabel = report.created_at ? Format.datetime(report.created_at) : '-';
            const completedAtLabel = report.completed_at ? Format.datetime(report.completed_at) : null;
            const completedAtDisplay = completedAtLabel
                ? `${completedAtLabel}${report.completed_at_inferred ? I18n.t('pageCopy.inspection.supplementLabel') : ''}`
                : (report.status === 'generating' ? I18n.t('pageCopy.inspection.generating') : I18n.t('pageCopy.inspection.notRecorded'));
            const durationLabel = this._formatDurationSeconds(report.duration_seconds);
            const reportIdLabel = report.id ? `#${report.id}` : '-';

            const summaryHtml = report.summary ? I18n.t('pageCopy.inspection.diagnosisSummaryValue', { value0: safe(report.summary) }) : '';

            const triggerDetailsHtml = report.trigger_reason ? I18n.t('pageCopy.inspection.triggerReasonValue', { value0: safe(triggerReason) }) : '';

            const diagnosisPrompt = I18n.t('pageCopy.inspection.basedOnTheInspectionDiagnosisReportGive', { value0: datasourceLabel, value1: reportTitle, value2: triggerTypeLabel, value3: triggerReason, value4: report.summary || '-' });

            content.innerHTML = I18n.t('pageCopy.inspection.returnToReportListValueEnterAi', { value0: this._renderOptions?.embedded ? 'renderWithOptions' : 'render', value1: this._renderOptions?.embedded ? 'InspectionPage._renderOptions' : '', value2: report.alert_id ? I18n.t('pageCopy.inspection.viewAssociatedAlarms', { value0: report.alert_id }) : '', value3: reportId, value4: reportId, value5: safe(reportIdLabel), value6: statusMeta.badge, value7: safe(statusMeta.text), value8: safe(triggerTypeLabel), value9: safe(reportTitle), value10: safeAttr(datasourceLabel), value11: safe(datasourceLabel), value12: safe(createdAtLabel), value13: safe(completedAtDisplay), value14: safe(durationLabel || '—'), value15: summaryHtml, value16: triggerDetailsHtml });
            const diagnosisBtn = DOM.$('#report-open-diagnosis');
            if (diagnosisBtn) {
                diagnosisBtn.addEventListener('click', () => {
                    this.openDiagnosisFromReport(report.datasource_id, report.alert_id, diagnosisPrompt);
                });
            }
            const reportContent = DOM.$('#reportContent');
            reportContent.className = 'report-content-markdown';
            const fallbackContent = report.error_message
                ? I18n.t('pageCopy.inspection.successStatusValueReasonValue', { value0: this.formatReportStatus(report.status).text, value1: report.error_message })
                : I18n.t('pageCopy.inspection.noContent');
            reportContent.innerHTML = MarkdownRenderer.render(report.content_md || fallbackContent);
        } catch (error) {
            Toast.show(I18n.t('pageCopy.inspection.loadFailed') + ': ' + error.message, 'error');
        }
    },

    async openLinkedAlert(alertId) {
        try {
            if (this._renderOptions?.embedded && this.filters.datasource_id) {
                const params = new URLSearchParams();
                params.set('datasource', this.filters.datasource_id);
                params.set('tab', 'alerts');
                params.set('alert', alertId);
                Router.navigate(`instance-detail?${params.toString()}`);
            } else {
                Router.navigate('alerts');
            }
        } catch (error) {
            Toast.show(I18n.t('pageCopy.inspection.alarmfailedValue', { value0: error.message }), 'error');
        }
    },

    openDiagnosisFromReport(datasourceId, alertId, prompt) {
        const params = new URLSearchParams();
        if (datasourceId) params.set('datasource', datasourceId);
        if (alertId) params.set('alert', alertId);
        if (prompt) params.set('ask', prompt);
        if (this._renderOptions?.embedded) {
            params.set('tab', 'ai');
            Router.navigate(`instance-detail?${params.toString()}`);
        } else {
            Router.navigate(`diagnosis?${params.toString()}`);
        }
    },

    async exportMarkdown(reportId) {
        try {
            await API.downloadInspectionReport(reportId, 'markdown');
            Toast.show(I18n.t('pageCopy.inspection.markdownExportSuccessful'), 'success');
        } catch (error) {
            Toast.show(I18n.t('pageCopy.inspection.exportFailedValue', { value0: error.message }), 'error');
        }
    },

    async exportPDF(reportId) {
        try {
            Toast.show(I18n.t('pageCopy.inspection.generatingPdf'), 'info');
            await API.downloadInspectionReport(reportId, 'pdf');
            Toast.show(I18n.t('pageCopy.inspection.pdfExportSuccessful'), 'success');
        } catch (error) {
            Toast.show(I18n.t('pageCopy.inspection.exportFailedValue', { value0: error.message }), 'error');
        }
    },

    startPolling() {
        // Clear any existing interval
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }

        // Poll every 5 seconds (reduced frequency)
        this.pollInterval = setInterval(() => this.loadReports(), 5000);
    },

    _errorTooltipHandler: null,

    setupErrorTooltips() {
        const container = DOM.$('#reportList');
        if (!container) return;

        this._removeErrorTooltip();

        // Remove old handler before adding new one
        if (this._errorTooltipHandler) {
            container.removeEventListener('mouseover', this._errorTooltipHandler, true);
            container.removeEventListener('mouseout', this._errorTooltipHandler, true);
        }
        if (this._errorTooltipHideHandler) {
            window.removeEventListener('scroll', this._errorTooltipHideHandler, true);
            window.removeEventListener('blur', this._errorTooltipHideHandler);
            document.removeEventListener('click', this._errorTooltipHideHandler, true);
        }

        this._errorTooltipHandler = (e) => {
            const icon = e.target.closest('.error-icon');
            if (!icon) return;

            if (e.type === 'mouseover') {
                if (this._errorTooltipEl && this._errorTooltipEl.dataset.anchorId === icon.dataset.tooltipAnchorId) {
                    return;
                }
                const errorMessage = icon.getAttribute('data-error');
                this._removeErrorTooltip();
                if (!icon.dataset.tooltipAnchorId) {
                    icon.dataset.tooltipAnchorId = `error-tooltip-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
                }

                const tooltip = document.createElement('div');
                tooltip.className = 'error-tooltip';
                tooltip.textContent = errorMessage;
                tooltip.dataset.anchorId = icon.dataset.tooltipAnchorId;
                document.body.appendChild(tooltip);
                this._errorTooltipEl = tooltip;

                const rect = icon.getBoundingClientRect();
                const tooltipRect = tooltip.getBoundingClientRect();

                let top = rect.top - tooltipRect.height - 10;
                let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);

                if (top < 10) top = rect.bottom + 10;
                if (left < 10) left = 10;
                if (left + tooltipRect.width > window.innerWidth - 10) {
                    left = window.innerWidth - tooltipRect.width - 10;
                }

                tooltip.style.top = top + 'px';
                tooltip.style.left = left + 'px';
                tooltip.style.opacity = '1';
            } else if (e.type === 'mouseout') {
                const nextIcon = e.relatedTarget?.closest?.('.error-icon');
                if (nextIcon === icon) {
                    return;
                }
                this._removeErrorTooltip();
            }
        };

        this._errorTooltipHideHandler = () => this._removeErrorTooltip();
        container.addEventListener('mouseover', this._errorTooltipHandler, true);
        container.addEventListener('mouseout', this._errorTooltipHandler, true);
        window.addEventListener('scroll', this._errorTooltipHideHandler, true);
        window.addEventListener('blur', this._errorTooltipHideHandler);
        document.addEventListener('click', this._errorTooltipHideHandler, true);
    },

    _removeErrorTooltip() {
        if (this._errorTooltipEl) {
            this._errorTooltipEl.remove();
            this._errorTooltipEl = null;
        }
    },

    confirmDelete(reportId) {
        if (confirm(I18n.t('pageCopy.inspection.areYouSureYouWantToDelete'))) {
            this.deleteReport(reportId);
        }
    },

    async deleteReport(reportId) {
        try {
            await API.delete(`/api/inspections/reports/${reportId}`);
            Toast.show(I18n.t('pageCopy.inspection.reportDeleted'), 'success');
            await this.loadReports();
        } catch (error) {
            Toast.show(I18n.t('pageCopy.inspection.deleteFailedValue', { value0: error.message }), 'error');
        }
    },

    cleanup() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
        if (this.datasourceSelector) {
            this.datasourceSelector.destroy();
            this.datasourceSelector = null;
        }
        // Cleanup tooltip event listeners
        if (this._errorTooltipHandler) {
            const container = DOM.$('#reportList');
            if (container) {
                container.removeEventListener('mouseover', this._errorTooltipHandler, true);
                container.removeEventListener('mouseout', this._errorTooltipHandler, true);
            }
            this._errorTooltipHandler = null;
        }
        if (this._errorTooltipHideHandler) {
            window.removeEventListener('scroll', this._errorTooltipHideHandler, true);
            window.removeEventListener('blur', this._errorTooltipHideHandler);
            document.removeEventListener('click', this._errorTooltipHideHandler, true);
            this._errorTooltipHideHandler = null;
        }
        this._removeErrorTooltip();
        this._renderOptions = null;
        this._container = null;
    }

};
