/* Reports page */
const ReportsPage = {
    pollInterval: null,

    async render() {
        const headerActions = DOM.el('div', { className: 'flex gap-8' });
        headerActions.appendChild(DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="file-plus"></i> Generate Report',
            onClick: () => this._showGenerateModal()
        }));
        Header.render('Reports', headerActions);

        const content = DOM.$('#page-content');
        content.innerHTML = '<div class="loading-overlay"><div class="spinner"></div></div>';

        await this._loadReports();

        return () => {
            if (this.pollInterval) clearInterval(this.pollInterval);
        };
    },

    async _loadReports() {
        const content = DOM.$('#page-content');
        try {
            const reports = await API.getReports();
            content.innerHTML = '';

            if (reports.length === 0) {
                content.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="file-text"></i>
                        <h3>No Reports</h3>
                        <p>Generate a diagnostic report to analyze your database health.</p>
                    </div>
                `;
                lucide.createIcons();
                return;
            }

            const grid = DOM.el('div', { className: 'connection-grid' });
            for (const report of reports) {
                grid.appendChild(this._createReportCard(report));
            }
            content.appendChild(grid);
            lucide.createIcons();

            // Poll for generating reports
            const hasGenerating = reports.some(r => r.status === 'generating');
            if (hasGenerating) {
                this.pollInterval = setInterval(() => this._loadReports(), 5000);
            } else if (this.pollInterval) {
                clearInterval(this.pollInterval);
                this.pollInterval = null;
            }

        } catch (err) {
            content.innerHTML = `<div class="empty-state"><h3>Error</h3><p>${err.message}</p></div>`;
        }
    },

    _createReportCard(report) {
        const card = DOM.el('div', { className: 'connection-card' });

        const statusBadge = {
            completed: '<span class="badge badge-success">Completed</span>',
            generating: '<span class="badge badge-warning">Generating...</span>',
            failed: '<span class="badge badge-danger">Failed</span>',
        }[report.status] || '';

        card.innerHTML = `
            <div class="connection-card-header">
                <span class="connection-card-name">${report.title}</span>
                ${statusBadge}
            </div>
            <div class="connection-card-info">
                <span><i data-lucide="calendar"></i> ${Format.datetime(report.created_at)}</span>
                <span><i data-lucide="tag"></i> ${report.report_type}</span>
                ${report.summary ? `<span style="margin-top:8px;color:var(--text-primary)">${report.summary}</span>` : ''}
            </div>
        `;

        if (report.status === 'completed') {
            const actions = DOM.el('div', { className: 'connection-card-actions' });
            actions.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: '<i data-lucide="file-text"></i> Markdown',
                onClick: () => window.open(API.getReportDownloadUrl(report.id, 'md'), '_blank')
            }));
            actions.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-primary',
                innerHTML: '<i data-lucide="file-down"></i> PDF',
                onClick: () => window.open(API.getReportDownloadUrl(report.id, 'pdf'), '_blank')
            }));
            actions.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-secondary',
                innerHTML: '<i data-lucide="eye"></i> View',
                onClick: () => this._viewReport(report)
            }));
            card.appendChild(actions);
        }

        return card;
    },

    async _showGenerateModal() {
        const form = DOM.el('form');

        let connectionsHtml = '<option value="">Select connection...</option>';
        try {
            const connections = await API.getConnections();
            const current = Store.get('currentConnection');
            for (const c of connections) {
                const selected = current && c.id === current.id ? 'selected' : '';
                connectionsHtml += `<option value="${c.id}" ${selected}>${c.name} (${c.db_type})</option>`;
            }
        } catch (e) { /* ignore */ }

        form.innerHTML = `
            <div class="form-group">
                <label>Connection</label>
                <select class="form-select" name="connection_id" required>${connectionsHtml}</select>
            </div>
            <div class="form-group">
                <label>Report Type</label>
                <select class="form-select" name="report_type">
                    <option value="comprehensive">Comprehensive</option>
                    <option value="performance">Performance</option>
                    <option value="security">Security</option>
                </select>
            </div>
            <div class="form-group">
                <label>Title (optional)</label>
                <input type="text" class="form-input" name="title" placeholder="Auto-generated if empty">
            </div>
        `;

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const data = Object.fromEntries(new FormData(form).entries());
            data.connection_id = parseInt(data.connection_id);
            if (!data.title) delete data.title;
            if (!data.connection_id) { Toast.warning('Select a connection'); return; }

            try {
                await API.generateReport(data);
                Toast.success('Report generation started');
                Modal.hide();
                this._loadReports();
            } catch (err) {
                Toast.error(err.message);
            }
        });

        const footer = DOM.el('div', { style: { display: 'flex', gap: '8px' } });
        footer.appendChild(DOM.el('button', { className: 'btn btn-secondary', textContent: 'Cancel', type: 'button', onClick: () => Modal.hide() }));
        footer.appendChild(DOM.el('button', {
            className: 'btn btn-primary', textContent: 'Generate', type: 'button',
            onClick: () => form.requestSubmit()
        }));

        Modal.show({ title: 'Generate Report', content: form, footer });
    },

    async _viewReport(report) {
        try {
            const full = await API.getReport(report.id);
            const container = DOM.el('div');

            if (full.findings && full.findings.length > 0) {
                for (const f of full.findings) {
                    const colors = { CRITICAL: 'var(--accent-red)', WARNING: 'var(--accent-yellow)', INFO: 'var(--accent-blue)' };
                    const item = DOM.el('div', {
                        style: {
                            padding: '12px', margin: '8px 0', borderRadius: '6px',
                            borderLeft: `3px solid ${colors[f.severity] || 'var(--border-color)'}`,
                            background: 'var(--bg-tertiary)'
                        }
                    });
                    item.innerHTML = `
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
                            <span class="badge badge-${f.severity === 'CRITICAL' ? 'danger' : f.severity === 'WARNING' ? 'warning' : 'info'}">${f.severity}</span>
                            <strong>${f.title}</strong>
                        </div>
                        <div class="text-sm" style="margin-bottom:6px">${f.detail}</div>
                        <div class="text-sm" style="color:var(--accent-green)"><strong>Recommendation:</strong> ${f.recommendation}</div>
                    `;
                    container.appendChild(item);
                }
            } else {
                container.innerHTML = '<p class="text-muted text-center">No findings</p>';
            }

            Modal.show({
                title: report.title,
                content: container,
                footer: DOM.el('button', { className: 'btn btn-secondary', textContent: 'Close', onClick: () => Modal.hide() }),
                width: '640px'
            });
        } catch (err) {
            Toast.error('Failed to load report');
        }
    }
};
