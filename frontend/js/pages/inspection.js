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
        Header.render('Database Intelligent Inspection');

        content.innerHTML = `
            <div class="page-container">
                <div class="filters" style="margin: 20px 0; display: flex; gap: 10px; flex-wrap: wrap; align-items: end;">
                    <div>
                        <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">Datasource</label>
                        <select id="filterDatasource" class="form-select" style="padding: 8px; border-radius: 4px; min-width: 180px;">
                            <option value="">All Datasources</option>
                        </select>
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">Status</label>
                        <select id="filterStatus" class="form-select" style="padding: 8px; border-radius: 4px;">
                            <option value="">All Status</option>
                            <option value="completed">Completed</option>
                            <option value="generating">Generating</option>
                            <option value="failed">Failed</option>
                        </select>
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">Trigger Type</label>
                        <select id="filterTriggerType" class="form-select" style="padding: 8px; border-radius: 4px;">
                            <option value="">All Types</option>
                            <option value="manual">Manual</option>
                            <option value="scheduled">Scheduled</option>
                            <option value="anomaly">Anomaly</option>
                        </select>
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">Start Date</label>
                        <input type="date" id="filterStartDate" class="form-input" style="padding: 8px; border-radius: 4px;">
                    </div>
                    <div>
                        <label style="display:block;font-size:12px;margin-bottom:4px;color:var(--text-muted);">End Date</label>
                        <input type="date" id="filterEndDate" class="form-input" style="padding: 8px; border-radius: 4px;">
                    </div>
                    <button id="applyFilters" class="btn btn-primary" style="padding: 8px 16px;">Apply Filters</button>
                    <button id="resetFilters" class="btn btn-secondary" style="padding: 8px 16px;">Reset</button>
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

        const response = await API.get(`/api/inspections/reports?${params.toString()}`);
        const reports = Array.isArray(response) ? response : response.reports || [];
        this.totalReports = response.total || reports.length;

        const container = DOM.$('#reports');
        if (reports.length === 0) {
            container.innerHTML = '<p style="text-align:center;color:#666;padding:20px;">No reports found</p>';
            DOM.$('#pagination').innerHTML = '';
            return;
        }

        container.innerHTML = `
            <table class="data-table">
                <thead>
                    <tr>
                        <th>Datasource</th>
                        <th>Trigger Type</th>
                        <th>Status</th>
                        <th>Title</th>
                        <th>Created At</th>
                        <th>Reason</th>
                    </tr>
                </thead>
                <tbody>
                    ${reports.map(r => `
                        <tr style="cursor:pointer;" onclick="InspectionPage.viewReport(${r.report_id})">
                            <td>${r.datasource_name || 'N/A'}</td>
                            <td>
                                <span class="badge badge-${r.trigger_type === 'anomaly' ? 'danger' : r.trigger_type === 'scheduled' ? 'success' : 'info'}">
                                    ${r.trigger_type === 'anomaly' ? '🔴 Anomaly' : r.trigger_type === 'scheduled' ? '📅 Scheduled' : '👤 Manual'}
                                </span>
                            </td>
                            <td>
                                <span class="badge badge-${r.status === 'completed' ? 'success' : r.status === 'failed' ? 'danger' : 'warning'}">
                                    ${r.status === 'completed' ? '✓ Completed' : r.status === 'failed' ? '✗ Failed' : '⏳ Generating'}
                                </span>
                            </td>
                            <td><strong>${r.title}</strong></td>
                            <td>${r.created_at}</td>
                            <td style="max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${r.trigger_reason || '-'}</td>
                        </tr>
                        ${r.status === 'failed' && r.error_message ? `
                        <tr>
                            <td colspan="6" style="background:#f8d7da;color:#721c24;font-size:12px;padding:8px;">
                                <strong>Error:</strong> ${r.error_message}
                            </td>
                        </tr>` : ''}
                    `).join('')}
                </tbody>
            </table>
        `;

        this.renderPagination();

        // Stop polling if no reports are generating
        const hasGeneratingReports = reports.some(r =>
            r.status !== 'completed' && r.status !== 'failed'
        );

        if (!hasGeneratingReports && this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
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
        buttons.push(`<button class="btn btn-sm btn-secondary" ${this.currentPage === 1 ? 'disabled' : ''} onclick="InspectionPage.goToPage(${this.currentPage - 1})">Previous</button>`);

        // Page numbers
        for (let i = 1; i <= totalPages; i++) {
            if (i === 1 || i === totalPages || (i >= this.currentPage - 2 && i <= this.currentPage + 2)) {
                buttons.push(`<button class="btn btn-sm ${i === this.currentPage ? 'btn-primary' : 'btn-secondary'}" onclick="InspectionPage.goToPage(${i})">${i}</button>`);
            } else if (i === this.currentPage - 3 || i === this.currentPage + 3) {
                buttons.push(`<span style="padding:0 5px;">...</span>`);
            }
        }

        // Next button
        buttons.push(`<button class="btn btn-sm btn-secondary" ${this.currentPage === totalPages ? 'disabled' : ''} onclick="InspectionPage.goToPage(${this.currentPage + 1})">Next</button>`);

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
            content.innerHTML = `
                <div style="max-width: 1200px; margin: 0 auto; padding: 20px;">
                    <button onclick="InspectionPage.render()" style="margin-bottom: 20px; padding: 8px 16px; background: #6c757d; color: white; border: none; border-radius: 4px; cursor: pointer;">← Back to Reports</button>
                    <div style="background:var(--background-secondary);padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div id="reportContent"></div>
                    </div>
                </div>
            `;
            const reportContent = DOM.$('#reportContent');
            reportContent.className = 'report-content-markdown';
            reportContent.innerHTML = MarkdownRenderer.render(report.content_md || 'No content available');
        } catch (error) {
            Toast.show('Failed to load report', 'error');
        }
    },

    startPolling() {
        // Clear any existing interval
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }

        // Poll every 3 seconds
        this.pollInterval = setInterval(() => this.loadReports(), 3000);
    },

    cleanup() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
            this.pollInterval = null;
        }
    }

};
