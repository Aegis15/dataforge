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
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import TypeAdapter

from dataforge.agent.tool_actions import Action
from dataforge.env.environment import DataForgeEnv, EnvState
from dataforge.env.observation import DataForgeObservation

logger = logging.getLogger("dataforge.env.server")

app = FastAPI(
    title="DataForge Environment",
    description="OpenEnv-compatible RL environment for data-quality repair.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_env = DataForgeEnv()


@app.post("/reset")
async def reset(seed: int | None = None) -> dict[str, Any]:
    """Reset the environment for a new episode."""
    result = _env.reset(seed=seed)
    return result.model_dump(mode="json")


@app.post("/step")
async def step(action: dict[str, Any]) -> dict[str, Any]:
    """Execute one agent action."""
    result = _env.step(action)
    return result.model_dump(mode="json")


@app.get("/state")
async def state() -> dict[str, Any]:
    """Return current environment state snapshot."""
    result = _env.state()
    return result.model_dump(mode="json")


@app.post("/close")
async def close() -> dict[str, Any]:
    """No-op close endpoint for OpenEnv compatibility."""
    _env.close()
    return {"status": "closed"}


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
            "INSPECT_ROWS", "SQL_QUERY", "STAT_TEST",
            "PATTERN_MATCH", "HYPOTHESIS", "DIAGNOSE", "FIX",
        ],
    }


@app.get("/schema")
async def schema() -> dict[str, Any]:
    """Return JSON schemas for action and observation models."""
    action_adapter = TypeAdapter(Action)
    return {
        "action": action_adapter.json_schema(),
        "observation": DataForgeObservation.model_json_schema(),
        "state": EnvState.model_json_schema(),
    }
