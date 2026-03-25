/* Chat widget component with file upload support */
const ChatWidget = {
    ws: null,
    currentContent: '',
    isStreaming: false,
    attachments: [],

    createMessagesContainer() {
        return DOM.el('div', { className: 'chat-messages', id: 'chat-messages' });
    },

    createToolPanel() {
        const panel = DOM.el('div', {
            id: 'tool-execution-panel',
            style: {
                width: '360px',
                minWidth: '360px',
                flexShrink: '0',
                height: '100%',
                borderLeft: '1px solid var(--border-color)',
                display: 'flex',
                flexDirection: 'column',
                background: 'var(--bg-secondary)',
                transition: 'width 0.3s ease',
                overflow: 'hidden',
                boxSizing: 'border-box'
            }
        });

        const header = DOM.el('div', {
            id: 'tool-panel-header',
            style: {
                padding: '8px',
                borderBottom: '1px solid var(--border-color)',
                display: 'flex',
                gap: '8px',
                alignItems: 'center',
                justifyContent: 'space-between'
            }
        });

        const title = DOM.el('div', {
            id: 'tool-panel-title',
            style: { fontSize: '14px', fontWeight: '600', color: 'var(--text-primary)' },
            textContent: 'Skill 调用记录'
        });

        const toggleBtn = DOM.el('button', {
            className: 'btn-icon-only',
            id: 'toggle-tool-panel-btn',
            innerHTML: '<i data-lucide="panel-right-close"></i>',
            title: '隐藏 skill 调用记录',
            onClick: () => this.toggleToolPanel()
        });

        const content = DOM.el('div', {
            id: 'tool-panel-content',
            style: { flex: '1', overflowY: 'auto', padding: '16px' }
        });

        header.appendChild(title);
        header.appendChild(toggleBtn);
        panel.appendChild(header);
        panel.appendChild(content);
        this.resetToolPanel();
        return panel;
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

            const response = await fetch(`/api/chat/sessions/${sessionId}/upload`, {
                method: 'POST',
                credentials: 'same-origin',
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

    _ensureMaps() {
        if (!this.pendingTools) this.pendingTools = new Map();
        if (!this.pendingApprovals) this.pendingApprovals = new Map();
    },

    _appendSystemCard(cardElement) {
        const content = DOM.$('#tool-panel-content');
        if (!content) return;
        const placeholder = content.querySelector('.tool-panel-empty');
        if (placeholder) placeholder.remove();
        content.appendChild(cardElement);
        DOM.createIcons();
        this._scrollToolPanelToBottom();
    },

    _stringifyData(data) {
        if (typeof data === 'string') return data;
        return JSON.stringify(data, null, 2);
    },

    _buildSummary(data, fallback = '') {
        if (!data) return fallback;
        if (typeof data === 'string') {
            const trimmed = data.trim();
            return trimmed.length > 120 ? `${trimmed.slice(0, 117)}...` : trimmed;
        }
        if (Array.isArray(data)) return `返回 ${data.length} 条记录`;
        if (typeof data === 'object') {
            if (data.error) return String(data.error);
            if (data.message) return String(data.message);
            const parts = Object.entries(data).slice(0, 3).map(([key, value]) => {
                const rendered = typeof value === 'object' ? JSON.stringify(value) : String(value);
                return `${key}=${rendered.length > 24 ? `${rendered.slice(0, 21)}...` : rendered}`;
            });
            return parts.join('，') || fallback;
        }
        return String(data);
    },

    _buildToolCard(toolId, toolName, args, statusLabel, statusClass) {
        const toolMsg = DOM.el('div', {
            className: 'chat-message assistant chat-system-message',
            id: toolId,
            'data-tool-name': toolName
        });
        const argsStr = this._stringifyData(args);
        toolMsg.innerHTML = `
            <div class="chat-system-body">
                <div class="chat-tool-call">
                    <div class="chat-tool-header" onclick="ChatWidget.toggleToolBody('${toolId}')" aria-expanded="false">
                        <div class="chat-tool-icon"><i data-lucide="wrench"></i></div>
                        <div class="chat-tool-main">
                            <span class="chat-tool-name">${this._escapeHtml(toolName)}</span>
                        </div>
                        <span class="chat-tool-status ${statusClass}">${statusLabel}</span>
                        <i data-lucide="chevron-right" class="chat-tool-expand"></i>
                    </div>
                    <div class="chat-tool-body" style="display:none;">
                        <div class="chat-tool-section">
                            <div class="chat-tool-section-title">
                                <span>Arguments</span>
                                <button class="chat-tool-copy-btn" onclick="ChatWidget.copyToClipboard('${toolId}-args', event)">
                                    <i data-lucide="copy"></i> Copy
                                </button>
                            </div>
                            <div class="chat-tool-content" id="${toolId}-args">${this._escapeHtml(argsStr)}</div>
                        </div>
                        <div class="chat-tool-section" id="${toolId}-result" style="display:none;">
                            <div class="chat-tool-section-title">
                                <span>Result</span>
                                <button class="chat-tool-copy-btn" onclick="ChatWidget.copyToClipboard('${toolId}-result-content', event)">
                                    <i data-lucide="copy"></i> Copy
                                </button>
                            </div>
                            <div class="chat-tool-content" id="${toolId}-result-content"></div>
                        </div>
                    </div>
                </div>
            </div>
        `;
        return toolMsg;
    },

    addToolCall(toolName, args, toolCallId = null) {
        this._ensureMaps();
        const existingApprovalCard = toolCallId
            ? DOM.$(`[data-tool-call-id="${toolCallId}"]`)
            : null;

        if (existingApprovalCard) {
            const toolId = existingApprovalCard.id;
            const toolMsg = this._buildToolCard(toolId, toolName, args, '执行中', 'running');
            toolMsg.setAttribute('data-tool-call-id', toolCallId);
            existingApprovalCard.replaceWith(toolMsg);
            DOM.createIcons();
            this._scrollToolPanelToBottom();
            this.pendingTools.set(toolCallId || toolName, toolId);
            return;
        }

        const toolId = `tool-${toolCallId || `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`}`;
        const toolMsg = this._buildToolCard(toolId, toolName, args, '执行中', 'running');
        if (toolCallId) toolMsg.setAttribute('data-tool-call-id', toolCallId);
        this._appendSystemCard(toolMsg);
        this.pendingTools.set(toolCallId || toolName, toolId);
    },

    addToolResult(toolName, result, executionTimeMs = null, toolCallId = null) {
        this._ensureMaps();
        const toolId = this.pendingTools.get(toolCallId || toolName);
        if (!toolId) return;

        const toolMsg = DOM.$(`#${toolId}`);
        if (!toolMsg) return;

        let resultStr = result;
        let isTruncated = false;
        let parsedResult = result;
        if (typeof result === 'string') {
            if (result.length >= 1999) isTruncated = true;
            try {
                parsedResult = JSON.parse(result);
                resultStr = JSON.stringify(parsedResult, null, 2);
            } catch (e) {
                resultStr = result;
            }
        } else {
            resultStr = JSON.stringify(result, null, 2);
        }

        const isError = parsedResult && ((typeof parsedResult === 'object' && parsedResult.error) || (typeof result === 'string' && result.toLowerCase().includes('error')));
        const status = toolMsg.querySelector('.chat-tool-status');
        if (status) {
            status.className = `chat-tool-status ${isError ? 'error' : 'success'}`;
            status.textContent = `${isError ? '失败' : '完成'}${executionTimeMs !== null ? ` · ${executionTimeMs}ms` : ''}`;
        }

        const resultSection = toolMsg.querySelector(`#${toolId}-result`);
        if (resultSection) {
            resultSection.style.display = 'block';
            const resultContent = resultSection.querySelector('.chat-tool-content');
            if (resultContent) resultContent.textContent = resultStr;
            if (isTruncated && !resultSection.querySelector('.chat-tool-truncate')) {
                const notice = DOM.el('div', { className: 'chat-tool-truncate', textContent: '结果过长，当前仅展示前 2000 个字符' });
                resultSection.appendChild(notice);
            }
        }

        this.pendingTools.delete(toolCallId || toolName);
        DOM.createIcons();
        this._scrollToolPanelToBottom();
    },

    addApprovalRequest(data, options = {}) {
        this._ensureMaps();
        const { showModal = true } = options;
        const approvalId = data.approval_id;
        const cardId = `approval-${approvalId}`;
        const existingCard = DOM.$(`#${cardId}`);
        if (existingCard) existingCard.remove();
        const card = DOM.el('div', {
            className: 'chat-message assistant chat-system-message',
            id: cardId,
        });
        if (data.tool_call_id) card.setAttribute('data-tool-call-id', data.tool_call_id);
        card.innerHTML = `
            <div class="chat-system-body">
                <div class="chat-tool-call chat-approval-card">
                    <div class="chat-tool-header" onclick="ChatWidget.toggleToolBody('${cardId}')" aria-expanded="false">
                        <div class="chat-tool-icon"><i data-lucide="shield-alert"></i></div>
                        <div class="chat-tool-main">
                            <span class="chat-tool-name">${this._escapeHtml(data.tool_name)}</span>
                            ${data.risk_reason ? `<div class="chat-approval-risk">${this._escapeHtml(data.risk_reason)}</div>` : ''}
                        </div>
                        <span class="chat-tool-status pending">待确认</span>
                        <i data-lucide="chevron-right" class="chat-tool-expand"></i>
                    </div>
                    <div class="chat-tool-body" style="display:none;">
                        <div class="chat-tool-section">
                            <div class="chat-tool-section-title"><span>计划</span></div>
                            <div class="chat-tool-content">${this._escapeHtml(data.plan_markdown || '')}</div>
                        </div>
                        <div class="chat-tool-section">
                            <div class="chat-tool-section-title"><span>参数</span></div>
                            <div class="chat-tool-content">${this._escapeHtml(this._stringifyData(data.tool_args || {}))}</div>
                        </div>
                        <div class="chat-approval-actions">
                            <button class="btn btn-danger" onclick="ChatWidget.handleApprovalAction('${approvalId}', 'approved')">确认执行</button>
                            <button class="btn btn-secondary" onclick="ChatWidget.handleApprovalAction('${approvalId}', 'rejected')">取消</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
        this.pendingApprovals.set(approvalId, cardId);
        this._appendSystemCard(card);
        if (showModal && typeof this.onApprovalRequest === 'function') this.onApprovalRequest(data);
    },

    updateApprovalStatus(approvalId, action) {
        this._ensureMaps();
        const cardId = this.pendingApprovals.get(approvalId) || `approval-${approvalId}`;
        const card = DOM.$(`#${cardId}`);
        if (!card) return;
        const status = card.querySelector('.chat-tool-status');
        if (status) {
            status.className = `chat-tool-status ${action === 'approved' ? 'success' : 'error'}`;
            status.textContent = action === 'approved' ? '已确认' : '已取消';
        }
        const actions = card.querySelector('.chat-approval-actions');
        if (actions) actions.style.display = 'none';
        this.pendingApprovals.delete(approvalId);
    },

    async handleApprovalAction(approvalId, action) {
        if (typeof this.onApprovalAction === 'function') {
            await this.onApprovalAction(approvalId, action);
        }
    },

    toggleToolBody(toolId) {
        const toolMsg = DOM.$(`#${toolId}`);
        if (!toolMsg) return;
        const header = toolMsg.querySelector('.chat-tool-header');
        const body = toolMsg.querySelector('.chat-tool-body');
        const expand = toolMsg.querySelector('.chat-tool-expand');
        if (!body || !expand) return;
        const isExpanded = body.classList.contains('expanded');
        body.classList.toggle('expanded', !isExpanded);
        body.style.display = isExpanded ? 'none' : 'block';
        expand.classList.toggle('expanded', !isExpanded);
        if (header) header.setAttribute('aria-expanded', String(!isExpanded));
    },

    copyToClipboard(elementId, event) {
        if (event) event.stopPropagation();
        const element = DOM.$(`#${elementId}`);
        if (!element) return;
        const text = element.textContent;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => Toast.success('已复制到剪贴板')).catch(() => Toast.error('复制失败'));
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
        this.resetToolPanel();
        this.pendingTools = new Map();
        this.pendingApprovals = new Map();

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
                        renderedContent = msg.content.replace(/\n/g, '<br>');
                    }
                } else {
                    renderedContent = msg.content.replace(/\n/g, '<br>');
                }
                msgEl.innerHTML = `
                    <div class="chat-avatar">AI</div>
                    <div class="chat-bubble">${renderedContent}</div>
                `;
                const copyBtn = DOM.el('button', { className: 'message-copy-btn', title: '复制', innerHTML: '<i data-lucide="copy"></i>' });
                msgEl.appendChild(copyBtn);
                copyBtn.addEventListener('click', () => this._copyMessageContent(msgEl));
                container.appendChild(msgEl);
                this._highlightCode(msgEl.querySelector('.chat-bubble'));
            } else if (msg.role === 'tool_call') {
                try {
                    const data = JSON.parse(msg.content);
                    this.addToolCall(data.tool_name, data.tool_args, data.tool_call_id || msg.tool_call_id || null);
                } catch (e) {
                    console.error('Failed to parse tool_call message:', e);
                }
            } else if (msg.role === 'tool_result') {
                try {
                    const data = JSON.parse(msg.content);
                    this.addToolResult(data.tool_name, data.result, data.execution_time_ms, data.tool_call_id || msg.tool_call_id || null);
                } catch (e) {
                    console.error('Failed to parse tool_result message:', e);
                }
            } else if (msg.role === 'approval_request') {
                try {
                    const data = JSON.parse(msg.content);
                    this.addApprovalRequest(data, { showModal: false });
                } catch (e) {
                    console.error('Failed to parse approval_request message:', e);
                }
            } else if (msg.role === 'approval_response') {
                try {
                    const data = JSON.parse(msg.content);
                    this.updateApprovalStatus(data.approval_id, data.action);
                } catch (e) {
                    console.error('Failed to parse approval_response message:', e);
                }
            }
        }

        this._scrollToBottom();
        this._scrollToolPanelToBottom();
    },

    showToolPanelLoading() {
        const content = DOM.$('#tool-panel-content');
        if (content) {
            content.innerHTML = `
                <div class="tool-panel-empty" style="color: var(--text-muted); font-size: 13px; display:flex; align-items:center; gap:8px;">
                    <div class="spinner" style="width:14px;height:14px;"></div>
                    <span>正在加载当前会话的 skill 调用记录...</span>
                </div>
            `;
        }
    },

    resetToolPanel() {
        const content = DOM.$('#tool-panel-content');
        if (content) {
            content.innerHTML = '<div class="tool-panel-empty" style="color: var(--text-muted); font-size: 13px;">当前会话的 skill 调用记录会显示在这里</div>';
        }
    },

    toggleToolPanel() {
        const panel = DOM.$('#tool-execution-panel');
        const btn = DOM.$('#toggle-tool-panel-btn');
        const header = DOM.$('#tool-panel-header');
        const title = DOM.$('#tool-panel-title');
        const content = DOM.$('#tool-panel-content');

        if (!panel || !btn) return;

        const isCollapsed = panel.style.width === '40px';

        if (isCollapsed) {
            panel.style.width = '360px';
            panel.style.minWidth = '360px';
            btn.innerHTML = '<i data-lucide="panel-right-close"></i>';
            btn.title = '隐藏 skill 调用记录';
            if (header) header.style.justifyContent = 'space-between';
            if (title) title.style.display = '';
            if (content) content.style.display = 'block';
        } else {
            panel.style.width = '40px';
            panel.style.minWidth = '40px';
            btn.innerHTML = '<i data-lucide="panel-right-open"></i>';
            btn.title = '显示 skill 调用记录';
            if (header) header.style.justifyContent = 'center';
            if (title) title.style.display = 'none';
            if (content) content.style.display = 'none';
        }

        requestAnimationFrame(() => DOM.createIcons());
    },

    _scrollToBottom() {
        const messages = DOM.$('#chat-messages');
        if (messages) messages.scrollTop = messages.scrollHeight;
    },

    _scrollToolPanelToBottom() {
        const content = DOM.$('#tool-panel-content');
        if (content) content.scrollTop = content.scrollHeight;
    },

    _updateSendButton(isStreaming) {
        const sendBtn = DOM.$('#chat-send-btn');
        const stopBtn = DOM.$('#chat-stop-btn');
        const input = DOM.$('#chat-input');
        const attachBtn = DOM.$('.chat-attach-btn');

        if (sendBtn) sendBtn.style.display = isStreaming ? 'none' : '';
        if (stopBtn) stopBtn.style.display = isStreaming ? '' : 'none';
        if (input) input.disabled = isStreaming;
        if (attachBtn) attachBtn.disabled = isStreaming;
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text == null ? '' : String(text);
        return div.innerHTML;
    },

    _highlightCode(element) {
        if (typeof hljs !== 'undefined' && element) {
            element.querySelectorAll('pre code').forEach((block) => {
                hljs.highlightElement(block);
            });
        }
    },

    _copyMessageContent(messageElement) {
        const bubble = messageElement.querySelector('.chat-bubble');
        if (!bubble) return;
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
    }
};

window.ChatWidget = ChatWidget;
