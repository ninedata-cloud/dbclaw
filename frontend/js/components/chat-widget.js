/* Chat widget component */
const ChatWidget = {
    ws: null,
    currentContent: '',
    isStreaming: false,

    createMessagesContainer() {
        return DOM.el('div', { className: 'chat-messages', id: 'chat-messages' });
    },

    createInputBar(onSend) {
        const bar = DOM.el('div', { className: 'chat-input-bar' });
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
                    onSend(input.value.trim());
                    input.value = '';
                    input.style.height = 'auto';
                }
            }
        });

        input.addEventListener('input', () => {
            input.style.height = 'auto';
            input.style.height = Math.min(input.scrollHeight, 120) + 'px';
        });

        const sendBtn = DOM.el('button', {
            className: 'chat-send-btn',
            id: 'chat-send-btn',
            innerHTML: '<i data-lucide="send"></i>',
            onClick: () => {
                if (!this.isStreaming) {
                    onSend(input.value.trim());
                    input.value = '';
                    input.style.height = 'auto';
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

        bar.appendChild(input);
        bar.appendChild(clearBtn);
        bar.appendChild(stopBtn);
        bar.appendChild(sendBtn);
        return bar;
    },

    addUserMessage(text) {
        const messages = DOM.$('#chat-messages');
        if (!messages) return;
        const msg = DOM.el('div', { className: 'chat-message user' });
        msg.innerHTML = `
            <div class="chat-avatar">U</div>
            <div class="chat-bubble">${this._escapeHtml(text)}</div>
        `;
        messages.appendChild(msg);
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
        const msg = DOM.$('#streaming-message');
        if (!msg) return;
        const bubble = msg.querySelector('.chat-bubble');
        bubble.innerHTML = this._renderMarkdown(this.currentContent);
        this._scrollToBottom();
    },

    addToolCall(toolName, toolArgs) {
        const msg = DOM.$('#streaming-message');
        if (!msg) return;
        const bubble = msg.querySelector('.chat-bubble');
        const toolDiv = DOM.el('div', { className: 'chat-tool-call' });
        const toolId = 'tool-' + Date.now() + '-' + Math.random().toString(36).substr(2, 9);
        toolDiv.innerHTML = `
            <div class="tool-header" style="cursor:pointer;display:flex;align-items:center;gap:4px">
                <i data-lucide="wrench" style="width:12px;height:12px"></i>
                <span class="tool-name">${toolName}</span>
                <i data-lucide="chevron-down" style="width:12px;height:12px;margin-left:auto"></i>
            </div>
            <div class="tool-details" style="display:none;margin-top:4px;font-size:12px;opacity:0.8">
                <div><strong>Arguments:</strong></div>
                <pre style="margin:4px 0;padding:4px;background:rgba(0,0,0,0.2);border-radius:4px;overflow-x:auto">${JSON.stringify(toolArgs, null, 2)}</pre>
                <div class="tool-result-container"></div>
            </div>
        `;
        toolDiv.dataset.toolId = toolId;
        const header = toolDiv.querySelector('.tool-header');
        const details = toolDiv.querySelector('.tool-details');
        const chevron = header.querySelector('[data-lucide="chevron-down"]');
        header.addEventListener('click', () => {
            const isHidden = details.style.display === 'none';
            details.style.display = isHidden ? 'block' : 'none';
            chevron.style.transform = isHidden ? 'rotate(180deg)' : '';
        });
        bubble.appendChild(toolDiv);
        lucide.createIcons();
        this._scrollToBottom();
        return toolId;
    },

    addToolResult(toolName, result) {
        const msg = DOM.$('#streaming-message');
        if (!msg) return;
        const toolDivs = msg.querySelectorAll('.chat-tool-call');
        const lastTool = toolDivs[toolDivs.length - 1];
        if (lastTool) {
            const resultContainer = lastTool.querySelector('.tool-result-container');
            if (resultContainer) {
                resultContainer.innerHTML = `
                    <div style="margin-top:8px"><strong>Result:</strong></div>
                    <pre style="margin:4px 0;padding:4px;background:rgba(0,0,0,0.2);border-radius:4px;overflow-x:auto;max-height:200px">${this._escapeHtml(result)}</pre>
                `;
            }
        }
    },

    finishAssistantMessage() {
        const msg = DOM.$('#streaming-message');
        if (msg) {
            msg.removeAttribute('id');
            const bubble = msg.querySelector('.chat-bubble');
            if (this.currentContent) {
                bubble.innerHTML = this._renderMarkdown(this.currentContent);
            }
        }
        this.currentContent = '';
        this.isStreaming = false;
        this._updateSendButton(false);
    },

    showError(text) {
        const msg = DOM.$('#streaming-message');
        if (msg) {
            msg.removeAttribute('id');
            const bubble = msg.querySelector('.chat-bubble');
            bubble.innerHTML = `<span style="color: var(--accent-red)">${this._escapeHtml(text)}</span>`;
        }
        this.isStreaming = false;
        this._updateSendButton(false);
    },

    loadMessages(messages) {
        const container = DOM.$('#chat-messages');
        if (!container) return;
        container.innerHTML = '';
        for (const msg of messages) {
            if (msg.role === 'user') {
                this.addUserMessage(msg.content);
            } else if (msg.role === 'assistant' && msg.content) {
                const div = DOM.el('div', { className: 'chat-message assistant' });
                div.innerHTML = `
                    <div class="chat-avatar">AI</div>
                    <div class="chat-bubble">${this._renderMarkdown(msg.content)}</div>
                `;
                container.appendChild(div);
            }
        }
        this._scrollToBottom();
    },

    _updateSendButton(isStreaming) {
        const sendBtn = DOM.$('#chat-send-btn');
        const stopBtn = DOM.$('#chat-stop-btn');
        if (sendBtn) {
            sendBtn.style.display = isStreaming ? 'none' : '';
            sendBtn.disabled = isStreaming;
        }
        if (stopBtn) {
            stopBtn.style.display = isStreaming ? '' : 'none';
        }
        lucide.createIcons();
    },

    _scrollToBottom() {
        const messages = DOM.$('#chat-messages');
        if (messages) {
            requestAnimationFrame(() => {
                messages.scrollTop = messages.scrollHeight;
            });
        }
    },

    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    _renderMarkdown(text) {
        try {
            if (typeof marked !== 'undefined') {
                marked.setOptions({
                    highlight: function(code, lang) {
                        if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
                            return hljs.highlight(code, { language: lang }).value;
                        }
                        return code;
                    },
                    breaks: true,
                });
                return marked.parse(text);
            }
        } catch (e) {
            // fallback
        }
        return text.replace(/\n/g, '<br>');
    }
};
