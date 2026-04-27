/* Frontend release version checker */
(function() {
    const POLL_INTERVAL_MS = 60 * 1000;
    const FOREGROUND_THROTTLE_MS = 30 * 1000;

    const initialInfo = window.DBCLAW_APP_INFO || {};
    const currentAssetVersion = String(
        window.DBCLAW_ASSET_VERSION || initialInfo.frontend_asset_version || ''
    ).trim();

    let lastForegroundCheckAt = 0;
    let promptedVersion = '';
    let inFlight = false;

    function getAssetVersion(appInfo) {
        return String(appInfo?.frontend_asset_version || '').trim();
    }

    function getDisplayVersion(appInfo, assetVersion) {
        const appVersion = String(appInfo?.app_version || '').trim();
        return appVersion ? (appVersion.startsWith('v') ? appVersion : `v${appVersion}`) : assetVersion;
    }

    function removeExistingPrompt() {
        const existing = document.getElementById('version-update-banner');
        if (existing) existing.remove();
    }

    function showUpdatePrompt(appInfo, assetVersion) {
        if (!assetVersion || promptedVersion === assetVersion) return;
        promptedVersion = assetVersion;
        removeExistingPrompt();

        const banner = DOM.el('div', { className: 'version-update-banner', id: 'version-update-banner' },
            DOM.el('div', { className: 'version-update-content' },
                DOM.el('strong', { textContent: '检测到新版本' }),
                DOM.el('span', { textContent: `${getDisplayVersion(appInfo, assetVersion)} 可刷新后生效` })
            ),
            DOM.el('button', {
                className: 'btn btn-primary btn-sm',
                textContent: '立即刷新',
                onClick: () => window.location.reload()
            }),
            DOM.el('button', {
                className: 'version-update-dismiss',
                textContent: '稍后',
                title: '暂不刷新',
                onClick: () => removeExistingPrompt()
            })
        );

        document.body.appendChild(banner);
    }

    async function checkVersion({ throttle = false } = {}) {
        if (!currentAssetVersion || inFlight) return;

        const now = Date.now();
        if (throttle && now - lastForegroundCheckAt < FOREGROUND_THROTTLE_MS) {
            return;
        }
        if (throttle) {
            lastForegroundCheckAt = now;
        }

        inFlight = true;
        try {
            const response = await fetch(`/api/app/info?ts=${Date.now()}`, {
                cache: 'no-store',
                credentials: 'same-origin',
                headers: { Accept: 'application/json' }
            });
            if (!response.ok) return;

            const appInfo = await response.json();
            const latestAssetVersion = getAssetVersion(appInfo);
            if (latestAssetVersion && latestAssetVersion !== currentAssetVersion) {
                showUpdatePrompt(appInfo, latestAssetVersion);
            }
        } catch (error) {
            console.warn('Failed to check frontend version:', error);
        } finally {
            inFlight = false;
        }
    }

    function start() {
        checkVersion();
        window.setInterval(() => checkVersion(), POLL_INTERVAL_MS);
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                checkVersion({ throttle: true });
            }
        });
        window.addEventListener('focus', () => checkVersion({ throttle: true }));
    }

    window.VersionChecker = { checkVersion };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start, { once: true });
    } else {
        start();
    }
})();
