"""Deployment contract tests for the Cloudflare-hosted frontend."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from playground.api.app import _build_cors_origins, _build_cors_origin_regex

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WRANGLER_PATH = PROJECT_ROOT / "wrangler.toml"
ASSETSIGNORE_PATH = PROJECT_ROOT / "playground" / "web" / ".assetsignore"
HEADERS_PATH = PROJECT_ROOT / "playground" / "web" / "_headers"
RENDERER_PATH = PROJECT_ROOT / "scripts" / "playground" / "render_web_config.py"
VERIFIER_PATH = PROJECT_ROOT / "scripts" / "playground" / "verify_frontend_deploy.py"


def _load_renderer_module():
    """Load the config renderer without requiring package imports."""
    spec = importlib.util.spec_from_file_location("render_web_config", RENDERER_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_wrangler_config_declares_assets_only_worker() -> None:
    """The frontend deploy contract names the Worker and assets directory explicitly."""
    body = WRANGLER_PATH.read_text(encoding="utf-8")
    assert 'name = "dataforge"' in body
    assert 'compatibility_date = "2026-04-27"' in body
    assert 'directory = "./playground/web"' in body
    assert 'not_found_handling = "404-page"' in body


def test_assetsignore_and_headers_protect_runtime_config() -> None:
    """Non-public docs stay out of the asset upload and config.js stays uncached."""
    assert "DEPLOY.md" in ASSETSIGNORE_PATH.read_text(encoding="utf-8")
    headers = HEADERS_PATH.read_text(encoding="utf-8")
    assert "/config.js" in headers
    assert "Cache-Control: no-store" in headers
    assert VERIFIER_PATH.exists()


def test_renderer_writes_normalized_backend_url(tmp_path: Path) -> None:
    """The config renderer strips trailing slashes and writes valid JS."""
    module = _load_renderer_module()
    output_path = tmp_path / "config.js"

    rendered = module.render_config(
        "https://Praneshrajan15-data-quality-env.hf.space/",
        output_path=output_path,
    )

    body = rendered.read_text(encoding="utf-8")
    assert '"https://Praneshrajan15-data-quality-env.hf.space"' in body
    assert 'https://Praneshrajan15-data-quality-env.hf.space/"' not in body


@pytest.mark.parametrize(
    "value",
    [
        "",
        "http://Praneshrajan15-data-quality-env.hf.space",
        "https://Praneshrajan15-data-quality-env.hf.space?preview=true",
    ],
)
def test_renderer_rejects_invalid_backend_urls(value: str) -> None:
    """The config renderer fails closed on missing or unsafe backend URLs."""
    module = _load_renderer_module()
    with pytest.raises(ValueError):
        module.normalize_backend_url(value)


def test_cors_helpers_allow_workers_dev_and_explicit_origins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The backend allowlist covers workers.dev plus explicit custom domains."""
    monkeypatch.setenv(
        "DATAFORGE_PLAYGROUND_ORIGINS",
        "https://demo.example.com, https://dataforge.example.com",
    )
    explicit = _build_cors_origins()
    regex = _build_cors_origin_regex()

    assert explicit == ["https://demo.example.com", "https://dataforge.example.com"]
    assert re.fullmatch(regex, "https://dataforge.account-subdomain.workers.dev") is not None
