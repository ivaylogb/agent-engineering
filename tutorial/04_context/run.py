"""Step 4: wrap the Step 2 agent in ManagedAgentRunner for a 15-turn run.

The Step 2 agent runs unchanged. We construct it via Step 2's
``build_config`` and its ``@tool``-decorated handlers, then wrap the
resulting ``AgentRunner`` in a ``ManagedAgentRunner`` that replaces the
runner's static context with an actively-managed ``ContextWindow``.

Budget is tight (input ≈ 5_200 tokens after the 800-token reply
reservation) so compaction has to do real work mid-conversation. The
per-turn table shows total tokens and per-category usage; the final
state dump confirms the pinned customer_id survives, tool results
progress through full → summary → reference, and the history rolls into
a summary.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Import Step 2's @tool handlers and AgentConfig builder — no duplication.
THIS_DIR = Path(__file__).resolve().parent
STEP_2 = THIS_DIR.parent / "02_tools"
sys.path.insert(0, str(STEP_2))

from tools import initiate_refund, lookup_order  # noqa: E402
from run import build_config  # noqa: E402

from agent_eval_loop.agent.runner import AgentRunner  # noqa: E402
from agent_eval_loop.models import ComponentType  # noqa: E402

from agent_context_kit import (  # noqa: E402
    ComponentCategory,
    ContextEventLog,
    ContextWindow,
    HistoryManager,
    ProgressiveCompactionStrategy,
    SummaryHistoryStrategy,
    TokenBudget,
    ToolResultCompactor,
    extractive_summarizer,
    truncate_summarizer,
)
from agent_context_kit.managed_runner import ManagedAgentRunner  # noqa: E402

from scenario import SCENARIO  # noqa: E402


def build_window(event_log: ContextEventLog, instructions: str) -> ContextWindow:
    """Construct a tight-budget ContextWindow with progressive compaction.

    The budget is deliberately small (6_000 total, 800 reply reservation)
    so the 15-turn conversation forces real compression. Hard limits keep
    the system prompt and tool-description prose bounded; shares split
    the remainder across history, tool results, and working memory.
    """
    budget = TokenBudget.for_window(
        total_window=3_500,
        reply_reservation=500,
        hard_limits={
            ComponentCategory.INSTRUCTIONS: 600,
            ComponentCategory.ROUTINE: 200,
            ComponentCategory.TOOL_DESCRIPTIONS: 200,
        },
        shares={
            ComponentCategory.HISTORY: 0.5,
            ComponentCategory.TOOL_RESULTS: 0.3,
            ComponentCategory.WORKING_MEMORY: 0.2,
        },
    )
    history = HistoryManager(
        keep_recent=4,
        summarizer=extractive_summarizer(max_lines=3),
    )
    window = ContextWindow(budget=budget, history=history, event_log=event_log)
    window.set_instructions(instructions)

    # Progressive: full → summary (after 2 turns) → reference (after 5).
    compactor = ToolResultCompactor(
        full_ttl_turns=2,
        summary_ttl_turns=5,
        summarizer=truncate_summarizer(80),
    )
    window.set_compaction_strategy(
        ComponentCategory.TOOL_RESULTS,
        ProgressiveCompactionStrategy(compactor),
    )
    window.set_compaction_strategy(
        ComponentCategory.HISTORY,
        SummaryHistoryStrategy(extractive_summarizer(max_lines=3)),
    )
    return window


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set the Anthropic API key in the environment first.", file=sys.stderr)
        return 1

    cfg = build_config()
    instructions = cfg.components[ComponentType.INSTRUCTIONS].content

    runner = AgentRunner(
        config=cfg,
        tool_handlers={
            "lookup_order": lookup_order,
            "initiate_refund": initiate_refund,
        },
    )

    event_log = ContextEventLog()
    window = build_window(event_log, instructions)

    # Pin a fact that must survive every compaction pass.
    window.memory.set_typed(
        "customer_id", "CUST-42",
        entry_type="fact", priority=True,
    )

    managed = ManagedAgentRunner(runner=runner, window=window)

    header = (
        f"{'turn':<4} {'user_msg':<40} {'tokens':<8} "
        f"{'hist':<6} {'tools':<6} {'mem':<6}"
    )
    print(header)
    print("-" * len(header))

    for i, user_msg in enumerate(SCENARIO, start=1):
        try:
            managed.send_message(user_msg)
        except Exception as e:  # noqa: BLE001
            print(f"\n[turn {i}] managed.send_message raised: {e!r}", file=sys.stderr)
            raise
        # ManagedAgentRunner._mirror_tool_results records this turn's tool
        # calls into window.tool_results() automatically; no manual bridge.

        usage = window.usage()
        hist = usage[ComponentCategory.HISTORY]
        tools = usage[ComponentCategory.TOOL_RESULTS]
        mem = usage[ComponentCategory.WORKING_MEMORY]
        snippet = user_msg if len(user_msg) < 37 else user_msg[:34] + "..."
        print(f"{i:<4} {snippet:<40} {window.tokens():<8} "
              f"{hist:<6} {tools:<6} {mem:<6}")

    # ---- final state -----------------------------------------------------
    print("\n--- final window state ---")
    usage = window.usage()
    for cat, used in usage.items():
        print(f"  {cat.value:<20} {used}")
    print(f"  total tokens:        {window.tokens()}")

    print("\n--- working memory ---")
    print(f"  loaded skills:           {window.loaded_skill_names()}")
    print(f"  pinned customer_id:      {window.memory.get('customer_id')!r}")
    print(f"  memory_summary present:  {'memory_summary' in window.memory.entries}")

    print("\n--- tool result states ---")
    states: dict[str, int] = {}
    for slot in window.tool_results():
        states[slot.state] = states.get(slot.state, 0) + 1
    for state, count in sorted(states.items()):
        print(f"  {state:<10} {count}")
    print(f"  total slots:        {len(window.tool_results())}")
    print(f"  total runner.tool_calls: {len(runner.tool_calls)}")

    print("\n--- history ---")
    print(f"  turns retained:     {len(window.history.turns)}")
    print(f"  summary present:    {window.history.summary is not None}")
    if window.history.summary:
        print(f"  summary preview:    {window.history.summary[:140]!r}")

    print("\n--- event log summary ---")
    for event_type, count in event_log.summary().items():
        print(f"  {event_type:<28} {count}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
