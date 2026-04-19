/* Query editor component wrapping Monaco Editor */
const QueryEditor = {
    editor: null,
    completionProvider: null,
    disposables: [],

    create(container, defaultValue = '') {
        const wrapper = DOM.el('div', { className: 'sql-console-editor-wrapper' });
        const editorDiv = DOM.el('div', {
            id: 'monaco-editor',
            style: 'width: 100%; height: 100%;'
        });
        wrapper.appendChild(editorDiv);
        container.appendChild(wrapper);

        // Initialize Monaco Editor
        this._initMonaco(editorDiv, defaultValue);

        return wrapper;
    },

    setHeight(height) {
        const wrapper = DOM.$('.sql-console-editor-wrapper');
        if (wrapper) {
            wrapper.style.height = height + 'px';
        }
        if (this.editor) {
            this.editor.layout();
        }
    },

    _initMonaco(container, defaultValue) {
        // Wait for Monaco loader to be available
        if (typeof require === 'undefined' || typeof require.config === 'undefined') {
            console.error('Monaco loader not available');
            // Fallback to textarea
            this._createFallbackEditor(container, defaultValue);
            return;
        }

        // Configure Monaco loader
        const monacoConfig = { paths: { vs: '/lib/monaco-editor/min/vs' } };
        if (window.DBCLAW_ASSET_VERSION) {
            monacoConfig.urlArgs = `build=${window.DBCLAW_ASSET_VERSION}`;
        }
        require.config(monacoConfig);

        require(['vs/editor/editor.main'], () => {
            // Create editor instance
            this.editor = monaco.editor.create(container, {
                value: defaultValue,
                language: 'sql',
                theme: 'vs-dark',
                automaticLayout: true,
                minimap: { enabled: false },
                lineNumbers: 'on',
                wordWrap: 'on',
                fontSize: 14,
                fontFamily: 'JetBrains Mono, Consolas, monospace',
                scrollBeyondLastLine: false,
                renderWhitespace: 'selection',
                tabSize: 2,
                insertSpaces: true,
            });

            // Add keyboard shortcuts
            this.editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => {
                if (this.onExecute) this.onExecute();
            });

            // Store disposable
            this.disposables.push(this.editor);
        });
    },

    _createFallbackEditor(container, defaultValue) {
        // Create a simple textarea fallback
        const textarea = DOM.el('textarea', {
            className: 'sql-textarea-fallback',
            style: 'width: 100%; height: 400px; font-family: monospace; padding: 10px; background: #1e1e1e; color: #d4d4d4; border: 1px solid #3c3c3c;'
        });
        textarea.value = defaultValue;

        // Add keyboard shortcut for execute
        textarea.addEventListener('keydown', (e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                if (this.onExecute) this.onExecute();
            }
        });

        container.appendChild(textarea);
        this.fallbackTextarea = textarea;
    },

    async setSchema(datasourceId, context = {}) {
        console.log('[QueryEditor] setSchema called with datasourceId:', datasourceId);
        console.log('[QueryEditor] editor exists:', !!this.editor);
        console.log('[QueryEditor] monaco exists:', typeof monaco !== 'undefined');

        if (!this.editor || typeof monaco === 'undefined') {
            console.warn('[QueryEditor] Editor or Monaco not ready, skipping schema setup');
            return;
        }

        // Dispose old completion provider
        if (this.completionProvider) {
            console.log('[QueryEditor] Disposing old completion provider');
            this.completionProvider.dispose();
        }

        // Create new completion provider
        console.log('[QueryEditor] Creating new SQLCompletionProvider');
        const provider = new window.SQLCompletionProvider(datasourceId, window.SchemaCache, context);
        await provider.loadSchema();

        // Register completion provider
        console.log('[QueryEditor] Registering completion provider');
        this.completionProvider = monaco.languages.registerCompletionItemProvider('sql', {
            triggerCharacters: ['.', ' '],
            provideCompletionItems: async (model, position) => {
                console.log('[QueryEditor] provideCompletionItems called at position:', position);
                return await provider.provideCompletionItems(model, position);
            }
        });

        this.disposables.push(this.completionProvider);
        console.log('[QueryEditor] Schema setup complete');
    },

    getValue() {
        if (this.editor) {
            return this.editor.getValue();
        } else if (this.fallbackTextarea) {
            return this.fallbackTextarea.value;
        }
        return '';
    },

    getSelectedText() {
        if (this.editor) {
            const selection = this.editor.getSelection();
            if (selection && !selection.isEmpty()) {
                return this.editor.getModel().getValueInRange(selection);
            }
        } else if (this.fallbackTextarea) {
            const start = this.fallbackTextarea.selectionStart;
            const end = this.fallbackTextarea.selectionEnd;
            if (start !== end) {
                return this.fallbackTextarea.value.substring(start, end);
            }
        }
        return '';
    },

    setValue(value) {
        if (this.editor) {
            this.editor.setValue(value);
        } else if (this.fallbackTextarea) {
            this.fallbackTextarea.value = value;
        }
    },

    onExecute: null,

    destroy() {
        // Dispose all resources
        this.disposables.forEach(d => {
            if (d && typeof d.dispose === 'function') {
                d.dispose();
            }
        });
        this.disposables = [];
        this.editor = null;
        this.completionProvider = null;
        this.fallbackTextarea = null;
    }
};
