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
                        <p>选择文档进行查看或编辑</p>
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
                    el.innerHTML = `
                        <div class="docs-list-item-title">
                            ${doc.is_builtin ? '<i data-lucide="lock" class="builtin-icon"></i>' : ''}
                            ${Utils.escapeHtml(doc.title)}
                        </div>
                        <div class="docs-list-item-summary">${Utils.escapeHtml(doc.summary || '')}</div>
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
        panel.innerHTML = `
            <div class="docs-editor-toolbar">
                <span class="docs-editor-title" title="${Utils.escapeHtml(doc.title)}">${Utils.escapeHtml(doc.title)}</span>
                <div class="docs-editor-actions">
                    <button class="btn btn-sm" onclick="DocumentsPage.setViewMode('edit')">编辑</button>
                    <button class="btn btn-sm" onclick="DocumentsPage.setViewMode('split')">分栏</button>
                    <button class="btn btn-sm" onclick="DocumentsPage.setViewMode('preview')">预览</button>
                    <button class="btn btn-sm btn-primary" onclick="DocumentsPage.saveDocument()">保存</button>
                    <button class="btn btn-sm" onclick="DocumentsPage.exportDocument(${doc.id})">导出</button>
                    ${!doc.is_builtin ? `<button class="btn btn-sm btn-danger" onclick="DocumentsPage.deleteDocument(${doc.id})">删除</button>` : ''}
                </div>
            </div>
            <div class="docs-editor-body" id="docs-editor-body">
                <div class="docs-monaco-container" id="docs-monaco"></div>
                <div class="docs-preview-container" id="docs-preview"></div>
            </div>
        `;
        this.initMonaco(doc.content);
        this.setViewMode(this.viewMode);
    },

    initMonaco(content) {
        if (this.monacoEditor) {
            this.monacoEditor.dispose();
            this.monacoEditor = null;
        }
        require.config({ paths: { vs: '/lib/monaco-editor/min/vs' } });
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
            await API.updateDocument(this.currentDoc.id, { content });
            Utils.showToast('保存成功', 'success');
            if (this.currentCategory) await this.loadDocList(this.currentCategory.id);
        } catch (e) {
            Utils.showToast('保存失败: ' + e.message, 'error');
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
