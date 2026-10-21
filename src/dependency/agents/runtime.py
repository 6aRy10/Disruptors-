from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from dependency.agents.specs import AgentSpec
from dependency.agents.tools import TOOL_SCHEMAS, dispatch_tool


def _tool_subset(names: tuple[str, ...]) -> list[dict]:
    allowed = set(names)
    return [tool for tool in TOOL_SCHEMAS if tool["name"] in allowed]


def _item_value(item: Any, key: str, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def run_agent(
    *,
    spec: AgentSpec,
    task: str,
    model: str | None = None,
    max_tool_rounds: int = 8,
) -> dict:
    """Run one agent with an explicit deterministic tool loop."""
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Install project dependencies with pip install -e . before running agents."
        ) from exc

    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError(
            "OPENAI_API_KEY is not set. The deterministic backend still works without it."
        )

    chosen_model = model or os.getenv("OPENAI_MODEL", "gpt-6-sol")
    client = OpenAI()
    tools = _tool_subset(spec.tool_names)

    response = client.responses.create(
        model=chosen_model,
        instructions=spec.instructions,
        input=[{"role": "user", "content": task}],
        tools=tools,
        tool_choice="auto",
    )

    trace: list[dict] = []
    rounds = 0

    while rounds < max_tool_rounds:
        calls = [
            item
            for item in response.output
            if _item_value(item, "type") == "function_call"
        ]
        if not calls:
            return {
                "agent": spec.name,
                "role": spec.role,
                "model": chosen_model,
                "output_text": response.output_text,
                "tool_trace": trace,
                "tool_rounds": rounds,
                "response_id": response.id,
            }

        outputs = []
        for call in calls:
            name = _item_value(call, "name")
            call_id = _item_value(call, "call_id")
            raw_arguments = _item_value(call, "arguments", "{}")
            arguments = (
                json.loads(raw_arguments)
                if isinstance(raw_arguments, str)
                else dict(raw_arguments or {})
            )

            if name not in spec.tool_names:
                result = {
                    "error": "TOOL_NOT_ALLOWED_FOR_AGENT",
                    "tool": name,
                }
            else:
                try:
                    result = dispatch_tool(name, arguments)
                except Exception as exc:
                    result = {
                        "error": type(exc).__name__,
                        "message": str(exc),
                    }

            trace.append(
                {
                    "tool": name,
                    "arguments": arguments,
                    "result": result,
                }
            )
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(result, default=str),
                }
            )

        rounds += 1
        response = client.responses.create(
            model=chosen_model,
            instructions=spec.instructions,
            previous_response_id=response.id,
            input=outputs,
            tools=tools,
            tool_choice="auto",
        )

    return {
        "agent": spec.name,
        "role": spec.role,
        "model": chosen_model,
        "output_text": response.output_text,
        "tool_trace": trace,
        "tool_rounds": rounds,
        "response_id": response.id,
        "warning": "MAX_TOOL_ROUNDS_REACHED",
    }


def spec_summary(spec: AgentSpec) -> dict:
    return asdict(spec)
