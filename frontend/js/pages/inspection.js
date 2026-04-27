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

        if (days > 0) return `${days} 天 ${hours} 小时`;
        if (hours > 0) return `${hours} 小时 ${minutes} 分`;
        if (minutes > 0) return `${minutes} 分 ${remainSeconds} 秒`;
        return `${remainSeconds} 秒`;
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

        content.innerHTML = `
            <div class="inspection-page">
                <section id="reportList">
                    <div id="reports"></div>
                    <div class="inspection-pagination">
                        <div id="inspection-list-meta" class="inspection-list-meta">正在加载最新报告...</div>
                        <div id="pagination" class="inspection-pagination-controls"></div>
                    </div>
                </section>
            </div>
        `;
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
                textContent: '巡检管理'
            }));
            embeddedToolbar.appendChild(headerActions);
            content.insertBefore(embeddedToolbar, page);
        } else {
            Header.render('数据库智能巡检', headerActions);
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
        filtersContainer.innerHTML = `
            ${this._renderOptions?.fixedDatasourceId ? '' : '<div id="filterDatasource" class="inspection-filter-datasource"></div>'}
            <select id="filterStatus" class="filter-select">
                <option value="">所有状态</option>
                <option value="completed">已完成</option>
                <option value="generating">生成中</option>
                <option value="failed">失败</option>
            </select>
            <select id="filterTriggerType" class="filter-select">
                <option value="">所有类型</option>
                <option value="manual">手动</option>
                <option value="scheduled">定时</option>
                <option value="anomaly">异常</option>
            </select>
            <input type="date" id="filterStartDate" class="filter-input inspection-date-input" placeholder="开始日期">
            <input type="date" id="filterEndDate" class="filter-input inspection-date-input" placeholder="结束日期">
        `;

        // Bind events after render
        setTimeout(() => {
            if (!this._renderOptions?.fixedDatasourceId) {
                this.initDatasourceSelector();
            }
            this._bindFilterEvents();
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
            emptyText: '所有数据源',
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
            container.innerHTML = `
                <div class="inspection-state">
                    <div class="spinner"></div>
                    <p>正在加载巡检报告...</p>
                </div>
            `;
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
                meta.textContent = `共 ${this.totalReports.toLocaleString()} 条报告，当前第 ${this.currentPage} 页`;
            }

            if (reports.length === 0) {
                container.innerHTML = `
                    <div class="inspection-state inspection-state-empty">
                        <i data-lucide="file-search"></i>
                        <h3>未找到报告</h3>
                        <p>当前筛选条件下没有巡检记录，调整后再试一次。</p>
                    </div>
                `;
                DOM.$('#pagination').innerHTML = '';
                DOM.createIcons();
                return;
            }

            const renderTriggerBadge = (triggerType) => {
                const map = {
                    anomaly: { label: '异常触发', className: 'danger' },
                    scheduled: { label: '定时触发', className: 'success' },
                    manual: { label: '手动触发', className: 'info' },
                    threshold: { label: '阈值触发', className: 'warning' }
                };
                const meta = map[triggerType] || { label: this.formatTriggerType(triggerType), className: 'muted' };
                return `<span class="inspection-pill ${meta.className}">${this._escapeHtml(meta.label)}</span>`;
            };

	            container.innerHTML = `
	                <div class="data-table-container inspection-table-container">
	                    <table class="data-table inspection-table ${showDatasourceColumn ? '' : 'inspection-table-instance'}">
	                        <thead>
	                            <tr>
	                                <th class="inspection-col-id">编号</th>
	                                ${showDatasourceColumn ? '<th class="inspection-col-source">数据源</th>' : ''}
	                                <th class="inspection-col-trigger">触发类型</th>
	                                <th class="inspection-col-status">报告状态</th>
	                                <th class="inspection-col-title">标题</th>
	                                <th class="inspection-col-time">创建时间</th>
                                <th class="inspection-col-reason">触发原因</th>
                                <th class="inspection-actions-col">操作</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${reports.map(r => {
                                const statusMeta = InspectionPage.formatReportStatus(r.status);
	                                return `
	                                    <tr>
	                                        <td class="inspection-col-id">
	                                            <div class="inspection-id-text">#${InspectionPage._escapeHtml(r.report_id)}</div>
	                                        </td>
	                                        ${showDatasourceColumn ? `
	                                        <td class="inspection-col-source">
	                                            <div class="inspection-cell-stack">
	                                                <div class="inspection-primary-text inspection-nowrap-text" title="${InspectionPage._escapeAttr(r.datasource_name || 'N/A')}">${InspectionPage._escapeHtml(r.datasource_name || 'N/A')}</div>
	                                            </div>
	                                        </td>
	                                        ` : ''}
                                        <td class="inspection-col-trigger">${renderTriggerBadge(r.trigger_type)}</td>
                                        <td class="inspection-col-status">
                                            <div class="inspection-status-cell">
                                                <span class="inspection-pill ${statusMeta.badge}">${InspectionPage._escapeHtml(statusMeta.text)}</span>
                                                ${r.status !== 'completed' && r.error_message ? `
                                                    <span class="error-icon" data-error="${InspectionPage._escapeAttr(r.error_message)}">⚠</span>
                                                ` : ''}
                                            </div>
                                        </td>
	                                        <td class="inspection-col-title">
	                                            <div class="inspection-primary-text inspection-nowrap-text" title="${InspectionPage._escapeAttr(r.title)}">${InspectionPage._escapeHtml(r.title)}</div>
	                                        </td>
                                        <td class="inspection-col-time">
                                            <div class="inspection-secondary-text inspection-time-text">${InspectionPage._escapeHtml(Format.datetime(r.created_at))}</div>
                                        </td>
                                        <td class="inspection-col-reason">
                                            <div class="inspection-reason-text" title="${InspectionPage._escapeAttr(r.trigger_reason || '-')}">${InspectionPage._escapeHtml(r.trigger_reason || '-')}</div>
                                        </td>
                                        <td class="inspection-actions-col">
                                            <div class="inspection-actions-cell">
                                                <button
                                                    onclick="InspectionPage.viewReport(${r.report_id})"
                                                    class="inspection-action-btn inspection-action-btn-primary"
                                                    title="查看报告"
                                                    aria-label="查看报告"
                                                >
                                                    <i data-lucide="file-text"></i>
                                                </button>
                                                <button
                                                    onclick="InspectionPage.confirmDelete(${r.report_id})"
                                                    class="inspection-action-btn inspection-action-btn-danger"
                                                    title="删除报告"
                                                    aria-label="删除报告"
                                                >
                                                    <i data-lucide="trash-2"></i>
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            `;

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
            container.innerHTML = `
                <div class="inspection-state inspection-state-error">
                    <h3>加载失败</h3>
                    <p>巡检报告获取失败，请刷新后重试。</p>
                </div>
            `;
            Toast.show('加载报告失败', 'error');
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
        buttons.push(`<button class="btn btn-sm btn-secondary inspection-pagination-btn" ${this.currentPage === 1 ? 'disabled' : ''} onclick="InspectionPage.goToPage(${this.currentPage - 1})">上一页</button>`);

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                buttons.push(`<button class="btn btn-sm ${i === this.currentPage ? 'btn-primary' : 'btn-secondary'} inspection-pagination-btn" onclick="InspectionPage.goToPage(${i})">${i}</button>`);
            } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                buttons.push('<span class="inspection-pagination-ellipsis">...</span>');
            }
        }

        // Next button
        buttons.push(`<button class="btn btn-sm btn-secondary inspection-pagination-btn" ${this.currentPage === totalPages ? 'disabled' : ''} onclick="InspectionPage.goToPage(${this.currentPage + 1})">下一页</button>`);

        pagination.innerHTML = buttons.join('');
    },

    async goToPage(page) {
        this.currentPage = page;
        await this.loadReports();
    },

    formatReportStatus(status) {
        const map = {
            completed: { text: '已完成', badge: 'success' },
            partial: { text: '部分结果', badge: 'warning' },
            timed_out: { text: '已超时', badge: 'warning' },
            awaiting_confirm: { text: '待确认', badge: 'warning' },
            failed: { text: '失败', badge: 'danger' },
            generating: { text: '生成中', badge: 'info' }
        };
        return map[status] || { text: status || '未知', badge: 'warning' };
    },

    formatTriggerType(triggerType) {
        const map = {
            anomaly: '异常触发',
            scheduled: '定时触发',
            threshold: '阈值触发',
            manual: '手动触发',
            connection_failure: '连接失败'
        };
        return map[triggerType] || triggerType || '未知类型';
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
            const datasourceLabel = report.datasource_name || (report.datasource_id ? `数据源 #${report.datasource_id}` : '未关联数据源');
            const createdAtLabel = report.created_at ? Format.datetime(report.created_at) : '-';
            const completedAtLabel = report.completed_at ? Format.datetime(report.completed_at) : null;
            const completedAtDisplay = completedAtLabel
                ? `${completedAtLabel}${report.completed_at_inferred ? '（补记）' : ''}`
                : (report.status === 'generating' ? '生成中' : '未记录');
            const durationLabel = this._formatDurationSeconds(report.duration_seconds);
            const reportIdLabel = report.id ? `#${report.id}` : '-';

            const summaryHtml = report.summary ? `
                <section class="inspection-report-section inspection-report-summary">
                    <div class="inspection-report-section-title">诊断摘要</div>
                    <div class="inspection-report-summary-text">${safe(report.summary)}</div>
                </section>
            ` : '';

            const triggerDetailsHtml = report.trigger_reason ? `
                <section class="inspection-report-section inspection-report-trigger">
                    <div class="inspection-report-section-title">触发原因</div>
                    <div class="inspection-report-trigger-text">${safe(report.trigger_reason)}</div>
                </section>
            ` : '';

            const diagnosisPrompt = `基于巡检/诊断报告，给出【现象-证据-根因-建议动作-验证方式】的处置建议。\n\n数据源：${datasourceLabel}\n报告标题：${report.title}\n触发类型：${report.trigger_type || '-'}\n触发原因：${report.trigger_reason || '-'}\n诊断摘要：${report.summary || '-'}\n\n如果需要，请调用技能进一步确认（Top SQL/EXPLAIN/连接情况/OS 指标）。`;

            content.innerHTML = `
                <div class="inspection-report-shell">
                    <div class="inspection-report-toolbar">
                        <button onclick="InspectionPage.${this._renderOptions?.embedded ? 'renderWithOptions' : 'render'}(${this._renderOptions?.embedded ? 'InspectionPage._renderOptions' : ''})" class="btn btn-secondary inspection-report-back">← 返回报告列表</button>
                        <div class="inspection-report-toolbar-actions">
                            ${report.alert_id ? `<button onclick="InspectionPage.openLinkedAlert(${report.alert_id})" class="btn btn-secondary">查看关联告警</button>` : ''}
                            <button id="report-open-diagnosis" class="btn btn-secondary">进入 AI 诊断</button>
                            <button onclick="InspectionPage.exportMarkdown(${reportId})" class="btn btn-secondary">导出 Markdown</button>
                            <button onclick="InspectionPage.exportPDF(${reportId})" class="btn btn-primary">导出 PDF</button>
                        </div>
                    </div>

                    <div class="inspection-report-header">
                        <div class="inspection-report-header-top">
                            <div class="inspection-report-heading-meta">
                                <div class="inspection-report-kicker">巡检报告</div>
                                <div class="inspection-report-id-chip">${safe(reportIdLabel)}</div>
                            </div>
                            <div class="inspection-report-badges">
                                <span class="badge badge-${statusMeta.badge}">${safe(statusMeta.text)}</span>
                                <span class="badge badge-info">${safe(triggerTypeLabel)}</span>
                            </div>
                        </div>
                        <h1 class="inspection-report-title">${safe(report.title)}</h1>
                        <div class="inspection-report-facts">
                            <div class="inspection-report-fact">
                                <span class="inspection-report-fact-label">数据源</span>
                                <span class="inspection-report-fact-value" title="${safeAttr(datasourceLabel)}">${safe(datasourceLabel)}</span>
                            </div>
                            <div class="inspection-report-fact">
                                <span class="inspection-report-fact-label">创建时间</span>
                                <span class="inspection-report-fact-value">${safe(createdAtLabel)}</span>
                            </div>
                            <div class="inspection-report-fact">
                                <span class="inspection-report-fact-label">完成时间</span>
                                <span class="inspection-report-fact-value">${safe(completedAtDisplay)}</span>
                            </div>
                            <div class="inspection-report-fact">
                                <span class="inspection-report-fact-label">耗时</span>
                                <span class="inspection-report-fact-value">${safe(durationLabel || '—')}</span>
                            </div>
                        </div>
                    </div>

                    <div class="inspection-report-overview">
                        ${summaryHtml}
                        ${triggerDetailsHtml}
                    </div>

                    <section class="inspection-report-section inspection-report-body">
                        <div class="inspection-report-section-title">报告正文</div>
                        <div id="reportContent"></div>
                    </section>
                </div>
            `;
            const diagnosisBtn = DOM.$('#report-open-diagnosis');
            if (diagnosisBtn) {
                diagnosisBtn.addEventListener('click', () => {
                    this.openDiagnosisFromReport(report.datasource_id, report.alert_id, diagnosisPrompt);
                });
            }
            const reportContent = DOM.$('#reportContent');
            reportContent.className = 'report-content-markdown';
            const fallbackContent = report.error_message
                ? `## 报告未生成成功\n\n状态：${this.formatReportStatus(report.status).text}\n\n原因：${report.error_message}`
                : '暂无内容';
            reportContent.innerHTML = MarkdownRenderer.render(report.content_md || fallbackContent);
        } catch (error) {
            Toast.show('加载失败 report', 'error');
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
            Toast.show(`打开关联告警失败: ${error.message}`, 'error');
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
            const response = await fetch(`/api/inspections/reports/export/${reportId}/markdown`);
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '导出失败');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `inspection_report_${reportId}_${new Date().toISOString().slice(0,10)}.md`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            Toast.show('Markdown 导出成功', 'success');
        } catch (error) {
            Toast.show(`导出失败: ${error.message}`, 'error');
        }
    },

    async exportPDF(reportId) {
        try {
            Toast.show('正在生成 PDF...', 'info');
            const response = await fetch(`/api/inspections/reports/export/${reportId}/pdf`);
            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.detail || '导出失败');
            }

            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `inspection_report_${reportId}_${new Date().toISOString().slice(0,10)}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);

            Toast.show('PDF 导出成功', 'success');
        } catch (error) {
            Toast.show(`导出失败: ${error.message}`, 'error');
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
        if (confirm('确定要删除这个报告吗？此操作无法撤销。')) {
            this.deleteReport(reportId);
        }
    },

    async deleteReport(reportId) {
        try {
            await API.delete(`/api/inspections/reports/${reportId}`);
            Toast.show('报告已删除', 'success');
            await this.loadReports();
        } catch (error) {
            Toast.show(`删除失败: ${error.message}`, 'error');
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
