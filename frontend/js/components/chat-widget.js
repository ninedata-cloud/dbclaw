/* Chat widget component with file upload support */
const ChatWidget = {
    ws: null,
    currentContent: '',
    isStreaming: false,
    attachments: [],

    createMessagesContainer() {
        return DOM.el('div', { className: 'chat-messages', id: 'chat-messages' });
    },

    createInputBar(onSend, getSessionId) {
        const bar = DOM.el('div', { className: 'chat-input-bar' });
        this.getSessionId = getSessionId;

        // Attachment preview area
        const attachmentPreview = DOM.el('div', {
            className: 'chat-attachments-preview',
            id: 'chat-attachments-preview',
            style: { display: 'none' }
        });

        const input = DOM.el('textarea', {
            className: 'chat-input',
            id: 'chat-input',
            placeholder: 'Ask about your database...',
            rows: '1',
        });

        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !e.shiftKey) {
                e.preventDefault();
                if (!this.isStreaming) {
                    onSend(input.value.trim(), this.attachments);
                    input.value = '';
                    input.style.height = 'auto';
                    this.clearAttachments();
                }
            }
        });

        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 120) + 'px';
        });

        // File input (hidden)
        const fileInput = DOM.el('input', {
            type: 'file',
            id: 'chat-file-input',
            style: { display: 'none' },
            multiple: true,
            accept: 'image/*,.txt,.log,.sql,.json,.yaml,.yml,.md,.csv,.pdf'
        });

        fileInput.addEventListener('change', async (e) => {
            const files = Array.from(e.target.files);
            const sessionId = this.getSessionId ? this.getSessionId() : null;
            for (const file of files) {
                await this.addAttachment(file, sessionId);
            }
            fileInput.value = ''; // Reset input
        });

        const attachBtn = DOM.el('button', {
            className: 'chat-attach-btn',
            innerHTML: '<i data-lucide="paperclip"></i>',
            title: 'Attach file',
            onClick: () => fileInput.click()
        });

        const sendBtn = DOM.el('button', {
            className: 'chat-send-btn',
            id: 'chat-send-btn',
            innerHTML: '<i data-lucide="send"></i>',
            onClick: () => {
                if (!this.isStreaming) {
                    onSend(input.value.trim(), this.attachments);
                    input.value = '';
                    input.style.height = 'auto';
                    this.clearAttachments();
                }
            }
        });

        const stopBtn = DOM.el('button', {
            className: 'chat-send-btn',
            id: 'chat-stop-btn',
            innerHTML: '<i data-lucide="square"></i>',
            style: { display: 'none', background: 'var(--accent-red)' },
            onClick: () => {
                if (this.onStop) this.onStop();
            }
        });

        const clearBtn = DOM.el('button', {
            className: 'chat-send-btn',
            id: 'chat-clear-btn',
            innerHTML: '<i data-lucide="eraser"></i>',
            title: 'Clear session',
            onClick: () => {
                if (this.onClear) this.onClear();
            }
        });

        bar.appendChild(attachmentPreview);
        bar.appendChild(fileInput);
        bar.appendChild(input);
        bar.appendChild(attachBtn);
        bar.appendChild(clearBtn);
        bar.appendChild(stopBtn);
        bar.appendChild(sendBtn);
        return bar;
    },

    async addAttachment(file, sessionId) {
        // Check file size (10MB limit)
        if (file.size > 10 * 1024 * 1024) {
            Toast.error('File too large (max 10MB)');
            return;
        }

        // Upload file
        try {
            if (!sessionId) {
                Toast.error('No active session');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            const token = localStorage.getItem('auth_token');
            const response = await fetch(`/api/chat/sessions/${sessionId}/upload`, {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${token}` },
                body: formData
            });

            if (!response.ok) {
                throw new Error('Upload failed');
            }

            const metadata = await response.json();
            this.attachments.push(metadata);
            this.updateAttachmentPreview();
            Toast.success('File attached');
        } catch (error) {
            Toast.error('Failed to upload file: ' + error.message);
        }
    },

    updateAttachmentPreview() {
        const preview = DOM.$('#chat-attachments-preview');
        if (!preview) return;

        if (this.attachments.length === 0) {
            preview.style.display = 'none';
            return;
        }

        preview.style.display = 'flex';
        preview.innerHTML = this.attachments.map((att, idx) => `
            <div class="attachment-chip">
                <i data-lucide="${this.getFileIcon(att.file_type)}"></i>
                <span>${att.filename}</span>
                <button onclick="ChatWidget.removeAttachment(${idx})" class="remove-btn">
                    <i data-lucide="x"></i>
                </button>
            </div>
        `).join('');
        lucide.createIcons();
    },

    getFileIcon(fileType) {
        const icons = {
            'image': 'image',
            'text': 'file-text',
            'document': 'file'
        };
        return icons[fileType] || 'file';
    },

    removeAttachment(index) {
        this.attachments.splice(index, 1);
        this.updateAttachmentPreview();
    },

    clearAttachments() {
        this.attachments = [];
        this.updateAttachmentPreview();
    },

    addUserMessage(text, attachments = []) {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;
        const msg = DOM.el('div', { className: 'chat-message user' });

        let attachmentHtml = '';
        if (attachments && attachments.length > 0) {
            attachmentHtml = '<div class="message-attachments">' +
                attachments.map(att => `
                    <div class="attachment-item">
                        <i data-lucide="${this.getFileIcon(att.file_type)}"></i>
                        <span>${att.filename}</span>
                    </div>
                `).join('') +
                '</div>';
        }

        msg.innerHTML = `
            <div class="chat-avatar">U</div>
            <div class="chat-bubble">
                ${attachmentHtml}
                ${text ? this._escapeHtml(text) : ''}
            </div>
        `;
        messages.appendChild(msg);
        lucide.createIcons();
        this._scrollToBottom();
    },

    startAssistantMessage() {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;
        this.currentContent = '';
        this.isStreaming = true;
        const msg = DOM.el('div', { className: 'chat-message assistant', id: 'streaming-message' });
        msg.innerHTML = `
            <div class="chat-avatar">AI</div>
            <div class="chat-bubble"><div class="spinner"></div></div>
        `;
        messages.appendChild(msg);
        this._updateSendButton(true);
        this._scrollToBottom();
    },

    appendContent(text) {
        this.currentContent += text;
        const streamingMsg = DOM.$('#streaming-message');
        if (streamingMsg) {
            const bubble = streamingMsg.querySelector('.chat-bubble');
            bubble.innerHTML = marked.parse(this.currentContent);
            this._highlightCode(bubble);
            this._scrollToBottom();
        }
    },

    finishAssistantMessage() {
        this.isStreaming = false;
        const streamingMsg = DOM.$('#streaming-message');
        if (streamingMsg) {
            streamingMsg.removeAttribute('id');
        }
        this._updateSendButton(false);
    },

    addToolCall(toolName, args) {
        // Add to tool panel instead of messages
        const toolPanel = DOM.$('#tool-panel-content');
        if (!toolPanel) return;

        // Clear empty state if exists
        if (toolPanel.querySelector('div[style*="No tool executions"]')) {
            toolPanel.innerHTML = '';
        }

        const toolId = `tool-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const argsStr = typeof args === 'string' ? args : JSON.stringify(args, null, 2);

        const toolMsg = DOM.el('div', {
            className: 'chat-tool-call',
            id: toolId,
            'data-tool-name': toolName
        });

        toolMsg.innerHTML = `
            <div class="chat-tool-header" onclick="ChatWidget.toggleToolBody('${toolId}')">
                <div class="chat-tool-icon">
                    <i data-lucide="wrench"></i>
                </div>
                <span class="chat-tool-name">${this._escapeHtml(toolName)}</span>
                <span class="chat-tool-status running">
                    <i data-lucide="loader" style="animation: spin 1s linear infinite;"></i>
                    Running
                </span>
                <i data-lucide="chevron-right" class="chat-tool-expand"></i>
            </div>
            <div class="chat-tool-body">
                <div class="chat-tool-section">
                    <div class="chat-tool-section-title">
                        <span>Arguments</span>
                        <button class="chat-tool-copy-btn" onclick="ChatWidget.copyToClipboard('${toolId}-args', event)">
                            <i data-lucide="copy"></i> Copy
                        </button>
                    </div>
                    <div class="chat-tool-content" id="${toolId}-args">${this._escapeHtml(argsStr)}</div>
                </div>
                <div class="chat-tool-section" id="${toolId}-result" style="display: none;">
                    <div class="chat-tool-section-title">
                        <span>Result</span>
                        <button class="chat-tool-copy-btn" onclick="ChatWidget.copyToClipboard('${toolId}-result-content', event)">
                            <i data-lucide="copy"></i> Copy
                        </button>
                    </div>
                    <div class="chat-tool-content" id="${toolId}-result-content"></div>
                </div>
            </div>
        `;

        toolPanel.insertBefore(toolMsg, toolPanel.firstChild);
        lucide.createIcons();

        // Auto-scroll tool panel
        toolPanel.scrollTop = 0;

        // Store tool ID for result matching
        if (!this.pendingTools) this.pendingTools = new Map();
        this.pendingTools.set(toolName, toolId);
    },

    addToolResult(toolName, result) {
        if (!this.pendingTools) return;

        const toolId = this.pendingTools.get(toolName);
        if (!toolId) return;

        const toolMsg = DOM.$(`#${toolId}`);
        if (!toolMsg) return;

        // Parse result if it's a string
        let resultStr = result;
        let isJson = false;
        let isTruncated = false;

        if (typeof result === 'string') {
            // Check if truncated
            if (result.length >= 1999) {
                isTruncated = true;
            }

            // Try to parse as JSON for better formatting
            try {
                const parsed = JSON.parse(result);
                resultStr = JSON.stringify(parsed, null, 2);
                isJson = true;
            } catch (e) {
                resultStr = result;
            }
        } else {
            resultStr = JSON.stringify(result, null, 2);
            isJson = true;
        }

        // Check for errors
        const isError = result && (
            (typeof result === 'object' && result.error) ||
            (typeof result === 'string' && (result.toLowerCase().includes('error') || result.includes('"error"')))
        );

        // Update status
        const status = toolMsg.querySelector('.chat-tool-status');
        if (status) {
            status.className = `chat-tool-status ${isError ? 'error' : 'success'}`;
            status.innerHTML = isError
                ? '<i data-lucide="alert-circle"></i> Error'
                : '<i data-lucide="check-circle"></i> Complete';
            lucide.createIcons();
        }

        // Add result
        const resultSection = toolMsg.querySelector(`#${toolId}-result`);
        if (resultSection) {
            resultSection.style.display = 'block';
            const resultContent = resultSection.querySelector('.chat-tool-content');
            if (resultContent) {
                resultContent.textContent = resultStr;

                // Add truncation notice
                if (isTruncated) {
                    const notice = DOM.el('div', {
                        style: {
                            marginTop: '8px',
                            padding: '6px 10px',
                            background: 'rgba(255,193,7,0.1)',
                            border: '1px solid rgba(255,193,7,0.3)',
                            borderRadius: '4px',
                            fontSize: '11px',
                            color: 'var(--text-muted)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px'
                        }
                    });
                    notice.innerHTML = '<i data-lucide="info" style="width:14px;height:14px;"></i> Result truncated for display (showing first 2000 chars)';
                    resultSection.appendChild(notice);
                    lucide.createIcons();
                }
            }
        }

        this.pendingTools.delete(toolName);
        this._scrollToBottom();
    },

    toggleToolBody(toolId) {
        const toolMsg = DOM.$(`#${toolId}`);
        if (!toolMsg) return;

        const body = toolMsg.querySelector('.chat-tool-body');
        const expand = toolMsg.querySelector('.chat-tool-expand');

        if (body && expand) {
            const isExpanded = body.classList.contains('expanded');
            if (isExpanded) {
                body.classList.remove('expanded');
                expand.classList.remove('expanded');
            } else {
                body.classList.add('expanded');
                expand.classList.add('expanded');
            }
        }
    },

    copyToClipboard(elementId, event) {
        // Stop propagation to prevent toggling the tool body
        if (event) {
            event.stopPropagation();
        }

        const element = DOM.$(`#${elementId}`);
        if (!element) return;

        const text = element.textContent;

        // Use modern clipboard API
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => {
                Toast.success('Copied to clipboard');
            }).catch(() => {
                Toast.error('Failed to copy');
            });
        } else {
            // Fallback for older browsers
            const textarea = document.createElement('textarea');
            textarea.value = text;
            textarea.style.position = 'fixed';
            textarea.style.opacity = '0';
            document.body.appendChild(textarea);
            textarea.select();
            try {
                document.execCommand('copy');
                Toast.success('Copied to clipboard');
            } catch (err) {
                Toast.error('Failed to copy');
            }
            document.body.removeChild(textarea);
        }
    },

    addError(message) {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;
        const errorMsg = DOM.el('div', { className: 'chat-message error' });
        errorMsg.innerHTML = `
            <div class="chat-avatar">!</div>
            <div class="chat-bubble">${this._escapeHtml(message)}</div>
        `;
        messages.appendChild(errorMsg);
        this._scrollToBottom();
    },

    showError(message) {
        this.addError(message);
        this.finishAssistantMessage();
    },

    loadMessages(messages) {
        const container = DOM.$('#chat-messages');
        if (!container) return;
        container.innerHTML = '';

        // Clear tool panel
        const toolPanel = DOM.$('#tool-panel-content');
        if (toolPanel) {
            toolPanel.innerHTML = '';
        }

        for (const msg of messages) {
            if (msg.role === 'user') {
                this.addUserMessage(msg.content, msg.attachments || []);
            } else if (msg.role === 'assistant') {
                const msgEl = DOM.el('div', { className: 'chat-message assistant' });
                msgEl.innerHTML = `
                    <div class="chat-avatar">AI</div>
                    <div class="chat-bubble">${marked.parse(msg.content)}</div>
                `;
                container.appendChild(msgEl);
                this._highlightCode(msgEl.querySelector('.chat-bubble'));
            }
        }
        this._scrollToBottom();
    },

    _updateSendButton(isStreaming) {
        const sendBtn = DOM.$('#chat-send-btn');
        const stopBtn = DOM.$('#chat-stop-btn');
        if (sendBtn && stopBtn) {
            sendBtn.style.display = isStreaming ? 'none' : 'block';
            stopBtn.style.display = isStreaming ? 'block' : 'none';
        }
    },

    _scrollToBottom() {
        const messages = DOM.$('#chat-messages');
        if (messages) {
            messages.scrollTop = messages.scrollHeight;
        }
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    _highlightCode(element) {
        if (typeof hljs !== 'undefined') {
            element.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);
            });
        }
    }
};

window.ChatWidget = ChatWidget;
