/* Modal component */
const Modal = {
    show({ title, content, footer, width }) {
        const overlay = DOM.$('#modal-overlay');
        const container = DOM.$('#modal-container');
        if (width) container.style.minWidth = width;
        else container.style.minWidth = '480px';

        container.innerHTML = '';
        const header = DOM.el('div', { className: 'modal-header' },
            DOM.el('h3', { className: 'modal-title', textContent: title }),
            DOM.el('button', {
                className: 'btn-icon',
                innerHTML: '<i data-lucide="x"></i>',
                onClick: () => this.hide()
            })
        );
        container.appendChild(header);

        const body = DOM.el('div', { className: 'modal-body' });
        if (typeof content === 'string') body.innerHTML = content;
        else if (content instanceof Node) body.appendChild(content);
        container.appendChild(body);

        if (footer) {
            const foot = DOM.el('div', { className: 'modal-footer' });
            if (typeof footer === 'string') foot.innerHTML = footer;
            else if (footer instanceof Node) foot.appendChild(footer);
            container.appendChild(foot);
        }

        DOM.show(overlay);
        lucide.createIcons();

        // Close on overlay click
        overlay.onclick = (e) => {
            if (e.target === overlay) this.hide();
        };
    },

    hide() {
        const overlay = DOM.$('#modal-overlay');
        DOM.hide(overlay);
        overlay.onclick = null;
    }
};
