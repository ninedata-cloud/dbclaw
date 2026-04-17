/* Modal component */
const Modal = {
    _onHide: null,

    show({
        title,
        content,
        buttons,
        footer,
        size = 'medium',
        width,
        maxHeight,
        containerClassName = '',
        bodyClassName = '',
        onHide = null,
        closeOnOverlayClick = false,
    }) {
        const overlay = DOM.$('#modal-overlay');
        const container = DOM.$('#modal-container');

        const sizes = { small: '420px', medium: '640px', large: '880px', xlarge: '1180px' };
        const resolvedWidth = width || sizes[size] || sizes.medium;

        container.className = 'modal-container';
        if (containerClassName) {
            containerClassName.split(/\s+/).filter(Boolean).forEach(cls => container.classList.add(cls));
        }
        container.style.width = resolvedWidth;
        container.style.maxWidth = 'calc(100vw - 24px)';
        container.style.maxHeight = maxHeight || '90vh';
        this._onHide = typeof onHide === 'function' ? onHide : null;

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

        const bodyClasses = ['modal-body'];
        if (bodyClassName) {
            bodyClassName.split(/\s+/).filter(Boolean).forEach(cls => bodyClasses.push(cls));
        }
        const body = DOM.el('div', { className: bodyClasses.join(' ') });
        if (typeof content === 'string') body.innerHTML = content;
        else if (content instanceof Node) body.appendChild(content);
        container.appendChild(body);

        if (footer) {
            if (footer instanceof Node) {
                if (!footer.classList.contains('modal-footer')) {
                    footer.classList.add('modal-footer');
                }
                container.appendChild(footer);
            }
        } else if (buttons && buttons.length > 0) {
            const footerEl = DOM.el('div', { className: 'modal-footer' });
            buttons.forEach(btn => {
                const button = DOM.el('button', {
                    className: `btn btn-${btn.variant || 'secondary'}`,
                    textContent: btn.text,
                    onClick: async (event) => {
                        if (button.dataset.modalBusy === '1') {
                            return;
                        }

                        const result = btn.onClick?.(event);
                        if (!result || typeof result.then !== 'function') {
                            return result;
                        }

                        button.dataset.modalBusy = '1';
                        DOM._setControlBusy(button, true);
                        const footerButtons = Array.from(footerEl.querySelectorAll('button'));
                        footerButtons.forEach((item) => {
                            if (item === button) return;
                            item.dataset.modalOriginalDisabled = item.disabled ? '1' : '0';
                            item.disabled = true;
                        });

                        try {
                            await result;
                        } finally {
                            delete button.dataset.modalBusy;
                            if (button.isConnected) {
                                DOM._setControlBusy(button, false);
                            }
                            footerButtons.forEach((item) => {
                                if (item === button) return;
                                const originalDisabled = item.dataset.modalOriginalDisabled === '1';
                                delete item.dataset.modalOriginalDisabled;
                                if (item.isConnected) {
                                    item.disabled = originalDisabled;
                                }
                            });
                        }
                    }
                });
                footerEl.appendChild(button);
            });
            container.appendChild(footerEl);
        }

        DOM.show(overlay);
        overlay.onclick = (event) => {
            if (closeOnOverlayClick && event.target === overlay) {
                this.hide();
            }
        };
        DOM.createIcons();
    },

    hide() {
        const overlay = DOM.$('#modal-overlay');
        const onHide = this._onHide;
        this._onHide = null;
        DOM.hide(overlay);
        overlay.onclick = null;
        if (typeof onHide === 'function') {
            try {
                onHide();
            } catch (error) {
                console.error('Modal onHide failed:', error);
            }
        }
    }
};
