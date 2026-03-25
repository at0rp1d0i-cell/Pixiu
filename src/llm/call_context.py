from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_llm_call_config(
    *,
    stage: str,
    round_index: int | None,
    agent_role: str,
    llm_profile: str,
    island: str | None = None,
    subspace: str | None = None,
    extra_metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "stage": stage,
        "round": round_index,
        "agent_role": agent_role,
        "llm_profile": llm_profile,
    }
    if island:
        metadata["island"] = island
    if subspace:
        metadata["subspace"] = subspace
    if extra_metadata:
        metadata.update(dict(extra_metadata))

    tags = [
        f"stage:{stage}",
        f"profile:{llm_profile}",
        f"role:{agent_role}",
    ]
    if island:
        tags.append(f"island:{island}")
    if subspace:
        tags.append(f"subspace:{subspace}")

    return {
        "metadata": metadata,
        "tags": tags,
    }
