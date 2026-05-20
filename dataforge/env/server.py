"""FastAPI server for the DataForge RL environment.

Provides OpenEnv-compatible HTTP endpoints:
    POST /reset    — Start a new episode
    POST /step     — Execute an action
    GET  /state    — Return current state snapshot
    POST /close    — No-op shutdown
    GET  /health   — Liveness check
    GET  /metadata — Environment metadata
    GET  /schema   — Action/observation JSON schemas
"""

from __future__ import annotations

import logging
import os
from threading import RLock
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import TypeAdapter

from dataforge.agent.tool_actions import Action
from dataforge.env.environment import DataForgeEnv, EnvState
from dataforge.env.observation import DataForgeObservation
from dataforge.http.problem import problem_exception_handler
from dataforge.observability import configure_fastapi_observability

logger = logging.getLogger("dataforge.env.server")


def _build_cors_origins() -> list[str]:
    """Build the explicit OpenEnv CORS allowlist from the environment."""
    raw_origins = os.environ.get("DATAFORGE_OPENENV_ORIGINS", "")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


def _build_cors_origin_regex() -> str | None:
    """Allow local browser development only when explicitly enabled."""
    if os.environ.get("DATAFORGE_OPENENV_DEV") != "1":
        return None
    return r"^http://(?:localhost|127(?:\.\d{1,3}){3})(?::\d+)?$"


app = FastAPI(
    title="DataForge Environment",
    description="OpenEnv-compatible RL environment for data-quality repair.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_build_cors_origins(),
    allow_origin_regex=_build_cors_origin_regex(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.add_exception_handler(HTTPException, problem_exception_handler)
configure_fastapi_observability(app, service_name="dataforge-openenv")

_registry_lock = RLock()
_default_env = DataForgeEnv()
_sessions: dict[str, DataForgeEnv] = {}


def _get_env(episode_id: str | None) -> DataForgeEnv:
    """Resolve an environment by episode id, preserving legacy no-id behavior."""
    if not episode_id:
        return _default_env
    with _registry_lock:
        try:
            return _sessions[episode_id]
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": "episode_not_found", "episode_id": episode_id},
            ) from exc


def _remember_env(env: DataForgeEnv, episode_id: str) -> None:
    """Register a session and update the legacy default environment."""
    global _default_env
    with _registry_lock:
        _sessions[episode_id] = env
        _default_env = env


@app.post("/reset")
async def reset(seed: int | None = None) -> dict[str, Any]:
    """Reset the environment for a new episode."""
    env = DataForgeEnv()
    result = env.reset(seed=seed)
    episode_id = str(result.info["episode_id"])
    _remember_env(env, episode_id)
    return result.model_dump(mode="json")


@app.post("/step")
async def step(action: dict[str, Any]) -> dict[str, Any]:
    """Execute one agent action."""
    action_payload = dict(action)
    raw_episode_id = action_payload.pop("episode_id", None)
    episode_id = str(raw_episode_id) if raw_episode_id else None
    result = _get_env(episode_id).step(action_payload)
    return result.model_dump(mode="json")


@app.get("/state")
async def state(episode_id: str | None = None) -> dict[str, Any]:
    """Return current environment state snapshot."""
    result = _get_env(episode_id).state()
    return result.model_dump(mode="json")


@app.post("/close")
async def close(request: Request, episode_id: str | None = None) -> dict[str, Any]:
    """No-op close endpoint for OpenEnv compatibility."""
    body_episode_id: str | None = None
    if episode_id is None:
        try:
            payload = await request.json()
        except Exception:
            payload = None
        if isinstance(payload, dict) and payload.get("episode_id"):
            body_episode_id = str(payload["episode_id"])

    target_episode_id = episode_id or body_episode_id
    env = _get_env(target_episode_id)
    env.close()
    if target_episode_id:
        with _registry_lock:
            _sessions.pop(target_episode_id, None)
    return {"status": "closed", "episode_id": target_episode_id}


@app.get("/health")
async def health() -> dict[str, Any]:
    """Liveness check."""
    return {"status": "healthy", "environment": "dataforge-env"}


@app.get("/metadata")
async def metadata() -> dict[str, Any]:
    """Environment metadata for OpenEnv discovery."""
    return {
        "name": "dataforge-env",
        "version": "0.1.0",
        "description": (
            "DataForge RL Environment — agents learn to detect, diagnose, "
            "and repair data-quality issues in tabular datasets."
        ),
        "action_types": [
            "INSPECT_ROWS",
            "SQL_QUERY",
            "STAT_TEST",
            "PATTERN_MATCH",
            "HYPOTHESIS",
            "ROOT_CAUSE",
            "DIAGNOSE",
            "FIX",
        ],
    }


@app.get("/schema")
async def schema() -> dict[str, Any]:
    """Return JSON schemas for action and observation models."""
    action_adapter: TypeAdapter[Action] = TypeAdapter(Action)
    return {
        "action": action_adapter.json_schema(),
        "observation": DataForgeObservation.model_json_schema(),
        "state": EnvState.model_json_schema(),
    }
