"""Step 3: end-to-end eval against the composed agent.

Wires Step 2's typed @tool handlers + AgentConfig into eval-loop's
ConversationGenerator, then scores transcripts with Scorer. Single pass.
Uncalibrated judges. One persona, six scenarios, four judges.
"""

from __future__ import annotations

import io
import os
import sys
from pathlib import Path

import anthropic
from rich.console import Console

# Reuse Step 2's tools + config builder. Importing rather than duplicating
# keeps the @tool instances and shared AuditLog as a single source of truth.
THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR.parent / "02_tools"))
from tools import initiate_refund, lookup_order  # noqa: E402
from run import build_config  # noqa: E402

import agent_eval_loop.evaluate.scorer as scorer_module  # noqa: E402
from agent_eval_loop.evaluate.judges import get_standard_judges  # noqa: E402
from agent_eval_loop.evaluate.scorer import Scorer  # noqa: E402
from agent_eval_loop.models import EvalCategory  # noqa: E402
from agent_eval_loop.simulate.generator import ConversationGenerator  # noqa: E402
from agent_eval_loop.simulate.personas import get_persona  # noqa: E402
from agent_eval_loop.simulate.scenarios import load_scenarios  # noqa: E402


SCENARIOS_PATH = THIS_DIR / "scenarios.yaml"
OUTPUTS_DIR = THIS_DIR / "outputs"
TRANSCRIPTS_DIR = OUTPUTS_DIR / "transcripts"
SUMMARY_PATH = OUTPUTS_DIR / "eval_summary.txt"


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set the Anthropic API key in the environment first.", file=sys.stderr)
        return 1

    OUTPUTS_DIR.mkdir(exist_ok=True)
    TRANSCRIPTS_DIR.mkdir(exist_ok=True)

    client = anthropic.Anthropic()

    # --- Simulator ---
    config = build_config()
    generator = ConversationGenerator(
        agent_config=config,
        tool_handlers={
            "lookup_order": lookup_order,
            "initiate_refund": initiate_refund,
        },
        simulator_model="claude-sonnet-4-5",
        client=client,
    )

    suite = load_scenarios(str(SCENARIOS_PATH))
    persona = get_persona("happy_path_novice")
    print(f"Running {len(suite.scenarios)} scenarios × persona={persona.id}...")

    conversations = generator.generate_batch(
        scenarios=suite,
        personas=[persona],
        max_conversations=len(suite.scenarios),
    )
    print(f"Generated {len(conversations)} conversations.\n")

    # --- Persist transcripts (for debugging; gitignored) ---
    for conv in conversations:
        path = TRANSCRIPTS_DIR / f"{conv.scenario_id}.json"
        path.write_text(conv.model_dump_json(indent=2))

    # --- Evaluation ---
    judges = get_standard_judges(
        categories=[
            EvalCategory.TOOL_SELECTION,
            EvalCategory.RESPONSE_ACCURACY,
            EvalCategory.ROUTINE_ADHERENCE,
            EvalCategory.COMPLETENESS,
        ],
        model="claude-sonnet-4-5",
        client=client,
    )
    scorer = Scorer(judges=judges)
    results = scorer.evaluate_batch(conversations)

    # --- Summary: capture to file AND print once ---
    # Scorer.print_summary uses the module-level `console`. Swap in a
    # recording Console pointed at an in-memory buffer so the table is
    # captured (not echoed to the terminal twice) and we can write it to
    # disk before printing the single copy ourselves.
    recording = Console(record=True, width=100, file=io.StringIO())
    original_console = scorer_module.console
    scorer_module.console = recording
    try:
        scorer.print_summary(results)
    finally:
        scorer_module.console = original_console

    summary_text = recording.export_text()
    SUMMARY_PATH.write_text(summary_text)
    print(summary_text)

    # --- Per-scenario passed/failed breakdown (for the README narrative) ---
    print("--- per-scenario verdict counts ---")
    for conv, res in zip(conversations, results):
        passed = sum(1 for v in res.verdicts if v.passed)
        total = len(res.verdicts)
        print(
            f"  {conv.scenario_id:<28} aggregate={res.aggregate_score:.2f}  "
            f"passed={passed}/{total}  turns={len(conv.messages)}"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
