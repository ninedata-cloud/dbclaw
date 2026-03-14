/* Markdown rendering utility using markdown-it */
const MarkdownRenderer = {
    md: null,

    init() {
        if (typeof markdownit !== 'undefined') {
            this.md = markdownit({
                html: true,
                breaks: true,
                linkify: true,
                highlight: (str, lang) => {
                    if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
                        try {
                            return hljs.highlight(str, { language: lang }).value;
                        } catch (e) {}
                    }
                    return typeof hljs !== 'undefined' ? hljs.highlightAuto(str).value : str;
                }
            });
        }
    },

    render(markdown) {
        if (!this.md) this.init();
        return this.md ? this.md.render(markdown || '') : `<pre>${markdown || ''}</pre>`;
    }
};

// Initialize on load
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => MarkdownRenderer.init());
} else {
    MarkdownRenderer.init();
}
