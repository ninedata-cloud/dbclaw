/* Query editor component wrapping CodeMirror */
const QueryEditor = {
    editor: null,

    create(container, defaultValue = '') {
        const wrapper = DOM.el('div', { className: 'query-editor-wrapper' });
        const textarea = DOM.el('textarea', { id: 'sql-editor' });
        textarea.value = defaultValue;
        wrapper.appendChild(textarea);
        container.appendChild(wrapper);

        // Initialize CodeMirror after DOM insertion
        requestAnimationFrame(() => {
            if (typeof CodeMirror !== 'undefined') {
                this.editor = CodeMirror.fromTextArea(textarea, {
                    mode: 'text/x-sql',
                    theme: 'material-darker',
                    lineNumbers: true,
                    matchBrackets: true,
                    autoCloseBrackets: true,
                    indentWithTabs: false,
                    tabSize: 2,
                    lineWrapping: true,
                    placeholder: 'Enter SQL query...',
                    extraKeys: {
                        'Ctrl-Enter': () => {
                            if (this.onExecute) this.onExecute();
                        },
                        'Cmd-Enter': () => {
                            if (this.onExecute) this.onExecute();
                        }
                    }
                });
            }
        });

        return wrapper;
    },

    getValue() {
        if (this.editor) return this.editor.getValue();
        const textarea = DOM.$('#sql-editor');
        return textarea ? textarea.value : '';
    },

    setValue(value) {
        if (this.editor) this.editor.setValue(value);
        else {
            const textarea = DOM.$('#sql-editor');
            if (textarea) textarea.value = value;
        }
    },

    onExecute: null,

    destroy() {
        if (this.editor) {
            this.editor.toTextArea();
            this.editor = null;
        }
    }
};
