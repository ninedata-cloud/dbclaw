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
                onClick: async () => {
                    try {
                        await API.downloadReport(report.id, 'md');
                    } catch (err) {
                        Toast.error('Download failed: ' + err.message);
                    }
                }
            }));
            actions.appendChild(DOM.el('button', {
                className: 'btn btn-sm btn-primary',
                innerHTML: '<i data-lucide="file-down"></i> PDF',
                onClick: async () => {
                    try {
                        await API.downloadReport(report.id, 'pdf');
                    } catch (err) {
                        Toast.error('Download failed: ' + err.message);
                    }
                }
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
            const container = DOM.el('div', { className: 'report-view-container' });

            // Show full report content if available
            if (full.content_html) {
                // Display HTML content - extract body content only, strip inline styles
                const htmlContainer = DOM.el('div', { className: 'report-content-html' });

                // Parse HTML and extract body content
                const parser = new DOMParser();
                const doc = parser.parseFromString(full.content_html, 'text/html');
                const bodyContent = doc.querySelector('.container') || doc.body;

                // Clone the content and remove all inline styles
                const cleanContent = bodyContent.cloneNode(true);
                cleanContent.querySelectorAll('[style]').forEach(el => el.removeAttribute('style'));
                cleanContent.querySelectorAll('style').forEach(el => el.remove());

                // Set the cleaned HTML
                htmlContainer.innerHTML = cleanContent.innerHTML;

                // Apply syntax highlighting to code blocks
                if (typeof hljs !== 'undefined') {
                    htmlContainer.querySelectorAll('pre code:not(.hljs)').forEach((block) => {
                        hljs.highlightElement(block);
                    });
                }
                container.appendChild(htmlContainer);
            } else if (full.content_md) {
                // Display markdown content
                const mdContainer = DOM.el('div', { className: 'report-content-markdown' });
                if (typeof marked !== 'undefined') {
                    try {
                        // Configure marked with proper options
                        marked.setOptions({
                            breaks: true,
                            gfm: true,
                            headerIds: false,
                            mangle: false
                        });

                        // Configure highlight.js integration
                        if (typeof hljs !== 'undefined') {
                            marked.setOptions({
                                highlight: function(code, lang) {
                                    if (lang && hljs.getLanguage(lang)) {
                                        try {
                                            return hljs.highlight(code, { language: lang }).value;
                                        } catch (err) {
                                            console.error('Highlight error:', err);
                                        }
                                    }
                                    return hljs.highlightAuto(code).value;
                                }
                            });
                        }

                        // Parse markdown
                        const html = marked.parse(full.content_md);
                        mdContainer.innerHTML = html;

                        // Additional highlighting pass for any missed code blocks
                        if (typeof hljs !== 'undefined') {
                            mdContainer.querySelectorAll('pre code:not(.hljs)').forEach((block) => {
                                hljs.highlightElement(block);
                            });
                        }
                    } catch (error) {
                        console.error('Markdown rendering error:', error);
                        mdContainer.innerHTML = `<pre style="white-space: pre-wrap; color: var(--text-primary);">${full.content_md}</pre>`;
                    }
                } else {
                    console.warn('marked.js not available, displaying raw markdown');
                    mdContainer.innerHTML = `<pre style="white-space: pre-wrap; color: var(--text-primary);">${full.content_md}</pre>`;
                }
                container.appendChild(mdContainer);
            } else if (full.findings && full.findings.length > 0) {
                // Fallback: show only findings if no content available
                const findingsTitle = DOM.el('h4', {
                    textContent: 'Findings',
                    className: 'report-findings-title'
                });
                container.appendChild(findingsTitle);

                for (const f of full.findings) {
                    const severityClass = f.severity.toLowerCase();
                    const item = DOM.el('div', {
                        className: `report-finding-item ${severityClass}`
                    });
                    item.innerHTML = `
                        <div class="report-finding-header">
                            <span class="badge badge-${f.severity === 'CRITICAL' ? 'danger' : f.severity === 'WARNING' ? 'warning' : 'info'}">${f.severity}</span>
                            <strong class="report-finding-title">${f.title}</strong>
                        </div>
                        <div class="report-finding-detail">${f.detail}</div>
                        <div class="report-finding-recommendation"><strong>Recommendation:</strong> ${f.recommendation}</div>
                    `;
                    container.appendChild(item);
                }
            } else {
                container.innerHTML = '<div class="report-empty-content"><p>No report content available</p></div>';
            }

            const footer = DOM.el('div', { style: { display: 'flex', gap: '8px' } });
            footer.appendChild(DOM.el('button', {
                className: 'btn btn-secondary',
                textContent: 'Close',
                onClick: () => Modal.hide()
            }));

            // Add download buttons
            if (full.status === 'completed') {
                footer.appendChild(DOM.el('button', {
                    className: 'btn btn-primary',
                    innerHTML: '<i data-lucide="download"></i> Download PDF',
                    onClick: async () => {
                        try {
                            await API.downloadReport(report.id, 'pdf');
                            DOM.createIcons();
                        } catch (err) {
                            Toast.error('Download failed: ' + err.message);
                        }
                    }
                }));
            }

            Modal.show({
                title: report.title,
                content: container,
                footer: footer,
                width: '900px'
            });

            DOM.createIcons();
        } catch (err) {
            Toast.error('Failed to load report');
        }
    },

    _startAIGeneration(report) {
        // Create streaming modal
        const container = DOM.el('div', { style: { minHeight: '400px' } });

        // Status section
        const statusSection = DOM.el('div', { className: 'report-generation-status' });
        statusSection.innerHTML = '<div id="report-status">Connecting...</div>';
        container.appendChild(statusSection);

        // AI Analysis section
        const analysisSection = DOM.el('div', { className: 'report-generation-section' });
        analysisSection.innerHTML = `
            <h4>AI Analysis</h4>
            <div id="report-ai-content" class="report-ai-content"></div>
        `;
        container.appendChild(analysisSection);

        // Tool execution log
        const toolSection = DOM.el('div', { className: 'report-generation-section' });
        toolSection.innerHTML = `
            <h4>Diagnostic Tools</h4>
            <div id="report-tool-log" class="report-tool-log"></div>
        `;
        container.appendChild(toolSection);

        // Findings section
        const findingsSection = DOM.el('div', { className: 'report-generation-section' });
        findingsSection.innerHTML = `
            <h4>Findings</h4>
            <div id="report-findings" class="report-findings-container"></div>
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
                    const toolItem = DOM.el('div', { className: 'report-tool-item' });
                    toolItem.innerHTML = `
                        <div class="report-tool-header">
                            <div class="report-tool-name">
                                <span class="badge badge-info" style="font-size:10px;">${data.tool_name}</span>
                                <span class="text-muted" style="font-size:11px;">Executing...</span>
                            </div>
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
                    toolItem.className = `report-tool-item ${hasError ? 'error' : 'success'}`;
                    toolItem.innerHTML = `
                        <div class="report-tool-header">
                            <div class="report-tool-name">
                                <span class="badge badge-${hasError ? 'danger' : 'success'}" style="font-size:10px;">${data.tool_name}</span>
                                <span class="text-muted" style="font-size:11px;">${hasError ? 'Failed' : 'Completed'}</span>
                            </div>
                            <span class="report-tool-time">${data.execution_time_ms}ms</span>
                        </div>
                    `;
                }
                break;

            case 'finding':
                if (findingsEl) {
                    const severityClass = data.severity.toLowerCase();
                    const findingItem = DOM.el('div', {
                        className: `report-finding-item ${severityClass}`
                    });
                    findingItem.innerHTML = `
                        <div class="report-finding-header">
                            <span class="badge badge-${data.severity === 'CRITICAL' ? 'danger' : data.severity === 'WARNING' ? 'warning' : 'info'}" style="font-size:10px;">${data.severity}</span>
                            <strong class="report-finding-title">${data.title}</strong>
                        </div>
                        <div class="report-finding-detail">${data.detail}</div>
                    `;
                    findingsEl.appendChild(findingItem);
                    findingsEl.scrollTop = findingsEl.scrollHeight;
                }
                break;

            case 'report_complete':
                if (statusEl) {
                    statusEl.innerHTML = `<span class="report-status-success">✓ ${data.summary}</span>`;
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
                    statusEl.innerHTML = `<span class="report-status-error">✗ Error: ${errorMsg}</span>`;
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
