/* Chat widget component with file upload support */
const ChatWidget = {
    ws: null,
    currentContent: '',
    currentRenderSegments: [],
    isStreaming: false,
    isThinking: false,
    thinkingPhase: null,
    thinkingMessage: '',
    attachments: [],
    autoScrollEnabled: true,
    hasUnreadWhileDetached: false,
    _streamTimeoutTimer: null,
    _streamTimeoutMs: 10 * 60 * 1000,
    _bottomThresholdPx: 48,
    _ignoreScrollStateChanges: false,
    _scrollResumeRaf: null,
    _suppressMessageAutoScroll: false,
    diagnosticInsights: null,
    toolCardStates: null,

    createMessagesContainer() {
        const shell = DOM.el('div', { className: 'chat-messages-shell' });
        const messages = DOM.el('div', { className: 'chat-messages', id: 'chat-messages' });
        const scrollBtn = DOM.el('button', {
            type: 'button',
            className: 'chat-scroll-bottom-btn',
            id: 'chat-scroll-bottom-btn',
            title: I18n.t('pageCopy.chatWidget.backToBottom'),
            onClick: () => this.scrollToBottomAndResume({ smooth: true })
        });

        scrollBtn.innerHTML = I18n.t('pageCopy.chatWidget.backToBottom2');

        messages.addEventListener('scroll', () => this._handleMessagesScroll());
        shell.appendChild(messages);
        shell.appendChild(scrollBtn);
        this.resetScrollState();
        return shell;
    },

    createInputBar(onSend, getSessionId, options = {}) {
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
            placeholder: I18n.t('placeholders.chatQuestion'),
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
            title: I18n.t('pageCopy.chatWidget.attachedFiles'),
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

        bar.appendChild(attachmentPreview);
        bar.appendChild(fileInput);
        bar.appendChild(input);
        bar.appendChild(attachBtn);
        bar.appendChild(sendBtn);
        if (options.showClearButton !== false) {
            const clearBtn = DOM.el('button', {
                className: 'chat-send-btn',
                id: 'chat-clear-btn',
                innerHTML: '<i data-lucide="eraser"></i>',
                title: I18n.t('pageCopy.diagnosis.clearCurrentSession'),
                onClick: () => {
                    if (this.onClear) this.onClear();
                }
            });
            bar.appendChild(clearBtn);
        }
        bar.appendChild(stopBtn);
        return bar;
    },

    async addAttachment(file, sessionId) {
        // Check file size (10MB limit)
        if (file.size > 10 * 1024 * 1024) {
            Toast.error(I18n.t('chat.fileTooLarge'));
            return;
        }

        // Upload file
        try {
            if (!sessionId) {
                Toast.error(I18n.t('chat.noActiveSession'));
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            const response = await API.fetch(`/api/chat/sessions/${sessionId}/upload`, {
                method: 'POST',
                credentials: 'same-origin',
                body: formData
            });

            if (!response.ok) {
                throw new Error(I18n.t('chat.uploadError'));
            }

            const metadata = await response.json();
            this.attachments.push(metadata);
            this.updateAttachmentPreview();
            Toast.success(I18n.t('chat.attached'));
        } catch (error) {
            Toast.error(I18n.t('chat.uploadFailed', { message: error.message }));
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

    addUserMessage(text, attachments = [], options = {}) {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;
        const msg = DOM.el('div', { className: 'chat-message user' });
        msg.setAttribute('data-raw-content', text || '');

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

        const textHtml = text
            ? `<div class="chat-user-text">${this._escapeHtml(text)}</div>`
            : '';

        msg.innerHTML = I18n.t('pageCopy.chatWidget.uValueValue', { value0: attachmentHtml, value1: textHtml });

        // Add copy functionality
        const copyBtn = msg.querySelector('.message-copy-btn');
        copyBtn.addEventListener('click', () => this._copyMessageContent(msg));

        messages.appendChild(msg);
        DOM.createIcons();
        if (options.forceScroll !== false) {
            this.scrollToBottomAndResume({ smooth: false });
        }
    },

    startAssistantMessage() {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;
        this.currentContent = '';
        this.currentRenderSegments = [];
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
        msg.setAttribute('data-render-segments', '[]');
        messages.appendChild(msg);
        this._updateSendButton(true);
        this._resetStreamTimeout();
        this._maybeAutoScroll();
    },

    resumeAssistantMessage(content = '', renderSegments = null) {
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

        this.currentRenderSegments = this._normalizeAssistantRenderSegments(renderSegments, content || '');
        this.currentContent = (content || '') || this._extractTextFromRenderSegments(this.currentRenderSegments);
        this.isStreaming = true;
        this.isThinking = false;
        this._updateSendButton(true);
        this._resetStreamTimeout();

        const bubble = streamingMsg.querySelector('.chat-bubble');
        if (bubble) {
            if (this.currentRenderSegments.length > 0 || this.currentContent) {
                this._renderAssistantSegments(bubble, this.currentRenderSegments, this.currentContent);
            } else {
                bubble.innerHTML = '<div class="spinner"></div>';
            }
        }

        streamingMsg.setAttribute('data-raw-content', this.currentContent);
        streamingMsg.setAttribute('data-render-segments', JSON.stringify(this.currentRenderSegments || []));
        this._maybeAutoScroll();
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
        this._maybeAutoScroll();
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
        this._maybeAutoScroll();
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

    _cloneRenderSegments(segments) {
        if (!Array.isArray(segments)) return [];
        try {
            return JSON.parse(JSON.stringify(segments));
        } catch (error) {
            console.warn('Failed to clone render segments:', error);
            return [];
        }
    },

    _extractTextFromRenderSegments(segments = []) {
        if (!Array.isArray(segments)) return '';
        return segments
            .filter((segment) => segment?.type === 'markdown')
            .map((segment) => String(segment?.content || ''))
            .join('');
    },

    _normalizeAssistantRenderSegments(segments = null, fallbackContent = '') {
        if (Array.isArray(segments) && segments.length > 0) {
            return this._cloneRenderSegments(segments);
        }
        if (fallbackContent) {
            return [{
                id: 'legacy_markdown',
                type: 'markdown',
                content: fallbackContent,
            }];
        }
        return [];
    },

    _appendMarkdownRenderSegment(segments = [], text = '') {
        const normalized = this._cloneRenderSegments(segments);
        const content = String(text || '');
        if (!content) return normalized;

        const last = normalized[normalized.length - 1];
        if (last && last.type === 'markdown') {
            last.content = `${last.content || ''}${content}`;
        } else {
            normalized.push({
                id: `seg_${Date.now()}_${normalized.length + 1}`,
                type: 'markdown',
                content,
            });
        }
        return normalized;
    },

    _getToolSegmentMetadata(metadata = {}, overrides = {}) {
        return {
            ...(metadata || {}),
            ...Object.fromEntries(
                Object.entries(overrides || {}).filter(([, value]) => value !== undefined)
            ),
        };
    },

    _upsertToolRenderSegment(segments = [], toolName, toolCallId = null, patch = {}) {
        const normalized = this._cloneRenderSegments(segments);
        const lookupId = toolCallId || patch.tool_call_id || patch.id || toolName;
        let segment = normalized.find((item) => item?.type === 'tool' && (item.tool_call_id || item.id) === lookupId);

        if (!segment) {
            segment = {
                id: lookupId || `tool_${Date.now()}_${normalized.length + 1}`,
                type: 'tool',
                tool_call_id: toolCallId || patch.tool_call_id || null,
                tool_name: toolName || patch.tool_name || I18n.t('pageCopy.chatWidget.tool'),
                status: patch.status || 'running',
            };
            normalized.push(segment);
        }

        segment.tool_name = toolName || patch.tool_name || segment.tool_name || I18n.t('pageCopy.chatWidget.tool');
        if (toolCallId || patch.tool_call_id) {
            segment.tool_call_id = toolCallId || patch.tool_call_id;
        }
        Object.entries(patch || {}).forEach(([key, value]) => {
            if (value === undefined) return;
            if (value === null) {
                delete segment[key];
                return;
            }
            if (key === 'metadata') {
                segment.metadata = {
                    ...(segment.metadata || {}),
                    ...(value || {}),
                };
                return;
            }
            segment[key] = value;
        });

        return normalized;
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
        return I18n.t('pageCopy.chatWidget.reasoningProcessValue', { value0: thinkHtml });
    },

    _getThinkBlockOpenStates(container) {
        if (!container) return [];
        return Array.from(container.querySelectorAll('.assistant-think-block')).map((block) => block.open);
    },

    _getToolBlockOpenStates(container) {
        if (!container) return {};
        return Array.from(container.querySelectorAll('.chat-tool-details[data-tool-segment-id]')).reduce((states, block) => {
            const segmentId = block.getAttribute('data-tool-segment-id');
            if (segmentId) {
                states[segmentId] = Boolean(block.open);
            }
            return states;
        }, {});
    },

    _restoreThinkBlockOpenStates(container, openStates = []) {
        if (!container || !Array.isArray(openStates) || openStates.length === 0) return;
        Array.from(container.querySelectorAll('.assistant-think-block')).forEach((block, index) => {
            if (openStates[index]) {
                block.open = true;
            }
        });
    },

    _restoreToolBlockOpenStates(container, openStates = {}) {
        if (!container || !openStates || typeof openStates !== 'object') return;
        Array.from(container.querySelectorAll('.chat-tool-details[data-tool-segment-id]')).forEach((block) => {
            const segmentId = block.getAttribute('data-tool-segment-id');
            if (segmentId && openStates[segmentId]) {
                block.open = true;
            }
        });
    },

    _buildToolStateFromSegment(segment = {}) {
        const parsed = this._parseToolResultPayload(segment.result);
        const status = segment.status || (parsed.isError ? 'failed' : (segment.result ? 'completed' : 'running'));
        const statusMap = {
            running: { label: I18n.t('pageCopy.chatWidget.executing'), className: 'running' },
            completed: { label: I18n.t('pageCopy.chatWidget.complete'), className: 'success' },
            failed: { label: I18n.t('pageCopy.chatWidget.failed'), className: 'error' },
            waiting_approval: { label: I18n.t('pageCopy.chatWidget.toBeConfirmed'), className: 'pending' },
        };
        const meta = statusMap[status] || statusMap.running;
        const metadata = segment.metadata || {};
        const visualization = segment.visualization || null;
        const approvalId = metadata.approval_id || null;
        const approvalStatus = metadata.approval_status || (status === 'waiting_approval' ? 'pending' : null);

        return {
            toolId: segment.tool_call_id || segment.id || `inline-tool-${segment.tool_name || 'tool'}`,
            toolName: segment.tool_name || I18n.t('pageCopy.chatWidget.tool'),
            toolCallId: segment.tool_call_id || segment.id || null,
            args: segment.args || {},
            argsStr: segment.args ? this._stringifyData(segment.args) : '',
            statusLabel: meta.label,
            statusClass: meta.className,
            summary: segment.summary || parsed.summary || (status === 'failed' ? I18n.t('pageCopy.chatWidget.executionFailed') : I18n.t('pageCopy.chatWidget.theCallHasBeenInitiatedWaitingFor')),
            executionTimeMs: segment.execution_time_ms ?? null,
            metadata,
            displayResultStr: parsed.displayResultStr,
            resultStr: parsed.resultStr,
            isError: status === 'failed' || parsed.isError,
            isTruncated: parsed.isTruncated,
            visualization,
            approvalId,
            approvalStatus,
            riskLevel: metadata.risk_level || null,
            riskReason: metadata.risk_reason || '',
        };
    },

    _renderAssistantTextSegmentHtml(content) {
        return this._parseAssistantSegments(content).map((segment) => {
            if (segment.type === 'think') {
                return this._buildThinkBlockHtml(segment.content);
            }
            return this._renderMarkdown(segment.content);
        }).join('');
    },

    _renderAssistantSegments(bubble, renderSegments = [], fallbackContent = '') {
        if (!bubble) return;
        this._ensureMaps();
        const thinkBlockOpenStates = this._getThinkBlockOpenStates(bubble);
        const toolBlockOpenStates = this._getToolBlockOpenStates(bubble);
        const normalizedSegments = this._normalizeAssistantRenderSegments(renderSegments, fallbackContent);

        bubble.innerHTML = normalizedSegments.map((segment) => {
            if (segment?.type === 'tool') {
                const toolState = this._buildToolStateFromSegment(segment);
                if (toolState.visualization) {
                    this.toolVisualizations.set(toolState.toolCallId || toolState.toolName, {
                        toolName: toolState.toolName,
                        visualization: toolState.visualization,
                    });
                }
                return this._buildToolCardHtml(toolState, {
                    inline: true,
                    segmentId: segment.tool_call_id || segment.id || toolState.toolId,
                });
            }
            return this._renderAssistantTextSegmentHtml(segment?.content || '');
        }).join('');

        this._restoreThinkBlockOpenStates(bubble, thinkBlockOpenStates);
        this._restoreToolBlockOpenStates(bubble, toolBlockOpenStates);
        this._highlightCode(bubble);
        DOM.createIcons();
    },

    _renderAssistantBubble(bubble, content) {
        this._renderAssistantSegments(bubble, null, content);
    },

    appendContent(text) {
        this.currentContent += text;
        this.currentRenderSegments = this._appendMarkdownRenderSegment(this.currentRenderSegments, text);
        this._resetStreamTimeout();
        const streamingMsg = DOM.$('#streaming-message');
        if (streamingMsg) {
            const bubble = streamingMsg.querySelector('.chat-bubble');
            this._renderAssistantSegments(bubble, this.currentRenderSegments, this.currentContent);
            streamingMsg.setAttribute('data-raw-content', this.currentContent);
            streamingMsg.setAttribute('data-render-segments', JSON.stringify(this.currentRenderSegments || []));
            this._maybeAutoScroll();
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
            streamingMsg.setAttribute('data-render-segments', JSON.stringify(this.currentRenderSegments || []));
            // Add copy button to finished message
            const copyBtn = DOM.el('button', {
                className: 'message-copy-btn',
                title: I18n.t('pageCopy.chatWidget.copy'),
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
        panel.innerHTML = I18n.t('pageCopy.chatWidget.thisSessionHasBeenUsedValueTokens', { value0: I18n.formatNumber(usage.total_tokens), value1: I18n.formatNumber(usage.input_tokens), value2: I18n.formatNumber(usage.output_tokens), value3: contextWindow ? I18n.t('pageCopy.chatWidget.aggregateBadge2', { value0: String(Number(contextWindow)) }) : I18n.t('pageCopy.chatWidget.contextLimitNotConfigured'), value4: usageRate !== null ? I18n.t('pageCopy.chatWidget.usageValue', { value0: usageRate.toFixed(1) }) : '', value5: warningText ? `<div style="color:${tone.text};font-weight:600;">${this._escapeHtml(warningText)}</div>` : '' });
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
        if (!this.toolCardStates) this.toolCardStates = new Map();
        if (!this.toolVisualizations) this.toolVisualizations = new Map();
        if (!this.toolVisualizationModes) this.toolVisualizationModes = new Map();
    },

    _getToolLookupKey(toolName, toolCallId = null) {
        return toolCallId || toolName;
    },

    _generateToolCardId() {
        this._toolCardSeq = (this._toolCardSeq || 0) + 1;
        return `tool-card-${Date.now()}-${this._toolCardSeq}`;
    },

    _appendToolMessage(cardElement) {
        const messages = DOM.$('#chat-messages');
        if (!messages || !cardElement) return;
        messages.appendChild(cardElement);
        this._moveStreamingMessageToTailIfEmpty();
        DOM.createIcons();
        this._maybeAutoScroll();
    },

    _moveStreamingMessageToTailIfEmpty() {
        const messages = DOM.$('#chat-messages');
        const streamingMsg = DOM.$('#streaming-message');
        if (!messages || !streamingMsg) return;

        const rawContent = String(streamingMsg.getAttribute('data-raw-content') || this.currentContent || '').trim();
        if (!rawContent) {
            messages.appendChild(streamingMsg);
        }
    },

    _parseToolResultPayload(result) {
        let resultStr = result;
        let parsedResult = result;

        if (typeof result === 'string') {
            try {
                parsedResult = JSON.parse(result);
                resultStr = JSON.stringify(parsedResult, null, 2);
            } catch (error) {
                resultStr = result;
            }
        } else {
            resultStr = JSON.stringify(result, null, 2);
        }

        resultStr = resultStr == null ? '' : String(resultStr);

        const isError = Boolean(
            parsedResult &&
            typeof parsedResult === 'object' &&
            (parsedResult.success === false || parsedResult.error)
        );

        const maxPreviewLength = 2000;
        const isTruncated = resultStr.length > maxPreviewLength;
        const displayResultStr = isTruncated
            ? I18n.t('pageCopy.chatWidget.truncatedPreview', { value0: resultStr.slice(0, maxPreviewLength).trimEnd() })
            : resultStr;

        return {
            parsedResult,
            resultStr,
            displayResultStr,
            isError,
            isTruncated,
            summary: this._buildSummary(parsedResult, isError ? I18n.t('pageCopy.chatWidget.executionFailed') : I18n.t('pageCopy.chatWidget.resultsReturned')),
        };
    },

    _buildToolMetadataItems(metadata = {}) {
        const items = [
            metadata.action_title ? { label: I18n.t('pageCopy.chatWidget.action'), value: metadata.action_title } : null,
            metadata.phase ? { label: I18n.t('pageCopy.chatWidget.stage'), value: metadata.phase } : null,
            metadata.skill_execution_id ? { label: 'skill_execution_id', value: metadata.skill_execution_id, code: true } : null,
            metadata.action_run_id ? { label: 'action_run_id', value: metadata.action_run_id, code: true } : null,
        ].filter(Boolean);
        return items;
    },

    _buildToolTextSectionHtml(title, elementId, content) {
        if (!content) return '';
        return I18n.t('pageCopy.chatWidget.copyableSection', { value0: this._escapeHtml(title), value1: elementId, value2: elementId, value3: this._escapeHtml(content) });
    },

    _buildToolMetadataHtml(metadata = {}) {
        const items = this._buildToolMetadataItems(metadata);
        if (items.length === 0) return '';

        return I18n.t('pageCopy.chatWidget.metaInformationValue', { value0: items.map((item) => `
                        <div class="chat-tool-meta-item">
                            <span class="chat-tool-meta-label">${this._escapeHtml(item.label)}</span>
                            <span class="chat-tool-meta-value${item.code ? ' is-code' : ''}">${this._escapeHtml(item.value)}</span>
                        </div>
                    `).join('') });
    },

    _buildToolApprovalHtml(toolState) {
        if (!toolState?.approvalId) return '';

        const riskText = toolState.riskReason
            ? `<div class="chat-tool-approval-reason">${this._escapeHtml(toolState.riskReason)}</div>`
            : '';

        if (toolState.approvalStatus === 'pending' && toolState.statusClass === 'pending') {
            return I18n.t('pageCopy.chatWidget.approvalValueApprovalForExecutionReject', { value0: riskText, value1: this._escapeHtml(toolState.approvalId), value2: this._escapeHtml(toolState.approvalId) });
        }

        if (toolState.approvalStatus === 'approving' && toolState.statusClass === 'running') {
            return I18n.t('pageCopy.chatWidget.approvalApprovedExecuting');
        }

        if (toolState.approvalStatus === 'rejected') {
            return I18n.t('pageCopy.chatWidget.approvalExecutionRefused');
        }

        return '';
    },

    _buildToolVisualizationSectionHtml(toolState) {
        if (!toolState?.visualization || toolState.visualization.type !== 'monitoring_history') return '';

        const visualizationId = toolState.toolCallId || toolState.toolName;
        return I18n.t('pageCopy.chatWidget.monitoringChartsValue', { value0: this._escapeHtml(visualizationId), value1: this._buildToolVisualizationCard(toolState.toolName, toolState.visualization, visualizationId) });
    },

    _buildToolCardHtml(toolState, options = {}) {
        const executionTime = toolState.executionTimeMs !== null && toolState.executionTimeMs !== undefined
            ? `${toolState.executionTimeMs} ms`
            : '';
        const summaryText = toolState.summary || I18n.t('pageCopy.chatWidget.theCallHasBeenInitiatedWaitingFor');
        const detailClass = `chat-tool-details tool-tone-${toolState.statusClass || 'running'}`;
        const wrapperClass = options.inline ? 'assistant-tool-block' : 'chat-system-body';
        const shouldOpenByDefault = toolState.approvalStatus === 'pending' && toolState.statusClass === 'pending';
        const detailAttrs = [
            options.segmentId ? `data-tool-segment-id="${this._escapeHtml(options.segmentId)}"` : '',
            options.inline ? 'data-inline-tool="true"' : '',
            shouldOpenByDefault ? 'open' : '',
        ].filter(Boolean).join(' ');

        return `
            <div class="${wrapperClass}">
                <details class="${detailClass}" ${detailAttrs}>
                    <summary class="chat-tool-summary">
                        <div class="chat-tool-summary-main">
                            <div class="chat-tool-icon" aria-hidden="true"><span class="chat-tool-icon-glyph">⚙</span></div>
                            <div class="chat-tool-main">
                                <div class="chat-tool-title-row">
                                    <span class="chat-tool-name">${this._escapeHtml(toolState.toolName)}</span>
                                    <span class="chat-tool-status ${toolState.statusClass || 'running'}">${this._escapeHtml(toolState.statusLabel || I18n.t('pageCopy.chatWidget.executing'))}</span>
                                    ${executionTime ? `<span class="chat-tool-time">${this._escapeHtml(executionTime)}</span>` : ''}
                                </div>
                                <div class="chat-tool-summary-text">${this._escapeHtml(summaryText)}</div>
                            </div>
                        </div>
                    </summary>
                    <div class="chat-tool-body">
                        ${this._buildToolTextSectionHtml(I18n.t('pageCopy.chatWidget.addGinseng'), `${toolState.toolId}-args`, toolState.argsStr)}
                        ${this._buildToolTextSectionHtml(I18n.t('pageCopy.chatWidget.result'), `${toolState.toolId}-result-content`, toolState.displayResultStr)}
                        ${this._buildToolVisualizationSectionHtml(toolState)}
                        ${this._buildToolApprovalHtml(toolState)}
                        ${this._buildToolMetadataHtml(toolState.metadata)}
                        ${toolState.isTruncated ? I18n.t('pageCopy.chatWidget.resultCurrent2000') : ''}
                    </div>
                </details>
            </div>
        `;
    },

    _renderToolCard(toolId) {
        const toolMsg = DOM.$(`#${toolId}`);
        const toolState = this.toolCardStates?.get(toolId);
        if (!toolMsg || !toolState) return;

        const wasOpen = Boolean(toolMsg.querySelector('.chat-tool-details')?.open);
        toolMsg.innerHTML = this._buildToolCardHtml(toolState);

        const details = toolMsg.querySelector('.chat-tool-details');
        if (details && wasOpen) {
            details.open = true;
        }
        DOM.createIcons();
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
            return I18n.t('pageCopy.chatWidget.noneYet');
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
        if (Array.isArray(data)) return I18n.t('pageCopy.chatWidget.backValueRecords', { value0: data.length });
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

    _renderStreamingAssistantSegments() {
        const streamingMsg = DOM.$('#streaming-message');
        if (!streamingMsg) return false;
        const bubble = streamingMsg.querySelector('.chat-bubble');
        this._renderAssistantSegments(bubble, this.currentRenderSegments, this.currentContent);
        streamingMsg.setAttribute('data-raw-content', this.currentContent || '');
        streamingMsg.setAttribute('data-render-segments', JSON.stringify(this.currentRenderSegments || []));
        this._maybeAutoScroll();
        return true;
    },

    _applyInlineToolCall(toolName, args, toolCallId = null, metadata = {}) {
        const streamingMsg = DOM.$('#streaming-message');
        if (!streamingMsg) return false;
        this._ensureMaps();
        this.currentRenderSegments = this._upsertToolRenderSegment(this.currentRenderSegments, toolName, toolCallId, {
            status: 'running',
            args: args || {},
            summary: I18n.t('pageCopy.chatWidget.theCallHasBeenInitiatedWaitingFor'),
            metadata: this._getToolSegmentMetadata({}, metadata),
        });
        return this._renderStreamingAssistantSegments();
    },

    _applyInlineToolResult(toolName, result, executionTimeMs = null, toolCallId = null, metadata = {}) {
        const streamingMsg = DOM.$('#streaming-message');
        if (!streamingMsg) return false;
        this._ensureMaps();
        const parsed = this._parseToolResultPayload(result);
        const visualization = metadata.visualization || null;
        this.currentRenderSegments = this._upsertToolRenderSegment(this.currentRenderSegments, toolName, toolCallId, {
            status: parsed.isError ? 'failed' : 'completed',
            result,
            execution_time_ms: executionTimeMs,
            summary: parsed.summary || (parsed.isError ? I18n.t('pageCopy.chatWidget.executionFailed') : I18n.t('pageCopy.chatWidget.executionCompleted')),
            metadata: this._getToolSegmentMetadata({}, metadata),
            visualization,
        });
        if (visualization) {
            this.toolVisualizations.set(toolCallId || toolName, { toolName, visualization });
        }
        return this._renderStreamingAssistantSegments();
    },

    _addLegacyToolCall(toolName, args, toolCallId = null) {
        this._ensureMaps();
        this._resetStreamTimeout();
        const lookupKey = this._getToolLookupKey(toolName, toolCallId);
        let toolId = this.pendingTools.get(lookupKey);
        let toolMsg = toolId ? DOM.$(`#${toolId}`) : null;

        if (!toolId || !toolMsg) {
            toolId = this._generateToolCardId();
            toolMsg = DOM.el('div', {
                className: 'chat-message assistant chat-system-message chat-tool-message',
                id: toolId,
                'data-tool-name': toolName
            });
            if (toolCallId) toolMsg.setAttribute('data-tool-call-id', toolCallId);
            this._appendToolMessage(toolMsg);
            this.pendingTools.set(lookupKey, toolId);
        }

        const previousState = this.toolCardStates.get(toolId) || {};
        this.toolCardStates.set(toolId, {
            ...previousState,
            toolId,
            toolName,
            toolCallId,
            args,
            argsStr: this._stringifyData(args),
            statusLabel: previousState.statusLabel || I18n.t('pageCopy.chatWidget.executing'),
            statusClass: previousState.statusClass || 'running',
            summary: previousState.summary || I18n.t('pageCopy.chatWidget.theCallHasBeenInitiatedWaitingFor'),
            executionTimeMs: previousState.executionTimeMs ?? null,
            metadata: previousState.metadata || {},
            displayResultStr: previousState.displayResultStr || '',
            resultStr: previousState.resultStr || '',
            isError: previousState.isError || false,
            isTruncated: previousState.isTruncated || false,
            visualization: previousState.visualization || null,
        });
        this._renderToolCard(toolId);
        this._moveStreamingMessageToTailIfEmpty();
        this._maybeAutoScroll();
    },

    _addLegacyToolResult(toolName, result, executionTimeMs = null, toolCallId = null, metadata = {}) {
        this._ensureMaps();
        this._resetStreamTimeout();
        const lookupKey = this._getToolLookupKey(toolName, toolCallId);
        let toolId = this.pendingTools.get(lookupKey);

        if (!toolId || !DOM.$(`#${toolId}`)) {
            this.addToolCall(toolName, {}, toolCallId);
            toolId = this.pendingTools.get(lookupKey);
        }

        if (!toolId) return;

        const previousState = this.toolCardStates.get(toolId) || {};
        const parsed = this._parseToolResultPayload(result);
        const visualization = metadata.visualization || previousState.visualization || null;

        this.toolCardStates.set(toolId, {
            ...previousState,
            toolId,
            toolName,
            toolCallId,
            statusLabel: parsed.isError ? I18n.t('pageCopy.chatWidget.failed') : I18n.t('pageCopy.chatWidget.complete'),
            statusClass: parsed.isError ? 'error' : 'success',
            summary: parsed.summary || (parsed.isError ? I18n.t('pageCopy.chatWidget.executionFailed') : I18n.t('pageCopy.chatWidget.executionCompleted')),
            executionTimeMs,
            metadata: {
                ...(previousState.metadata || {}),
                ...metadata,
            },
            displayResultStr: parsed.displayResultStr,
            resultStr: parsed.resultStr,
            isError: parsed.isError,
            isTruncated: parsed.isTruncated,
            visualization,
        });

        if (visualization) {
            this.toolVisualizations.set(toolCallId || toolName, { toolName, visualization, toolId });
        }

        this._renderToolCard(toolId);
        this.pendingTools.delete(lookupKey);
        this._maybeAutoScroll();
    },

    addToolCall(toolName, args, toolCallId = null, metadata = {}) {
        this._resetStreamTimeout();
        if (this._applyInlineToolCall(toolName, args, toolCallId, metadata)) {
            return;
        }
        this._addLegacyToolCall(toolName, args, toolCallId);
    },

    addToolResult(toolName, result, executionTimeMs = null, toolCallId = null, metadata = {}) {
        this._resetStreamTimeout();
        if (this._applyInlineToolResult(toolName, result, executionTimeMs, toolCallId, metadata)) {
            return;
        }
        this._addLegacyToolResult(toolName, result, executionTimeMs, toolCallId, metadata);
    },

    addToolApprovalRequest(toolName, args, toolCallId = null, summary = '', metadata = {}) {
        const streamingMsg = DOM.$('#streaming-message');
        if (!streamingMsg) return false;
        this._resetStreamTimeout();
        this._ensureMaps();
        this.currentRenderSegments = this._upsertToolRenderSegment(this.currentRenderSegments, toolName, toolCallId, {
            status: 'waiting_approval',
            args: args || {},
            summary: summary || `${I18n.t('pageCopy.chatWidget.skills')} ${toolName} ${I18n.t('pageCopy.chatWidget.needToConfirmBeforeExecuting')}`,
            metadata: this._getToolSegmentMetadata({}, metadata),
        });
        return this._renderStreamingAssistantSegments();
    },

    _patchApprovalSegment(segments = [], approvalId, patch = {}) {
        const normalized = this._cloneRenderSegments(segments);
        let updated = false;

        normalized.forEach((segment) => {
            if (segment?.type !== 'tool') return;
            const metadata = segment.metadata || {};
            if (metadata.approval_id !== approvalId) return;

            if (patch.status !== undefined) {
                segment.status = patch.status;
            }
            if (patch.summary !== undefined) {
                if (patch.summary === null) {
                    delete segment.summary;
                } else {
                    segment.summary = patch.summary;
                }
            }
            segment.metadata = {
                ...metadata,
                ...(patch.metadata || {}),
            };
            updated = true;
        });

        return { updated, segments: normalized };
    },

    updateApprovalState(approvalId, patch = {}) {
        if (!approvalId) return false;

        let anyUpdated = false;
        const assistantMessages = Array.from(document.querySelectorAll('.chat-message.assistant'));

        assistantMessages.forEach((msgEl) => {
            if (msgEl.hasAttribute('data-approval-id')) return;
            const rawSegments = msgEl.getAttribute('data-render-segments');
            if (!rawSegments) return;

            let parsedSegments;
            try {
                parsedSegments = JSON.parse(rawSegments);
            } catch (error) {
                return;
            }

            const { updated, segments } = this._patchApprovalSegment(parsedSegments, approvalId, patch);
            if (!updated) return;

            const bubble = msgEl.querySelector('.chat-bubble');
            const rawContent = msgEl.getAttribute('data-raw-content') || this._extractTextFromRenderSegments(segments);
            msgEl.setAttribute('data-render-segments', JSON.stringify(segments));
            msgEl.setAttribute('data-raw-content', rawContent);
            this._renderAssistantSegments(bubble, segments, rawContent);

            if (msgEl.id === 'streaming-message') {
                this.currentRenderSegments = this._cloneRenderSegments(segments);
                this.currentContent = rawContent;
            } else if (!DOM.$('#streaming-message')) {
                this.currentRenderSegments = this._cloneRenderSegments(segments);
                this.currentContent = rawContent;
            }
            anyUpdated = true;
        });

        return anyUpdated;
    },

    _getVisualizationPalette(index = 0) {
        const palette = [
            { stroke: '#2f81f7', bg: 'rgba(47,129,247,0.08)', border: 'rgba(47,129,247,0.18)' },
            { stroke: '#f59e0b', bg: 'rgba(245,158,11,0.10)', border: 'rgba(245,158,11,0.2)' },
            { stroke: '#10b981', bg: 'rgba(16,185,129,0.10)', border: 'rgba(16,185,129,0.2)' },
            { stroke: '#ef4444', bg: 'rgba(239,68,68,0.08)', border: 'rgba(239,68,68,0.18)' },
            { stroke: '#8b5cf6', bg: 'rgba(139,92,246,0.08)', border: 'rgba(139,92,246,0.18)' },
            { stroke: '#06b6d4', bg: 'rgba(6,182,212,0.08)', border: 'rgba(6,182,212,0.18)' },
        ];
        return palette[index % palette.length];
    },

    _formatVisualizationTime(value) {
        if (!value) return '-';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        return `${month}-${day} ${hours}:${minutes}`;
    },

    _formatVisualizationValue(value) {
        const numericValue = Number(value);
        if (!Number.isFinite(numericValue)) return '-';

        const absValue = Math.abs(numericValue);
        let maximumFractionDigits = 2;
        if (absValue >= 1000) maximumFractionDigits = 0;
        else if (absValue >= 100) maximumFractionDigits = 1;
        else if (absValue < 1) maximumFractionDigits = 4;

        return I18n.formatNumber(numericValue, {
            minimumFractionDigits: 0,
            maximumFractionDigits,
        });
    },

    _getVisualizationModeLabel(mode) {
        const labels = {
            avg: I18n.t('pageCopy.chatWidget.average'),
            min: I18n.t('pageCopy.chatWidget.minimum'),
            max: I18n.t('pageCopy.chatWidget.maximumValue'),
            last: I18n.t('pageCopy.chatWidget.finalValue'),
        };
        return labels[mode] || mode;
    },

    _getVisualizationMetricMode(visualizationId, panelKey, metricName) {
        this._ensureMaps();
        return this.toolVisualizationModes.get(`${visualizationId}:${panelKey}:${metricName}`) || 'avg';
    },

    _setVisualizationMetricMode(visualizationId, panelKey, metricName, mode) {
        this._ensureMaps();
        this.toolVisualizationModes.set(`${visualizationId}:${panelKey}:${metricName}`, mode);
    },

    _getMetricPointValue(point, mode = 'avg') {
        if (!point || typeof point !== 'object') return null;
        const preferred = Number(point?.[mode]);
        if (Number.isFinite(preferred)) return preferred;
        const fallbackOrder = ['avg', 'last', 'max', 'min'];
        for (const key of fallbackOrder) {
            const candidate = Number(point?.[key]);
            if (Number.isFinite(candidate)) return candidate;
        }
        return null;
    },

    _parseVisualizationTimestamp(value) {
        if (!value) return null;
        const timestamp = new Date(value).getTime();
        return Number.isFinite(timestamp) ? timestamp : null;
    },

    _buildNumericAxisTicks(minValue, maxValue) {
        if (!Number.isFinite(minValue) || !Number.isFinite(maxValue)) return [];
        if (Math.abs(maxValue - minValue) < 1e-9) {
            return [maxValue, minValue, minValue];
        }
        return [maxValue, (maxValue + minValue) / 2, minValue];
    },

    _buildTimeAxisTicks(minTimestamp, maxTimestamp) {
        if (!Number.isFinite(minTimestamp) || !Number.isFinite(maxTimestamp)) return [];
        if (minTimestamp === maxTimestamp) return [minTimestamp];

        const ticks = [minTimestamp, minTimestamp + (maxTimestamp - minTimestamp) / 2, maxTimestamp];
        return ticks.filter((tick, index, allTicks) => index === 0 || Math.abs(tick - allTicks[index - 1]) > 60 * 1000);
    },

    _buildTimeSeriesChartModel(points, mode = 'avg') {
        const width = 360;
        const height = 188;
        const margin = { top: 14, right: 12, bottom: 32, left: 56 };
        const chartWidth = width - margin.left - margin.right;
        const chartHeight = height - margin.top - margin.bottom;

        const normalizedPoints = (points || [])
            .map(point => {
                const value = this._getMetricPointValue(point, mode);
                const timestamp = this._parseVisualizationTimestamp(point?.time);
                if (!Number.isFinite(value) || !Number.isFinite(timestamp)) return null;
                return {
                    ...point,
                    value,
                    timestamp,
                };
            })
            .filter(Boolean);

        if (normalizedPoints.length === 0) return null;

        const minTimestamp = Math.min(...normalizedPoints.map(point => point.timestamp));
        const maxTimestamp = Math.max(...normalizedPoints.map(point => point.timestamp));
        const rawMinValue = Math.min(...normalizedPoints.map(point => point.value));
        const rawMaxValue = Math.max(...normalizedPoints.map(point => point.value));
        const baseRange = rawMaxValue - rawMinValue;
        const valuePadding = baseRange > 0 ? baseRange * 0.08 : Math.max(Math.abs(rawMaxValue) * 0.08, 1);
        let minValue = rawMinValue - valuePadding;
        let maxValue = rawMaxValue + valuePadding;
        if (rawMinValue >= 0 && minValue < 0) minValue = 0;
        if (Math.abs(maxValue - minValue) < 1e-9) {
            maxValue = minValue + 1;
        }

        const timeRange = Math.max(1, maxTimestamp - minTimestamp);
        const valueRange = Math.max(1e-9, maxValue - minValue);
        const chartBottom = margin.top + chartHeight;
        const chartRight = margin.left + chartWidth;

        const xScale = (timestamp) => {
            if (minTimestamp === maxTimestamp) {
                return margin.left + chartWidth / 2;
            }
            return margin.left + ((timestamp - minTimestamp) / timeRange) * chartWidth;
        };
        const yScale = (value) => margin.top + chartHeight - ((value - minValue) / valueRange) * chartHeight;

        const coordinates = normalizedPoints.map(point => ({
            ...point,
            x: xScale(point.timestamp),
            y: yScale(point.value),
        }));

        const linePath = coordinates
            .map((point, index) => `${index === 0 ? 'M' : 'L'} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`)
            .join(' ');
        const areaPath = `${linePath} L ${coordinates[coordinates.length - 1].x.toFixed(2)} ${chartBottom.toFixed(2)} L ${coordinates[0].x.toFixed(2)} ${chartBottom.toFixed(2)} Z`;
        const yTicks = this._buildNumericAxisTicks(minValue, maxValue);
        const xTicks = this._buildTimeAxisTicks(minTimestamp, maxTimestamp);
        return {
            width,
            height,
            margin,
            chartWidth,
            chartHeight,
            chartBottom,
            chartRight,
            minTimestamp,
            maxTimestamp,
            minValue,
            maxValue,
            xScale,
            yScale,
            coordinates,
            linePath,
            areaPath,
            yTicks,
            xTicks,
            gradientId: `chart-fill-${String(minTimestamp)}-${String(maxTimestamp)}-${String(normalizedPoints.length)}-${mode}-${palette.stroke.replace(/[^a-zA-Z0-9]/g, '')}`,
        };
    },

    _buildTimeSeriesSvg(points, palette, mode = 'avg') {
        const chartModel = this._buildTimeSeriesChartModel(points, mode);
        if (!chartModel) {
            return I18n.t('pageCopy.chatWidget.noTrendDataYet', { value0: palette.bg });
        }

        const { width, height, margin, chartBottom, chartRight, xScale, yScale, coordinates, linePath, areaPath, yTicks, xTicks, gradientId } = chartModel;

        return I18n.t('pageCopy.chatWidget.visualizationAxes', { value0: width, value1: height, value2: gradientId, value3: palette.stroke, value4: palette.stroke, value5: width, value6: height, value7: palette.bg, value8: yTicks.map(tick => {
                    const y = yScale(tick);
                    return `
                        <line x1="${margin.left}" y1="${y.toFixed(2)}" x2="${chartRight}" y2="${y.toFixed(2)}" stroke="rgba(127,127,127,0.14)" stroke-width="1" stroke-dasharray="4 4"></line>
                        <text x="${margin.left - 8}" y="${(y + 4).toFixed(2)}" text-anchor="end" fill="var(--text-secondary)" font-size="11">${this._escapeHtml(this._formatVisualizationValue(tick))}</text>
                    `;
                }).join(''), value9: xTicks.map(tick => {
                    const x = xScale(tick);
                    return `
                        <line x1="${x.toFixed(2)}" y1="${margin.top}" x2="${x.toFixed(2)}" y2="${chartBottom}" stroke="rgba(127,127,127,0.08)" stroke-width="1"></line>
                        <text x="${x.toFixed(2)}" y="${(chartBottom + 18).toFixed(2)}" text-anchor="middle" fill="var(--text-secondary)" font-size="11">${this._escapeHtml(this._formatVisualizationTime(tick))}</text>
                    `;
                }).join(''), value10: margin.left, value11: margin.top, value12: margin.left, value13: chartBottom, value14: margin.left, value15: chartBottom, value16: chartRight, value17: chartBottom, value18: areaPath, value19: gradientId, value20: linePath, value21: palette.stroke, value22: coordinates.map((point, index) => `
                    <circle cx="${point.x.toFixed(2)}" cy="${point.y.toFixed(2)}" r="${index === coordinates.length - 1 ? '4' : '2.4'}" fill="${palette.stroke}" fill-opacity="${index === coordinates.length - 1 ? '1' : '0.8'}" stroke="#fff" stroke-width="${index === coordinates.length - 1 ? '2' : '1'}">
                        <title>${this._formatVisualizationTime(point.time)}\n${this._formatVisualizationValue(point.value)}</title>
                    </circle>
                `).join(''), value23: margin.left, value24: height - 6, value25: chartRight, value26: height - 6, value27: this._escapeHtml(this._getVisualizationModeLabel(mode)) });
    },

    _buildVisualizationMetricCard(metric, palette, visualizationId, panelKey) {
        const points = Array.isArray(metric?.points) ? metric.points : [];
        const firstPoint = points[0] || null;
        const lastPoint = points[points.length - 1] || null;
        const summary = metric?.summary || {};
        const mode = this._getVisualizationMetricMode(visualizationId, panelKey, metric?.name || '');
        const summaryItems = [
            I18n.t('pageCopy.chatWidget.latestValue', { value0: this._formatVisualizationValue(summary.last) }),
            I18n.t('pageCopy.chatWidget.averageValue', { value0: this._formatVisualizationValue(summary.avg) }),
            I18n.t('pageCopy.chatWidget.smallestValue', { value0: this._formatVisualizationValue(summary.min) }),
            I18n.t('pageCopy.chatWidget.maximumValue2', { value0: this._formatVisualizationValue(summary.max) }),
        ];
        const modeButtons = ['avg', 'min', 'max', 'last'];
        const chartModel = this._buildTimeSeriesChartModel(points, mode);
        const verticalTop = chartModel ? `${(chartModel.margin.top / chartModel.height) * 100}%` : '7.45%';
        const verticalBottom = chartModel ? `${((chartModel.height - chartModel.chartBottom) / chartModel.height) * 100}%` : '17.02%';

        return I18n.t('pageCopy.chatWidget.visualizationRangeHeader', { value0: this._escapeHtml(`${visualizationId}:${panelKey}:${metric?.name || ''}`), value1: palette.border, value2: palette.bg, value3: this._escapeHtml(metric?.label || metric?.name || 'metric'), value4: points.length, value5: this._escapeHtml(this._getVisualizationModeLabel(mode)), value6: palette.stroke, value7: palette.border, value8: this._escapeHtml(metric?.name || ''), value9: modeButtons.map(buttonMode => `
                        <button
                            type="button"
                            onclick="ChatWidget.setVisualizationMetricMode('${this._escapeHtml(visualizationId)}', '${this._escapeHtml(panelKey)}', '${this._escapeHtml(metric?.name || '')}', '${buttonMode}')"
                            style="
                                border:1px solid ${buttonMode === mode ? palette.stroke : palette.border};
                                background:${buttonMode === mode ? '#fff' : 'transparent'};
                                color:${buttonMode === mode ? palette.stroke : 'var(--text-secondary)'};
                                border-radius:999px;
                                padding:3px 10px;
                                font-size:11px;
                                cursor:pointer;
                            "
                        >${this._escapeHtml(this._getVisualizationModeLabel(buttonMode))}</button>
                    `).join(''), value10: this._escapeHtml(visualizationId), value11: this._escapeHtml(panelKey), value12: this._escapeHtml(metric?.name || ''), value13: this._escapeHtml(visualizationId), value14: this._escapeHtml(panelKey), value15: this._escapeHtml(metric?.name || ''), value16: verticalTop, value17: verticalBottom, value18: this._buildTimeSeriesSvg(points, palette, mode), value19: this._escapeHtml(this._formatVisualizationTime(firstPoint?.time)), value20: this._escapeHtml(this._formatVisualizationTime(lastPoint?.time)), value21: summaryItems.map(item => `
                        <span style="font-size:11px;color:var(--text-secondary);background:#fff;border:1px solid ${palette.border};border-radius:999px;padding:2px 8px;">
                            ${this._escapeHtml(item)}
                        </span>
                    `).join('') });
    },

    _buildVisualizationPanel(panel, panelIndex, visualizationId) {
        const metrics = Array.isArray(panel?.metrics) ? panel.metrics : [];
        if (metrics.length === 0) return '';

        const panelTitle = panel?.title || I18n.t('pageCopy.chatWidget.monitorTrends');
        const targetName = panel?.target_name || '';
        const panelKey = panel?.panel_key || `panel-${panelIndex}`;
        const hiddenMetricCount = Number(panel?.hidden_metric_count) || 0;

        return `
            <div style="border:1px solid var(--border-color);border-radius:12px;padding:12px;background:var(--bg-primary);display:flex;flex-direction:column;gap:12px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
                    <div>
                        <div style="font-size:14px;font-weight:600;color:var(--text-primary);">${this._escapeHtml(panelTitle)}</div>
                        ${targetName ? `<div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">${this._escapeHtml(targetName)}</div>` : ''}
                    </div>
                    ${hiddenMetricCount > 0 ? I18n.t('pageCopy.chatWidget.otherValueMetricSkillsresultView', { value0: hiddenMetricCount }) : ''}
                </div>
                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:10px;">
                    ${metrics.map((metric, metricIndex) => this._buildVisualizationMetricCard(metric, this._getVisualizationPalette(panelIndex + metricIndex), visualizationId, panelKey)).join('')}
                </div>
            </div>
        `;
    },

    _buildToolVisualizationCard(toolName, visualization, visualizationId) {
        const title = visualization?.title || I18n.t('pageCopy.chatWidget.skillVisualizationResults');
        const datasourceName = visualization?.datasource_name || '';
        const bucketLabel = visualization?.aggregation?.bucket_label || '';
        const startTime = this._formatVisualizationTime(visualization?.time_range?.start_time);
        const endTime = this._formatVisualizationTime(visualization?.time_range?.end_time);
        const panels = Array.isArray(visualization?.panels) ? visualization.panels : [];

        return `
            <div style="border:1px solid var(--border-color);border-radius:14px;padding:14px;background:linear-gradient(180deg, rgba(47,129,247,0.08), rgba(47,129,247,0.02));display:flex;flex-direction:column;gap:12px;">
                <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
                    <div style="display:flex;align-items:flex-start;gap:10px;">
                        <div style="width:32px;height:32px;border-radius:10px;background:rgba(47,129,247,0.12);display:flex;align-items:center;justify-content:center;color:#2f81f7;flex-shrink:0;">
                            <i data-lucide="activity"></i>
                        </div>
                        <div>
                            <div style="font-size:15px;font-weight:600;color:var(--text-primary);">${this._escapeHtml(title)}</div>
                            <div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">
                                ${this._escapeHtml(toolName)}${datasourceName ? ` · ${this._escapeHtml(datasourceName)}` : ''}
                            </div>
                        </div>
                    </div>
                    <div style="display:flex;flex-wrap:wrap;gap:6px;justify-content:flex-end;">
                        ${bucketLabel ? I18n.t('pageCopy.chatWidget.aggregateBadge', { value0: this._escapeHtml(bucketLabel) }) : ''}
                        <span style="font-size:11px;color:var(--text-secondary);background:#fff;border:1px solid var(--border-color);border-radius:999px;padding:4px 10px;">${this._escapeHtml(startTime)} ~ ${this._escapeHtml(endTime)}</span>
                    </div>
                </div>
                <div style="display:flex;flex-direction:column;gap:12px;">
                    ${panels.map((panel, index) => this._buildVisualizationPanel(panel, index, visualizationId)).join('')}
                </div>
            </div>
        `;
    },

    _renderToolVisualization(toolName, visualization, toolCallId = null) {
        if (!visualization || visualization.type !== 'monitoring_history') return;

        const visualizationId = toolCallId || toolName;
        this._ensureMaps();
        this.toolVisualizations.set(visualizationId, { toolName, visualization });
        const host = DOM.$(`[data-tool-visualization-host="${visualizationId}"]`);
        if (host) {
            host.innerHTML = this._buildToolVisualizationCard(toolName, visualization, visualizationId);
            DOM.createIcons();
        }
    },

    setVisualizationMetricMode(visualizationId, panelKey, metricName, mode) {
        this._ensureMaps();
        const visualizationState = this.toolVisualizations.get(visualizationId);
        if (!visualizationState) return;

        this._setVisualizationMetricMode(visualizationId, panelKey, metricName, mode);

        const host = DOM.$(`[data-tool-visualization-host="${visualizationId}"]`);
        if (!host) return;
        host.innerHTML = this._buildToolVisualizationCard(
            visualizationState.toolName,
            visualizationState.visualization,
            visualizationId,
        );
        DOM.createIcons();
    },

    _findVisualizationMetric(visualizationId, panelKey, metricName) {
        this._ensureMaps();
        const visualizationState = this.toolVisualizations.get(visualizationId);
        if (!visualizationState?.visualization?.panels) return null;

        const panel = visualizationState.visualization.panels.find(item => (item?.panel_key || '') === panelKey);
        if (!panel?.metrics) return null;
        const metric = panel.metrics.find(item => (item?.name || '') === metricName);
        if (!metric) return null;
        return {
            toolName: visualizationState.toolName,
            visualization: visualizationState.visualization,
            panel,
            metric,
        };
    },

    handleVisualizationHover(event, visualizationId, panelKey, metricName) {
        const chart = event?.currentTarget || event?.target?.closest?.('.chat-timeseries-chart');
        if (!chart) return;

        const metricState = this._findVisualizationMetric(visualizationId, panelKey, metricName);
        if (!metricState?.metric) return;

        const mode = this._getVisualizationMetricMode(visualizationId, panelKey, metricName);
        const chartModel = this._buildTimeSeriesChartModel(metricState.metric.points || [], mode);
        if (!chartModel || !chartModel.coordinates?.length) return;

        const rect = chart.getBoundingClientRect();
        if (!rect.width) return;

        const relativeX = Math.max(0, Math.min(rect.width, event.clientX - rect.left));
        const viewBoxX = (relativeX / rect.width) * chartModel.width;
        let nearestPoint = chartModel.coordinates[0];
        let nearestDistance = Math.abs(nearestPoint.x - viewBoxX);

        for (const point of chartModel.coordinates.slice(1)) {
            const distance = Math.abs(point.x - viewBoxX);
            if (distance < nearestDistance) {
                nearestPoint = point;
                nearestDistance = distance;
            }
        }

        const crosshair = chart.querySelector('.chat-timeseries-crosshair');
        const tooltip = chart.querySelector('.chat-timeseries-tooltip');
        if (!crosshair || !tooltip) return;

        crosshair.style.display = 'block';
        crosshair.style.left = `${(nearestPoint.x / chartModel.width) * 100}%`;

        tooltip.style.display = 'block';
        tooltip.innerHTML = I18n.t('pageCopy.chatWidget.metricSummary', { value0: this._escapeHtml(metricState.metric.label || metricState.metric.name || metricName), value1: this._escapeHtml(this._formatVisualizationTime(nearestPoint.time)), value2: this._escapeHtml(this._getVisualizationModeLabel(mode)), value3: this._escapeHtml(this._formatVisualizationValue(this._getMetricPointValue(nearestPoint, mode))), value4: this._escapeHtml(this._formatVisualizationValue(nearestPoint.min)), value5: this._escapeHtml(this._formatVisualizationValue(nearestPoint.max)), value6: this._escapeHtml(this._formatVisualizationValue(nearestPoint.avg)), value7: this._escapeHtml(this._formatVisualizationValue(nearestPoint.last)) });

        const tooltipWidth = Math.min(220, Math.max(150, rect.width * 0.48));
        tooltip.style.width = `${tooltipWidth}px`;
        const tooltipLeftPx = relativeX > rect.width / 2
            ? Math.max(8, relativeX - tooltipWidth - 14)
            : Math.min(rect.width - tooltipWidth - 8, relativeX + 14);
        tooltip.style.left = `${tooltipLeftPx}px`;
    },

    clearVisualizationHover(event) {
        const chart = event?.currentTarget || event?.target?.closest?.('.chat-timeseries-chart');
        if (!chart) return;

        const crosshair = chart.querySelector('.chat-timeseries-crosshair');
        const tooltip = chart.querySelector('.chat-timeseries-tooltip');
        if (crosshair) crosshair.style.display = 'none';
        if (tooltip) tooltip.style.display = 'none';
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
                <span style="font-size:14px;line-height:1;color:var(--accent-blue);" aria-hidden="true">⚙</span>
                <span style="font-weight:500;color:var(--text-primary);">${I18n.t('pageCopy.chatWidget.executing2')} ${toolName}...</span>
            </div>
        `;
        messages.appendChild(step);
        DOM.createIcons();
        this._maybeAutoScroll();
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
                <span style="color:${statusColor};">${toolCallId ? I18n.t('pageCopy.chatWidget.completed') : I18n.t('pageCopy.chatWidget.complete')}</span>
            </div>
        `;
        DOM.createIcons();
        this._maybeAutoScroll();

        // Auto-hide after 3 seconds
        setTimeout(() => {
            if (step && step.parentNode) {
                step.style.transition = 'opacity 0.3s';
                step.style.opacity = '0.4';
            }
        }, 3000);
    },

    copyToClipboard(elementId, event) {
        if (event) event.stopPropagation();
        const element = DOM.$(`#${elementId}`);
        if (!element) return;
        const text = element.innerText || element.textContent || '';
        this._writeTextToClipboard(text)
            .then((success) => {
                if (success) {
                    Toast.success(I18n.t('pageCopy.chatWidget.copiedToClipboard'));
                } else {
                    Toast.error(I18n.t('pageCopy.chatWidget.copyFailed'));
                }
            })
            .catch(() => Toast.error(I18n.t('pageCopy.chatWidget.copyFailed')));
    },

    addError(message, options = {}) {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;
        const errorMsg = DOM.el('div', { className: 'chat-message error' });
        errorMsg.innerHTML = `
            <div class="chat-avatar">!</div>
            <div class="chat-bubble">${this._escapeHtml(message)}</div>
        `;
        messages.appendChild(errorMsg);
        if (options.forceScroll) {
            this.scrollToBottomAndResume({ smooth: false });
        } else {
            this._maybeAutoScroll();
        }
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

    _collectEmbeddedToolCallIds(messages = []) {
        const toolCallIds = new Set();
        (messages || []).forEach((msg) => {
            if (msg?.role !== 'assistant' || !Array.isArray(msg?.render_segments)) return;
            msg.render_segments.forEach((segment) => {
                if (segment?.type === 'tool' && segment?.tool_call_id) {
                    toolCallIds.add(segment.tool_call_id);
                }
            });
        });
        return toolCallIds;
    },

    _collectEmbeddedResolvableApprovalToolCallIds(messages = []) {
        const toolCallIds = new Set();
        (messages || []).forEach((msg) => {
            if (msg?.role !== 'assistant' || !Array.isArray(msg?.render_segments)) return;
            msg.render_segments.forEach((segment) => {
                if (
                    segment?.type === 'tool' &&
                    segment?.tool_call_id &&
                    segment?.metadata?.approval_id
                ) {
                    toolCallIds.add(segment.tool_call_id);
                }
            });
        });
        return toolCallIds;
    },

    loadMessages(messages) {
        const container = DOM.$('#chat-messages');
        if (!container) return;
        container.innerHTML = '';
        this.resetScrollState();
        this.resetToolPanel();
        this.pendingTools = new Map();
        this.toolCardStates = new Map();
        this.toolVisualizations = new Map();
        this.toolVisualizationModes = new Map();
        this.currentRenderSegments = [];
        this._suppressMessageAutoScroll = true;
        const embeddedToolCallIds = this._collectEmbeddedToolCallIds(messages);
        const embeddedResolvableApprovalToolCallIds = this._collectEmbeddedResolvableApprovalToolCallIds(messages);
        try {
            for (const msg of messages) {
                if (msg.role === 'user') {
                    this.addUserMessage(msg.content, msg.attachments || [], { forceScroll: false });
                } else if (msg.role === 'assistant') {
                    const msgEl = DOM.el('div', { className: 'chat-message assistant' });
                    msgEl.setAttribute('data-raw-content', msg.content || '');
                    msgEl.setAttribute('data-render-segments', JSON.stringify(msg.render_segments || []));
                    msgEl.innerHTML = `
                        <div class="chat-avatar">AI</div>
                        <div class="chat-bubble"></div>
                    `;
                    if (Array.isArray(msg.render_segments) && msg.render_segments.length > 0) {
                        this._renderAssistantSegments(msgEl.querySelector('.chat-bubble'), msg.render_segments, msg.content);
                    } else {
                        this._renderAssistantBubble(msgEl.querySelector('.chat-bubble'), msg.content);
                    }
                    const copyBtn = DOM.el('button', { className: 'message-copy-btn', title: I18n.t('pageCopy.chatWidget.copy'), innerHTML: '<i data-lucide="copy"></i>' });
                    msgEl.appendChild(copyBtn);
                    copyBtn.addEventListener('click', () => this._copyMessageContent(msgEl));
                    container.appendChild(msgEl);
                } else if (msg.role === 'tool_call') {
                    try {
                        const data = JSON.parse(msg.content);
                        const toolCallId = data.tool_call_id || msg.tool_call_id || null;
                        if (toolCallId && embeddedToolCallIds.has(toolCallId)) {
                            continue;
                        }
                        this._addLegacyToolCall(data.tool_name, data.tool_args, toolCallId);
                    } catch (e) {
                        console.error('Failed to parse tool_call message:', e);
                    }
                } else if (msg.role === 'tool_result') {
                    try {
                        const data = JSON.parse(msg.content);
                        const toolCallId = data.tool_call_id || msg.tool_call_id || null;
                        if (toolCallId && embeddedToolCallIds.has(toolCallId)) {
                            continue;
                        }
                        this._addLegacyToolResult(
                            data.tool_name,
                            data.result,
                            data.execution_time_ms,
                            toolCallId,
                            {
                                skill_execution_id: data.skill_execution_id,
                                action_run_id: data.action_run_id,
                                action_title: data.action_title,
                                phase: data.phase,
                                visualization: data.visualization,
                            }
                        );
                    } catch (e) {
                        console.error('Failed to parse tool_result message:', e);
                    }
                } else if (msg.role === 'approval_request') {
                    try {
                        const data = JSON.parse(msg.content);
                        const toolCallId = data.tool_call_id || null;
                        const resolved = messages.some(m =>
                            m.role === 'approval_response' && m.content && m.content.includes(data.approval_id)
                        );
                        if (
                            (toolCallId && embeddedResolvableApprovalToolCallIds.has(toolCallId)) ||
                            (resolved && toolCallId && embeddedToolCallIds.has(toolCallId))
                        ) {
                            continue;
                        }
                        if (this.onApprovalRequest) {
                            this.onApprovalRequest(data, resolved);
                        }
                    } catch (e) {
                        console.error('Failed to parse approval_request message:', e);
                    }
                }
            }
        } finally {
            this._suppressMessageAutoScroll = false;
        }

        this.scrollToBottomAndResume({ smooth: false });
    },

    resetToolPanel() {
        this.diagnosticInsights = {
            state: null,
            plan: null,
            conclusion: null,
            evidence: [],
            knowledgeRefs: [],
        };
        this.currentRenderSegments = [];
        this.pendingTools = new Map();
        this.toolCardStates = new Map();
        this.toolVisualizations = new Map();
        this.toolVisualizationModes = new Map();
    },

    getCurrentRenderSegments() {
        return this._cloneRenderSegments(this.currentRenderSegments);
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
                    this.showError(I18n.t('pageCopy.chatWidget.aiTheResponseTimedOutAndNo'));
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

    resetScrollState() {
        this.autoScrollEnabled = true;
        this.hasUnreadWhileDetached = false;
        this._suppressMessageAutoScroll = false;
        this._cancelScrollResumeTracking();
        this._updateScrollBottomButton();
    },

    _cancelScrollResumeTracking() {
        this._ignoreScrollStateChanges = false;
        if (this._scrollResumeRaf) {
            cancelAnimationFrame(this._scrollResumeRaf);
            this._scrollResumeRaf = null;
        }
    },

    _isNearBottom() {
        const messages = DOM.$('#chat-messages');
        if (!messages) return true;
        const distanceToBottom = messages.scrollHeight - messages.scrollTop - messages.clientHeight;
        return distanceToBottom <= this._bottomThresholdPx;
    },

    _handleMessagesScroll() {
        const nearBottom = this._isNearBottom();
        if (this._ignoreScrollStateChanges && !nearBottom) {
            return;
        }

        if (nearBottom) {
            this._cancelScrollResumeTracking();
            this.autoScrollEnabled = true;
            this.hasUnreadWhileDetached = false;
        } else {
            this.autoScrollEnabled = false;
        }

        this._updateScrollBottomButton();
    },

    _scrollToBottom(options = {}) {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;

        const smooth = options.smooth === true;
        const top = messages.scrollHeight;

        if (smooth) {
            if (typeof messages.scrollTo !== 'function') {
                messages.scrollTop = top;
                return;
            }

            this._cancelScrollResumeTracking();
            this._ignoreScrollStateChanges = true;
            messages.scrollTo({ top, behavior: 'smooth' });
            const startedAt = (typeof performance !== 'undefined' && typeof performance.now === 'function')
                ? performance.now()
                : Date.now();
            const waitForBottom = () => {
                if (!this._ignoreScrollStateChanges) return;

                const now = (typeof performance !== 'undefined' && typeof performance.now === 'function')
                    ? performance.now()
                    : Date.now();

                if (this._isNearBottom() || now - startedAt > 700) {
                    this._cancelScrollResumeTracking();
                    this._handleMessagesScroll();
                    return;
                }

                this._scrollResumeRaf = requestAnimationFrame(waitForBottom);
            };

            this._scrollResumeRaf = requestAnimationFrame(waitForBottom);
            return;
        }

        messages.scrollTop = top;
    },

    scrollToBottomAndResume(options = {}) {
        const smooth = options.smooth === true;
        this.autoScrollEnabled = true;
        this.hasUnreadWhileDetached = false;
        this._updateScrollBottomButton();
        this._scrollToBottom({ smooth });
    },

    _maybeAutoScroll(options = {}) {
        if (this._suppressMessageAutoScroll && !options.force) return;

        if (options.force) {
            this.scrollToBottomAndResume({ smooth: options.smooth === true });
            return;
        }

        if (this.autoScrollEnabled || this._isNearBottom()) {
            this.autoScrollEnabled = true;
            this.hasUnreadWhileDetached = false;
            this._updateScrollBottomButton();
            this._scrollToBottom({ smooth: false });
            return;
        }

        this.hasUnreadWhileDetached = true;
        this._updateScrollBottomButton();
    },

    _updateScrollBottomButton() {
        const button = DOM.$('#chat-scroll-bottom-btn');
        if (!button) return;

        const shouldShow = !this.autoScrollEnabled || this.hasUnreadWhileDetached;
        const label = button.querySelector('.chat-scroll-bottom-label');
        const text = this.hasUnreadWhileDetached ? I18n.t('pageCopy.chatWidget.thereIsNewContentReturnToThe') : I18n.t('pageCopy.chatWidget.backToBottom');

        button.classList.toggle('visible', shouldShow);
        button.classList.toggle('has-unread', this.hasUnreadWhileDetached);
        button.tabIndex = shouldShow ? 0 : -1;
        button.setAttribute('aria-hidden', shouldShow ? 'false' : 'true');
        button.title = text;
        if (label) label.textContent = text;
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
                title: I18n.t('pageCopy.chatWidget.problemAnalysis'),
                subtitle: I18n.t('pageCopy.chatWidget.identifyIntentAndFailureTypes'),
                icon: 'search',
                tone: 'violet',
                badge: I18n.t('pageCopy.chatWidget.analysis'),
            },
            context_building: {
                title: I18n.t('pageCopy.chatWidget.contextualAssembly'),
                subtitle: I18n.t('pageCopy.chatWidget.aggregateDatasourcesHistoricalConclusionsAndEnvironmentalInformation'),
                icon: 'database',
                tone: 'blue',
                badge: I18n.t('pageCopy.chatWidget.context'),
            },
            skill_selection: {
                title: I18n.t('pageCopy.chatWidget.diagnosticPathPlanning'),
                subtitle: I18n.t('pageCopy.chatWidget.chooseAppropriateDiagnosticSkillsAndSequencing'),
                icon: 'git-branch',
                tone: 'cyan',
                badge: I18n.t('pageCopy.chatWidget.planning'),
            },
            tool_execution: {
                title: I18n.t('pageCopy.chatWidget.evidenceIsBeingCollected'),
                subtitle: I18n.t('pageCopy.chatWidget.callingDatabaseOrHostDiagnosticTool'),
                icon: 'wrench',
                tone: 'amber',
                badge: I18n.t('pageCopy.chatWidget.execute'),
            },
            llm_thinking: {
                title: I18n.t('pageCopy.chatWidget.conclusionIsBeingGenerated'),
                subtitle: I18n.t('pageCopy.chatWidget.crossCheckEvidenceAndFormulateDiagnosticConclusions'),
                icon: 'sparkles',
                tone: 'green',
                badge: I18n.t('pageCopy.chatWidget.summary'),
            },
        };

        const meta = phaseMap[phase] || {
            title: I18n.t('pageCopy.chatWidget.aiThinking'),
            subtitle: I18n.t('pageCopy.chatWidget.processingCurrentDiagnosticStep'),
            icon: 'bot',
            tone: 'violet',
            badge: I18n.t('pageCopy.chatWidget.processing'),
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

    async _writeTextToClipboard(text) {
        const value = String(text || '');
        if (!value) return false;

        if (navigator.clipboard && navigator.clipboard.writeText) {
            try {
                await navigator.clipboard.writeText(value);
                return true;
            } catch (error) {
                console.warn('Clipboard API write failed, falling back to execCommand:', error);
            }
        }

        const textarea = document.createElement('textarea');
        textarea.value = value;
        textarea.setAttribute('readonly', '');
        textarea.style.position = 'fixed';
        textarea.style.top = '-9999px';
        textarea.style.left = '-9999px';
        textarea.style.opacity = '0';
        textarea.style.pointerEvents = 'none';
        document.body.appendChild(textarea);

        const selection = document.getSelection ? document.getSelection() : null;
        const originalRanges = [];
        if (selection) {
            for (let i = 0; i < selection.rangeCount; i += 1) {
                originalRanges.push(selection.getRangeAt(i));
            }
        }

        textarea.focus();
        textarea.select();
        textarea.setSelectionRange(0, textarea.value.length);

        let copied = false;
        try {
            copied = document.execCommand('copy');
        } catch (error) {
            console.warn('execCommand copy failed:', error);
            copied = false;
        }

        document.body.removeChild(textarea);

        if (selection) {
            selection.removeAllRanges();
            originalRanges.forEach((range) => selection.addRange(range));
        }

        return copied;
    },

    _copyMessageContent(messageElement) {
        const bubble = messageElement.querySelector('.chat-bubble');
        if (!bubble) return;
        const rawContent = messageElement.getAttribute('data-raw-content');
        const text = (rawContent && rawContent.trim()) || bubble.innerText || bubble.textContent || '';
        this._writeTextToClipboard(text).then((success) => {
            if (!success) {
                Toast.error(I18n.t('pageCopy.chatWidget.copyFailed'));
                return;
            }
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
            Toast.success(I18n.t('pageCopy.chatWidget.copiedToClipboard'));
        }).catch(err => {
            console.error('Failed to copy:', err);
            Toast.error(I18n.t('pageCopy.chatWidget.copyFailed'));
        });
    }
};

window.ChatWidget = ChatWidget;
