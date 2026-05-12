"""Step 2: wire @tool handlers into agent-eval-loop's AgentRunner.

Loads the scaffolded support_agent's system prompt and manifest, builds an
AgentConfig WITHOUT YAML tool_schemas (so the @tool decorator's schemas
reach the wire — the precedence gotcha documented in the integration check
and the README), then runs one turn that exercises the tool path.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

from agent_eval_loop.agent.runner import AgentRunner
from agent_eval_loop.models import AgentConfig, ComponentType, ComponentVersion

from tools import audit_log, initiate_refund, lookup_order


SUPPORT_AGENT_DIR = Path(__file__).resolve().parent.parent / "build" / "support_agent"
TEST_INPUT = "Where is my order ORD-12345?"


def build_config() -> AgentConfig:
    """Construct an AgentConfig from the scaffolded support_agent on disk.

    Only the system prompt is loaded into the config. The classify/dispatch
    machinery in the scaffolded runner.py is not used here — AgentRunner
    runs a single-prompt tool-call loop, so the agent's role/constraints
    in system.j2 are what shapes its behavior.
    """
    manifest_path = SUPPORT_AGENT_DIR / "agent.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())

    system_path = SUPPORT_AGENT_DIR / "prompts" / "system.j2"
    system_text = system_path.read_text()

    return AgentConfig(
        name=manifest["agent"],
        description=manifest.get("description", ""),
        model=manifest["model"],
        components={
            ComponentType.INSTRUCTIONS: ComponentVersion(
                component_type=ComponentType.INSTRUCTIONS,
                path=str(system_path),
                version=str(manifest["prompts"]["system"]),
                content=system_text,
            ),
        },
        # Deliberately empty: AgentRunner._build_tool_definitions falls back
        # to handler.tool_schema when this is empty. Populating it from
        # agent.yaml would silently override the @tool decorator's richer
        # description and when_not_to_use guidance.
        tool_schemas=[],
    )


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set the Anthropic API key in the environment first.", file=sys.stderr)
        return 1

    config = build_config()
    runner = AgentRunner(
        config=config,
        tool_handlers={
            "lookup_order": lookup_order,
            "initiate_refund": initiate_refund,
        },
    )

    print("=== user input ===")
    print(TEST_INPUT)
    print()

    print("=== tool schemas reaching the wire ===")
    for td in runner._build_tool_definitions():
        print(json.dumps(
            {"name": td["name"], "description": td["description"][:80] + "..."},
            indent=2,
        ))
    print()

    response = runner.send_message(TEST_INPUT)

    print("=== model final response ===")
    print(response.content)
    print()

    print("=== audit log (agent-tool-kit AuditLog) ===")
    for r in audit_log.records():
        print(json.dumps(
            {
                "tool": r.tool_name,
                "args": r.arguments,
                "result": r.result,
                "error": r.error,
                "latency_ms": round(r.latency_ms, 1),
            },
            indent=2,
            default=str,
        ))

    print()
    print("=== runner.tool_calls (agent-eval-loop view) ===")
    for tc in runner.tool_calls:
        print(json.dumps(
            {
                "tool": tc.tool_name,
                "args": tc.arguments,
                "latency_ms": round(tc.latency_ms or 0.0, 1),
            },
            indent=2,
            default=str,
        ))

    return 0


if __name__ == "__main__":
    sys.exit(main())
