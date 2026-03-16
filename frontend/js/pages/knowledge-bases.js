/* Knowledge Bases page */
const KnowledgeBasesPage = {
    currentKB: null,
    documents: [],
    pollInterval: null,

    async render() {
        const content = DOM.$('#page-content');

        // Set up header
        const headerActions = DOM.el('button', {
            className: 'btn btn-primary',
            innerHTML: '<i data-lucide="plus"></i> New Knowledge Base',
            onClick: () => this.showKBModal()
        });
        Header.render('知识库', headerActions);

        // Set up content
        content.innerHTML = '<div id="kb-list" class="kb-grid"></div>';

        DOM.createIcons();

        await this.loadKnowledgeBases();

        return () => {
            if (this.pollInterval) {
                clearInterval(this.pollInterval);
                this.pollInterval = null;
            }
        };
    },

    async loadKnowledgeBases() {
        try {
            const kbs = await API.getKnowledgeBases();
            const container = DOM.$('#kb-list');

            if (kbs.length === 0) {
                container.innerHTML = `
                    <div class="empty-state">
                        <i data-lucide="book-open" style="width: 64px; height: 64px; margin-bottom: 16px;"></i>
                        <h3>No Knowledge Bases</h3>
                        <p>Create a knowledge base to upload documentation for AI diagnosis</p>
                        <button class="btn btn-primary" onclick="KnowledgeBasesPage.showKBModal()">
                            <i data-lucide="plus"></i> Create Knowledge Base
                        </button>
                    </div>
                `;
                DOM.createIcons();
                return;
            }

            container.innerHTML = kbs.map(kb => `
                <div class="kb-card">
                    <div class="kb-card-header">
                        <h3>${Utils.escapeHtml(kb.name)}</h3>
                        <span class="badge ${kb.is_active ? 'badge-success' : 'badge-secondary'}">
                            ${kb.is_active ? 'Active' : 'Inactive'}
                        </span>
                    </div>
                    <p class="kb-description">${kb.description ? Utils.escapeHtml(kb.description) : '<em>No description</em>'}</p>
                    <div class="kb-stats">
                        <span><i data-lucide="file-text"></i> ${kb.document_count} documents</span>
                        <span><i data-lucide="calendar"></i> ${Utils.formatDate(kb.created_at)}</span>
                    </div>
                    <div class="kb-actions">
                        <button class="btn btn-sm btn-primary" onclick="KnowledgeBasesPage.showDocuments(${kb.id})">
                            <i data-lucide="folder-open"></i> 文档
                        </button>
                        <button class="btn btn-sm btn-secondary" onclick="KnowledgeBasesPage.showKBModal(${kb.id})">
                            <i data-lucide="edit"></i> Edit
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="KnowledgeBasesPage.deleteKB(${kb.id})">
                            <i data-lucide="trash-2"></i> Delete
                        </button>
                    </div>
                </div>
            `).join('');

            DOM.createIcons();
        } catch (error) {
            Utils.showToast('加载失败 knowledge bases: ' + error.message, 'error');
        }
    },

    showKBModal(kbId = null) {
        const isEdit = kbId !== null;
        Modal.show({
            title: isEdit ? 'Edit Knowledge Base' : '新建知识库',
            content: `
                <form id="kb-form">
                    <div class="form-group">
                        <label>Name *</label>
                        <input type="text" id="kb-name" class="form-input" required maxlength="200">
                    </div>
                    <div class="form-group">
                        <label>描述</label>
                        <textarea id="kb-description" class="form-textarea" rows="3"></textarea>
                    </div>
                    <div class="form-group">
                        <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                            <input type="checkbox" id="kb-active" checked>
                            <span>Active</span>
                        </label>
                    </div>
                </form>
            `,
            buttons: [
                { text: 'Cancel', variant: 'secondary', onClick: () => Modal.hide() },
                { text: isEdit ? 'Update' : 'Create', variant: 'primary', onClick: () => this.saveKB(kbId) }
            ]
        });

        if (isEdit) {
            this.loadKBData(kbId);
        }
    },

    async loadKBData(kbId) {
        try {
            const kb = await API.getKnowledgeBase(kbId);
            DOM.$('#kb-name').value = kb.name;
            DOM.$('#kb-description').value = kb.description || '';
            DOM.$('#kb-active').checked = kb.is_active;
        } catch (error) {
            Utils.showToast('加载失败 knowledge base: ' + error.message, 'error');
            Modal.hide();
        }
    },

    async saveKB(kbId) {
        const name = DOM.$('#kb-name').value.trim();
        if (!name) {
            Utils.showToast('Name is required', 'error');
            return;
        }

        const data = {
            name,
            description: DOM.$('#kb-description').value.trim() || null,
            is_active: DOM.$('#kb-active').checked
        };

        try {
            if (kbId) {
                await API.updateKnowledgeBase(kbId, data);
                Utils.showToast('Knowledge base updated', 'success');
            } else {
                await API.createKnowledgeBase(data);
                Utils.showToast('Knowledge base created', 'success');
            }
            Modal.hide();
            await this.loadKnowledgeBases();
        } catch (error) {
            Utils.showToast('Failed to save: ' + error.message, 'error');
        }
    },

    async deleteKB(kbId) {
        if (!confirm('Delete this knowledge base and all its documents? This cannot be undone.')) {
            return;
        }

        try {
            await API.deleteKnowledgeBase(kbId);
            Utils.showToast('Knowledge base deleted', 'success');
            await this.loadKnowledgeBases();
        } catch (error) {
            Utils.showToast('Failed to delete: ' + error.message, 'error');
        }
    },

    async showDocuments(kbId) {
        this.currentKB = kbId;
        const kb = await API.getKnowledgeBase(kbId);

        Modal.show({
            title: `文档 - ${kb.name}`,
            size: 'large',
            content: `
                <div class="document-manager">
                    <div class="upload-area" id="upload-area">
                        <i data-lucide="upload" style="width: 48px; height: 48px;"></i>
                        <p>Drag and drop files here or click to browse</p>
                        <p class="text-muted">Supported: .md, .pdf, .docx, .pptx, .txt, .html (max 50MB)</p>
                        <input type="file" id="file-input" multiple accept=".md,.pdf,.docx,.pptx,.txt,.html" style="display: none;">
                    </div>
                    <div id="document-list" class="document-list"></div>
                </div>
            `,
            buttons: [
                { text: 'Close', variant: 'secondary', onClick: () => {
                    if (this.pollInterval) {
                        clearInterval(this.pollInterval);
                        this.pollInterval = null;
                    }
                    Modal.hide();
                }}
            ]
        });

        DOM.createIcons();

        const uploadArea = DOM.$('#upload-area');
        const fileInput = DOM.$('#file-input');

        uploadArea.addEventListener('click', () => fileInput.click());
        fileInput.addEventListener('change', (e) => this.handleFileUpload(e.target.files));

        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('drag-over');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('drag-over');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
            this.handleFileUpload(e.dataTransfer.files);
        });

        await this.loadDocuments();

        // Poll for document status updates
        this.pollInterval = setInterval(() => this.loadDocuments(), 3000);
    },

    async loadDocuments() {
        if (!this.currentKB) return;

        try {
            this.documents = await API.getDocuments(this.currentKB);
            const container = DOM.$('#document-list');

            if (this.documents.length === 0) {
                container.innerHTML = '<p class="text-muted text-center">No documents uploaded yet</p>';
                return;
            }

            container.innerHTML = this.documents.map(doc => {
                const statusClass = {
                    pending: 'badge-secondary',
                    processing: 'badge-info',
                    completed: 'badge-success',
                    failed: 'badge-danger'
                }[doc.status] || 'badge-secondary';

                const fileIcon = {
                    md: 'file-text',
                    pdf: 'file',
                    docx: 'file-text',
                    pptx: 'presentation',
                    txt: 'file-text',
                    html: 'code'
                }[doc.file_type] || 'file';

                return `
                    <div class="document-item">
                        <div class="document-icon">
                            <i data-lucide="${fileIcon}"></i>
                        </div>
                        <div class="document-info">
                            <div class="document-name">${Utils.escapeHtml(doc.filename)}</div>
                            <div class="document-meta">
                                <span>${Utils.formatFileSize(doc.file_size)}</span>
                                <span>${doc.chunk_count} chunks</span>
                                <span>${Utils.formatDate(doc.created_at)}</span>
                            </div>
                            ${doc.error_message ? `<div class="text-danger">${Utils.escapeHtml(doc.error_message)}</div>` : ''}
                        </div>
                        <span class="badge ${statusClass}">${doc.status}</span>
                        <button class="btn btn-sm btn-secondary" onclick="KnowledgeBasesPage.previewDocument(${this.currentKB}, ${doc.id}, '${doc.file_type}')">
                            <i data-lucide="eye"></i>
                        </button>
                        <button class="btn btn-sm btn-danger" onclick="KnowledgeBasesPage.deleteDocument(${doc.id})">
                            <i data-lucide="trash-2"></i>
                        </button>
                    </div>
                `;
            }).join('');

            DOM.createIcons();
        } catch (error) {
            console.error('加载失败 documents:', error);
        }
    },

    async handleFileUpload(files) {
        const allowedTypes = ['.md', '.pdf', '.docx', '.pptx', '.txt', '.html'];
        const maxSize = 50 * 1024 * 1024; // 50MB

        for (const file of files) {
            const ext = '.' + file.name.split('.').pop().toLowerCase();
            if (!allowedTypes.includes(ext)) {
                Utils.showToast(`File type not allowed: ${file.name}`, 'error');
                continue;
            }

            if (file.size > maxSize) {
                Utils.showToast(`File too large: ${file.name} (max 50MB)`, 'error');
                continue;
            }

            try {
                await API.uploadDocument(this.currentKB, file);
                Utils.showToast(`Uploaded: ${file.name}`, 'success');
            } catch (error) {
                Utils.showToast(`Failed to upload ${file.name}: ${error.message}`, 'error');
            }
        }

        await this.loadDocuments();
    },

    async deleteDocument(docId) {
        if (!confirm('Delete this document?')) return;

        try {
            await API.deleteDocument(this.currentKB, docId);
            Utils.showToast('Document deleted', 'success');
            await this.loadDocuments();
        } catch (error) {
            Utils.showToast('Failed to delete: ' + error.message, 'error');
        }
    },

    async previewDocument(kbId, docId, fileType) {
        try {
            const data = await API.getDocumentContent(kbId, docId);
            let previewHtml;

            if (data.type === 'pdf') {
                previewHtml = `<iframe src="${data.url}" style="width:100%;height:70vh;border:none;border-radius:4px;"></iframe>`;
            } else if (data.file_type === 'md') {
                let rendered;
                if (typeof MarkdownRenderer !== 'undefined') {
                    try {
                        rendered = MarkdownRenderer.render(data.content);
                    } catch (error) {
                        console.error('Markdown rendering error:', error);
                        rendered = data.content.replace(/\n/g, '<br>');
                    }
                } else {
                    rendered = data.content.replace(/\n/g, '<br>');
                }
                previewHtml = `<div class="markdown-preview" style="max-height:70vh;overflow:auto;padding:16px;background:var(--bg-primary);border-radius:4px;">${rendered}</div>`;
            } else {
                previewHtml = `<pre style="max-height:70vh;overflow:auto;padding:16px;background:var(--bg-primary);border-radius:4px;white-space:pre-wrap;word-wrap:break-word;">${Utils.escapeHtml(data.content)}</pre>`;
            }

            // Pause document polling while preview is shown
            if (this.pollInterval) {
                clearInterval(this.pollInterval);
                this.pollInterval = null;
            }

            Modal.show({
                title: data.filename || 'Document Preview',
                size: 'large',
                content: previewHtml,
                buttons: [
                    { text: 'Close', variant: 'secondary', onClick: () => {
                        Modal.hide();
                        // Re-open documents view to restore polling
                        this.showDocuments(kbId);
                    }}
                ]
            });
        } catch (error) {
            Utils.showToast('Failed to preview document: ' + error.message, 'error');
        }
    }
};
