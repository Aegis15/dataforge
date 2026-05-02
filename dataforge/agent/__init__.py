"""DataForge agent package — typed tool-use actions and scratchpad.

Public API:
    parse_action — Parse raw dict into typed Action model.
    Action       — Discriminated union of all action types.
    Scratchpad   — In-episode hypothesis tracker.
"""

from dataforge.agent.scratchpad import Scratchpad
from dataforge.agent.tool_actions import Action, parse_action

__all__ = [
    "Action",
    "Scratchpad",
    "parse_action",
]
