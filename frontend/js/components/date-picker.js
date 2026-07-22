/* Locale-aware date and date-time picker for the Vanilla JS application. */
(function (global) {
    const instances = new WeakMap();
    const activeInstances = new Set();

    function pad(value) {
        return String(value).padStart(2, '0');
    }

    function parseValue(value) {
        const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}))?$/);
        if (!match) return null;
        const date = new Date(
            Number(match[1]), Number(match[2]) - 1, Number(match[3]),
            Number(match[4] || 0), Number(match[5] || 0), 0, 0
        );
        if (date.getFullYear() !== Number(match[1])
            || date.getMonth() !== Number(match[2]) - 1
            || date.getDate() !== Number(match[3])) return null;
        return date;
    }

    function serialize(date, includeTime) {
        const datePart = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
        return includeTime ? `${datePart}T${pad(date.getHours())}:${pad(date.getMinutes())}` : datePart;
    }

    function sameDay(left, right) {
        return Boolean(left && right)
            && left.getFullYear() === right.getFullYear()
            && left.getMonth() === right.getMonth()
            && left.getDate() === right.getDate();
    }

    function makeButton(className, text, label) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = className;
        button.textContent = text;
        if (label) button.setAttribute('aria-label', label);
        return button;
    }

    class LocaleDatePicker {
        constructor(input) {
            this.input = input;
            this.includeTime = input.type === 'datetime-local';
            this.isOpen = false;
            this.viewDate = parseValue(input.value) || new Date();
            this.draftDate = parseValue(input.value);
            this._build();
            this._wasConnected = this.root.isConnected;
            this.sync();
            activeInstances.add(this);
        }

        _build() {
            const originalClasses = Array.from(this.input.classList);
            this.root = document.createElement('span');
            this.root.className = ['date-picker', ...originalClasses].join(' ');

            this.trigger = makeButton('date-picker-trigger', '', I18n.t('datePicker.open'));
            this.trigger.setAttribute('aria-haspopup', 'dialog');
            this.trigger.setAttribute('aria-expanded', 'false');
            this.valueLabel = document.createElement('span');
            this.valueLabel.className = 'date-picker-value';
            this.icon = document.createElement('span');
            this.icon.className = 'date-picker-icon';
            this.icon.setAttribute('aria-hidden', 'true');
            this.icon.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16"><path d="M8 2v4m8-4v4M3 10h18M5 4h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';
            this.trigger.append(this.valueLabel, this.icon);

            this.input.parentNode.insertBefore(this.root, this.input);
            this.root.append(this.input, this.trigger);
            this.input.classList.add('date-picker-native');
            this.input.setAttribute('aria-hidden', 'true');
            this.input.tabIndex = -1;

            this.popover = document.createElement('div');
            this.popover.className = 'date-picker-popover hidden';
            this.popover.setAttribute('role', 'dialog');
            this.popover.setAttribute('aria-modal', 'false');
            document.body.appendChild(this.popover);

            this.trigger.addEventListener('click', () => this.toggle());
            this.input.addEventListener('input', () => this.sync());
            this.input.addEventListener('change', () => this.sync());
            this._outsideHandler = event => {
                if (this.isOpen && !this.root.contains(event.target) && !this.popover.contains(event.target)) this.close();
            };
            this._keyHandler = event => {
                if (!this.isOpen || event.key !== 'Escape') return;
                event.preventDefault();
                this.close(true);
            };
            this._positionHandler = () => this.isOpen && this._position();
            document.addEventListener('pointerdown', this._outsideHandler);
            document.addEventListener('keydown', this._keyHandler);
            window.addEventListener('resize', this._positionHandler);
            document.addEventListener('scroll', this._positionHandler, true);
        }

        _locale() {
            return I18n.getLocale();
        }

        _placeholder() {
            return this.input.getAttribute('placeholder')
                || I18n.t(this.includeTime ? 'datePicker.selectDateTime' : 'datePicker.selectDate');
        }

        _displayValue(date) {
            if (!date) return this._placeholder();
            const options = this.includeTime
                ? { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }
                : { year: 'numeric', month: '2-digit', day: '2-digit' };
            return new Intl.DateTimeFormat(this._locale(), options).format(date);
        }

        sync() {
            const selected = parseValue(this.input.value);
            if (selected) this.viewDate = new Date(selected);
            this.valueLabel.textContent = this._displayValue(selected);
            this.root.classList.toggle('date-picker-empty', !selected);
            this.trigger.disabled = this.input.disabled || this.input.readOnly;
            this.trigger.setAttribute('aria-label', `${I18n.t('datePicker.open')}: ${this._displayValue(selected)}`);
            if (this.isOpen) this._render();
        }

        setValue(value) {
            this.input.value = value || '';
            this.sync();
        }

        toggle() {
            if (this.isOpen) this.close();
            else this.open();
        }

        open() {
            if (this.input.disabled || this.input.readOnly) return;
            for (const instance of activeInstances) {
                if (instance !== this) instance.close();
            }
            const selected = parseValue(this.input.value);
            this.draftDate = selected ? new Date(selected) : null;
            this.viewDate = selected ? new Date(selected) : new Date();
            this.isOpen = true;
            this.trigger.setAttribute('aria-expanded', 'true');
            this.popover.classList.remove('hidden');
            this._render();
            this._position();
            requestAnimationFrame(() => this.popover.querySelector('.date-picker-day-selected, .date-picker-day-today, .date-picker-day')?.focus());
        }

        close(restoreFocus = false) {
            if (!this.isOpen) return;
            this.isOpen = false;
            this.trigger.setAttribute('aria-expanded', 'false');
            this.popover.classList.add('hidden');
            if (restoreFocus) this.trigger.focus();
        }

        _position() {
            const rect = this.trigger.getBoundingClientRect();
            const width = Math.min(320, window.innerWidth - 16);
            const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
            this.popover.style.width = `${width}px`;
            this.popover.style.left = `${left}px`;
            this.popover.style.top = `${Math.max(8, Math.min(rect.bottom + 6, window.innerHeight - this.popover.offsetHeight - 8))}px`;
        }

        _isDisabled(date) {
            const key = serialize(date, false);
            const min = (this.input.min || '').slice(0, 10);
            const max = (this.input.max || '').slice(0, 10);
            return Boolean((min && key < min) || (max && key > max));
        }

        _selectDay(date) {
            const timeSource = this.draftDate || parseValue(this.input.value) || new Date();
            date.setHours(timeSource.getHours(), timeSource.getMinutes(), 0, 0);
            this.draftDate = date;
            if (this.includeTime) this._render();
            else this._commit(date);
        }

        _commit(date) {
            this.input.value = date ? serialize(date, this.includeTime) : '';
            this.input.dispatchEvent(new Event('input', { bubbles: true }));
            this.input.dispatchEvent(new Event('change', { bubbles: true }));
            this.sync();
            this.close(true);
        }

        _render() {
            const locale = this._locale();
            this.popover.setAttribute('lang', locale);
            this.popover.setAttribute('aria-label', I18n.t(this.includeTime ? 'datePicker.selectDateTime' : 'datePicker.selectDate'));
            this.popover.innerHTML = '';

            const header = document.createElement('div');
            header.className = 'date-picker-header';
            const previous = makeButton('date-picker-nav', '‹', I18n.t('datePicker.previousMonth'));
            previous.addEventListener('click', () => {
                this.viewDate.setDate(1);
                this.viewDate.setMonth(this.viewDate.getMonth() - 1);
                this._render();
            });
            const title = document.createElement('div');
            title.className = 'date-picker-title';
            title.textContent = new Intl.DateTimeFormat(locale, { year: 'numeric', month: 'long' }).format(this.viewDate);
            const next = makeButton('date-picker-nav', '›', I18n.t('datePicker.nextMonth'));
            next.addEventListener('click', () => {
                this.viewDate.setDate(1);
                this.viewDate.setMonth(this.viewDate.getMonth() + 1);
                this._render();
            });
            header.append(previous, title, next);
            this.popover.appendChild(header);

            const grid = document.createElement('div');
            grid.className = 'date-picker-grid';
            const firstDay = locale === 'en-US' ? 0 : 1;
            const referenceSunday = new Date(2023, 0, 1);
            for (let index = 0; index < 7; index += 1) {
                const weekday = document.createElement('span');
                weekday.className = 'date-picker-weekday';
                const day = new Date(referenceSunday);
                day.setDate(referenceSunday.getDate() + ((firstDay + index) % 7));
                weekday.textContent = new Intl.DateTimeFormat(locale, { weekday: 'short' }).format(day);
                grid.appendChild(weekday);
            }

            const monthStart = new Date(this.viewDate.getFullYear(), this.viewDate.getMonth(), 1);
            const leading = (monthStart.getDay() - firstDay + 7) % 7;
            const gridStart = new Date(monthStart);
            gridStart.setDate(1 - leading);
            const selected = this.draftDate;
            const today = new Date();
            for (let index = 0; index < 42; index += 1) {
                const date = new Date(gridStart);
                date.setDate(gridStart.getDate() + index);
                const button = makeButton('date-picker-day', String(date.getDate()), new Intl.DateTimeFormat(locale, { dateStyle: 'full' }).format(date));
                if (date.getMonth() !== this.viewDate.getMonth()) button.classList.add('date-picker-day-outside');
                if (sameDay(date, today)) button.classList.add('date-picker-day-today');
                if (sameDay(date, selected)) {
                    button.classList.add('date-picker-day-selected');
                    button.setAttribute('aria-pressed', 'true');
                }
                button.disabled = this._isDisabled(date);
                button.addEventListener('click', () => this._selectDay(date));
                grid.appendChild(button);
            }
            this.popover.appendChild(grid);

            if (this.includeTime) this._renderTimeControls();
            this._renderFooter();
            requestAnimationFrame(() => this._position());
        }

        _renderTimeControls() {
            const source = this.draftDate || parseValue(this.input.value) || new Date();
            const row = document.createElement('div');
            row.className = 'date-picker-time';
            const createNumber = (labelText, value, max, onChange) => {
                const label = document.createElement('label');
                label.textContent = labelText;
                const input = document.createElement('input');
                input.type = 'number';
                input.min = '0';
                input.max = String(max);
                input.value = pad(value);
                input.setAttribute('inputmode', 'numeric');
                input.addEventListener('change', () => onChange(Math.max(0, Math.min(max, Number(input.value) || 0))));
                label.appendChild(input);
                return label;
            };
            row.append(
                createNumber(I18n.t('datePicker.hour'), source.getHours(), 23, value => {
                    if (!this.draftDate) this.draftDate = new Date(source);
                    this.draftDate.setHours(value);
                }),
                document.createTextNode(':'),
                createNumber(I18n.t('datePicker.minute'), source.getMinutes(), 59, value => {
                    if (!this.draftDate) this.draftDate = new Date(source);
                    this.draftDate.setMinutes(value);
                })
            );
            this.popover.appendChild(row);
        }

        _renderFooter() {
            const footer = document.createElement('div');
            footer.className = 'date-picker-footer';
            const today = makeButton('date-picker-action', I18n.t('datePicker.today'));
            today.addEventListener('click', () => {
                const now = new Date();
                if (this.includeTime) {
                    this.draftDate = now;
                    this.viewDate = new Date(now);
                    this._render();
                } else this._commit(now);
            });
            const clear = makeButton('date-picker-action', I18n.t('datePicker.clear'));
            clear.addEventListener('click', () => this._commit(null));
            const spacer = document.createElement('span');
            spacer.className = 'date-picker-footer-spacer';
            footer.append(today, clear, spacer);
            if (this.includeTime) {
                const cancel = makeButton('date-picker-action', I18n.t('datePicker.cancel'));
                cancel.addEventListener('click', () => this.close(true));
                const apply = makeButton('date-picker-action date-picker-action-primary', I18n.t('datePicker.apply'));
                apply.disabled = !this.draftDate;
                apply.addEventListener('click', () => this.draftDate && this._commit(this.draftDate));
                footer.append(cancel, apply);
            }
            this.popover.appendChild(footer);
        }

        destroy() {
            this.close();
            document.removeEventListener('pointerdown', this._outsideHandler);
            document.removeEventListener('keydown', this._keyHandler);
            window.removeEventListener('resize', this._positionHandler);
            document.removeEventListener('scroll', this._positionHandler, true);
            this.popover.remove();
            activeInstances.delete(this);
            instances.delete(this.input);
        }
    }

    const DatePicker = {
        enhance(input) {
            if (!input || !['date', 'datetime-local'].includes(input.type)) return null;
            if (!instances.has(input)) instances.set(input, new LocaleDatePicker(input));
            return instances.get(input);
        },
        enhanceAll(root = document) {
            if (root.matches?.('input[data-date-picker]')) this.enhance(root);
            root.querySelectorAll?.('input[data-date-picker]').forEach(input => this.enhance(input));
        },
        setValue(input, value) {
            const instance = this.enhance(input);
            if (instance) instance.setValue(value);
            else if (input) input.value = value || '';
        },
        sync(input) {
            instances.get(input)?.sync();
        },
        parseValue,
        serialize
    };

    global.DatePicker = DatePicker;
    document.addEventListener('dbclaw:localechange', () => activeInstances.forEach(instance => instance.sync()));
    document.addEventListener('DOMContentLoaded', () => {
        DatePicker.enhanceAll();
        const cleanupObserver = new MutationObserver(() => {
            for (const instance of activeInstances) {
                if (instance.root.isConnected) instance._wasConnected = true;
                else if (instance._wasConnected) instance.destroy();
            }
        });
        cleanupObserver.observe(document.body, { childList: true, subtree: true });
    });
})(window);
