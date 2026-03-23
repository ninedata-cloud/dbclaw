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
            placeholder: '询问数据库相关问题，按 Ctrl/Command+Enter 发送...',
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
            title: '附加文件',
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
        bar.appendChild(sendBtn);
        bar.appendChild(clearBtn);
        bar.appendChild(stopBtn);
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
        DOM.createIcons();
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
            <button class="message-copy-btn" title="复制内容">
                <i data-lucide="copy"></i>
            </button>
        `;

        // Add copy functionality
        const copyBtn = msg.querySelector('.message-copy-btn');
        copyBtn.addEventListener('click', () => this._copyMessageContent(msg));

        messages.appendChild(msg);
        DOM.createIcons();
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
            if (typeof MarkdownRenderer !== 'undefined') {
                try {
                    bubble.innerHTML = MarkdownRenderer.render(this.currentContent);
                } catch (error) {
                    console.error('Markdown rendering error:', error);
                    bubble.innerHTML = this.currentContent.replace(/\n/g, '<br>');
                }
            } else {
                bubble.innerHTML = this.currentContent.replace(/\n/g, '<br>');
            }
            this._highlightCode(bubble);
            this._scrollToBottom();
        }
    },

    finishAssistantMessage() {
        this.isStreaming = false;
        const streamingMsg = DOM.$('#streaming-message');
        if (streamingMsg) {
            streamingMsg.removeAttribute('id');
            // Add copy button to finished message
            const copyBtn = DOM.el('button', {
                className: 'message-copy-btn',
                title: '复制',
                innerHTML: '<i data-lucide="copy"></i>'
            });
            streamingMsg.appendChild(copyBtn);
            copyBtn.addEventListener('click', () => this._copyMessageContent(streamingMsg));
            DOM.createIcons();
        }
        this._updateSendButton(false);
    },

    updateTokenUsage(stats) {
        const panel = DOM.$('#chat-token-usage');
        if (!panel) return;

        const usage = stats?.usage || { input_tokens: 0, output_tokens: 0, total_tokens: 0 };
        const contextWindow = stats?.contextWindow || null;
        const usageRate = contextWindow ? Math.min((usage.total_tokens / contextWindow) * 100, 999) : null;
        const level = stats?.warningLevel || 'normal';
        const warningText = stats?.warningText || '';

        const toneMap = {
            normal: { bg: 'rgba(47,129,247,0.08)', border: 'rgba(47,129,247,0.25)', text: 'var(--text-secondary)' },
            warning: { bg: 'rgba(255,193,7,0.10)', border: 'rgba(255,193,7,0.28)', text: '#d29922' },
            danger: { bg: 'rgba(248,81,73,0.10)', border: 'rgba(248,81,73,0.28)', text: '#f85149' },
            critical: { bg: 'rgba(248,81,73,0.16)', border: 'rgba(248,81,73,0.4)', text: '#ff7b72' },
        };
        const tone = toneMap[level] || toneMap.normal;

        panel.style.display = 'block';
        panel.style.background = tone.bg;
        panel.style.border = `1px solid ${tone.border}`;
        panel.innerHTML = `
            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;">
                <div style="display:flex;gap:16px;flex-wrap:wrap;">
                    <span><strong>本次会话已用</strong> ${usage.total_tokens.toLocaleString()} tokens</span>
                    <span>输入 ${usage.input_tokens.toLocaleString()}</span>
                    <span>输出 ${usage.output_tokens.toLocaleString()}</span>
                    <span>${contextWindow ? `上限 ${contextWindow.toLocaleString()}` : '未配置上下文上限'}</span>
                    <span>${usageRate !== null ? `使用率 ${usageRate.toFixed(1)}%` : ''}</span>
                </div>
                ${warningText ? `<div style="color:${tone.text};font-weight:600;">${this._escapeHtml(warningText)}</div>` : ''}
            </div>
        `;
    },

    resetTokenUsage() {
        const panel = DOM.$('#chat-token-usage');
        if (panel) {
            panel.style.display = 'none';
            panel.innerHTML = '';
        }
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
        DOM.createIcons();

        // Auto-scroll tool panel
        toolPanel.scrollTop = 0;

        // Store tool ID for result matching
        if (!this.pendingTools) this.pendingTools = new Map();
        this.pendingTools.set(toolName, toolId);
    },

    addToolResult(toolName, result, executionTimeMs = null) {
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

        // Update status with execution time
        const status = toolMsg.querySelector('.chat-tool-status');
        if (status) {
            status.className = `chat-tool-status ${isError ? 'error' : 'success'}`;
            const timeStr = executionTimeMs !== null ? ` (${executionTimeMs}ms)` : '';
            status.innerHTML = isError
                ? `<i data-lucide="alert-circle"></i> Error${timeStr}`
                : `<i data-lucide="check-circle"></i> Complete${timeStr}`;
            DOM.createIcons();
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
                    DOM.createIcons();
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

        // Clear tool panel but don't show empty state yet
        const toolPanel = DOM.$('#tool-panel-content');
        if (toolPanel) {
            toolPanel.innerHTML = '';
        }

        // Reset restored tools map
        this.restoredTools = new Map();
        let hasToolMessages = false;

        for (const msg of messages) {
            if (msg.role === 'user') {
                this.addUserMessage(msg.content, msg.attachments || []);
            } else if (msg.role === 'assistant') {
                const msgEl = DOM.el('div', { className: 'chat-message assistant' });
                let renderedContent;
                if (typeof MarkdownRenderer !== 'undefined') {
                    try {
                        renderedContent = MarkdownRenderer.render(msg.content);
                    } catch (error) {
                        console.error('Markdown rendering error:', error);
                        renderedContent = msg.content.replace(/\n/g, '<br>');
                    }
                } else {
                    renderedContent = msg.content.replace(/\n/g, '<br>');
                }
                msgEl.innerHTML = `
                    <div class="chat-avatar">AI</div>
                    <div class="chat-bubble">${renderedContent}</div>
                `;

                // Add copy button
                const copyBtn = DOM.el('button', {
                    className: 'message-copy-btn',
                    title: '复制',
                    innerHTML: '<i data-lucide="copy"></i>'
                });
                msgEl.appendChild(copyBtn);
                copyBtn.addEventListener('click', () => this._copyMessageContent(msgEl));

                container.appendChild(msgEl);
                this._highlightCode(msgEl.querySelector('.chat-bubble'));
            } else if (msg.role === 'tool_call') {
                // Restore tool call from history
                try {
                    const data = JSON.parse(msg.content);
                    this._restoreToolCall(data.tool_name, data.tool_args);
                    hasToolMessages = true;
                } catch (e) {
                    console.error('Failed to parse tool_call message:', e);
                }
            } else if (msg.role === 'tool_result') {
                // Restore tool result from history
                try {
                    const data = JSON.parse(msg.content);
                    this._restoreToolResult(data.tool_name, data.result, data.execution_time_ms);
                    hasToolMessages = true;
                } catch (e) {
                    console.error('Failed to parse tool_result message:', e);
                }
            }
        }

        // Show empty state if no tool messages
        if (toolPanel && !hasToolMessages) {
            toolPanel.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:12px;">暂无skill调用记录</div>';
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
    },

    _copyMessageContent(messageElement) {
        const bubble = messageElement.querySelector('.chat-bubble');
        if (!bubble) return;

        // Get text content, preserving line breaks
        const text = bubble.innerText || bubble.textContent;

        navigator.clipboard.writeText(text).then(() => {
            const copyBtn = messageElement.querySelector('.message-copy-btn');
            if (copyBtn) {
                const icon = copyBtn.querySelector('i');
                if (icon) {
                    icon.setAttribute('data-lucide', 'check');
                    DOM.createIcons();
                    setTimeout(() => {
                        icon.setAttribute('data-lucide', 'copy');
                        DOM.createIcons();
                    }, 2000);
                }
            }
            Toast.success('已复制到剪贴板');
        }).catch(err => {
            console.error('Failed to copy:', err);
            Toast.error('复制失败');
        });
    },

    _restoreToolCall(toolName, args) {
        const toolPanel = DOM.$('#tool-panel-content');
        if (!toolPanel) return;

        // Clear empty state if exists
        const emptyState = toolPanel.querySelector('div[style*="暂无skill调用记录"]');
        if (emptyState) {
            toolPanel.innerHTML = '';
        }

        const toolId = `tool-restored-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
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
                <span class="chat-tool-status pending">
                    <i data-lucide="clock"></i>
                    Pending
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

        toolPanel.appendChild(toolMsg);
        DOM.createIcons();

        // Store mapping for matching results later
        if (!this.restoredTools) this.restoredTools = new Map();
        this.restoredTools.set(toolName, toolId);
    },

    _restoreToolResult(toolName, result, executionTimeMs = null) {
        if (!this.restoredTools) return;

        const toolId = this.restoredTools.get(toolName);
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

        // Update status with execution time
        const status = toolMsg.querySelector('.chat-tool-status');
        if (status) {
            status.className = `chat-tool-status ${isError ? 'error' : 'success'}`;
            const timeStr = executionTimeMs !== null ? ` (${executionTimeMs}ms)` : '';
            status.innerHTML = isError
                ? `<i data-lucide="alert-circle"></i> Error${timeStr}`
                : `<i data-lucide="check-circle"></i> Complete${timeStr}`;
            DOM.createIcons();
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
                    DOM.createIcons();
                }
            }
        }

        this.restoredTools.delete(toolName);
    }
};

window.ChatWidget = ChatWidget;
