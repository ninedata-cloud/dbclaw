/* Query editor component wrapping Monaco Editor */
const QueryEditor = {
    editor: null,
    completionProvider: null,
    disposables: [],

    create(container, defaultValue = '') {
        const wrapper = DOM.el('div', { className: 'query-editor-wrapper' });
        const editorDiv = DOM.el('div', {
            id: 'monaco-editor',
            style: 'width: 100%; height: 400px;'
        });
        wrapper.appendChild(editorDiv);
        container.appendChild(wrapper);

        // Initialize Monaco Editor
        this._initMonaco(editorDiv, defaultValue);

        return wrapper;
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
        require.config({ paths: { vs: '/lib/monaco-editor/min/vs' } });

        require(['vs/editor/editor.main'], () => {
            // Create editor instance
            this.editor = monaco.editor.create(container, {
                value: defaultValue,
                language: 'sql',
                theme: 'vs-dark',
                automaticLayout: true,
                minimap: { enabled: true },
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

    async setSchema(datasourceId) {
        if (!this.editor || typeof monaco === 'undefined') return;

        // Dispose old completion provider
        if (this.completionProvider) {
            this.completionProvider.dispose();
        }

        // Create new completion provider
        const provider = new window.SQLCompletionProvider(datasourceId, window.SchemaCache);
        await provider.loadSchema();

        // Register completion provider
        this.completionProvider = monaco.languages.registerCompletionItemProvider('sql', {
            provideCompletionItems: async (model, position) => {
                return await provider.provideCompletionItems(model, position);
            }
        });

        this.disposables.push(this.completionProvider);
    },

    getValue() {
        if (this.editor) {
            return this.editor.getValue();
        } else if (this.fallbackTextarea) {
            return this.fallbackTextarea.value;
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
