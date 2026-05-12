# Step 3 — Evaluate the composed agent end-to-end

Scaffolding and typed tools were necessary, but composition isn't proven until there are scores. 

Step 3 runs `agent-eval-loop`'s simulator and scorer against the Step 2-composed agent, producing real per-category scores across the full intent set.

## What this step uses

- `agent_eval_loop.simulate.generator.ConversationGenerator` — multi-turn simulator that runs a fresh `AgentRunner` per conversation and pairs it with a persona LLM.
- `agent_eval_loop.simulate.personas.PERSONA_ARCHETYPES` (via `get_persona`) — five pre-built personas.
- `agent_eval_loop.simulate.scenarios.load_scenarios` — YAML loader producing a `ScenarioSuite`.
- `agent_eval_loop.evaluate.judges.get_standard_judges` + `STANDARD_RUBRICS` — six pre-built LLM-as-judge rubrics; this step uses four.
- `agent_eval_loop.evaluate.scorer.Scorer` — runs judges across transcripts and aggregates per-category and overall scores.
- Step 2's `tools.py` (`@tool`-decorated `lookup_order` and `initiate_refund`) and `build_config()` — imported, not duplicated. The `Tool` instances and `AgentConfig` reaching the simulator are byte-identical to what Step 2 ran.

## Critical disclosures

Some honest contraints about the current system.

### 1. Runtime mismatch

Step 2 and Step 3 run the agent through `AgentRunner`'s single-prompt tool-use loop. The scaffolded `runner.py` from Step 1 (with classify → dispatch → flow → handoff via dedicated `classification.j2` and `handoff.j2` templates) is **not** used here. The eval measures the agent in the simpler runtime, not in the scaffolded orchestrator.

Consequence visible in the scores below: on the `security_oos` scenario, the agent engaged step-by-step with security advice (change your password, log out other sessions, turn on 2FA) instead of immediately escalating to a human security team. The system prompt's instruction to "escalate, not handle" out-of-scope intents is interpreted flexibly without the scaffolded handoff template enforcing it. This is a useful result. The scaffolded runner is a more sophisticated alternative; see `build/support_agent/runner.py` for that orchestration.

### 2. Uncalibrated judges

Judges run with no `JudgeExample` few-shot anchors. The `agent-eval-loop` README explicitly recommends calibrating against human annotations (Cohen's kappa > 0.6) before trusting scores in absolute terms. **Scores below are directional** — useful for comparing changes within this codebase across iterations, not for cross-product benchmarking. Production evals would add 5–10 human-annotated examples per rubric.

### 3. Single persona

This pass uses only `happy_path_novice` (Alex — novice, polite, neutral). Production evals run the full archetype set (5 personas in `PERSONA_ARCHETYPES`) to cover communication-style variance.

### 4. Asymmetric `max_turns`

In-scope scenarios get `max_turns: 10`. Out-of-scope scenarios get `max_turns: 4` — the persona LLM doesn't always emit `[END_CONVERSATION]` after an escalation, and burning ten turns of a customer being told "I can't help with that" both wastes API spend and degrades scores artificially.

## The scenarios

`scenarios.yaml` defines six scenarios, one per intent in the spec.json:

| Scenario | Category | Intent | Tests |
|---|---|---|---|
| `order_status_happy` | happy_path | order_status | tool call with valid fixture id |
| `refund_request_happy` | happy_path | refund_request | two-tool chain: lookup → refund |
| `account_info_happy` | happy_path | account_info | tool-less flow; gather info from customer |
| `billing_question_oos` | escalation | billing_question | out-of-scope refusal |
| `security_oos` | escalation | security | immediate-escalation policy |
| `legal_oos` | escalation | legal | escalation to legal/privacy team |

Order numbers in the openings are drawn from the Step 2 fixture (`ORD-12345`, `ORD-44444`) so the tool path resolves cleanly when called.

## Run

```bash
cd tutorial/03_eval
../.venv/bin/python run_eval.py
```

The script imports `tools.py` and `build_config` from `../02_tools/` (via `sys.path` insert), generates conversations through `ConversationGenerator.generate_batch`, persists each transcript to `outputs/transcripts/<scenario_id>.json` (gitignored), then runs the 4 judges and writes the aggregate table to `outputs/eval_summary.txt`.

## Results

Captured from `outputs/eval_summary.txt`:

```
                    Evaluation Summary
┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━┓
┃ Category          ┃ Mean Score ┃ Pass Rate ┃ Evaluated ┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━┩
│ tool_selection    │       0.87 │       83% │         6 │
│ response_accuracy │       0.83 │       83% │         6 │
│ routine_adherence │       0.78 │       67% │         6 │
│ completeness      │       0.75 │       67% │         6 │
├───────────────────┼────────────┼───────────┼───────────┤
│ Overall           │       0.80 │       33% │         6 │
└───────────────────┴────────────┴───────────┴───────────┘
```

Per-scenario aggregates (`aggregate_score`, `passed/total` judges, conversation turn count):

| Scenario | Aggregate | Judges passed | Turns |
|---|---|---|---|
| order_status_happy | 1.00 | 4 / 4 | 5 |
| account_info_happy | 0.97 | 4 / 4 | 7 |
| refund_request_happy | 0.82 | 3 / 4 | 5 |
| billing_question_oos | 0.81 | 3 / 4 | 5 |
| legal_oos | 0.75 | 3 / 4 | 5 |
| **security_oos** | **0.46** | **1 / 4** | **9** |

### The headline finding — security_oos at 0.46

The agent walked the customer through password change, active-sessions review, and 2FA enablement on a security report — instead of escalating to a human security team. That is exactly what disclosure #1 (Runtime mismatch) predicted: without the scaffolded `handoff.j2` template, the system prompt's "escalate, don't handle" policy becomes advice the model can override when it can be helpful.

See `outputs/transcripts/security_oos.json` for the full 9-message transcript.

## Interpretation

**What worked.** `tool_selection` and `response_accuracy` are the two strongest categories at 0.87 and 0.83. The `@tool` schemas (with `when_not_to_use` guidance from Step 2) reach the wire intact — the model picks the right tool, with correct arguments, and recovers when handed a real result. `order_status_happy` and `account_info_happy` both scored at or near ceiling: the tool path and the tool-less flow both behave.

**Where the agent underperformed.** `routine_adherence` and `completeness` are weaker (0.78 / 0.75). The biggest single drag is `security_oos` at 0.46 (1/4 judges passed, turn count maxed at 9 of `max_turns × 2 + 1`). The agent treated a security incident as something to walk the customer through rather than something to escalate — exactly the failure mode the runtime-mismatch disclosure predicts. The system prompt says "out-of-scope intents are escalated, not handled", but under `AgentRunner`'s single-prompt loop there's no `handoff.j2` template enforcing it, so the model interprets the instruction permissively.

**What this suggests for the next iteration.** The signal is: if out-of-scope routing matters, don't rely on the system prompt alone - wire in the scaffolded classify-then-dispatch runtime (Step 1's `support_agent/runner.py`), or add an explicit `escalate_to_team` tool with structured arguments so the policy becomes mechanically enforceable instead of textually requested. Either change is the natural Step 4 of an improvement loop; `agent-eval-loop`'s `improve/optimizer.py` and `ImprovementLoop` exist for exactly this cycle.

## What this proves

The four-layer model composes end-to-end:

- **Scaffolding** (Step 1, `agent-skill-kit`) produced the agent's prompts and manifest from a JSON spec.
- **Typed tools** (Step 2, `agent-tool-kit`) replaced stubs with `@tool`-decorated handlers carrying Pydantic schemas, structured errors, and an audit log.
- **Evaluation** (Step 3, `agent-eval-loop`) ran the composed system against six scenarios with one persona and four judges, producing per-category scores and an honest assessment of where the system is strong and where it leaks.

The recipes are independent with different repos and APIs, but the interfaces line up (`AgentRunner` reads `Tool.tool_schema` via duck typing; `ConversationGenerator` constructs its own `AgentRunner` per conversation from the same config). No glue code was needed beyond two `sys.path` inserts and one `build_config()` import.
