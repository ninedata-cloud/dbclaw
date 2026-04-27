/* Documents page - 知识库文档管理 */
const DocumentsPage = {
    currentCategory: null,
    currentDoc: null,
    monacoEditor: null,
    mdRenderer: null,
    viewMode: 'split', // 'split' | 'edit' | 'preview'

    async render() {
        const content = DOM.$('#page-content');
        Header.render('知识库文档');
        content.innerHTML = `
            <div class="docs-layout">
                <div class="docs-sidebar" id="docs-categories"></div>
                <div class="docs-list" id="docs-list"></div>
                <div class="docs-editor" id="docs-editor-panel">
                    <div class="docs-editor-placeholder">
                        <i data-lucide="file-text" style="width:48px;height:48px"></i>
                        <p>选择文档，查看正文、诊断属性和编译状态</p>
                    </div>
                </div>
            </div>
        `;
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
            container.innerHTML = `<div class="docs-cat-header">分类</div>`;
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
            Utils.showToast('加载分类失败: ' + e.message, 'error');
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
        container.innerHTML = '<div style="padding:12px;color:var(--text-muted)">加载中...</div>';
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
                container.innerHTML += '<div style="padding:20px;text-align:center;color:var(--text-muted)">暂无文档</div>';
            } else {
                docs.forEach(doc => {
                    const el = document.createElement('div');
                    el.className = 'docs-list-item';
                    el.dataset.docId = doc.id;
                    const warningCount = Array.isArray(doc.compile_warnings) ? doc.compile_warnings.length : 0;
                    el.innerHTML = `
                        <div class="docs-list-item-header">
                            <div class="docs-list-item-title">
                                ${doc.is_builtin ? '<i data-lucide="lock" class="builtin-icon"></i>' : ''}
                                ${Utils.escapeHtml(doc.title)}
                            </div>
                            <span class="docs-status-badge docs-status-${Utils.escapeHtml(doc.quality_status || 'draft')}">${Utils.escapeHtml(this.getQualityStatusLabel(doc.quality_status))}</span>
                        </div>
                        <div class="docs-list-item-summary">${Utils.escapeHtml(doc.summary || '')}</div>
                        <div class="docs-list-item-meta">
                            <span>${Utils.escapeHtml(doc.doc_kind || 'reference')}</span>
                            <span>单元 ${doc.compiled_snapshot_summary?.unit_count || 0}</span>
                            <span>告警 ${warningCount}</span>
                        </div>
                    `;
                    el.addEventListener('click', () => this.openDocument(doc.id, el));
                    container.appendChild(el);
                });
            }
            DOM.createIcons();
        } catch (e) {
            Utils.showToast('加载文档列表失败: ' + e.message, 'error');
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
            Utils.showToast('加载文档失败: ' + e.message, 'error');
        }
    },

    renderEditor(doc) {
        const panel = DOM.$('#docs-editor-panel');
        if (!panel) return;
        const diagnosisProfile = this.getDiagnosisProfile(doc);
        const compileWarnings = doc.compile_warnings || [];
        const summary = doc.compiled_snapshot_summary || {};
        panel.innerHTML = `
            <div class="docs-editor-toolbar">
                <div class="docs-editor-toolbar-main">
                    <span class="docs-editor-title" title="${Utils.escapeHtml(doc.title)}">${Utils.escapeHtml(doc.title)}</span>
                    <span class="docs-status-badge docs-status-${Utils.escapeHtml(doc.quality_status || 'draft')}">${Utils.escapeHtml(this.getQualityStatusLabel(doc.quality_status))}</span>
                </div>
                <div class="docs-editor-actions">
                    <button class="btn btn-sm" onclick="DocumentsPage.setViewMode('edit')">编辑</button>
                    <button class="btn btn-sm" onclick="DocumentsPage.setViewMode('split')">分栏</button>
                    <button class="btn btn-sm" onclick="DocumentsPage.setViewMode('preview')">预览</button>
                    <button class="btn btn-sm" onclick="DocumentsPage.recompileCurrentDocument()">重新编译</button>
                    <button class="btn btn-sm btn-primary" onclick="DocumentsPage.saveDocument()">保存</button>
                    <button class="btn btn-sm" onclick="DocumentsPage.exportDocument(${doc.id})">导出</button>
                    ${!doc.is_builtin ? `<button class="btn btn-sm btn-danger" onclick="DocumentsPage.deleteDocument(${doc.id})">删除</button>` : ''}
                </div>
            </div>
            <div class="docs-editor-body docs-editor-body-enhanced" id="docs-editor-body">
                <div class="docs-editor-main">
                    <div class="docs-editor-main-body">
                        <div class="docs-monaco-container" id="docs-monaco"></div>
                        <div class="docs-preview-container" id="docs-preview"></div>
                    </div>
                </div>
                <aside class="docs-profile-panel">
                    <div class="docs-profile-section">
                        <div class="docs-profile-section-title">诊断属性</div>
                        <label class="docs-form-field">
                            <span>文档标题</span>
                            <input type="text" id="doc-title" class="form-control" value="${Utils.escapeHtml(doc.title)}">
                        </label>
                        <label class="docs-form-field">
                            <span>文档类型</span>
                            <select id="doc-kind" class="form-select">
                                ${['reference', 'runbook', 'sop', 'known_issue', 'case'].map(kind => `
                                    <option value="${kind}" ${doc.doc_kind === kind ? 'selected' : ''}>${kind}</option>
                                `).join('')}
                            </select>
                        </label>
                        <label class="docs-form-field">
                            <span>问题标签</span>
                            <input type="text" id="doc-issue-categories" class="form-control" value="${Utils.escapeHtml((doc.issue_categories || []).join(', '))}" placeholder="performance, connectivity">
                        </label>
                        <label class="docs-form-field">
                            <span>症状标签</span>
                            <input type="text" id="doc-symptom-tags" class="form-control" value="${Utils.escapeHtml((diagnosisProfile.symptom_tags || []).join(', '))}" placeholder="连接失败, cpu高">
                        </label>
                        <label class="docs-form-field">
                            <span>信号标签</span>
                            <input type="text" id="doc-signal-tags" class="form-control" value="${Utils.escapeHtml((diagnosisProfile.signal_tags || []).join(', '))}" placeholder="iowait, slow_queries">
                        </label>
                        <label class="docs-form-field">
                            <span>推荐技能</span>
                            <textarea id="doc-recommended-skills" class="form-control" rows="3" placeholder="mysql_get_db_status, mysql_get_slow_queries">${Utils.escapeHtml((diagnosisProfile.recommended_skills || []).join(', '))}</textarea>
                        </label>
                        <label class="docs-form-field">
                            <span>关联文档 ID</span>
                            <input type="text" id="doc-related-doc-ids" class="form-control" value="${Utils.escapeHtml((diagnosisProfile.related_doc_ids || []).join(', '))}" placeholder="12, 18">
                        </label>
                        <div class="docs-form-grid">
                            <label class="docs-form-field">
                                <span>优先级</span>
                                <input type="number" id="doc-priority" class="form-control" value="${Number(doc.priority || 0)}" min="0" max="10">
                            </label>
                            <label class="docs-form-field">
                                <span>新鲜度</span>
                                <select id="doc-freshness" class="form-select">
                                    ${['stable', 'needs_review', 'expired'].map(level => `
                                        <option value="${level}" ${doc.freshness_level === level ? 'selected' : ''}>${level}</option>
                                    `).join('')}
                                </select>
                            </label>
                        </div>
                        <label class="docs-form-checkbox">
                            <input type="checkbox" id="doc-enabled-in-diagnosis" ${doc.enabled_in_diagnosis !== false ? 'checked' : ''}>
                            <span>参与 AI 诊断</span>
                        </label>
                    </div>
                    <div class="docs-profile-section">
                        <div class="docs-profile-section-title">编译状态</div>
                        <div class="docs-compile-summary">
                            <div class="docs-compile-stat">
                                <span>质量状态</span>
                                <strong>${Utils.escapeHtml(this.getQualityStatusLabel(doc.quality_status))}</strong>
                            </div>
                            <div class="docs-compile-stat">
                                <span>知识单元</span>
                                <strong>${summary.unit_count || 0}</strong>
                            </div>
                            <div class="docs-compile-stat">
                                <span>识别技能</span>
                                <strong>${summary.skill_count || 0}</strong>
                            </div>
                            <div class="docs-compile-stat">
                                <span>告警数量</span>
                                <strong>${summary.warning_count || 0}</strong>
                            </div>
                        </div>
                        <div class="docs-unit-type-list">
                            ${Object.entries(summary.unit_type_counts || {}).map(([key, value]) => `
                                <span class="docs-unit-type-chip">${Utils.escapeHtml(key)}: ${value}</span>
                            `).join('') || '<span class="docs-empty-hint">暂无知识单元</span>'}
                        </div>
                        <div class="docs-warning-list">
                            ${compileWarnings.length ? compileWarnings.map(item => `
                                <div class="docs-warning-item">${Utils.escapeHtml(item)}</div>
                            `).join('') : '<div class="docs-empty-hint">当前没有编译告警</div>'}
                        </div>
                        <div class="docs-compile-time">最近编译：${doc.compiled_at ? new Date(doc.compiled_at).toLocaleString('zh-CN') : '未编译'}</div>
                    </div>
                </aside>
            </div>
        `;
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
            ready: '可用',
            warning: '需补充',
            expired: '已过期',
            draft: '待编译',
        };
        return labels[status] || '待编译';
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
            this.monacoEditor.onDidChangeModelContent(() => this.updatePreview());
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
        if (!this.currentDoc || !this.monacoEditor) return;
        const content = this.monacoEditor.getValue();
        try {
            const payload = {
                ...this.readDocumentForm(),
                content,
            };
            const doc = await API.updateDocument(this.currentDoc.id, payload);
            this.currentDoc = doc;
            this.renderEditor(doc);
            Utils.showToast('保存成功', 'success');
            if (this.currentCategory) await this.loadDocList(this.currentCategory.id);
        } catch (e) {
            Utils.showToast('保存失败: ' + e.message, 'error');
        }
    },

    async recompileCurrentDocument() {
        if (!this.currentDoc?.id) return;
        try {
            const doc = await API.recompileDocument(this.currentDoc.id);
            this.currentDoc = doc;
            this.renderEditor(doc);
            Utils.showToast('重新编译完成', 'success');
            if (this.currentCategory) await this.loadDocList(this.currentCategory.id);
        } catch (e) {
            Utils.showToast('重新编译失败: ' + e.message, 'error');
        }
    },

    exportDocument(docId) {
        API.exportDocument(docId);
    },

    async deleteDocument(docId) {
        if (!confirm('确认删除此文档？此操作不可恢复。')) return;
        try {
            await API.deleteDocument(docId);
            Utils.showToast('文档已删除', 'success');
            const panel = DOM.$('#docs-editor-panel');
            if (panel) panel.innerHTML = '<div class="docs-editor-placeholder"><p>请选择文档</p></div>';
            this.currentDoc = null;
            if (this.currentCategory) await this.loadDocList(this.currentCategory.id);
        } catch (e) {
            Utils.showToast('删除失败: ' + e.message, 'error');
        }
    },

    async newDocument() {
        if (!this.currentCategory) {
            Utils.showToast('请先选择分类', 'warning');
            return;
        }
        Modal.show({
            title: '新建文档',
            content: `
                <div class="form-group">
                    <label>文档标题</label>
                    <input type="text" id="new-doc-title" class="form-control" placeholder="请输入文档标题">
                </div>
            `,
            buttons: [
                { text: '取消', variant: 'secondary', onClick: () => Modal.hide() },
                { text: '创建', variant: 'primary', onClick: async () => {
                    const titleEl = document.getElementById('new-doc-title');
                    const title = titleEl ? titleEl.value.trim() : '';
                    if (!title) { Utils.showToast('请输入标题', 'warning'); return; }
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
                        Utils.showToast('创建失败: ' + e.message, 'error');
                    }
                }}
            ]
        });
    },
};
