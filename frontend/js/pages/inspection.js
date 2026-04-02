/* Inspection Dashboard Page */
const InspectionPage = {
    currentPage: 1,
    pageSize: 10,
    totalReports: 0,
    pollInterval: null,
    datasourceSelector: null,
    filters: {
        datasource_id: null,
        status: null,
        trigger_type: null,
        start_date: null,
        end_date: null
    },
    currentReportDetail: null,

    async render() {
        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        // Build header with filters (like dashboard layout)
        Header.render('数据库智能巡检', this._buildHeaderActions());

        content.innerHTML = `
            <div class="page-container">
                <div id="reportList">
                    <div id="reports"></div>
                    <div id="pagination" style="margin-top: 15px; display: flex; justify-content: center; gap: 10px;"></div>
                </div>
            </div>
        `;

        await this.loadReports();
        this.startPolling();

        // Return cleanup function for Router
        return () => this.cleanup();
    },

    _buildHeaderActions() {
        // Build filters container
        const filtersContainer = DOM.el('div', { className: 'dashboard-filters' });
        filtersContainer.innerHTML = `
            <div id="filterDatasource" style="min-width: 400px;"></div>
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
            <button id="btn-apply-filters" class="btn btn-primary">
                <i data-lucide="search"></i> 检索
            </button>
            <button id="resetFilters" class="btn btn-secondary">
                <i data-lucide="x"></i> 重置
            </button>
        `;

        // Bind events after render
        setTimeout(() => {
            this.initDatasourceSelector();
            const btnApply = DOM.$('#btn-apply-filters');
            const btnReset = DOM.$('#resetFilters');
            if (btnApply) btnApply.addEventListener('click', () => this.applyFilters());
            if (btnReset) btnReset.addEventListener('click', () => this.resetFilters());
            DOM.createIcons();
        }, 0);

        return filtersContainer;
    },

    initDatasourceSelector() {
        this.datasourceSelector = new DatasourceSelector({
            container: DOM.$('#filterDatasource'),
            allowEmpty: true,
            emptyText: '所有数据源',
            minWidth: '400px',
            maxWidth: '400px',
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

    resetFilters() {
        this.filters = { datasource_id: null, status: null, trigger_type: null, start_date: null, end_date: null };

        // 重置数据源选择器
        if (this.datasourceSelector) {
            this.datasourceSelector.setValue(null);
        }

        DOM.$('#filterStatus').value = '';
        DOM.$('#filterTriggerType').value = '';
        DOM.$('#filterStartDate').value = '';
        DOM.$('#filterEndDate').value = '';
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

        // Show loading indicator only on initial load or filter change
        if (!this.pollInterval || container.innerHTML === '') {
            container.innerHTML = '<div style="text-align:center;padding:40px;color:#666;"><div class="spinner"></div><p style="margin-top:10px;">加载中...</p></div>';
        }

        try {
            const response = await API.get(`/api/inspections/reports?${params.toString()}`);
            const reports = Array.isArray(response) ? response : response.reports || [];
            this.totalReports = response.total || reports.length;

            if (reports.length === 0) {
                container.innerHTML = '<p style="text-align:center;color:#666;padding:20px;">未找到报告</p>';
                DOM.$('#pagination').innerHTML = '';
                return;
            }

            container.innerHTML = `
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>数据源</th>
                            <th>触发类型</th>
                            <th>报告状态</th>
                            <th>标题</th>
                            <th>创建时间</th>
                            <th>原因</th>
                            <th style="width:150px;">操作</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${reports.map(r => `
                            <tr>
                                <td>${r.datasource_name || 'N/A'}</td>
                                <td>
                                    <span class="badge badge-${r.trigger_type === 'anomaly' ? 'danger' : r.trigger_type === 'scheduled' ? 'success' : 'info'}">
                                        ${r.trigger_type === 'anomaly' ? '🔴 异常' : r.trigger_type === 'scheduled' ? '📅 定时' : '👤 手动'}
                                    </span>
                                </td>
                                <td>
                                    ${(() => { const s = InspectionPage.formatReportStatus(r.status); return `<span class="badge badge-${s.badge}">${s.text}</span>`; })()}
                                    ${r.status !== 'completed' && r.error_message ? `
                                        <span class="error-icon" data-error="${r.error_message.replace(/"/g, '&quot;')}" style="margin-left:6px;color:#dc3545;cursor:help;font-size:16px;">⚠️</span>
                                    ` : ''}
                                </td>
                                <td><strong>${r.title}</strong></td>
                                <td>${Format.datetime(r.created_at)}</td>
                                <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${r.trigger_reason || '-'}</td>
                                <td>
                                    <button onclick="InspectionPage.viewReport(${r.report_id})" class="btn btn-sm btn-primary" style="padding:4px 8px;margin-right:5px;">查看报告</button>
                                    <button onclick="InspectionPage.confirmDelete(${r.report_id})" class="btn btn-sm btn-danger" style="padding:4px 8px;">删除</button>
                                </td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;

            // Setup error icon tooltips
            this.setupErrorTooltips();

            this.renderPagination();

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
            container.innerHTML = '<p style="text-align:center;color:#dc3545;padding:20px;">加载失败，请刷新重试</p>';
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
        buttons.push(`<button class="btn btn-sm btn-secondary" style="flex: 0 0 auto;" ${this.currentPage === 1 ? 'disabled' : ''} onclick="InspectionPage.goToPage(${this.currentPage - 1})">上一页</button>`);

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                buttons.push(`<button class="btn btn-sm ${i === this.currentPage ? 'btn-primary' : 'btn-secondary'}" style="flex: 0 0 auto;" onclick="InspectionPage.goToPage(${i})">${i}</button>`);
            } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                buttons.push(`<span style="padding:0 5px; flex: 0 0 auto;">...</span>`);
            }
        }

        // Next button
        buttons.push(`<button class="btn btn-sm btn-secondary" style="flex: 0 0 auto;" ${this.currentPage === totalPages ? 'disabled' : ''} onclick="InspectionPage.goToPage(${this.currentPage + 1})">下一页</button>`);

        pagination.innerHTML = buttons.join('');
    },

    async goToPage(page) {
        this.currentPage = page;
        await this.loadReports();
    },

    formatReportStatus(status) {
        const map = {
            completed: { text: '✓ 已完成', badge: 'success' },
            partial: { text: '◐ 部分结果', badge: 'warning' },
            timed_out: { text: '⏱ 已超时', badge: 'warning' },
            awaiting_confirm: { text: '🛑 待确认', badge: 'warning' },
            failed: { text: '✗ 失败', badge: 'danger' },
            generating: { text: '⏳ 生成中', badge: 'warning' }
        };
        return map[status] || { text: status || '未知', badge: 'warning' };
    },

    formatTriggerType(triggerType) {
        const map = {
            anomaly: '异常触发',
            scheduled: '定时触发',
            threshold: '阈值触发',
            manual: '手动触发'
        };
        return map[triggerType] || triggerType || '未知类型';
    },

    async viewReport(reportId) {
        try {
            const report = await API.get(`/api/inspections/reports/detail/${reportId}`);
            this.currentReportDetail = report;
            const content = DOM.$('#page-content');

            const statusMeta = this.formatReportStatus(report.status);
            const triggerTypeLabel = this.formatTriggerType(report.trigger_type || 'manual');
            const datasourceLabel = report.datasource_name || `ID: ${report.datasource_id || '-'}`;
            const createdAtLabel = report.created_at ? Format.datetime(report.created_at) : '-';
            const completedAtLabel = report.completed_at ? Format.datetime(report.completed_at) : null;

            const summaryHtml = report.summary ? `
                <section class="inspection-report-section inspection-report-summary">
                    <div class="inspection-report-section-title">诊断摘要</div>
                    <div class="inspection-report-summary-text">${report.summary}</div>
                </section>
            ` : '';

            const triggerDetailsHtml = report.trigger_reason ? `
                <section class="inspection-report-section inspection-report-trigger">
                    <div class="inspection-report-section-title">触发原因</div>
                    <div class="inspection-report-trigger-text">${report.trigger_reason}</div>
                </section>
            ` : '';

            const actions = Array.isArray(report.actions) ? report.actions : [];
            const actionsHtml = actions.length ? `
                <section class="inspection-report-section inspection-report-actions">
                    <div class="inspection-report-section-title">动作建议</div>
                    <div class="inspection-report-actions-list">
                        ${actions.map(action => `
                            <div class="inspection-report-action-card">
                                <div class="inspection-report-action-header">
                                    <div>
                                        <div class="inspection-report-action-title">${action.title || '未命名动作'}</div>
                                        <div class="inspection-report-action-summary">${action.summary || ''}</div>
                                        ${action.precheck ? `<div class="inspection-report-action-meta">前置检查：${action.precheck}</div>` : ''}
                                        ${action.verification?.success_criteria ? `<div class="inspection-report-action-meta">验证：${action.verification.success_criteria}</div>` : ''}
                                    </div>
                                    <div class="inspection-report-action-badges">
                                        <span class="badge badge-${action.risk_level === 'destructive' ? 'danger' : action.risk_level === 'high' ? 'warning' : 'success'}">${action.risk_level || 'safe'}</span>
                                        ${action.latest_run ? `<span class="badge badge-info">${InspectionPage.formatActionRunStatus(action.latest_run.status)}</span>` : ''}
                                    </div>
                                </div>
                                <div class="inspection-report-action-buttons">
                                    <button class="btn btn-sm btn-primary" onclick="InspectionPage.executeRecommendedAction(${report.id}, '${String(action.id).replace(/'/g, "\\'")}')">审批并执行</button>
                                    ${action.latest_run ? `<button class="btn btn-sm btn-secondary" onclick="InspectionPage.verifyActionRun(${action.latest_run.run_id})">执行后验证</button>` : ''}
                                    ${action.latest_run ? `<button class="btn btn-sm btn-secondary" onclick="InspectionPage.showActionRunDetail(${action.latest_run.run_id})">查看执行记录</button>` : ''}
                                    ${action.latest_run ? `<button class="btn btn-sm btn-secondary" onclick="InspectionPage.openDiagnosisFromActionRun(${action.latest_run.run_id}, ${report.datasource_id}, ${report.alert_id || 'null'}, ${report.id})">进入 AI 诊断</button>` : ''}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </section>
            ` : '';

            const diagnosisPrompt = `基于巡检/诊断报告，给出【现象-证据-根因-建议动作-验证方式】的处置建议。\n\n数据源：${datasourceLabel}\n报告标题：${report.title}\n触发类型：${report.trigger_type || '-'}\n触发原因：${report.trigger_reason || '-'}\n诊断摘要：${report.summary || '-'}\n\n如果需要，请调用技能进一步确认（Top SQL/EXPLAIN/连接情况/OS 指标）。`;

            content.innerHTML = `
                <div class="inspection-report-shell">
                    <div class="inspection-report-toolbar">
                        <button onclick="InspectionPage.render()" class="btn btn-secondary inspection-report-back">← 返回报告列表</button>
                        <div class="inspection-report-toolbar-actions">
                            ${report.alert_id ? `<button onclick="InspectionPage.openLinkedAlert(${report.alert_id})" class="btn btn-secondary">查看关联告警</button>` : ''}
                            <button id="report-open-diagnosis" class="btn btn-secondary">进入 AI 诊断</button>
                            <button onclick="InspectionPage.exportMarkdown(${reportId})" class="btn btn-secondary">导出 Markdown</button>
                            <button onclick="InspectionPage.exportPDF(${reportId})" class="btn btn-primary">导出 PDF</button>
                        </div>
                    </div>

                    <div class="inspection-report-header">
                        <div>
                            <div class="inspection-report-kicker">巡检报告</div>
                            <h1 class="inspection-report-title">${report.title}</h1>
                            <div class="inspection-report-badges">
                                <span class="badge badge-${statusMeta.badge}">${statusMeta.text}</span>
                                <span class="badge badge-info">${triggerTypeLabel}</span>
                                <span class="badge badge-secondary">${datasourceLabel}</span>
                            </div>
                        </div>
                        <div class="inspection-report-meta">
                            <div class="inspection-report-meta-item">
                                <span class="inspection-report-meta-label">创建时间</span>
                                <span class="inspection-report-meta-value">${createdAtLabel}</span>
                            </div>
                            <div class="inspection-report-meta-item">
                                <span class="inspection-report-meta-label">完成时间</span>
                                <span class="inspection-report-meta-value">${completedAtLabel || '—'}</span>
                            </div>
                            <div class="inspection-report-meta-item">
                                <span class="inspection-report-meta-label">报告 ID</span>
                                <span class="inspection-report-meta-value">#${report.id}</span>
                            </div>
                        </div>
                    </div>

                    <div class="inspection-report-overview">
                        ${summaryHtml}
                        ${triggerDetailsHtml}
                        ${actionsHtml}
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
            Router.navigate('alerts');
            setTimeout(async () => {
                try {
                    const alert = await API.getAlert(alertId);
                    await AlertsPage.showAlertDetail(alert);
                } catch (error) {
                    Toast.show(`加载关联告警失败: ${error.message}`, 'error');
                }
            }, 0);
        } catch (error) {
            Toast.show(`打开关联告警失败: ${error.message}`, 'error');
        }
    },

    openDiagnosisFromReport(datasourceId, alertId, prompt) {
        const params = new URLSearchParams();
        if (datasourceId) params.set('datasource', datasourceId);
        if (alertId) params.set('alert', alertId);
        if (prompt) params.set('ask', prompt);
        Router.navigate(`diagnosis?${params.toString()}`);
    },

    openDiagnosisFromActionRun(runId, datasourceId, alertId, reportId) {
        const params = new URLSearchParams();
        if (datasourceId) params.set('datasource', datasourceId);
        if (alertId) params.set('alert', alertId);
        if (reportId) params.set('report', reportId);
        if (runId) params.set('action_run', runId);
        Router.navigate(`diagnosis?${params.toString()}`);
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
            Toast.show(`Export failed: ${error.message}`, 'error');
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
            Toast.show(`Export failed: ${error.message}`, 'error');
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

        // Remove old handler before adding new one
        if (this._errorTooltipHandler) {
            container.removeEventListener('mouseenter', this._errorTooltipHandler, true);
            container.removeEventListener('mouseleave', this._errorTooltipHandler, true);
        }

        let currentTooltip = null;
        this._errorTooltipHandler = (e) => {
            const icon = e.target.closest('.error-icon');
            if (!icon) return;

            if (e.type === 'mouseenter') {
                const errorMessage = icon.getAttribute('data-error');
                currentTooltip = document.createElement('div');
                currentTooltip.className = 'error-tooltip';
                currentTooltip.textContent = errorMessage;
                document.body.appendChild(currentTooltip);

                const rect = icon.getBoundingClientRect();
                const tooltipRect = currentTooltip.getBoundingClientRect();

                let top = rect.top - tooltipRect.height - 10;
                let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);

                if (top < 10) top = rect.bottom + 10;
                if (left < 10) left = 10;
                if (left + tooltipRect.width > window.innerWidth - 10) {
                    left = window.innerWidth - tooltipRect.width - 10;
                }

                currentTooltip.style.top = top + 'px';
                currentTooltip.style.left = left + 'px';
                currentTooltip.style.opacity = '1';
            } else if (e.type === 'mouseleave' && currentTooltip) {
                currentTooltip.remove();
                currentTooltip = null;
            }
        };

        container.addEventListener('mouseenter', this._errorTooltipHandler, true);
        container.addEventListener('mouseleave', this._errorTooltipHandler, true);
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

    async executeRecommendedAction(reportId, recommendationId) {
        try {
            const res = await API.createActionRun({ report_id: reportId, recommendation_id: recommendationId });
            const run = res?.run;
            if (!run?.run_id) {
                Toast.show('创建动作执行记录失败', 'error');
                return;
            }

            Toast.show('动作已执行', 'success');
            await this.viewReport(reportId);
        } catch (e) {
            Toast.show('执行失败: ' + e.message, 'error');
        }
    },

    async verifyActionRun(runId) {
        try {
            await API.verifyActionRun(runId);
            Toast.show('验证已触发', 'success');
            if (this.currentReportDetail?.id) {
                await this.viewReport(this.currentReportDetail.id);
            }
        } catch (e) {
            Toast.show('验证失败: ' + e.message, 'error');
        }
    },

    async showActionRunDetail(runId) {
        try {
            const res = await API.getActionRun(runId);
            const run = res?.run;
            if (!run) {
                Toast.show('未找到执行记录', 'error');
                return;
            }
            const safe = (v) => String(v ?? '').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            Modal.show({
                title: '执行记录',
                content: `
                            <div style="display:flex;flex-direction:column;gap:10px;">
                            <div><strong>动作：</strong>${safe(run.title)}</div>
                            <div><strong>状态：</strong>${safe(this.formatActionRunStatus(run.status))}</div>
                            <div><strong>执行：</strong>${safe(this.formatExecutionStatus(run.execution_status))} ${run.skill_execution_id ? `(skill_execution_id=${safe(run.skill_execution_id)})` : ''}</div>
                            ${run.execution_result_summary ? `<pre style="margin:0;background:var(--bg-input);padding:10px;border-radius:8px;white-space:pre-wrap;">${safe(run.execution_result_summary)}</pre>` : ''}
                            <div><strong>验证：</strong>${safe(this.formatVerificationStatus(run.verification_status))} ${run.verification_skill_execution_id ? `(skill_execution_id=${safe(run.verification_skill_execution_id)})` : ''}</div>
                            ${run.verification_summary ? `<pre style="margin:0;background:var(--bg-input);padding:10px;border-radius:8px;white-space:pre-wrap;">${safe(run.verification_summary)}</pre>` : ''}
                        </div>
                `,
                buttons: [
                    { text: '关闭', variant: 'secondary', onClick: () => Modal.hide() }
                ]
            });
        } catch (e) {
            Toast.show('加载执行记录失败: ' + e.message, 'error');
        }
    },

    formatActionRunStatus(status) {
        const map = {
            rejected: '已拒绝',
            executing: '执行中',
            execution_succeeded: '执行成功',
            execution_failed: '执行失败',
            verifying: '验证中',
            verified_passed: '验证通过',
            verified_failed: '验证失败',
            closed: '已关闭'
        };
        return map[status] || status || '-';
    },

    formatExecutionStatus(status) {
        const map = {
            pending: '待执行',
            running: '执行中',
            succeeded: '执行成功',
            failed: '执行失败'
        };
        return map[status] || status || '-';
    },

    formatVerificationStatus(status) {
        const map = {
            not_requested: '未验证',
            running: '验证中',
            passed: '验证通过',
            failed: '验证失败'
        };
        return map[status] || status || '-';
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
                container.removeEventListener('mouseenter', this._errorTooltipHandler, true);
                container.removeEventListener('mouseleave', this._errorTooltipHandler, true);
            }
            this._errorTooltipHandler = null;
        }
    }

};
