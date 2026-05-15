# Tutorial — composing four kits

A 30-minute walkthrough that wires together four kits from `agent-engineering`:

1. `agent-skill-kit` — scaffold a customer-support agent from a JSON spec.
2. `agent-tool-kit` — replace the scaffolded stub tools with typed `@tool` handlers.
3. `agent-eval-loop` — run an eval against the wired-up agent.
4. `agent-context-kit` — manage the agent's runtime context across a multi-turn conversation under a tight token budget.

Each step has a script you run and an expected outcome. If the script doesn't run, the tutorial stops — composition only counts when it actually composes.

## Layout

```
tutorial/
  01_scaffold/        spec.json — the agent description fed to scaffold_agent
  02_tools/           tools.py (@tool handlers) + run.py (AgentRunner wiring)
  03_eval/            scenarios.yaml + run_eval.py (ConversationGenerator + Scorer)
  04_context/        scenario.py + run.py (ManagedAgentRunner around the Step 2 agent)
  README.md           this file
  .gitignore          excludes .venv/, build/, outputs/
```

Generated artifacts (`build/`, `.venv/`, `outputs/`) are gitignored.

## Prerequisites

- Python 3.11+
- The four sibling repos checked out next to `agent-engineering/`:
  - `agent-skill-kit/`
  - `agent-tool-kit/`
  - `agent-eval-loop/`
  - `agent-context-kit/`
- `ANTHROPIC_API_KEY` exported for the smoke run.

## Setup (one-time)

```bash
cd tutorial
python3.11 -m venv .venv
./.venv/bin/pip install \
    git+https://github.com/ivaylogb/agent-tool-kit.git \
    git+https://github.com/ivaylogb/agent-eval-loop.git \
    git+https://github.com/ivaylogb/agent-context-kit.git \
    "jinja2>=3.1.0"
```

`agent-skill-kit` has no `pyproject.toml`, so it isn't pip-installed — clone it (`git clone https://github.com/ivaylogb/agent-skill-kit.git`) and point `PYTHONPATH` at the checkout where the steps below use it.

---

## Step 1 — Scaffold the agent

Step 1 uses `scaffold_agent`'s `from-spec` mode, not the conversational `describe` mode. `from-spec` reads a JSON spec — deterministic, no LLM call, reproducible across runs.

The spec lives at `01_scaffold/spec.json` and matches the `AgentSpec` dataclass in `agent-skill-kit/scaffold_agent/spec.py`. It describes a customer-support agent with:

- **Three in-scope intents:** `order_status`, `refund_request`, `account_info` — each with a matching flow.
- **Three out-of-scope intents:** `billing_question`, `security`, `legal` — no flow; the agent will route to handoff.
- **Two tools:** `lookup_order`, `initiate_refund` — these will be rewritten as typed `@tool` handlers in Step 2. The `account_info` flow is intentionally tool-less (it gathers a request from the customer; the actual mutation happens out-of-band after identity verification).
- **One ambiguous eval example** (`"I have a question about my recent activity"`) whose `expected_intent` is `unknown`, exercising the low-confidence handoff path.

Run the scaffolder:

```bash
PYTHONPATH=path/to/agent-skill-kit ./.venv/bin/python \
    -m scaffold_agent from-spec 01_scaffold/spec.json --output build/
```

Output:

```
Generated 16 files into build/support_agent
```

The generated layout:

```
build/support_agent/
  agent.yaml              manifest (intents, model, routing.confidence_threshold)
  runner.py               classify → dispatch → tool loop → structured output
  prompts/
    system.j2
    classification.j2
    handoff.j2
    order_status_flow.j2
    refund_request_flow.j2
    account_info_flow.j2
  tools/
    lookup_order.py       stub: definition + call() returning {}
    initiate_refund.py    stub: definition + call() returning {}
  evals/routing/golden.jsonl
```

Tools are deliberately stubbed — `call()` returns `{}`. Step 2 swaps them for real `@tool` handlers.

### Smoke test

```bash
cd build
PYTHONPATH=. ../.venv/bin/python -m support_agent.runner \
    --input "I need to change my shipping address on my account" --show-trace
```

Trace and response from one turn against `claude-sonnet-4-5`:

```
[classify] sending classification prompt
[classify] intent=account_info confidence=0.95
[flow] entered account_info_flow
```

```json
{
  "decision": "handled_by_flow",
  "flow": "account_info_flow",
  "classification": {
    "intent": "account_info",
    "confidence": 0.95,
    "reasoning": "..."
  },
  "response": "Thank you for reaching out! I can help you update your shipping address. To proceed... please provide the new address you'd like to use..."
}
```

The smoke test exercises one classification + flow against an `account_info` input to confirm the scaffolded agent functions end-to-end: the classifier returns the new intent at 0.95 confidence, the runner dispatches into the tool-less `account_info` flow, and the flow produces a structured response asking the customer for the missing information. The tool path is not exercised here because the `account_info` flow is tool-less by design; Step 2 exercises the tool path through the `order_status` and `refund_request` flows, and full intent coverage runs in Step 3 (eval).

Next: [Step 2 — wire typed `@tool` handlers into AgentRunner](02_tools/README.md).

Then: [Step 3 — evaluate the composed agent end-to-end](03_eval/README.md).

Then: [Step 4 — manage the runtime under pressure with `ManagedAgentRunner`](04_context/README.md).

---
