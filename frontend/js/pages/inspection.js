/* Inspection Dashboard Page */
const InspectionPage = {
    currentPage: 1,
    pageSize: 10,
    totalReports: 0,
    pollInterval: null,
    filters: {
        datasource_id: null,
        status: null,
        trigger_type: null,
        start_date: null,
        end_date: null
    },

    async render() {
        const content = DOM.$('#page-content');
        Header.render('数据库智能巡检');

        content.innerHTML = `
            <div class="page-container">
                <div class="filters" style="margin: 20px 0; display: flex; gap: 10px; flex-wrap: wrap; align-items: end;">
                    <div>
                        <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">数据源</label>
                        <select id="filterDatasource" class="form-select" style="padding: 8px; border-radius: 4px; min-width: 180px;">
                            <option value="">所有数据源</option>
                        </select>
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">状态</label>
                        <select id="filterStatus" class="form-select" style="padding: 8px; border-radius: 4px;">
                            <option value="">所有状态</option>
                            <option value="completed">已完成</option>
                            <option value="generating">生成中</option>
                            <option value="failed">失败</option>
                        </select>
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">触发类型</label>
                        <select id="filterTriggerType" class="form-select" style="padding: 8px; border-radius: 4px;">
                            <option value="">所有类型</option>
                            <option value="manual">手动</option>
                            <option value="scheduled">定时</option>
                            <option value="anomaly">异常</option>
                        </select>
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">开始日期</label>
                        <input type="date" id="filterStartDate" class="form-input" style="padding: 8px; border-radius: 4px;">
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">结束日期</label>
                        <input type="date" id="filterEndDate" class="form-input" style="padding: 8px; border-radius: 4px;">
                    </div>
                    <button id="applyFilters" class="btn btn-primary" style="padding: 8px 16px;">应用筛选</button>
                    <button id="resetFilters" class="btn btn-secondary" style="padding: 8px 16px;">重置</button>
                </div>
                <div id="reportList" style="margin-top: 20px;">
                    <div id="reports"></div>
                    <div id="pagination" style="margin-top: 15px; display: flex; justify-content: center; gap: 10px;"></div>
                </div>
            </div>
        `;

        await this.loadDatasources();
        this.setupEventListeners();
        await this.loadReports();
        this.startPolling();

        // Return cleanup function for Router
        return () => this.cleanup();
    },

    async loadDatasources() {
        const datasources = await API.getDatasources();
        const select = DOM.$('#filterDatasource');
        datasources.forEach(ds => {
            const option = DOM.el('option', { value: ds.id, textContent: `${ds.name} (${ds.db_type})` });
            select.appendChild(option);
        });
    },

    setupEventListeners() {
        DOM.$('#applyFilters')?.addEventListener('click', () => this.applyFilters());
        DOM.$('#resetFilters')?.addEventListener('click', () => this.resetFilters());
    },

    applyFilters() {
        this.filters.datasource_id = DOM.$('#filterDatasource')?.value || null;
        this.filters.status = DOM.$('#filterStatus')?.value || null;
        this.filters.trigger_type = DOM.$('#filterTriggerType')?.value || null;
        this.filters.start_date = DOM.$('#filterStartDate')?.value || null;
        this.filters.end_date = DOM.$('#filterEndDate')?.value || null;
        this.currentPage = 1;
        this.loadReports();
    },

    resetFilters() {
        this.filters = { datasource_id: null, status: null, trigger_type: null, start_date: null, end_date: null };
        DOM.$('#filterDatasource').value = '';
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
                            <th>状态</th>
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
                                    <span class="badge badge-${r.status === 'completed' ? 'success' : r.status === 'failed' ? 'danger' : 'warning'}">
                                        ${r.status === 'completed' ? '✓ 已完成' : r.status === 'failed' ? '✗ 失败' : '⏳ 生成中'}
                                    </span>
                                    ${r.status === 'failed' && r.error_message ? `
                                        <span class="error-icon" data-error="${r.error_message.replace(/"/g, '&quot;')}" style="margin-left:6px;color:#dc3545;cursor:help;font-size:16px;">⚠️</span>
                                    ` : ''}
                                </td>
                                <td><strong>${r.title}</strong></td>
                                <td>${r.created_at}</td>
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
        const totalPages = Math.ceil(this.totalReports / this.pageSize);
        if (totalPages <= 1) {
            DOM.$('#pagination').innerHTML = '';
            return;
        }

        const pagination = DOM.$('#pagination');
        const buttons = [];

        // Previous button
        buttons.push(`<button class="btn btn-sm btn-secondary" ${this.currentPage === 1 ? 'disabled' : ''} onclick="InspectionPage.goToPage(${this.currentPage - 1})">上一页</button>`);

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                buttons.push(`<button class="btn btn-sm ${i === this.currentPage ? 'btn-primary' : 'btn-secondary'}" onclick="InspectionPage.goToPage(${i})">${i}</button>`);
            } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                buttons.push(`<span style="padding:0 5px;">...</span>`);
            }
        }

        // Next button
        buttons.push(`<button class="btn btn-sm btn-secondary" ${this.currentPage === totalPages ? 'disabled' : ''} onclick="InspectionPage.goToPage(${this.currentPage + 1})">下一页</button>`);

        pagination.innerHTML = buttons.join('');
    },

    async goToPage(page) {
        this.currentPage = page;
        await this.loadReports();
    },

    async viewReport(reportId) {
        try {
            const report = await API.get(`/api/inspections/reports/detail/${reportId}`);
            const content = DOM.$('#page-content');

            // Parse trigger reason to show threshold details
            let triggerDetailsHtml = '';
            if (report.trigger_reason) {
                triggerDetailsHtml = `
                    <div style="background:#e3f2fd;padding:12px;border-radius:4px;margin-bottom:15px;border-left:4px solid #2196f3;">
                        <strong style="color:#1976d2;">触发原因:</strong>
                        <span style="margin-left:8px; color:black">${report.trigger_reason}</span>
                    </div>
                `;
            }

            content.innerHTML = `
                <div style="max-width: 1200px; margin: 0 auto; padding: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                        <button onclick="InspectionPage.render()" style="padding: 8px 16px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;">← 返回报告列表</button>
                        <div style="display: flex; gap: 10px;">
                            <button onclick="InspectionPage.exportMarkdown(${reportId})" class="btn btn-secondary" style="padding: 8px 16px;">
                                📄 Export Markdown
                            </button>
                            <button onclick="InspectionPage.exportPDF(${reportId})" class="btn btn-primary" style="padding: 8px 16px;">
                                📑 Export PDF
                            </button>
                        </div>
                    </div>
                    <div style="background:var(--background-secondary);padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        ${triggerDetailsHtml}
                        <div id="reportContent"></div>
                    </div>
                </div>
            `;
            const reportContent = DOM.$('#reportContent');
            reportContent.className = 'report-content-markdown';
            reportContent.innerHTML = MarkdownRenderer.render(report.content_md || '暂无内容');
        } catch (error) {
            Toast.show('加载失败 report', 'error');
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

    setupErrorTooltips() {
        const errorIcons = document.querySelectorAll('.error-icon');
        let tooltip = null;

        errorIcons.forEach(icon => {
            icon.addEventListener('mouseenter', (e) => {
                const errorMessage = icon.getAttribute('data-error');

                // Create tooltip
                tooltip = document.createElement('div');
                tooltip.className = 'error-tooltip';
                tooltip.textContent = errorMessage;
                document.body.appendChild(tooltip);

                // Position tooltip
                const rect = icon.getBoundingClientRect();
                const tooltipRect = tooltip.getBoundingClientRect();

                // Position above the icon
                let top = rect.top - tooltipRect.height - 10;
                let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);

                // Adjust if tooltip goes off screen
                if (top < 10) {
                    top = rect.bottom + 10; // Show below if not enough space above
                }
                if (left < 10) {
                    left = 10;
                }
                if (left + tooltipRect.width > window.innerWidth - 10) {
                    left = window.innerWidth - tooltipRect.width - 10;
                }

                tooltip.style.top = top + 'px';
                tooltip.style.left = left + 'px';
                tooltip.style.opacity = '1';
            });

            icon.addEventListener('mouseleave', () => {
                if (tooltip) {
                    tooltip.remove();
                    tooltip = null;
                }
            });
        });
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
    }

};
