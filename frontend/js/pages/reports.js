/* Reports page */
const ReportsPage = {
    pollInterval: null,
    ws: null,

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
            if (this.ws) {
                this.ws.shouldReconnect = false;
                this.ws.disconnect();
            }
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
                DOM.createIcons();
                return;
            }

            const grid = DOM.el('div', { className: 'datasource-grid' });
            for (const report of reports) {
                grid.appendChild(this._createReportCard(report));
            }
            content.appendChild(grid);
            DOM.createIcons();

            // Poll for generating reports (only for non-AI reports)
            const hasGenerating = reports.some(r => r.status === 'generating' && r.generation_method !== 'ai');
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
        const card = DOM.el('div', { className: 'datasource-card' });

        const statusBadge = {
            completed: '<span class="badge badge-success">Completed</span>',
            generating: '<span class="badge badge-warning">Generating...</span>',
            pending: '<span class="badge badge-info">Pending</span>',
            failed: '<span class="badge badge-danger">Failed</span>',
        }[report.status] || '';

        const methodBadge = report.generation_method === 'ai'
            ? '<span class="badge badge-primary" style="margin-left:4px;">AI</span>'
            : '';

        card.innerHTML = `
            <div class="datasource-card-header">
                <span class="datasource-card-name">${report.title}</span>
                <div>${statusBadge}${methodBadge}</div>
            </div>
            <div class="datasource-card-info">
                <span><i data-lucide="calendar"></i> ${Format.datetime(report.created_at)}</span>
                <span><i data-lucide="tag"></i> ${report.report_type}</span>
                ${report.summary ? `<span style="margin-top:8px;color:var(--text-primary)">${report.summary}</span>` : ''}
            </div>
        `;

        if (report.status === 'completed') {
            const actions = DOM.el('div', { className: 'datasource-card-actions' });
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
        } else if (report.status === 'pending' && report.generation_method === 'ai') {
            const actions = DOM.el('div', { className: 'datasource-card-actions' });
            actions.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-primary',
                innerHTML: '<i data-lucide="play"></i> Start Generation',
                onClick: () => this._startAIGeneration(report)
            }));
            card.appendChild(actions);
        }

        return card;
    },

    async _showGenerateModal() {
        const form = DOM.el('form');

        let connectionsHtml = '<option value="">Select connection...</option>';
        try {
            const connections = await API.getDatasources();
            const current = Store.get('currentConnection');
            for (const c of connections) {
                const selected = current && c.id === current.id ? 'selected' : '';
                connectionsHtml += `<option value="${c.id}" ${selected}>${c.name} (${c.db_type})</option>`;
            }
        } catch (e) { /* ignore */ }

        let modelsHtml = '<option value="">Default model</option>';
        try {
            const models = await API.getAIModels();
            for (const m of models) {
                modelsHtml += `<option value="${m.id}">${m.name}</option>`;
            }
        } catch (e) { /* ignore */ }

        let kbsHtml = '';
        try {
            const kbs = await API.getKnowledgeBases();
            for (const kb of kbs) {
                kbsHtml += `
                    <label style="display:flex;align-items:center;gap:8px;padding:8px;cursor:pointer;">
                        <input type="checkbox" name="kb_ids" value="${kb.id}">
                        <span>${kb.name}</span>
                    </label>
                `;
            }
        } catch (e) { /* ignore */ }

        form.innerHTML = `
            <div class="form-group">
                <label>Datasource</label>
                <select class="form-select" name="datasource_id" required>${connectionsHtml}</select>
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
            <div class="form-group">
                <label style="display:flex;align-items:center;gap:8px;">
                    <input type="checkbox" name="ai_enabled" checked>
                    <span>Use AI Analysis</span>
                </label>
                <small class="text-muted">Enable AI-powered diagnostic analysis with real-time streaming</small>
            </div>
            <div id="ai-options" style="margin-top:16px;">
                <div class="form-group">
                    <label>AI Model</label>
                    <select class="form-select" name="model_id">${modelsHtml}</select>
                </div>
                <div class="form-group">
                    <label>Knowledge Bases</label>
                    <div style="max-height:150px;overflow-y:auto;border:1px solid var(--border-color);border-radius:4px;padding:8px;">
                        ${kbsHtml || '<p class="text-muted text-center" style="padding:8px;">No knowledge bases available</p>'}
                    </div>
                </div>
            </div>
        `;

        const aiEnabledCheckbox = form.querySelector('[name="ai_enabled"]');
        const aiOptions = form.querySelector('#ai-options');

        aiEnabledCheckbox.addEventListener('change', () => {
            aiOptions.style.display = aiEnabledCheckbox.checked ? 'block' : 'none';
        });

        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(form);
            const data = {
                datasource_id: parseInt(formData.get('datasource_id')),
                report_type: formData.get('report_type'),
                title: formData.get('title') || undefined,
                ai_enabled: formData.get('ai_enabled') === 'on',
                model_id: formData.get('model_id') ? parseInt(formData.get('model_id')) : undefined,
                kb_ids: formData.getAll('kb_ids').map(id => parseInt(id))
            };

            if (!data.datasource_id) {
                Toast.warning('Select a datasource');
                return;
            }

            try {
                const report = await API.generateReport(data);
                Toast.success('Report created');
                Modal.hide();

                if (data.ai_enabled) {
                    // Start AI generation with streaming
                    this._startAIGeneration(report);
                } else {
                    // Traditional generation runs in background
                    this._loadReports();
                }
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
    },

    _startAIGeneration(report) {
        // Create streaming modal
        const container = DOM.el('div', { style: { minHeight: '400px' } });

        // Status section
        const statusSection = DOM.el('div', {
            style: {
                padding: '12px',
                background: 'var(--bg-tertiary)',
                borderRadius: '6px',
                marginBottom: '16px'
            }
        });
        statusSection.innerHTML = '<div id="report-status" class="text-sm">Connecting...</div>';
        container.appendChild(statusSection);

        // AI Analysis section
        const analysisSection = DOM.el('div', { style: { marginBottom: '16px' } });
        analysisSection.innerHTML = `
            <h4 style="margin-bottom:8px;">AI Analysis</h4>
            <div id="report-ai-content" style="
                max-height:200px;
                overflow-y:auto;
                padding:12px;
                background:var(--bg-tertiary);
                border-radius:6px;
                font-size:13px;
                line-height:1.6;
                white-space:pre-wrap;
            "></div>
        `;
        container.appendChild(analysisSection);

        // Tool execution log
        const toolSection = DOM.el('div', { style: { marginBottom: '16px' } });
        toolSection.innerHTML = `
            <h4 style="margin-bottom:8px;">Diagnostic Tools</h4>
            <div id="report-tool-log" style="
                max-height:150px;
                overflow-y:auto;
                padding:12px;
                background:var(--bg-tertiary);
                border-radius:6px;
                font-size:12px;
            "></div>
        `;
        container.appendChild(toolSection);

        // Findings section
        const findingsSection = DOM.el('div');
        findingsSection.innerHTML = `
            <h4 style="margin-bottom:8px;">Findings</h4>
            <div id="report-findings" style="max-height:150px;overflow-y:auto;"></div>
        `;
        container.appendChild(findingsSection);

        const footer = DOM.el('div', { style: { display: 'flex', gap: '8px', justifyContent: 'flex-end' } });
        const cancelBtn = DOM.el('button', {
            className: 'btn btn-secondary',
            textContent: 'Cancel',
            onClick: () => {
                if (this.ws) {
                    this.ws.shouldReconnect = false;
                    this.ws.disconnect();
                }
                Modal.hide();
                this._loadReports();
            }
        });
        footer.appendChild(cancelBtn);

        Modal.show({
            title: `Generating Report: ${report.title}`,
            content: container,
            footer,
            width: '800px'
        });

        // Connect WebSocket
        this._connectReportWebSocket(report.id);
    },

    _connectReportWebSocket(reportId) {
        if (this.ws) {
            this.ws.shouldReconnect = false;
            this.ws.disconnect();
        }

        const ws = new WSManager(`/ws/reports/generate/${reportId}`);
        this.ws = ws;

        ws.on('open', () => {
            console.log('Report WebSocket connected');
        });

        ws.on('message', (data) => this._handleReportWSMessage(data));

        ws.on('error', (error) => {
            console.error('Report WebSocket error:', error);
        });

        ws.on('close', (event) => {
            console.log('Report WebSocket closed:', event);
            if (event && event.code === 1000) {
                // Normal closure
                console.log('Report WebSocket closed normally');
            } else if (event && event.code === 1008) {
                // Policy violation (auth error)
                Toast.error('Authentication failed. Please refresh and try again.');
                Modal.hide();
            } else if (event && event.code !== 1000) {
                // Abnormal closure - provide better context
                const reason = event?.reason || 'Connection closed unexpectedly';
                Toast.error(`Report generation connection lost: ${reason}`);
                Modal.hide();
            }
        });

        ws.connect();
    },

    _handleReportWSMessage(data) {
        const statusEl = DOM.$('#report-status');
        const aiContentEl = DOM.$('#report-ai-content');
        const toolLogEl = DOM.$('#report-tool-log');
        const findingsEl = DOM.$('#report-findings');

        switch (data.type) {
            case 'status':
                if (statusEl) {
                    statusEl.textContent = data.message;
                }
                break;

            case 'content':
                if (aiContentEl) {
                    aiContentEl.textContent += data.content;
                    aiContentEl.scrollTop = aiContentEl.scrollHeight;
                }
                break;

            case 'tool_call':
                if (toolLogEl) {
                    const toolItem = DOM.el('div', {
                        style: {
                            padding: '6px',
                            marginBottom: '4px',
                            background: 'var(--bg-secondary)',
                            borderRadius: '4px',
                            borderLeft: '3px solid var(--accent-blue)'
                        }
                    });
                    toolItem.innerHTML = `
                        <div style="display:flex;align-items:center;gap:8px;">
                            <span class="badge badge-info" style="font-size:10px;">${data.tool_name}</span>
                            <span class="text-muted" style="font-size:11px;">Executing...</span>
                        </div>
                    `;
                    toolItem.id = `tool-${data.tool_call_id}`;
                    toolLogEl.appendChild(toolItem);
                    toolLogEl.scrollTop = toolLogEl.scrollHeight;
                }
                break;

            case 'tool_result':
                const toolItem = DOM.$(`#tool-${data.tool_call_id}`);
                if (toolItem) {
                    const resultData = typeof data.result === 'string' ? JSON.parse(data.result) : data.result;
                    const hasError = resultData.error;
                    toolItem.style.borderLeftColor = hasError ? 'var(--accent-red)' : 'var(--accent-green)';
                    toolItem.innerHTML = `
                        <div style="display:flex;align-items:center;gap:8px;justify-content:space-between;">
                            <div style="display:flex;align-items:center;gap:8px;">
                                <span class="badge badge-${hasError ? 'danger' : 'success'}" style="font-size:10px;">${data.tool_name}</span>
                                <span class="text-muted" style="font-size:11px;">${hasError ? 'Failed' : 'Completed'}</span>
                            </div>
                            <span class="text-muted" style="font-size:10px;">${data.execution_time_ms}ms</span>
                        </div>
                    `;
                }
                break;

            case 'finding':
                if (findingsEl) {
                    const colors = {
                        CRITICAL: 'var(--accent-red)',
                        WARNING: 'var(--accent-yellow)',
                        INFO: 'var(--accent-blue)'
                    };
                    const findingItem = DOM.el('div', {
                        style: {
                            padding: '8px',
                            margin: '4px 0',
                            borderRadius: '4px',
                            borderLeft: `3px solid ${colors[data.severity] || 'var(--border-color)'}`,
                            background: 'var(--bg-tertiary)',
                            fontSize: '12px'
                        }
                    });
                    findingItem.innerHTML = `
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
                            <span class="badge badge-${data.severity === 'CRITICAL' ? 'danger' : data.severity === 'WARNING' ? 'warning' : 'info'}" style="font-size:10px;">${data.severity}</span>
                            <strong style="font-size:12px;">${data.title}</strong>
                        </div>
                        <div style="font-size:11px;color:var(--text-muted);">${data.detail}</div>
                    `;
                    findingsEl.appendChild(findingItem);
                    findingsEl.scrollTop = findingsEl.scrollHeight;
                }
                break;

            case 'report_complete':
                if (statusEl) {
                    statusEl.innerHTML = `<span style="color:var(--accent-green);">✓ ${data.summary}</span>`;
                }
                Toast.success('Report generation completed');
                setTimeout(() => {
                    Modal.hide();
                    this._loadReports();
                }, 2000);
                break;

            case 'done':
                if (this.ws) {
                    this.ws.shouldReconnect = false;
                    this.ws.disconnect();
                }
                break;

            case 'error':
                const errorMsg = data.message || data.content || 'Unknown error';
                if (statusEl) {
                    statusEl.innerHTML = `<span style="color:var(--accent-red);">✗ Error: ${errorMsg}</span>`;
                }
                Toast.error(`Report generation failed: ${errorMsg}`);
                // Auto-close modal after 3 seconds
                setTimeout(() => {
                    Modal.hide();
                    this._loadReports();
                }, 3000);
                break;
        }
    }
};
