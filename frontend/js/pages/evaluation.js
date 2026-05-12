/* AI 诊断评测 page */
const EvaluationPage = {
    cases: [],
    suites: [],
    runs: [],
    aiModels: [],
    activeTab: 'runs',          // runs | cases
    activeRunId: null,
    pollingTimer: null,
    runDetailRefreshInFlight: false,
    runDetailDigestByRunId: {},
    runDetailMetaDigestByRunId: {},

    render() {
        Header.render('AI 评测', this._buildHeaderActions());
        const content = DOM.$('#page-content');
        content.innerHTML = `
            <div class="eval-page">
                <div class="eval-tabs">
                    <button class="eval-tab ${this.activeTab === 'runs' ? 'active' : ''}" data-tab="runs">运行记录</button>
                    <button class="eval-tab ${this.activeTab === 'cases' ? 'active' : ''}" data-tab="cases">Case 库</button>
                </div>
                <div id="eval-tab-content"></div>
            </div>
        `;
        content.querySelectorAll('.eval-tab').forEach(btn => {
            btn.onclick = () => {
                this._stopPolling();
                this.activeTab = btn.dataset.tab;
                this.render();
            };
        });
        this._injectStyles();
        if (this.activeTab === 'runs') this._renderRunsTab();
        else this._renderCasesTab();
    },

    _buildHeaderActions() {
        const startBtn = DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="play"></i> 启动评测',
            onClick: () => this._showStartRunModal(),
        });
        return [startBtn];
    },

    _injectStyles() {
        if (document.getElementById('eval-page-style')) return;
        const style = document.createElement('style');
        style.id = 'eval-page-style';
        style.textContent = `
            .eval-page {
                display: flex;
                flex-direction: column;
                gap: 16px;
                padding: 8px 4px 24px;
                color: var(--text-primary);
            }
            .eval-tabs {
                display: flex;
                gap: 4px;
                border-bottom: 1px solid var(--border-color);
            }
            .eval-tab {
                min-height: 40px;
                padding: 0 18px;
                background: transparent;
                border: 0;
                border-bottom: 2px solid transparent;
                color: var(--text-secondary);
                cursor: pointer;
                font-size: 14px;
                transition: color var(--transition), background var(--transition), border-color var(--transition);
            }
            .eval-tab:hover {
                color: var(--text-primary);
                background: rgba(255, 255, 255, 0.03);
            }
            .eval-tab.active {
                color: var(--text-primary);
                border-bottom-color: var(--accent-blue);
                background: rgba(47, 129, 247, 0.08);
                font-weight: 600;
            }
            .eval-table-card {
                overflow-x: auto;
                border: 1px solid var(--border-color);
                border-radius: 12px;
                background: var(--bg-secondary);
                box-shadow: var(--shadow-md);
            }
            .eval-table {
                width: 100%;
                min-width: 960px;
                border-collapse: collapse;
                color: var(--text-primary);
            }
            .eval-run-table { min-width: 980px; }
            .eval-case-table { min-width: 1320px; }
            .eval-result-table { min-width: 940px; }
            .eval-table th,
            .eval-table td {
                padding: 13px 14px;
                border-bottom: 1px solid var(--border-color);
                text-align: left;
                vertical-align: top;
                line-height: 1.45;
            }
            .eval-table th {
                color: var(--text-secondary);
                background: rgba(255, 255, 255, 0.03);
                font-size: 12px;
                font-weight: 700;
                white-space: nowrap;
                letter-spacing: 0;
            }
            .eval-table td {
                color: var(--text-primary);
                font-size: 13px;
            }
            .eval-table tbody tr {
                transition: background var(--transition);
            }
            .eval-table tbody tr:hover {
                background: var(--bg-hover);
                cursor: pointer;
            }
            .eval-table tr:last-child td {
                border-bottom: 0;
            }
            .eval-table code,
            .eval-mono {
                font-family: var(--font-mono);
                font-size: 12px;
                color: #c9d1d9;
            }
            .eval-case-id {
                display: inline-block;
                max-width: 320px;
                overflow-wrap: anywhere;
                line-height: 1.5;
            }
            .eval-primary-text {
                color: var(--text-primary);
                font-weight: 700;
            }
            .eval-secondary-text {
                color: var(--text-muted);
                font-size: 12px;
            }
            .eval-score {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-height: 24px;
                min-width: 46px;
                padding: 0 10px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 999px;
                font-size: 12px;
                font-weight: 700;
                font-variant-numeric: tabular-nums;
                color: var(--text-secondary);
                background: rgba(255, 255, 255, 0.06);
            }
            .eval-score-high {
                color: var(--accent-green);
                background: rgba(63, 185, 80, 0.12);
                border-color: rgba(63, 185, 80, 0.22);
            }
            .eval-score-mid {
                color: var(--accent-yellow);
                background: rgba(210, 153, 34, 0.13);
                border-color: rgba(210, 153, 34, 0.24);
            }
            .eval-score-low {
                color: var(--accent-red);
                background: rgba(248, 81, 73, 0.13);
                border-color: rgba(248, 81, 73, 0.24);
            }
            .eval-status {
                display: inline-flex;
                align-items: center;
                min-height: 24px;
                padding: 0 9px;
                border-radius: 999px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                font-size: 12px;
                font-weight: 700;
                white-space: nowrap;
                color: var(--text-secondary);
                background: rgba(255, 255, 255, 0.06);
            }
            .eval-status-running,
            .eval-status-pending {
                color: var(--accent-blue);
                background: rgba(47, 129, 247, 0.12);
                border-color: rgba(47, 129, 247, 0.24);
            }
            .eval-status-completed,
            .eval-status-success,
            .eval-status-passed {
                color: var(--accent-green);
                background: rgba(63, 185, 80, 0.12);
                border-color: rgba(63, 185, 80, 0.22);
            }
            .eval-status-failed,
            .eval-status-error {
                color: var(--accent-red);
                background: rgba(248, 81, 73, 0.13);
                border-color: rgba(248, 81, 73, 0.24);
            }
            .eval-status-cancelled,
            .eval-status-skipped {
                color: var(--text-muted);
                background: rgba(255, 255, 255, 0.06);
            }
            .eval-tool-list {
                display: flex;
                flex-wrap: wrap;
                gap: 6px;
                max-width: 560px;
            }
            .eval-tool-chip {
                display: inline-flex;
                align-items: center;
                min-height: 24px;
                max-width: 100%;
                padding: 2px 8px;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 999px;
                font-family: var(--font-mono);
                font-size: 11px;
                line-height: 1.45;
                overflow-wrap: anywhere;
                color: var(--accent-blue);
                background: rgba(47, 129, 247, 0.1);
            }
            .eval-tool-chip.forbidden {
                color: #ff7b72;
                background: rgba(248, 81, 73, 0.1);
                border-color: rgba(248, 81, 73, 0.2);
            }
            .eval-tool-chip.empty {
                color: var(--text-muted);
                background: rgba(255, 255, 255, 0.05);
            }
            .eval-detail {
                padding: 16px;
                background: var(--bg-secondary);
                border: 1px solid var(--border-color);
                border-radius: 12px;
                box-shadow: var(--shadow-md);
            }
            .eval-summary-grid {
                display: flex;
                flex-wrap: wrap;
                align-items: stretch;
                gap: 14px;
                margin-bottom: 14px;
            }
            .eval-summary-item {
                min-width: 132px;
                padding: 10px 12px;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
                background: rgba(255, 255, 255, 0.03);
            }
            .eval-summary-item.score {
                min-width: 160px;
            }
            .eval-summary-label {
                margin-bottom: 5px;
                color: var(--text-secondary);
                font-size: 12px;
            }
            .eval-summary-value {
                color: var(--text-primary);
                font-size: 14px;
                font-weight: 600;
            }
            .eval-summary-score {
                color: var(--text-primary);
                font-size: 32px;
                font-weight: 700;
                line-height: 1;
                font-variant-numeric: tabular-nums;
            }
            .eval-summary-score span {
                color: var(--text-secondary);
                font-size: 14px;
                font-weight: 600;
            }
            .eval-dim-section {
                border-top: 1px solid var(--border-color);
                padding-top: 12px;
            }
            .eval-dim-bar {
                display: flex;
                align-items: center;
                gap: 12px;
                margin-bottom: 8px;
                font-size: 13px;
            }
            .eval-dim-name {
                width: 130px;
                color: var(--text-secondary);
                overflow-wrap: anywhere;
            }
            .eval-dim-track {
                flex: 1;
                min-width: 120px;
                height: 8px;
                background: rgba(255, 255, 255, 0.07);
                border-radius: 999px;
                overflow: hidden;
            }
            .eval-dim-fill {
                display: block;
                height: 100%;
                border-radius: inherit;
                background: linear-gradient(to right, var(--accent-blue), var(--accent-cyan));
            }
            .eval-dim-value {
                width: 92px;
                color: var(--text-primary);
                text-align: right;
                font-variant-numeric: tabular-nums;
            }
            .eval-dim-detail {
                margin: -2px 0 10px 130px;
                color: var(--text-muted);
                font-size: 12px;
                line-height: 1.5;
            }
            .eval-back {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                width: fit-content;
                margin-bottom: 12px;
                color: var(--text-secondary);
                cursor: pointer;
                font-weight: 600;
            }
            .eval-back svg {
                width: 16px;
                height: 16px;
            }
            .eval-back:hover {
                color: var(--text-primary);
            }
            .eval-result-row td {
                vertical-align: top;
            }
            .eval-fixture-block,
            .eval-conclusion-md {
                color: var(--text-primary);
                background: var(--bg-input);
                border: 1px solid var(--border-color);
                border-radius: 8px;
            }
            .eval-fixture-block {
                padding: 10px;
                margin-top: 8px;
                font-family: var(--font-mono);
                font-size: 12px;
                white-space: pre-wrap;
                max-height: 220px;
                overflow-y: auto;
            }
            .eval-conclusion-md {
                padding: 12px;
                max-height: 480px;
                overflow-y: auto;
                font-size: 13px;
                line-height: 1.6;
                white-space: pre-wrap;
            }
            .eval-feedback-card {
                padding: 10px 12px;
                background: rgba(47, 129, 247, 0.1);
                border-left: 3px solid var(--accent-blue);
                border-radius: 6px;
                margin: 8px 0;
                color: var(--text-primary);
                font-size: 13px;
                line-height: 1.5;
            }
            .eval-feedback-card.eval-feedback-danger {
                background: rgba(248, 81, 73, 0.1);
                border-left-color: var(--accent-red);
            }
            .eval-empty,
            .eval-page .loading {
                padding: 44px 20px;
                text-align: center;
                color: var(--text-secondary);
                background: var(--bg-secondary);
                border: 1px solid var(--border-color);
                border-radius: 12px;
            }
            .eval-replay-meta {
                display: flex;
                flex-wrap: wrap;
                gap: 10px 12px;
                padding: 10px 12px;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                margin-bottom: 14px;
                font-size: 12px;
                color: var(--text-secondary);
            }
            .eval-replay-list {
                display: flex;
                flex-direction: column;
                gap: 10px;
                max-height: 62vh;
                overflow-y: auto;
                padding-right: 4px;
            }
            .eval-replay-message {
                border: 1px solid var(--border-color);
                border-radius: 8px;
                background: var(--bg-secondary);
                overflow: hidden;
            }
            .eval-replay-message-head {
                display: flex;
                justify-content: space-between;
                gap: 12px;
                padding: 8px 10px;
                background: rgba(255, 255, 255, 0.04);
                font-size: 12px;
                color: var(--text-secondary);
            }
            .eval-replay-message-body {
                padding: 10px;
                color: var(--text-primary);
                white-space: pre-wrap;
                font-size: 13px;
                line-height: 1.55;
                max-height: 360px;
                overflow: auto;
            }
            .eval-replay-role {
                font-weight: 700;
                color: var(--text-primary);
            }
            .eval-inline-action {
                padding: 0;
                color: var(--accent-blue);
                background: transparent;
                border: 0;
            }
            .eval-inline-action:hover {
                color: var(--accent-blue-hover);
                background: transparent;
            }
            .eval-actions-cell {
                width: 92px;
                text-align: right;
                white-space: nowrap;
            }
            .eval-actions-cell .btn {
                min-width: 0;
            }
            @media (max-width: 720px) {
                .eval-page { padding: 4px 0 20px; }
                .eval-tabs { overflow-x: auto; }
                .eval-tab { flex: 0 0 auto; }
                .eval-summary-grid { display: grid; grid-template-columns: 1fr; }
                .eval-summary-item { min-width: 0; }
                .eval-dim-bar { align-items: flex-start; flex-wrap: wrap; gap: 8px; }
                .eval-dim-name { width: 100%; }
                .eval-dim-detail { margin-left: 0; }
            }
        `;
        document.head.appendChild(style);
    },

    cleanup() {
        this._stopPolling();
    },

    // ---------------- Runs tab

    async _renderRunsTab() {
        this._stopPolling();
        this.activeRunId = null;
        this.runDetailDigestByRunId = {};
        this.runDetailMetaDigestByRunId = {};
        const host = DOM.$('#eval-tab-content');
        host.innerHTML = '<div class="loading">正在加载评测记录...</div>';
        try {
            this.runs = await API.listEvalRuns();
        } catch (err) {
            host.innerHTML = `<div class="eval-empty">加载失败：${Utils.escapeHtml(err.message)}</div>`;
            return;
        }
        if (!this.runs.length) {
            host.innerHTML = '<div class="eval-empty">还没有评测记录。点击右上角"启动评测"开始第一次评测。</div>';
            return;
        }
        host.innerHTML = `
            <div class="eval-table-card">
                <table class="eval-table eval-run-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>套件</th>
                            <th>AI 模型</th>
                            <th>状态</th>
                            <th>进度</th>
                            <th>总分</th>
                            <th>开始时间</th>
                            <th>耗时</th>
                            <th></th>
                        </tr>
                    </thead>
                    <tbody id="eval-runs-tbody"></tbody>
                </table>
            </div>
        `;
        const tbody = DOM.$('#eval-runs-tbody');
        for (const run of this.runs) {
            const tr = document.createElement('tr');
            tr.onclick = () => this._showRunDetail(run.id);
            const score = run.total_score == null ? '-' : run.total_score.toFixed(1);
            const scoreClass = this._scoreClass(run.total_score);
            const elapsed = this._formatElapsed(run.started_at, run.finished_at);
            const deletingTitle = this._isRunActive(run) ? '停止并删除评测记录' : '删除评测记录';
            tr.innerHTML = `
                <td><span class="eval-mono">#${run.id}</span></td>
                <td><span class="eval-primary-text">${Utils.escapeHtml(run.suite_name || '-')}</span></td>
                <td>${Utils.escapeHtml(run.ai_model_name || '-')}</td>
                <td>${this._renderStatus(run.status)}</td>
                <td>${run.completed_cases}/${run.total_cases} ${run.failed_cases ? `(失败 ${run.failed_cases})` : ''}</td>
                <td><span class="eval-score ${scoreClass}">${score}</span></td>
                <td>${this._fmtTime(run.started_at)}</td>
                <td>${elapsed}</td>
                <td class="eval-actions-cell"><button class="btn btn-sm btn-danger" title="${deletingTitle}" aria-label="${deletingTitle}"><i data-lucide="trash-2"></i></button></td>
            `;
            const deleteBtn = tr.querySelector('.btn-danger');
            if (deleteBtn) {
                deleteBtn.onclick = (event) => {
                    event.stopPropagation();
                    this._deleteRun(run);
                };
            }
            tbody.appendChild(tr);
        }
        DOM.createIcons();
    },

    async _showRunDetail(runId, options = {}) {
        const silent = options.silent === true;
        if (!silent) {
            this.activeRunId = runId;
        } else if (this.activeTab !== 'runs' || this.activeRunId !== runId) {
            return;
        }
        const host = DOM.$('#eval-tab-content');
        const hasDetailShell = Boolean(DOM.$('#eval-run-detail-root'));

        if (!silent) {
            host.innerHTML = '<div class="loading">正在加载详情...</div>';
        } else if (!hasDetailShell) {
            return;
        }
        if (silent && this.runDetailRefreshInFlight) {
            return;
        }

        this.runDetailRefreshInFlight = true;
        let run, results;
        try {
            if (silent) {
                run = await API.getEvalRun(runId);
                const metaDigest = this._buildRunMetaDigest(run);
                if (this.runDetailMetaDigestByRunId[runId] === metaDigest) {
                    this._stopPolling();
                    if (this.activeRunId === runId && this.activeTab === 'runs' && (run.status === 'running' || run.status === 'pending')) {
                        this.pollingTimer = setTimeout(() => this._showRunDetail(runId, { silent: true }), 4000);
                    }
                    return;
                }
                this.runDetailMetaDigestByRunId[runId] = metaDigest;
                results = await API.listEvalRunResults(runId);
            } else {
                [run, results] = await Promise.all([
                    API.getEvalRun(runId),
                    API.listEvalRunResults(runId),
                ]);
                this.runDetailMetaDigestByRunId[runId] = this._buildRunMetaDigest(run);
            }
        } catch (err) {
            if (!silent || !hasDetailShell) {
                host.innerHTML = `<div class="eval-empty">加载失败：${Utils.escapeHtml(err.message)}</div>`;
            } else if (this.activeRunId === runId && this.activeTab === 'runs') {
                this._stopPolling();
                this.pollingTimer = setTimeout(() => this._showRunDetail(runId, { silent: true }), 6000);
            }
            return;
        } finally {
            this.runDetailRefreshInFlight = false;
        }

        if (this.activeRunId !== runId || this.activeTab !== 'runs') {
            return;
        }

        const digest = this._buildRunDetailDigest(run, results);
        if (silent && this.runDetailDigestByRunId[runId] === digest) {
            this._stopPolling();
            if (this.activeRunId === runId && this.activeTab === 'runs' && (run.status === 'running' || run.status === 'pending')) {
                this.pollingTimer = setTimeout(() => this._showRunDetail(runId, { silent: true }), 4000);
            }
            return;
        }
        this.runDetailDigestByRunId[runId] = digest;

        if (!silent || !hasDetailShell) {
            host.innerHTML = `
                <div id="eval-run-detail-root">
                    <div class="eval-back" id="eval-back-btn"><i data-lucide="arrow-left"></i> 返回评测列表</div>
                    <div class="eval-detail" style="margin-bottom:16px;">
                        <div class="eval-summary-grid">
                            <div class="eval-summary-item score">
                                <div class="eval-summary-label">总分</div>
                                <div class="eval-summary-score" id="eval-run-score">-<span> / 100</span></div>
                            </div>
                            <div class="eval-summary-item">
                                <div class="eval-summary-label">套件</div>
                                <div class="eval-summary-value" id="eval-run-suite">-</div>
                            </div>
                            <div class="eval-summary-item">
                                <div class="eval-summary-label">AI 模型</div>
                                <div class="eval-summary-value" id="eval-run-model">-</div>
                            </div>
                            <div class="eval-summary-item">
                                <div class="eval-summary-label">状态</div>
                                <div id="eval-run-status">-</div>
                            </div>
                            <div class="eval-summary-item">
                                <div class="eval-summary-label">进度</div>
                                <div class="eval-summary-value" id="eval-run-progress">-</div>
                            </div>
                        </div>
                        <div style="display:flex; justify-content:flex-end; margin-bottom:14px;">
                            <button class="btn btn-danger" id="eval-run-delete-btn"><i data-lucide="trash-2"></i> 删除记录</button>
                        </div>
                        <div class="eval-dim-section" id="eval-run-dim-section" style="display:none;"></div>
                    </div>
                    <div class="eval-table-card">
                        <table class="eval-table eval-result-table">
                            <thead>
                                <tr>
                                    <th>Case</th>
                                    <th>类别</th>
                                    <th>状态</th>
                                    <th>得分</th>
                                    <th>用时</th>
                                    <th>Tokens</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody id="eval-results-tbody"></tbody>
                        </table>
                    </div>
                </div>
            `;
            DOM.$('#eval-back-btn').onclick = () => {
                this._stopPolling();
                this.activeRunId = null;
                this._renderRunsTab();
            };
        }

        const scoreEl = DOM.$('#eval-run-score');
        const suiteEl = DOM.$('#eval-run-suite');
        const modelEl = DOM.$('#eval-run-model');
        const statusEl = DOM.$('#eval-run-status');
        const progressEl = DOM.$('#eval-run-progress');
        const dimSectionEl = DOM.$('#eval-run-dim-section');
        const deleteBtnEl = DOM.$('#eval-run-delete-btn');

        const totalScore = run.total_score == null ? '-' : run.total_score.toFixed(2);
        if (scoreEl) scoreEl.innerHTML = `${totalScore}<span> / 100</span>`;
        if (suiteEl) suiteEl.textContent = run.suite_name || '-';
        if (modelEl) modelEl.textContent = run.ai_model_name || '-';
        if (statusEl) statusEl.innerHTML = this._renderStatus(run.status);
        if (progressEl) progressEl.textContent = `${run.completed_cases}/${run.total_cases}${run.failed_cases ? ` (失败 ${run.failed_cases})` : ''}`;
        if (deleteBtnEl) {
            deleteBtnEl.disabled = false;
            deleteBtnEl.title = this._isRunActive(run) ? '停止并删除当前评测记录' : '删除当前评测记录';
            deleteBtnEl.onclick = () => this._deleteRun(run);
        }

        const dimSummary = run.dimension_summary || {};
        const dimRows = Object.entries(dimSummary).map(([name, val]) => {
            const max = this._dimensionMax(name);
            const pct = Math.round((val / max) * 100);
            return `
                <div class="eval-dim-bar">
                    <span class="eval-dim-name">${Utils.escapeHtml(name)}</span>
                    <span class="eval-dim-track"><span class="eval-dim-fill" style="width:${pct}%;"></span></span>
                    <span class="eval-dim-value">${val.toFixed(2)} / ${max}</span>
                </div>
            `;
        }).join('');
        if (dimSectionEl) {
            if (dimRows) {
                dimSectionEl.innerHTML = dimRows;
                dimSectionEl.style.display = '';
            } else {
                dimSectionEl.innerHTML = '';
                dimSectionEl.style.display = 'none';
            }
        }

        const tbody = DOM.$('#eval-results-tbody');
        if (tbody) {
            tbody.innerHTML = '';
            for (const r of results) {
                const tr = document.createElement('tr');
                tr.classList.add('eval-result-row');
                tr.onclick = () => this._showCaseResultDrawer(runId, r.case_id);
                const score = r.score == null ? '-' : r.score.toFixed(1);
                const scoreClass = this._scoreClass(r.score);
                const latency = r.latency_ms == null ? '-' : `${(r.latency_ms / 1000).toFixed(1)}s`;
                tr.innerHTML = `
                    <td><span class="eval-primary-text">${Utils.escapeHtml(r.case_title || r.case_id)}</span><div class="eval-secondary-text">${Utils.escapeHtml(r.case_id)}</div></td>
                    <td>${Utils.escapeHtml(r.case_category || '-')}</td>
                    <td>${this._renderStatus(r.status)}</td>
                    <td><span class="eval-score ${scoreClass}">${score}</span></td>
                    <td>${latency}</td>
                    <td>${r.total_tokens || '-'}</td>
                    <td><button class="btn btn-sm eval-inline-action">详情</button></td>
                `;
                tbody.appendChild(tr);
            }
        }
        DOM.createIcons();

        // auto-refresh while running
        this._stopPolling();
        if (this.activeRunId === runId && this.activeTab === 'runs' && (run.status === 'running' || run.status === 'pending')) {
            this.pollingTimer = setTimeout(() => this._showRunDetail(runId, { silent: true }), 4000);
        }
    },

    _stopPolling() {
        if (this.pollingTimer) {
            clearTimeout(this.pollingTimer);
            this.pollingTimer = null;
        }
        this.runDetailRefreshInFlight = false;
    },

    async _showCaseResultDrawer(runId, caseId) {
        let detail;
        try {
            detail = await API.getEvalRunResult(runId, caseId);
        } catch (err) {
            Toast.error(`加载详情失败: ${err.message}`);
            return;
        }
        const dims = (detail.dimension_scores || []).map(d => `
            <div class="eval-dim-bar">
                <span class="eval-dim-name">${Utils.escapeHtml(d.name)}</span>
                <span class="eval-dim-track"><span class="eval-dim-fill" style="width:${Math.round(d.score / d.max_score * 100)}%;"></span></span>
                <span class="eval-dim-value">${d.score.toFixed(2)} / ${d.max_score}</span>
            </div>
            <div class="eval-dim-detail">${Utils.escapeHtml(d.detail || '')}</div>
        `).join('');
        const judge = detail.judge_feedback || {};
        const tools = detail.tool_call_summary || {};
        const calls = (tools.called || []).map(c => {
            const args = JSON.stringify(c.args || {});
            return `<li>${c.matched ? '命中' : '未命中'} <code>${Utils.escapeHtml(c.tool)}</code> <span class="eval-secondary-text">${Utils.escapeHtml(args.slice(0, 120))}</span></li>`;
        }).join('');

        const body = document.createElement('div');
        body.innerHTML = `
            <h3 style="margin:0 0 8px 0;">${Utils.escapeHtml(detail.case_title || caseId)}</h3>
            <div style="color:var(--text-secondary); font-size:12px; margin-bottom:14px;">${Utils.escapeHtml(detail.case_id)} · ${Utils.escapeHtml(detail.case_category || '')}</div>

            <h4 style="margin:14px 0 6px;">评分明细</h4>
            ${dims}

            <h4 style="margin:14px 0 6px;">Judge 反馈</h4>
            ${judge.root_cause_feedback ? `<div class="eval-feedback-card"><strong>根因 (${(judge.root_cause_score || 0).toFixed(1)})：</strong> ${Utils.escapeHtml(judge.root_cause_feedback)}</div>` : ''}
            ${judge.action_feedback ? `<div class="eval-feedback-card"><strong>行动建议 (${(judge.action_score || 0).toFixed(1)})：</strong> ${Utils.escapeHtml(judge.action_feedback)}</div>` : ''}
            ${judge.error ? `<div class="eval-feedback-card eval-feedback-danger"><strong>Judge 错误：</strong> ${Utils.escapeHtml(judge.error)}</div>` : ''}

            <h4 style="margin:14px 0 6px;">工具调用</h4>
            <div style="font-size:13px; color:var(--text-secondary);">
                调用 ${(tools.called || []).length} 次工具，未命中 fixture ${tools.unmatched_count || 0} 次
                ${tools.missing_required && tools.missing_required.length ? `<br>缺失必需工具：<code>${Utils.escapeHtml(tools.missing_required.join(', '))}</code>` : ''}
                ${tools.forbidden_hits && tools.forbidden_hits.length ? `<br><span class="text-danger">触发禁用工具：<code>${Utils.escapeHtml(tools.forbidden_hits.join(', '))}</code></span>` : ''}
            </div>
            <ul style="font-size:12px; padding-left:20px; max-height:200px; overflow-y:auto;">${calls || '<li>无</li>'}</ul>

            <h4 style="margin:14px 0 6px;">AI 结论</h4>
            <div class="eval-conclusion-md">${Utils.escapeHtml(detail.conclusion_md || '(空)')}</div>

            ${detail.session_id ? `<div style="margin-top:14px;"><button class="btn btn-secondary" id="eval-replay-btn"><i data-lucide="messages-square"></i> 查看完整对话回放</button></div>` : ''}
            ${detail.error_message ? `<div class="eval-feedback-card eval-feedback-danger" style="margin-top:12px;"><strong>错误：</strong> ${Utils.escapeHtml(detail.error_message)}</div>` : ''}
        `;
        const replayBtn = body.querySelector('#eval-replay-btn');
        if (replayBtn) {
            replayBtn.onclick = () => this._showReplayModal(runId, caseId);
        }
        Modal.show({
            title: 'Case 详情',
            content: body,
            size: 'large',
            buttons: [{ text: '关闭', variant: 'secondary', onClick: () => Modal.hide() }],
        });
        DOM.createIcons();
    },

    async _showReplayModal(runId, caseId) {
        let replay;
        try {
            replay = await API.getEvalRunReplay(runId, caseId);
        } catch (err) {
            Toast.error(`加载回放失败: ${err.message}`);
            return;
        }

        const roleName = (role) => ({
            user: '用户',
            assistant: 'AI',
            tool_call: '工具调用',
            tool_result: '工具结果',
            system: '系统',
            approval_request: '审批请求',
            approval_response: '审批结果',
        }[role] || role || '消息');

        const messages = (replay.messages || []).map((message) => `
            <div class="eval-replay-message">
                <div class="eval-replay-message-head">
                    <span class="eval-replay-role">${Utils.escapeHtml(roleName(message.role))}</span>
                    <span>${this._fmtTime(message.created_at)}</span>
                </div>
                <div class="eval-replay-message-body">${Utils.escapeHtml(message.content || '')}</div>
            </div>
        `).join('');

        const body = document.createElement('div');
        body.innerHTML = `
            <div class="eval-replay-meta">
                <span>Run #${replay.run_id}</span>
                <span>${Utils.escapeHtml(replay.case_title || replay.case_id)}</span>
                <span>Session #${replay.session_id}</span>
                <span>Tokens ${replay.total_tokens || 0}</span>
            </div>
            <div class="eval-replay-list">
                ${messages || '<div class="eval-empty">暂无可回放消息。</div>'}
            </div>
        `;
        Modal.show({
            title: '完整对话回放',
            content: body,
            size: 'xlarge',
            buttons: [{ text: '关闭', variant: 'secondary', onClick: () => Modal.hide() }],
        });
    },

    // ---------------- Cases tab

    async _renderCasesTab() {
        const host = DOM.$('#eval-tab-content');
        host.innerHTML = '<div class="loading">加载 case 库...</div>';
        try {
            this.cases = await API.listEvalCases();
        } catch (err) {
            host.innerHTML = `<div class="eval-empty">加载失败：${Utils.escapeHtml(err.message)}</div>`;
            return;
        }
        if (!this.cases.length) {
            host.innerHTML = '<div class="eval-empty">未找到任何评测 case。</div>';
            return;
        }
        host.innerHTML = `
            <div class="eval-table-card">
                <table class="eval-table eval-case-table">
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>名称</th>
                            <th>类别</th>
                            <th>DB 类型</th>
                            <th>难度</th>
                            <th>必需工具</th>
                            <th>禁用工具</th>
                            <th>预期轮数</th>
                        </tr>
                    </thead>
                    <tbody id="eval-cases-tbody"></tbody>
                </table>
            </div>
        `;
        const tbody = DOM.$('#eval-cases-tbody');
        for (const c of this.cases) {
            const tr = document.createElement('tr');
            tr.onclick = () => this._showCaseDetail(c.id);
            tr.innerHTML = `
                <td><code class="eval-case-id">${Utils.escapeHtml(c.id)}</code></td>
                <td><span class="eval-primary-text">${Utils.escapeHtml(c.title)}</span></td>
                <td>${Utils.escapeHtml(c.category)}</td>
                <td>${Utils.escapeHtml(c.db_type)}</td>
                <td>${Utils.escapeHtml(c.difficulty)}</td>
                <td>${this._renderToolChips(c.required_tools)}</td>
                <td>${this._renderToolChips(c.forbidden_tools, { forbidden: true })}</td>
                <td>${c.min_tool_rounds}-${c.max_tool_rounds}</td>
            `;
            tbody.appendChild(tr);
        }
    },

    async _showCaseDetail(caseId) {
        let c;
        try {
            c = await API.getEvalCase(caseId);
        } catch (err) {
            Toast.error(err.message);
            return;
        }
        const fixturesHtml = (c.fixtures || []).map(f => {
            return `<div><strong>${Utils.escapeHtml(f.tool)}</strong> · args: <code>${Utils.escapeHtml(JSON.stringify(f.args))}</code><div class="eval-fixture-block">${Utils.escapeHtml(JSON.stringify(f.response, null, 2))}</div></div>`;
        }).join('<hr style="margin:10px 0; border:0; border-top:1px solid var(--border-color);">');

        const body = document.createElement('div');
        body.innerHTML = `
            <h3 style="margin:0 0 4px;">${Utils.escapeHtml(c.title)}</h3>
            <div style="color:var(--text-secondary); font-size:12px; margin-bottom:14px;">${Utils.escapeHtml(c.id)}</div>
            ${c.description ? `<p>${Utils.escapeHtml(c.description)}</p>` : ''}
            <h4>用户提问</h4>
            <div class="eval-conclusion-md">${Utils.escapeHtml(c.user_message)}</div>
            <h4>预期根因</h4>
            <ul>${(c.root_causes || []).map(x => `<li>${Utils.escapeHtml(x)}</li>`).join('')}</ul>
            <h4>必需工具</h4>
            ${this._renderToolChips(c.required_tools)}
            <h4>禁用工具</h4>
            ${this._renderToolChips(c.forbidden_tools, { forbidden: true })}
            <h4>工具固件</h4>
            ${fixturesHtml}
        `;
        Modal.show({
            title: 'Case 详情',
            content: body,
            size: 'large',
            buttons: [{ text: '关闭', variant: 'secondary', onClick: () => Modal.hide() }],
        });
    },

    // ---------------- Start run modal

    async _showStartRunModal() {
        try {
            [this.suites, this.aiModels] = await Promise.all([
                API.listEvalSuites(),
                API.getAIModels(),
            ]);
        } catch (err) {
            Toast.error(`加载失败：${err.message}`);
            return;
        }
        const suiteOptions = this.suites.map(s =>
            `<option value="${s.id}">${Utils.escapeHtml(s.name)} (${(s.case_ids || []).length} cases)</option>`
        ).join('');
        const modelOptions = this.aiModels.filter(m => m.is_active).map(m =>
            `<option value="${m.id}">${Utils.escapeHtml(m.name)} (${Utils.escapeHtml(m.model_name)})</option>`
        ).join('');

        const form = document.createElement('div');
        form.innerHTML = `
            <div class="form-group">
                <label>评测套件</label>
                <select id="eval-form-suite" class="form-input">${suiteOptions}</select>
            </div>
            <div class="form-group">
                <label>AI 诊断模型</label>
                <select id="eval-form-model" class="form-input">${modelOptions}</select>
            </div>
            <div class="form-group">
                <label>裁判模型 (可选，默认与诊断模型一致)</label>
                <select id="eval-form-judge" class="form-input">
                    <option value="">同诊断模型</option>
                    ${modelOptions}
                </select>
            </div>
            <div style="font-size:12px; color:var(--text-secondary);">评测启动后会异步执行，期间可在列表中看到实时进度。</div>
        `;
        Modal.show({
            title: '启动评测',
            content: form,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '启动', variant: 'primary', onClick: () => this._submitRun() },
            ],
        });
    },

    async _submitRun() {
        const suiteId = parseInt(DOM.$('#eval-form-suite').value, 10);
        const modelId = parseInt(DOM.$('#eval-form-model').value, 10);
        const judgeRaw = DOM.$('#eval-form-judge').value;
        const judgeId = judgeRaw ? parseInt(judgeRaw, 10) : null;
        if (!suiteId || !modelId) {
            Toast.error('请选择套件和 AI 模型');
            return;
        }
        try {
            const run = await API.createEvalRun({
                suite_id: suiteId,
                ai_model_id: modelId,
                judge_model_id: judgeId,
            });
            Modal.hide();
            Toast.success(`评测 #${run.id} 已启动`);
            this.activeTab = 'runs';
            this.render();
            setTimeout(() => this._showRunDetail(run.id), 500);
        } catch (err) {
            Toast.error(`启动失败：${err.message}`);
        }
    },

    async _deleteRun(run) {
        if (!run || !run.id) return;
        const activeHint = this._isRunActive(run) ? '该评测仍在运行，删除会先停止后台任务。' : '';
        if (!confirm(`确认删除评测记录 #${run.id} 吗？${activeHint}相关结果和隐藏回放也会一并删除，此操作不可撤销。`)) return;
        try {
            await API.deleteEvalRun(run.id);
            Toast.success(`评测 #${run.id} 已删除`);
            this._stopPolling();
            this.runDetailDigestByRunId[run.id] = undefined;
            this.runDetailMetaDigestByRunId[run.id] = undefined;
            this.runs = this.runs.filter(item => item.id !== run.id);
            if (this.activeRunId === run.id) {
                this.activeRunId = null;
                await this._renderRunsTab();
            } else {
                await this._renderRunsTab();
            }
        } catch (err) {
            Toast.error(`删除失败：${err.message}`);
        }
    },

    // ---------------- helpers

    _isRunActive(run) {
        return ['pending', 'running'].includes(String(run?.status || '').toLowerCase());
    },

    _scoreClass(score) {
        if (score == null) return '';
        if (score >= 80) return 'eval-score-high';
        if (score >= 60) return 'eval-score-mid';
        return 'eval-score-low';
    },

    _renderStatus(status) {
        const rawStatus = String(status || 'unknown');
        const statusClass = rawStatus.toLowerCase().replace(/[^a-z0-9_-]+/g, '-');
        return `<span class="eval-status eval-status-${statusClass}">${Utils.escapeHtml(rawStatus)}</span>`;
    },

    _renderToolChips(tools = [], options = {}) {
        if (!tools.length) {
            return '<span class="eval-tool-chip empty">-</span>';
        }
        const className = options.forbidden ? 'eval-tool-chip forbidden' : 'eval-tool-chip';
        return `
            <div class="eval-tool-list">
                ${tools.map(tool => `<span class="${className}">${Utils.escapeHtml(tool)}</span>`).join('')}
            </div>
        `;
    },

    _buildRunDetailDigest(run, results) {
        const compactResults = (results || []).map(item => [
            item.case_id,
            item.status,
            item.score == null ? null : Number(item.score),
            item.latency_ms == null ? null : Number(item.latency_ms),
            item.total_tokens == null ? null : Number(item.total_tokens),
        ]);
        return JSON.stringify({
            status: run.status || '',
            completed_cases: run.completed_cases || 0,
            total_cases: run.total_cases || 0,
            failed_cases: run.failed_cases || 0,
            total_score: run.total_score == null ? null : Number(run.total_score),
            suite_name: run.suite_name || '',
            ai_model_name: run.ai_model_name || '',
            dimension_summary: run.dimension_summary || {},
            results: compactResults,
        });
    },

    _buildRunMetaDigest(run) {
        return JSON.stringify({
            status: run.status || '',
            completed_cases: run.completed_cases || 0,
            total_cases: run.total_cases || 0,
            failed_cases: run.failed_cases || 0,
            total_score: run.total_score == null ? null : Number(run.total_score),
            suite_name: run.suite_name || '',
            ai_model_name: run.ai_model_name || '',
            dimension_summary: run.dimension_summary || {},
        });
    },

    _dimensionMax(name) {
        const map = {
            root_cause: 30,
            tool_selection: 20,
            action_quality: 15,
            structure: 10,
            evidence: 10,
            efficiency: 10,
            latency: 5,
        };
        return map[name] || 10;
    },

    _fmtTime(iso) {
        if (!iso) return '-';
        try { return new Date(iso).toLocaleString('zh-CN'); } catch (e) { return iso; }
    },

    _formatElapsed(start, end) {
        if (!start || !end) return '-';
        const ms = new Date(end).getTime() - new Date(start).getTime();
        if (ms < 1000) return `${ms}ms`;
        if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
        return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
    },
};
