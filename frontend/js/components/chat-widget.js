/* Chat widget component with file upload support */
const ChatWidget = {
    ws: null,
    currentContent: '',
    isStreaming: false,
    isThinking: false,
    thinkingPhase: null,
    thinkingMessage: '',
    attachments: [],
    _streamTimeoutTimer: null,
    _streamTimeoutMs: 600 * 1000,
    diagnosticInsights: null,

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
            style: { fontSize: '14px', fontWeight: '600', color: 'var(--text-primary)', display: '' },
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
            style: { flex: '1', overflowY: 'auto', padding: '8px', display: 'block' }
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

    setDraft(text) {
        const input = DOM.$('#chat-input');
        if (!input) return;
        input.value = text || '';
        input.style.height = 'auto';
        input.style.height = Math.min(input.scrollHeight, 120) + 'px';
        input.focus();
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
        this.isThinking = false;
        this.thinkingPhase = null;
        this.thinkingMessage = '';
        const msg = DOM.el('div', { className: 'chat-message assistant', id: 'streaming-message' });
        msg.innerHTML = `
            <div class="chat-avatar">AI</div>
            <div class="chat-bubble"><div class="spinner"></div></div>
        `;
        msg.setAttribute('data-raw-content', '');
        messages.appendChild(msg);
        this._updateSendButton(true);
        this._resetStreamTimeout();
        this._scrollToBottom();
    },

    resumeAssistantMessage(content = '') {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;

        let streamingMsg = DOM.$('#streaming-message');
        if (!streamingMsg) {
            const reusable = Array.from(messages.querySelectorAll('.chat-message.assistant'))
                .reverse()
                .find((el) => {
                    if (el.classList.contains('thinking-indicator') || el.classList.contains('chat-system-message')) return false;
                    if (el.hasAttribute('data-approval-id')) return false;
                    const avatarText = (el.querySelector('.chat-avatar')?.textContent || '').trim();
                    return avatarText === 'AI';
                });
            const reusableRawContent = reusable?.getAttribute('data-raw-content') || '';

            if (reusable && reusableRawContent === (content || '')) {
                streamingMsg = reusable;
                streamingMsg.id = 'streaming-message';
                const copyBtn = streamingMsg.querySelector('.message-copy-btn');
                if (copyBtn) copyBtn.remove();
            } else {
                this.startAssistantMessage();
                streamingMsg = DOM.$('#streaming-message');
            }
        }

        if (!streamingMsg) return;

        this.currentContent = content || '';
        this.isStreaming = true;
        this.isThinking = false;
        this._updateSendButton(true);
        this._resetStreamTimeout();

        const bubble = streamingMsg.querySelector('.chat-bubble');
        if (bubble) {
            if (this.currentContent) {
                this._renderAssistantBubble(bubble, this.currentContent);
            } else {
                bubble.innerHTML = '<div class="spinner"></div>';
            }
        }

        streamingMsg.setAttribute('data-raw-content', this.currentContent);
        this._scrollToBottom();
    },

    startThinkingMessage(phase, message) {
        const streamingMsg = DOM.$('#streaming-message');
        if (!streamingMsg) return;
        this.isThinking = true;
        this.thinkingPhase = phase;
        this.thinkingMessage = message;
        const bubble = streamingMsg.querySelector('.chat-bubble');
        bubble.innerHTML = this._buildThinkingMarkup(phase, message, true);
        DOM.createIcons();
        this._scrollToBottom();
    },

    showThinkingIndicator(phase, message) {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;

        // Remove existing thinking indicator if any
        this.hideThinkingIndicator();

        this.thinkingPhase = phase;
        this.thinkingMessage = message;

        const indicator = DOM.el('div', {
            className: 'chat-message assistant thinking-indicator',
            id: 'thinking-indicator'
        });

        indicator.innerHTML = this._buildThinkingMarkup(phase, message);
        messages.appendChild(indicator);
        DOM.createIcons();
        this._scrollToBottom();
    },

    updateThinkingIndicator(phase, message) {
        this.thinkingPhase = phase;
        this.thinkingMessage = message;
        const indicator = DOM.$('#thinking-indicator');
        if (indicator) {
            indicator.innerHTML = this._buildThinkingMarkup(phase, message);
            DOM.createIcons();
        }
    },

    hideThinkingIndicator() {
        const indicator = DOM.$('#thinking-indicator');
        if (indicator) {
            indicator.remove();
        }
        this.thinkingPhase = null;
        this.thinkingMessage = '';
    },

    _renderMarkdown(content) {
        if (typeof MarkdownRenderer !== 'undefined') {
            try {
                return MarkdownRenderer.render(content || '');
            } catch (error) {
                console.error('Markdown rendering error:', error);
                return (content || '').replace(/\n/g, '<br>');
            }
        }

        return (content || '').replace(/\n/g, '<br>');
    },

    _parseAssistantSegments(content) {
        const source = content || '';
        const segments = [];
        const openTagPattern = /<think\b[^>]*>/ig;
        let cursor = 0;
        let match;

        while ((match = openTagPattern.exec(source)) !== null) {
            if (match.index > cursor) {
                segments.push({ type: 'markdown', content: source.slice(cursor, match.index) });
            }

            const thinkStart = match.index + match[0].length;
            const closeTagPattern = /<\/think>/ig;
            closeTagPattern.lastIndex = thinkStart;
            const closeMatch = closeTagPattern.exec(source);
            const thinkEnd = closeMatch ? closeMatch.index : source.length;

            segments.push({ type: 'think', content: source.slice(thinkStart, thinkEnd) });
            cursor = closeMatch ? closeMatch.index + closeMatch[0].length : source.length;
            openTagPattern.lastIndex = cursor;
        }

        if (cursor < source.length) {
            segments.push({ type: 'markdown', content: source.slice(cursor) });
        }

        return segments.length > 0 ? segments : [{ type: 'markdown', content: source }];
    },

    _buildThinkBlockHtml(content) {
        const thinkHtml = this._renderMarkdown(content || '');
        return `
            <details class="assistant-think-block">
                <summary class="assistant-think-summary">推理过程</summary>
                <div class="assistant-think-content">${thinkHtml}</div>
            </details>
        `;
    },

    _renderAssistantBubble(bubble, content) {
        if (!bubble) return;

        const segments = this._parseAssistantSegments(content);
        bubble.innerHTML = segments.map((segment) => {
            if (segment.type === 'think') {
                return this._buildThinkBlockHtml(segment.content);
            }
            return this._renderMarkdown(segment.content);
        }).join('');

        this._highlightCode(bubble);
    },

    appendContent(text) {
        this.currentContent += text;
        this._resetStreamTimeout();
        const streamingMsg = DOM.$('#streaming-message');
        if (streamingMsg) {
            const bubble = streamingMsg.querySelector('.chat-bubble');
            this._renderAssistantBubble(bubble, this.currentContent);
            streamingMsg.setAttribute('data-raw-content', this.currentContent);
            this._scrollToBottom();
        }
    },

    finishAssistantMessage() {
        this.isStreaming = false;
        this.isThinking = false;
        this._clearStreamTimeout();
        this.hideThinkingIndicator();
        const streamingMsg = DOM.$('#streaming-message');
        if (streamingMsg) {
            streamingMsg.removeAttribute('id');
            streamingMsg.setAttribute('data-raw-content', this.currentContent || '');
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
    },

    _appendSystemCard(cardElement) {
        const content = DOM.$('#tool-log-section');
        if (!content) return;
        const placeholder = content.querySelector('.tool-panel-empty');
        if (placeholder) placeholder.remove();
        content.appendChild(cardElement);
        DOM.createIcons();
        this._scrollToolPanelToBottom();
    },

    _ensureInsightState() {
        if (!this.diagnosticInsights) {
            this.diagnosticInsights = {
                state: null,
                plan: null,
                conclusion: null,
                evidence: [],
                knowledgeRefs: [],
            };
        }
    },

    _setToolPanelScaffold() {
        const content = DOM.$('#tool-panel-content');
        if (!content) return;
        content.innerHTML = `
            <div id="tool-log-section">
                <div class="tool-panel-empty" style="color: var(--text-muted); font-size: 13px;">当前会话的 skill 调用记录会显示在这里</div>
            </div>
        `;
    },

    _renderInfoCard(title, bodyHtml) {
        return `
            <div style="border:1px solid var(--border-color);border-radius:8px;padding:10px;background:var(--bg-primary);">
                <div style="font-size:12px;color:var(--text-secondary);margin-bottom:6px;">${title}</div>
                ${bodyHtml}
            </div>
        `;
    },

    _renderSimpleList(items, formatter) {
        if (!items || items.length === 0) {
            return '<div style="font-size:12px;color:var(--text-muted);">暂无</div>';
        }
        return `<div style="display:flex;flex-direction:column;gap:6px;">${items.map(formatter).join('')}</div>`;
    },

    _renderDiagnosticInsights() {
        return;
    },

    updateDiagnosisState(state) {
        this._ensureInsightState();
        this.diagnosticInsights.state = { ...(this.diagnosticInsights.state || {}), ...(state || {}) };
        this._renderDiagnosticInsights();
    },

    updateDiagnosisPlan(plan) {
        this._ensureInsightState();
        this.diagnosticInsights.plan = plan || null;
        this._renderDiagnosticInsights();
    },

    updateDiagnosisConclusion(conclusion) {
        this._ensureInsightState();
        this.diagnosticInsights.conclusion = conclusion || null;
        this.diagnosticInsights.evidence = conclusion?.evidence_refs || this.diagnosticInsights.evidence;
        if (Array.isArray(conclusion?.knowledge_refs)) {
            this.diagnosticInsights.knowledgeRefs = conclusion.knowledge_refs;
        }
        this._renderDiagnosticInsights();
    },

    addKnowledgeReference(ref) {
        this._ensureInsightState();
        const title = ref?.title || ref?.document_title;
        if (!title) return;
        const exists = this.diagnosticInsights.knowledgeRefs.some(item => item.title === title && item.document_id === ref.document_id);
        if (!exists) {
            this.diagnosticInsights.knowledgeRefs.push({
                document_id: ref.document_id || null,
                title,
            });
        }
        this._renderDiagnosticInsights();
    },

    loadDiagnosticInsights(insights) {
        this._ensureInsightState();
        this.diagnosticInsights.state = insights?.latest_state || null;
        this.diagnosticInsights.plan = insights?.latest_plan || null;
        this.diagnosticInsights.conclusion = insights?.latest_conclusion || null;
        this.diagnosticInsights.evidence = insights?.evidence || insights?.latest_conclusion?.evidence_refs || [];
        this.diagnosticInsights.knowledgeRefs = insights?.knowledge_refs || insights?.latest_conclusion?.knowledge_refs || [];
        this._renderDiagnosticInsights();
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
        this._resetStreamTimeout();
        const toolId = `tool-${toolCallId || `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`}`;
        const toolMsg = this._buildToolCard(toolId, toolName, args, '执行中', 'running');
        if (toolCallId) toolMsg.setAttribute('data-tool-call-id', toolCallId);
        this._appendSystemCard(toolMsg);
        this.pendingTools.set(toolCallId || toolName, toolId);
    },

    addToolResult(toolName, result, executionTimeMs = null, toolCallId = null, metadata = {}) {
        this._ensureMaps();
        this._resetStreamTimeout();
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

        const isError = parsedResult && typeof parsedResult === 'object' && parsedResult.success === false;
        const status = toolMsg.querySelector('.chat-tool-status');
        if (status) {
            status.className = `chat-tool-status ${isError ? 'error' : 'success'}`;
            const phaseLabel = metadata.phase ? ` · ${metadata.phase}` : '';
            status.textContent = `${isError ? '失败' : '完成'}${phaseLabel}${executionTimeMs !== null ? ` · ${executionTimeMs}ms` : ''}`;
        }

        const resultSection = toolMsg.querySelector(`#${toolId}-result`);
        if (resultSection) {
            resultSection.style.display = 'block';
            const resultContent = resultSection.querySelector('.chat-tool-content');
            const headerLines = [];
            if (metadata.action_title) headerLines.push(`动作: ${metadata.action_title}`);
            if (metadata.action_run_id) headerLines.push(`action_run_id: ${metadata.action_run_id}`);
            if (metadata.skill_execution_id) headerLines.push(`skill_execution_id: ${metadata.skill_execution_id}`);
            const decorated = headerLines.length ? `${headerLines.join('\n')}\n\n${resultStr}` : resultStr;
            if (resultContent) resultContent.textContent = decorated;
            if (isTruncated && !resultSection.querySelector('.chat-tool-truncate')) {
                const notice = DOM.el('div', { className: 'chat-tool-truncate', textContent: '结果过长，当前仅展示前 2000 个字符' });
                resultSection.appendChild(notice);
            }
        }

        this.pendingTools.delete(toolCallId || toolName);
        DOM.createIcons();
        this._scrollToolPanelToBottom();
    },

    addInlineToolStep(toolName, status, toolCallId = null) {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;

        // Remove any existing inline step for this tool
        const existing = toolCallId ? DOM.$(`[data-inline-tool-id="${toolCallId}"]`) : null;
        if (existing) existing.remove();

        const step = DOM.el('div', {
            className: 'chat-message assistant inline-tool-step',
            'data-inline-tool-id': toolCallId || toolName,
            style: { padding: '8px 12px', borderLeft: '3px solid var(--accent-blue)', margin: '4px 0 4px 48px' }
        });

        step.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px;font-size:13px;color:var(--text-secondary);">
                <i data-lucide="wrench" style="width:14px;height:14px;color:var(--accent-blue);"></i>
                <span style="font-weight:500;color:var(--text-primary);">正在执行 ${toolName}...</span>
            </div>
        `;
        messages.appendChild(step);
        DOM.createIcons();
        this._scrollToBottom();
    },

    updateInlineToolStep(toolCallId, status, result, executionTimeMs = null, metadata = {}) {
        const step = DOM.$(`[data-inline-tool-id="${toolCallId || toolName}"]`);
        if (!step) return;

        const isError = result && ((typeof result === 'object' && result.error) || (typeof result === 'string' && result.toLowerCase().includes('error')));
        const statusColor = isError ? 'var(--accent-red)' : 'var(--accent-green)';
        const statusIcon = isError ? 'x-circle' : 'check-circle';
        const statusText = status;
        const timeText = executionTimeMs !== null ? ` (${executionTimeMs}ms)` : '';

        step.innerHTML = `
            <div style="display:flex;align-items:center;gap:8px;font-size:13px;">
                <i data-lucide="${statusIcon}" style="width:14px;height:14px;color:${statusColor};"></i>
                <span style="font-weight:500;color:var(--text-primary);">${statusText}${timeText}</span>
                <span style="color:var(--text-muted);">·</span>
                <span style="color:${statusColor};">${toolCallId ? '已完成' : '完成'}</span>
            </div>
        `;
        DOM.createIcons();
        this._scrollToBottom();

        // Auto-hide after 3 seconds
        setTimeout(() => {
            if (step && step.parentNode) {
                step.style.transition = 'opacity 0.3s';
                step.style.opacity = '0.4';
            }
        }, 3000);
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
        // Remove the streaming message first (with spinner) before adding error
        const streamingMsg = DOM.$('#streaming-message');
        if (streamingMsg) streamingMsg.remove();
        this.addError(message);
        this.isStreaming = false;
        this._clearStreamTimeout();
        this._updateSendButton(false);
    },

    loadMessages(messages) {
        const container = DOM.$('#chat-messages');
        if (!container) return;
        container.innerHTML = '';
        this.resetToolPanel();
        this.pendingTools = new Map();

        for (const msg of messages) {
            if (msg.role === 'user') {
                this.addUserMessage(msg.content, msg.attachments || []);
            } else if (msg.role === 'assistant') {
                const msgEl = DOM.el('div', { className: 'chat-message assistant' });
                msgEl.setAttribute('data-raw-content', msg.content || '');
                msgEl.innerHTML = `
                    <div class="chat-avatar">AI</div>
                    <div class="chat-bubble"></div>
                `;
                this._renderAssistantBubble(msgEl.querySelector('.chat-bubble'), msg.content);
                const copyBtn = DOM.el('button', { className: 'message-copy-btn', title: '复制', innerHTML: '<i data-lucide="copy"></i>' });
                msgEl.appendChild(copyBtn);
                copyBtn.addEventListener('click', () => this._copyMessageContent(msgEl));
                container.appendChild(msgEl);
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
                    this.addToolResult(
                        data.tool_name,
                        data.result,
                        data.execution_time_ms,
                        data.tool_call_id || msg.tool_call_id || null,
                        {
                            skill_execution_id: data.skill_execution_id,
                            action_run_id: data.action_run_id,
                            action_title: data.action_title,
                            phase: data.phase,
                        }
                    );
                } catch (e) {
                    console.error('Failed to parse tool_result message:', e);
                }
            } else if (msg.role === 'approval_request') {
                try {
                    const data = JSON.parse(msg.content);
                    // Check if this approval has been resolved
                    const resolved = messages.some(m =>
                        m.role === 'approval_response' && m.content && m.content.includes(data.approval_id)
                    );
                    if (this.onApprovalRequest) {
                        this.onApprovalRequest(data, resolved);
                    }
                } catch (e) {
                    console.error('Failed to parse approval_request message:', e);
                }
            }
        }

        this._scrollToBottom();
        this._scrollToolPanelToBottom();
    },

    showToolPanelLoading() {
        this._setToolPanelScaffold();
        const toolLog = DOM.$('#tool-log-section');
        if (toolLog) {
            toolLog.innerHTML = `
                <div class="tool-panel-empty" style="color: var(--text-muted); font-size: 13px; display:flex; align-items:center; gap:8px;">
                    <div class="spinner" style="width:14px;height:14px;"></div>
                    <span>正在加载当前会话的 skill 调用记录...</span>
                </div>
            `;
        }
        this._renderDiagnosticInsights();
    },

    resetToolPanel() {
        this.diagnosticInsights = {
            state: null,
            plan: null,
            conclusion: null,
            evidence: [],
            knowledgeRefs: [],
        };
        this._setToolPanelScaffold();
        this._renderDiagnosticInsights();
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

    _resetStreamTimeout() {
        if (this._streamTimeoutTimer) {
            clearTimeout(this._streamTimeoutTimer);
            this._streamTimeoutTimer = null;
        }
        if (this.isStreaming) {
            this._streamTimeoutTimer = setTimeout(() => {
                if (this.isStreaming) {
                    console.warn('Stream timeout: no events received for', this._streamTimeoutMs / 1000, 'seconds');
                    this.showError('AI 响应超时，长时间未收到数据。请重新发送消息或刷新页面。');
                }
            }, this._streamTimeoutMs);
        }
    },

    _clearStreamTimeout() {
        if (this._streamTimeoutTimer) {
            clearTimeout(this._streamTimeoutTimer);
            this._streamTimeoutTimer = null;
        }
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

    _getThinkingMeta(phase, message) {
        const phaseMap = {
            intent_detection: {
                title: '问题分析中',
                subtitle: '识别意图和故障类型',
                icon: 'search',
                tone: 'violet',
                badge: '分析',
            },
            context_building: {
                title: '上下文装配中',
                subtitle: '汇总数据源、历史结论和环境信息',
                icon: 'database',
                tone: 'blue',
                badge: '上下文',
            },
            skill_selection: {
                title: '诊断路径规划中',
                subtitle: '选择合适的诊断技能和排查顺序',
                icon: 'git-branch',
                tone: 'cyan',
                badge: '规划',
            },
            tool_execution: {
                title: '证据收集中',
                subtitle: '正在调用数据库或主机诊断工具',
                icon: 'wrench',
                tone: 'amber',
                badge: '执行',
            },
            llm_thinking: {
                title: '结论生成中',
                subtitle: '交叉整理证据并形成诊断结论',
                icon: 'sparkles',
                tone: 'green',
                badge: '总结',
            },
        };

        const meta = phaseMap[phase] || {
            title: 'AI 思考中',
            subtitle: '正在处理当前诊断步骤',
            icon: 'bot',
            tone: 'violet',
            badge: '处理中',
        };
        return {
            ...meta,
            message: message || meta.subtitle,
        };
    },

    _buildThinkingMarkup(phase, message, compact = false) {
        const meta = this._getThinkingMeta(phase, message);
        const compactClass = compact ? ' thinking-card-compact' : '';
        return `
            <div class="thinking-card thinking-tone-${meta.tone}${compactClass}">
                <div class="thinking-card-accent"></div>
                <div class="thinking-card-main">
                    <div class="thinking-card-topline">
                        <div class="thinking-card-icon">
                            <i data-lucide="${meta.icon}"></i>
                        </div>
                        <div class="thinking-card-copy">
                            <div class="thinking-card-title-row">
                                <div class="thinking-card-title">${this._escapeHtml(meta.title)}</div>
                                <span class="thinking-card-badge">${this._escapeHtml(meta.badge)}</span>
                            </div>
                            <div class="thinking-card-subtitle">${this._escapeHtml(meta.subtitle)}</div>
                        </div>
                    </div>
                    <div class="thinking-card-message">${this._escapeHtml(meta.message)}</div>
                    <div class="thinking-card-progress">
                        <span class="thinking-card-progress-dot"></span>
                        <span class="thinking-card-progress-dot"></span>
                        <span class="thinking-card-progress-dot"></span>
                    </div>
                </div>
            </div>
        `;
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
