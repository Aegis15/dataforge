"""Static contract tests for the playground frontend."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_PATH = PROJECT_ROOT / "playground" / "web" / "index.html"
CONFIG_PATH = PROJECT_ROOT / "playground" / "web" / "public" / "config.js"
PACKAGE_PATH = PROJECT_ROOT / "playground" / "web" / "package.json"
SRC_DIR = PROJECT_ROOT / "playground" / "web" / "src"


def test_index_uses_relative_asset_paths_and_config_contract() -> None:
    """The static frontend must be deployable from Cloudflare assets without HF static assumptions."""
    body = INDEX_PATH.read_text(encoding="utf-8")
    assert "/static/" not in body
    assert 'src="/config.js"' in body
    assert 'src="/src/main.tsx"' in body


def test_config_js_exposes_backend_url_contract() -> None:
    """config.js defines the committed runtime contract for the backend URL."""
    body = CONFIG_PATH.read_text(encoding="utf-8")
    assert "window.__DATAFORGE_CONFIG__" in body
    assert "BACKEND_URL" in body
    assert 'BACKEND_URL: ""' not in body
    assert "https://Praneshrajan15-dataforge-playground.hf.space" in body


def test_frontend_stays_storage_free_and_capability_aware() -> None:
    """The frontend remains storage-free and consumes health capability metadata."""
    body = "\n".join(path.read_text(encoding="utf-8") for path in SRC_DIR.rglob("*") if path.is_file())
    assert "normalizeBackendUrl" in body
    assert "advanced_available" in body
    assert "ArrowRight" in body
    assert "ArrowLeft" in body


def test_frontend_has_typed_vite_quality_gates() -> None:
    """The playground frontend is a typed Vite app with unit, browser, and budget gates."""
    body = PACKAGE_PATH.read_text(encoding="utf-8")
    assert '"vite"' in body
    assert '"typescript"' in body
    assert '"@playwright/test"' in body
    assert '"@axe-core/playwright"' in body
    assert '"budget"' in body
