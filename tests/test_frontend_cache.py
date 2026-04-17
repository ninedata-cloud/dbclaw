from fastapi.testclient import TestClient

from backend.app import add_asset_version_to_url, app


client = TestClient(app)


def test_app_info_includes_frontend_asset_version_and_no_store_headers():
    response = client.get("/api/app/info")

    assert response.status_code == 200
    payload = response.json()
    assert payload["frontend_asset_version"]
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-dbclaw-asset-version"] == payload["frontend_asset_version"]


def test_index_html_injects_versioned_static_asset_urls():
    response = client.get("/")

    assert response.status_code == 200
    html = response.text
    asset_version = response.headers["x-dbclaw-asset-version"]

    assert response.headers["cache-control"] == "no-store"
    assert "window.DBCLAW_APP_INFO" in html
    assert f'window.DBCLAW_ASSET_VERSION = "{asset_version}"' in html
    assert f'/js/app.js?build={asset_version}' in html
    assert f'/css/main.css?build={asset_version}' in html
    assert f'/css/query.css?v=2&build={asset_version}' in html
    assert f'/lib/chart.js/dist/chart.umd.js?build={asset_version}' in html
    assert f'/assets/logo-1.svg?build={asset_version}' in html


def test_static_assets_use_immutable_cache_only_with_build_parameter():
    versioned = client.get("/js/app.js?build=test")
    unversioned = client.get("/js/app.js")

    assert versioned.status_code == 200
    assert versioned.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert unversioned.status_code == 200
    assert unversioned.headers["cache-control"] == "no-cache, max-age=0, must-revalidate"


def test_add_asset_version_to_url_does_not_double_encode_safe_version():
    version = "dev-2026-04-15T12%3A00%3A00Z"

    assert add_asset_version_to_url("/js/app.js", version) == f"/js/app.js?build={version}"
    assert add_asset_version_to_url("/css/query.css?v=2", version) == f"/css/query.css?v=2&build={version}"
