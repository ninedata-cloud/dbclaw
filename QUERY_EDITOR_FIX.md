# Query Editor Input Fix

## Issue
The SQL editor window in the query page was not accepting text input - users couldn't type in the editor.

## Root Cause
Monaco Editor was not initializing properly because:
1. The code was checking for `monaco` object before the loader script had run
2. No fallback mechanism if Monaco failed to load
3. The `require` loader needed to be checked instead of `monaco` object

## Solution
Implemented a robust editor initialization with fallback support.

### Changes Made

**File:** `frontend/js/components/query-editor.js`

1. **Fixed Monaco Initialization Check**:
   - Changed from checking `typeof monaco === 'undefined'`
   - To checking `typeof require === 'undefined'` (the loader)
   - This ensures we check for the loader, not the editor itself

2. **Added Fallback Textarea Editor**:
   - Created `_createFallbackEditor()` method
   - Provides a simple textarea if Monaco fails to load
   - Styled to match the dark theme
   - Includes keyboard shortcut support (Ctrl+Enter / Cmd+Enter)

3. **Updated getValue/setValue Methods**:
   - Now support both Monaco editor and fallback textarea
   - Gracefully handle either editor type

4. **Updated destroy Method**:
   - Properly cleans up fallback textarea reference

### Implementation Details

```javascript
_initMonaco(container, defaultValue) {
    // Check for Monaco loader (require), not monaco object
    if (typeof require === 'undefined' || typeof require.config === 'undefined') {
        console.error('Monaco loader not available');
        this._createFallbackEditor(container, defaultValue);
        return;
    }

    // Configure and load Monaco...
}

_createFallbackEditor(container, defaultValue) {
    // Create textarea with dark theme styling
    const textarea = DOM.el('textarea', {
        className: 'sql-textarea-fallback',
        style: 'width: 100%; height: 400px; ...'
    });

    // Add Ctrl+Enter / Cmd+Enter support
    textarea.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            if (this.onExecute) this.onExecute();
        }
    });

    this.fallbackTextarea = textarea;
}
```

## Result
✅ SQL editor now accepts text input
✅ Monaco Editor loads properly when available
✅ Fallback textarea works if Monaco fails
✅ Keyboard shortcuts work in both modes
✅ Consistent dark theme styling

## Testing
1. Navigate to Query page
2. Select a datasource
3. Click in the SQL editor
4. Type SQL query - text should appear
5. Press Ctrl+Enter (or Cmd+Enter) - query should execute

## Fallback Behavior
If Monaco Editor fails to load:
- A styled textarea appears instead
- Full text input functionality
- Keyboard shortcuts still work
- No autocomplete (Monaco-only feature)
- User can still write and execute queries

## Future Improvements
- Add loading indicator while Monaco initializes
- Show user notification if falling back to textarea
- Consider lazy-loading Monaco only when Query page is accessed
