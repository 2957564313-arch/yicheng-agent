from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def append_trace(
    state: dict[str, Any],
    node: str,
    summary: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        *state.get("node_trace", []),
        {
            "node": node,
            "at": datetime.now(UTC).isoformat(),
            "summary": summary,
        },
    ]

