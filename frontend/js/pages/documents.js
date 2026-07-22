/* Documents page - 知识库文档管理 */
const DocumentsPage = {
    currentCategory: null,
    currentDoc: null,
    monacoEditor: null,
    mdRenderer: null,
    viewMode: 'split', // 'split' | 'edit' | 'preview'

    async render() {
        const content = DOM.$('#page-content');
        Header.render(I18n.t('pageCopy.documents.knowledgeBaseDocuments'));
        content.innerHTML = I18n.t('pageCopy.documents.selectADocumentToViewItsContent');
        DOM.createIcons();
        this.mdRenderer = window.markdownit ? window.markdownit() : null;
        await this.loadCategories();
        return () => {
            if (this.monacoEditor) {
                this.monacoEditor.dispose();
                this.monacoEditor = null;
            }
        };
    },

    async loadCategories() {
        try {
            const categories = await API.getDocCategories();
            const container = DOM.$('#docs-categories');
            if (!container) return;
            container.innerHTML = I18n.t('pageCopy.documents.category');
            categories.forEach((root, i) => {
                const rootEl = document.createElement('div');
                rootEl.className = 'docs-cat-root';
                rootEl.innerHTML = `
                    <div class="docs-cat-root-name" data-idx="${i}">
                        <i data-lucide="database"></i>
                        <span>${Utils.escapeHtml(root.name)}</span>
                        <i data-lucide="chevron-down" class="chevron"></i>
                    </div>
                    <div class="docs-cat-children" id="cat-children-${i}">
                        ${(root.children || []).map(ch => `
                            <div class="docs-cat-child" data-cat-id="${ch.id}" data-cat-name="${Utils.escapeHtml(ch.name)}">
                                <span>${Utils.escapeHtml(ch.name)}</span>
                                <span class="docs-cat-count">${ch.document_count}</span>
                            </div>
                        `).join('')}
                    </div>
                `;
                container.appendChild(rootEl);

                rootEl.querySelector('.docs-cat-root-name').addEventListener('click', () => {
                    const children = rootEl.querySelector('.docs-cat-children');
                    children.classList.toggle('hidden');
                });

                rootEl.querySelectorAll('.docs-cat-child').forEach(el => {
                    el.addEventListener('click', () => this.selectCategory(el));
                });
            });
            DOM.createIcons();
        } catch (e) {
            Utils.showToast(I18n.t('pageCopy.documents.failedToLoadCategories') + e.message, 'error');
        }
    },

    async selectCategory(el) {
        DOM.$$('.docs-cat-child').forEach(e => e.classList.remove('active'));
        el.classList.add('active');
        this.currentCategory = { id: +el.dataset.catId, name: el.dataset.catName };
        await this.loadDocList(this.currentCategory.id);
    },

    async loadDocList(categoryId) {
        const container = DOM.$('#docs-list');
        if (!container) return;
        container.innerHTML = I18n.t('pageCopy.documents.loading');
        try {
            const docs = await API.getCategoryDocuments(categoryId);
            container.innerHTML = `
                <div class="docs-list-header">
                    <span>${Utils.escapeHtml(this.currentCategory?.name || '')}</span>
                    <button class="btn btn-sm btn-primary" onclick="DocumentsPage.newDocument()">
                        <i data-lucide="plus"></i>
                    </button>
                </div>
            `;
            if (docs.length === 0) {
                container.innerHTML += I18n.t('pageCopy.documents.noDocumentYet');
            } else {
                docs.forEach(doc => {
                    const el = document.createElement('div');
                    el.className = 'docs-list-item';
                    el.dataset.docId = doc.id;
                    const warningCount = Array.isArray(doc.compile_warnings) ? doc.compile_warnings.length : 0;
                    el.innerHTML = I18n.t('pageCopy.documents.documentListItem', { value0: doc.is_builtin ? '<i data-lucide="lock" class="builtin-icon"></i>' : '', value1: Utils.escapeHtml(doc.title), value2: Utils.escapeHtml(doc.quality_status || 'draft'), value3: Utils.escapeHtml(this.getQualityStatusLabel(doc.quality_status)), value4: Utils.escapeHtml(doc.summary || ''), value5: Utils.escapeHtml(doc.doc_kind || 'reference'), value6: doc.compiled_snapshot_summary?.unit_count || 0, value7: warningCount });
                    el.addEventListener('click', () => this.openDocument(doc.id, el));
                    container.appendChild(el);
                });
            }
            DOM.createIcons();
        } catch (e) {
            Utils.showToast(I18n.t('pageCopy.documents.failedToLoadDocumentList') + e.message, 'error');
        }
    },

    async openDocument(docId, listEl) {
        DOM.$$('.docs-list-item').forEach(e => e.classList.remove('active'));
        if (listEl) listEl.classList.add('active');
        try {
            const doc = await API.getDocument(docId);
            this.currentDoc = doc;
            this.renderEditor(doc);
        } catch (e) {
            Utils.showToast(I18n.t('pageCopy.documents.failedToLoadDocument') + e.message, 'error');
        }
    },

    renderEditor(doc) {
        const panel = DOM.$('#docs-editor-panel');
        if (!panel) return;
        const diagnosisProfile = this.getDiagnosisProfile(doc);
        const compileWarnings = doc.compile_warnings || [];
        const summary = doc.compiled_snapshot_summary || {};
        panel.innerHTML = I18n.t('pageCopy.documents.documentEditor', { value0: Utils.escapeHtml(doc.title), value1: Utils.escapeHtml(doc.title), value2: Utils.escapeHtml(doc.quality_status || 'draft'), value3: Utils.escapeHtml(this.getQualityStatusLabel(doc.quality_status)), value4: doc.id, value5: !doc.is_builtin ? I18n.t('pageCopy.documents.delete', { value0: doc.id }) : '', value6: Utils.escapeHtml(doc.title), value7: ['reference', 'runbook', 'sop', 'known_issue', 'case'].map(kind => `
                                    <option value="${kind}" ${doc.doc_kind === kind ? 'selected' : ''}>${kind}</option>
                                `).join(''), value8: Utils.escapeHtml((doc.issue_categories || []).join(', ')), value9: Utils.escapeHtml((diagnosisProfile.symptom_tags || []).join(', ')), value10: I18n.t('placeholders.symptomTags'), value11: Utils.escapeHtml((diagnosisProfile.signal_tags || []).join(', ')), value12: Utils.escapeHtml((diagnosisProfile.recommended_skills || []).join(', ')), value13: Utils.escapeHtml((diagnosisProfile.related_doc_ids || []).join(', ')), value14: Number(doc.priority || 0), value15: ['stable', 'needs_review', 'expired'].map(level => `
                                        <option value="${level}" ${doc.freshness_level === level ? 'selected' : ''}>${level}</option>
                                    `).join(''), value16: doc.enabled_in_diagnosis !== false ? 'checked' : '', value17: Utils.escapeHtml(this.getQualityStatusLabel(doc.quality_status)), value18: summary.unit_count || 0, value19: summary.skill_count || 0, value20: summary.warning_count || 0, value21: Object.entries(summary.unit_type_counts || {}).map(([key, value]) => `
                                <span class="docs-unit-type-chip">${Utils.escapeHtml(key)}: ${value}</span>
                            `).join('') || I18n.t('pageCopy.documents.noKnowledgeUnits'), value22: compileWarnings.length ? compileWarnings.map(item => `
                                <div class="docs-warning-item">${Utils.escapeHtml(item)}</div>
                            `).join('') : I18n.t('pageCopy.documents.noCompilationAlerts'), value23: doc.compiled_at ? I18n.formatDate(doc.compiled_at, { dateStyle: 'medium', timeStyle: 'medium' }) : I18n.t('pageCopy.documents.notCompiled') });
        this.initMonaco(doc.content);
        this.setViewMode(this.viewMode);
    },

    getDiagnosisProfile(doc = {}) {
        return {
            symptom_tags: doc?.diagnosis_profile?.symptom_tags || [],
            signal_tags: doc?.diagnosis_profile?.signal_tags || [],
            recommended_skills: doc?.diagnosis_profile?.recommended_skills || [],
            applicability_rules: doc?.diagnosis_profile?.applicability_rules || [],
            evidence_requirements: doc?.diagnosis_profile?.evidence_requirements || [],
            related_doc_ids: doc?.diagnosis_profile?.related_doc_ids || [],
        };
    },

    getQualityStatusLabel(status) {
        const labels = {
            ready: I18n.t('pageCopy.documents.ready'),
            warning: I18n.t('pageCopy.documents.needsMoreContent'),
            expired: I18n.t('pageCopy.documents.expired'),
            draft: I18n.t('pageCopy.documents.pendingCompilation'),
        };
        return labels[status] || I18n.t('pageCopy.documents.pendingCompilation');
    },

    parseTagInput(value) {
        return String(value || '')
            .split(/[\n,，]/)
            .map(item => item.trim())
            .filter(Boolean);
    },

    parseIntegerInput(value) {
        return this.parseTagInput(value)
            .map(item => Number(item))
            .filter(item => Number.isInteger(item));
    },

    readDocumentForm() {
        const title = document.getElementById('doc-title')?.value?.trim() || this.currentDoc?.title || '';
        const docKind = document.getElementById('doc-kind')?.value || this.currentDoc?.doc_kind || 'reference';
        const issueCategories = this.parseTagInput(document.getElementById('doc-issue-categories')?.value);
        const diagnosisProfile = {
            ...this.getDiagnosisProfile(this.currentDoc),
            symptom_tags: this.parseTagInput(document.getElementById('doc-symptom-tags')?.value),
            signal_tags: this.parseTagInput(document.getElementById('doc-signal-tags')?.value),
            recommended_skills: this.parseTagInput(document.getElementById('doc-recommended-skills')?.value),
            related_doc_ids: this.parseIntegerInput(document.getElementById('doc-related-doc-ids')?.value),
        };
        const priorityValue = Number(document.getElementById('doc-priority')?.value);
        return {
            title,
            doc_kind: docKind,
            issue_categories: issueCategories,
            priority: Number.isFinite(priorityValue) ? priorityValue : 0,
            freshness_level: document.getElementById('doc-freshness')?.value || 'stable',
            enabled_in_diagnosis: Boolean(document.getElementById('doc-enabled-in-diagnosis')?.checked),
            diagnosis_profile: diagnosisProfile,
        };
    },

    initMonaco(content) {
        if (this.monacoEditor) {
            this.monacoEditor.dispose();
            this.monacoEditor = null;
        }
        const monacoConfig = { paths: { vs: '/lib/monaco-editor/min/vs' } };
        if (I18n.getLocale() === 'zh-CN') {
            monacoConfig['vs/nls'] = { availableLanguages: { '*': 'zh-cn' } };
        }
        if (window.DBCLAW_ASSET_VERSION) {
            monacoConfig.urlArgs = `build=${window.DBCLAW_ASSET_VERSION}`;
        }
        require.config(monacoConfig);
        require(['vs/editor/editor.main'], () => {
            const container = DOM.$('#docs-monaco');
            if (!container) return;
            const isDark = document.documentElement.getAttribute('data-theme') === 'dark' ||
                           document.body.classList.contains('dark');
            this.monacoEditor = monaco.editor.create(container, {
                value: content,
                language: 'markdown',
                theme: isDark ? 'vs-dark' : 'vs',
                wordWrap: 'on',
                minimap: { enabled: false },
                lineNumbers: 'off',
                fontSize: 14,
                scrollBeyondLastLine: false,
                automaticLayout: true,
            });
            this.monacoEditor.onDidChangeModelContent(() => {
                DirtyState.mark('page');
                this.updatePreview();
            });
            this.updatePreview();
        });
    },

    updatePreview() {
        const preview = DOM.$('#docs-preview');
        if (!preview || !this.monacoEditor) return;
        const md = this.monacoEditor.getValue();
        if (this.mdRenderer) {
            preview.innerHTML = this.mdRenderer.render(md);
        } else {
            preview.innerHTML = `<pre style="white-space:pre-wrap">${Utils.escapeHtml(md)}</pre>`;
        }
    },

    setViewMode(mode) {
        this.viewMode = mode;
        const monacoEl = DOM.$('#docs-monaco');
        const previewEl = DOM.$('#docs-preview');
        if (!monacoEl || !previewEl) return;
        if (mode === 'edit') {
            monacoEl.style.cssText = 'display:flex;width:100%;flex:1;';
            previewEl.style.cssText = 'display:none;';
        } else if (mode === 'preview') {
            monacoEl.style.cssText = 'display:none;';
            previewEl.style.cssText = 'display:block;width:100%;flex:1;';
            this.updatePreview();
        } else {
            monacoEl.style.cssText = 'display:flex;width:50%;';
            previewEl.style.cssText = 'display:block;width:50%;';
            this.updatePreview();
        }
        if (this.monacoEditor) this.monacoEditor.layout();
    },

    async saveDocument() {
        Utils.showToast(I18n.t('pageCopy.documents.notAvailableInThisVersion'), 'warning');
    },

    async recompileCurrentDocument() {
        if (!this.currentDoc?.id) return;
        try {
            const doc = await API.recompileDocument(this.currentDoc.id);
            this.currentDoc = doc;
            this.renderEditor(doc);
            Utils.showToast(I18n.t('pageCopy.documents.recompilationCompleted'), 'success');
            if (this.currentCategory) await this.loadDocList(this.currentCategory.id);
        } catch (e) {
            Utils.showToast(I18n.t('pageCopy.documents.recompilationFailed') + e.message, 'error');
        }
    },

    async exportDocument(docId) {
        try {
            await API.exportDocument(docId);
        } catch (error) {
            Utils.showToast(I18n.t('pageCopy.documents.exportFailedValue', { value0: error.message }), 'error');
        }
    },

    async deleteDocument(docId) {
        if (!confirm(I18n.t('pageCopy.documents.confirmToDeleteThisDocumentThisOperation'))) return;
        try {
            await API.deleteDocument(docId);
            Utils.showToast(I18n.t('pageCopy.documents.documentDeleted'), 'success');
            const panel = DOM.$('#docs-editor-panel');
            if (panel) panel.innerHTML = I18n.t('pageCopy.documents.selectADocument');
            this.currentDoc = null;
            if (this.currentCategory) await this.loadDocList(this.currentCategory.id);
        } catch (e) {
            Utils.showToast(I18n.t('pageCopy.documents.deleteFailed') + e.message, 'error');
        }
    },

    async newDocument() {
        if (!this.currentCategory) {
            Utils.showToast(I18n.t('pageCopy.documents.selectACategoryFirst'), 'warning');
            return;
        }
        Modal.show({
            title: I18n.t('pageCopy.documents.newDocument'),
            content: I18n.t("pageCopy.documents.newDocumentContent", { value0: I18n.t('placeholders.documentTitle') }),
            buttons: [
                { text: I18n.t('pageCopy.documents.cancel'), variant: 'secondary', onClick: () => Modal.hide() },
                { text: I18n.t('pageCopy.documents.create'), variant: 'primary', onClick: async () => {
                    const titleEl = document.getElementById('new-doc-title');
                    const title = titleEl ? titleEl.value.trim() : '';
                    if (!title) { Utils.showToast(I18n.t('pageCopy.documents.enterATitle'), 'warning'); return; }
                    try {
                        const doc = await API.createDocument({
                            category_id: this.currentCategory.id,
                            title,
                            content: `# ${title}\n\n`,
                        });
                        Modal.hide();
                        await this.loadDocList(this.currentCategory.id);
                        const newEl = document.querySelector(`.docs-list-item[data-doc-id="${doc.id}"]`);
                        await this.openDocument(doc.id, newEl);
                    } catch (e) {
                        Utils.showToast(I18n.t('pageCopy.documents.createFailed') + e.message, 'error');
                    }
                }}
            ]
        });
    },
};
