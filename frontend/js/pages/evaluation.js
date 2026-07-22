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
        Header.render(I18n.t('pageCopy.evaluation.aiEvaluation'), this._buildHeaderActions());
        const content = DOM.$('#page-content');
        content.innerHTML = I18n.t('pageCopy.evaluation.runsCaseLibrary', { value0: this.activeTab === 'runs' ? 'active' : '', value1: this.activeTab === 'cases' ? 'active' : '' });
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
            innerHTML: I18n.t('pageCopy.evaluation.startEvaluation'),
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
        host.innerHTML = I18n.t('pageCopy.evaluation.loadingReviewRecords');
        try {
            this.runs = await API.listEvalRuns();
        } catch (err) {
            host.innerHTML = I18n.t('pageCopy.evaluation.loadingFailedValue', { value0: Utils.escapeHtml(err.message) });
            return;
        }
        if (!this.runs.length) {
            host.innerHTML = I18n.t('pageCopy.evaluation.noEvaluationRunsYetSelectStartEvaluation');
            return;
        }
        host.innerHTML = I18n.t('pageCopy.evaluation.idKitAiModelsStatusProgressTotal');
        const tbody = DOM.$('#eval-runs-tbody');
        for (const run of this.runs) {
            const tr = document.createElement('tr');
            tr.onclick = () => this._showRunDetail(run.id);
            const score = run.total_score == null ? '-' : run.total_score.toFixed(1);
            const scoreClass = this._scoreClass(run.total_score);
            const elapsed = this._formatElapsed(run.started_at, run.finished_at);
            const deletingTitle = this._isRunActive(run) ? I18n.t('pageCopy.evaluation.stopAndDeleteReviewHistory') : I18n.t('pageCopy.evaluation.deleteReviewRecord');
            tr.innerHTML = `
                <td><span class="eval-mono">#${run.id}</span></td>
                <td><span class="eval-primary-text">${Utils.escapeHtml(run.suite_name || '-')}</span></td>
                <td>${Utils.escapeHtml(run.ai_model_name || '-')}</td>
                <td>${this._renderStatus(run.status)}</td>
                <td>${run.completed_cases}/${run.total_cases} ${run.failed_cases ? I18n.t('pageCopy.evaluation.failedValue', { value0: run.failed_cases }) : ''}</td>
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
            host.innerHTML = I18n.t('pageCopy.evaluation.loadingDetails');
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
                host.innerHTML = I18n.t('pageCopy.evaluation.loadingFailedValue', { value0: Utils.escapeHtml(err.message) });
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
            host.innerHTML = I18n.t('pageCopy.evaluation.returnToReviewListTotalScore100');
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
        if (progressEl) progressEl.textContent = `${run.completed_cases}/${run.total_cases}${run.failed_cases ? I18n.t('pageCopy.evaluation.failedValue2', { value0: run.failed_cases }) : ''}`;
        if (deleteBtnEl) {
            deleteBtnEl.disabled = false;
            deleteBtnEl.title = this._isRunActive(run) ? I18n.t('pageCopy.evaluation.stopAndDeleteTheCurrentReviewRecord') : I18n.t('pageCopy.evaluation.deleteCurrentReviewRecord');
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
                tr.innerHTML = I18n.t('pageCopy.evaluation.evaluationRow', { value0: Utils.escapeHtml(r.case_title || r.case_id), value1: Utils.escapeHtml(r.case_id), value2: Utils.escapeHtml(r.case_category || '-'), value3: this._renderStatus(r.status), value4: scoreClass, value5: score, value6: latency, value7: r.total_tokens || '-' });
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
            Toast.error(err.message || I18n.t('common.requestFailed'));
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
            return `<li>${c.matched ? I18n.t('pageCopy.evaluation.hitLabel') : I18n.t('pageCopy.evaluation.missLabel')} <code>${Utils.escapeHtml(c.tool)}</code> <span class="eval-secondary-text">${Utils.escapeHtml(args.slice(0, 120))}</span></li>`;
        }).join('');

        const body = document.createElement('div');
        body.innerHTML = I18n.t('pageCopy.evaluation.evaluationDetails', { value0: Utils.escapeHtml(detail.case_title || caseId), value1: Utils.escapeHtml(detail.case_id), value2: Utils.escapeHtml(detail.case_category || ''), value3: dims, value4: judge.root_cause_feedback ? I18n.t('pageCopy.evaluation.rootCauseLabel', { value0: (judge.root_cause_score || 0).toFixed(1), value1: Utils.escapeHtml(judge.root_cause_feedback) }) : '', value5: judge.action_feedback ? I18n.t('pageCopy.evaluation.recommendedActionsLabel', { value0: (judge.action_score || 0).toFixed(1), value1: Utils.escapeHtml(judge.action_feedback) }) : '', value6: judge.error ? I18n.t('pageCopy.evaluation.judgeErrorValue', { value0: Utils.escapeHtml(judge.error) }) : '', value7: (tools.called || []).length, value8: tools.unmatched_count || 0, value9: tools.missing_required && tools.missing_required.length ? I18n.t('pageCopy.evaluation.requiredToolsValue', { value0: Utils.escapeHtml(tools.missing_required.join(', ')) }) : '', value10: tools.forbidden_hits && tools.forbidden_hits.length ? I18n.t('pageCopy.evaluation.triggerdisabledToolsValue', { value0: Utils.escapeHtml(tools.forbidden_hits.join(', ')) }) : '', value11: calls || I18n.t('pageCopy.evaluation.noneLabel'), value12: Utils.escapeHtml(detail.conclusion_md || I18n.t('pageCopy.evaluation.emptyLabel')), value13: detail.session_id ? I18n.t('pageCopy.evaluation.viewfullConversationReplay') : '', value14: detail.error_message ? I18n.t('pageCopy.evaluation.errorValue', { value0: Utils.escapeHtml(detail.error_message) }) : '' });
        const replayBtn = body.querySelector('#eval-replay-btn');
        if (replayBtn) {
            replayBtn.onclick = () => this._showReplayModal(runId, caseId);
        }
        Modal.show({
            title: I18n.t('pageCopy.evaluation.caseDetails'),
            content: body,
            size: 'large',
            buttons: [{ text: I18n.t('pageCopy.evaluation.close'), variant: 'secondary', onClick: () => Modal.hide() }],
        });
        DOM.createIcons();
    },

    async _showReplayModal(runId, caseId) {
        let replay;
        try {
            replay = await API.getEvalRunReplay(runId, caseId);
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
            return;
        }

        const roleName = (role) => ({
            user: I18n.t('pageCopy.evaluation.user'),
            assistant: 'AI',
            tool_call: I18n.t('pageCopy.evaluation.toolCall'),
            tool_result: I18n.t('pageCopy.evaluation.toolResults'),
            system: I18n.t('pageCopy.evaluation.system'),
            approval_request: I18n.t('pageCopy.evaluation.approvalRequest'),
            approval_response: I18n.t('pageCopy.evaluation.approvalResults'),
        }[role] || role || I18n.t('pageCopy.evaluation.news'));

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
                ${messages || I18n.t('pageCopy.evaluation.noneYetNews')}
            </div>
        `;
        Modal.show({
            title: I18n.t('pageCopy.evaluation.fullConversationReplay'),
            content: body,
            size: 'xlarge',
            buttons: [{ text: I18n.t('pageCopy.evaluation.close'), variant: 'secondary', onClick: () => Modal.hide() }],
        });
    },

    // ---------------- Cases tab

    async _renderCasesTab() {
        const host = DOM.$('#eval-tab-content');
        host.innerHTML = I18n.t('pageCopy.evaluation.loadCaseLibrary');
        try {
            this.cases = await API.listEvalCases();
        } catch (err) {
            host.innerHTML = I18n.t('pageCopy.evaluation.loadingFailedValue', { value0: Utils.escapeHtml(err.message) });
            return;
        }
        if (!this.cases.length) {
            host.innerHTML = I18n.t('pageCopy.evaluation.noReviewCasesFound');
            return;
        }
        host.innerHTML = I18n.t('pageCopy.evaluation.idNameCategoryDbTypeDifficultyRequired');
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
        body.innerHTML = I18n.t('pageCopy.evaluation.caseFixture', { value0: Utils.escapeHtml(c.title), value1: Utils.escapeHtml(c.id), value2: c.description ? `<p>${Utils.escapeHtml(c.description)}</p>` : '', value3: Utils.escapeHtml(c.user_message), value4: (c.root_causes || []).map(x => `<li>${Utils.escapeHtml(x)}</li>`).join(''), value5: this._renderToolChips(c.required_tools), value6: this._renderToolChips(c.forbidden_tools, { forbidden: true }), value7: fixturesHtml });
        Modal.show({
            title: I18n.t('pageCopy.evaluation.caseDetails'),
            content: body,
            size: 'large',
            buttons: [{ text: I18n.t('pageCopy.evaluation.close'), variant: 'secondary', onClick: () => Modal.hide() }],
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
            Toast.error(err.message || I18n.t('common.requestFailed'));
            return;
        }
        const suiteOptions = this.suites.map(s =>
            `<option value="${s.id}">${Utils.escapeHtml(s.name)} (${(s.case_ids || []).length} cases)</option>`
        ).join('');
        const modelOptions = this.aiModels.filter(m => m.is_active).map(m =>
            `<option value="${m.id}">${Utils.escapeHtml(m.name)} (${Utils.escapeHtml(m.model_name)})</option>`
        ).join('');

        const form = document.createElement('div');
        form.innerHTML = I18n.t('pageCopy.evaluation.evaluationKitValueAiDiagnosticModelValue', { value0: suiteOptions, value1: modelOptions, value2: modelOptions });
        Modal.show({
            title: I18n.t('pageCopy.evaluation.startEvaluation2'),
            content: form,
            buttons: [
                { text: I18n.t('pageCopy.evaluation.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('pageCopy.evaluation.start'), variant: 'primary', onClick: () => this._submitRun() },
            ],
        });
    },

    async _submitRun() {
        const suiteId = parseInt(DOM.$('#eval-form-suite').value, 10);
        const modelId = parseInt(DOM.$('#eval-form-model').value, 10);
        const judgeRaw = DOM.$('#eval-form-judge').value;
        const judgeId = judgeRaw ? parseInt(judgeRaw, 10) : null;
        if (!suiteId || !modelId) {
            Toast.error(I18n.t('pageCopy.evaluation.suiteAndModelRequired'));
            return;
        }
        try {
            const run = await API.createEvalRun({
                suite_id: suiteId,
                ai_model_id: modelId,
                judge_model_id: judgeId,
            });
            Modal.hide();
            Toast.success(I18n.t('pageCopy.evaluation.reviewValueStarted', { value0: run.id }));
            this.activeTab = 'runs';
            this.render();
            setTimeout(() => this._showRunDetail(run.id), 500);
        } catch (err) {
            Toast.error(err.message || I18n.t('common.requestFailed'));
        }
    },

    async _deleteRun(run) {
        if (!run || !run.id) return;
        const activeHint = this._isRunActive(run) ? I18n.t('pageCopy.evaluation.theReviewIsStillRunningDeletingIt') : '';
        if (!confirm(I18n.t('pageCopy.evaluation.confirmDeletionOfReviewRecordValueValue', { value0: run.id, value1: activeHint }))) return;
        try {
            await API.deleteEvalRun(run.id);
            Toast.success(I18n.t('pageCopy.evaluation.reviewValueDeleted', { value0: run.id }));
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
            Toast.error(err.message || I18n.t('common.requestFailed'));
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
        try { return I18n.formatDate(iso, { dateStyle: 'medium', timeStyle: 'medium' }); } catch (e) { return iso; }
    },

    _formatElapsed(start, end) {
        if (!start || !end) return '-';
        const ms = new Date(end).getTime() - new Date(start).getTime();
        if (ms < 1000) return `${ms}ms`;
        if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
        return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
    },
};
