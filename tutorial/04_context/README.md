# Step 4 — Manage the agent's runtime with `ManagedAgentRunner`

*Wraps the Step 2 agent in a budget-enforced context window for a 15-turn multi-issue conversation.*

## Why

Steps 1–3 build a support agent and score it on single-issue paths. Step 4 takes the same agent and runs it through a 15-turn multi-issue conversation. The conversation grows. Tool results pile up. Older turns go stale. `ManagedAgentRunner` decides what stays in the model's input each turn: it enforces a per-component token budget, ages tool results through full → summary → reference, rolls older turns into a summary, and pins facts that have to survive every compaction pass.

The Step 2 agent runs unchanged. We import its `@tool` handlers and `build_config()`, then wrap the resulting `AgentRunner`.

## What this step uses

- `agent_context_kit.ContextWindow` — the single source of truth for the system prompt and API messages each turn.
- `agent_context_kit.TokenBudget` — per-category allocator. Hard limits for static components (instructions, routine, tool descriptions); proportional shares for the dynamic ones (history, tool results, working memory).
- `agent_context_kit.HistoryManager` — keeps the four most recent turns verbatim; older turns become eligible for summarization.
- `agent_context_kit.SummaryHistoryStrategy` — plumbs an extractive summarizer into `HistoryManager.rollover`, so older turns collapse into a summary blob.
- `agent_context_kit.ProgressiveCompactionStrategy` + `ToolResultCompactor` — full → summary → reference aging for tool results (TTL: 2 turns full, 5 turns summary).
- `agent_context_kit.ContextEventLog` — audit trail. Records when compaction fires and how often.
- `agent_context_kit.managed_runner.ManagedAgentRunner` — the adapter that sits between the window and `agent_eval_loop.agent.runner.AgentRunner`.
- Step 2's `tools.py` (`@tool`-decorated `lookup_order`, `initiate_refund`) and `build_config()`. Imported via `sys.path` insert, byte-identical to what Steps 2 and 3 ran.

## How the wiring works

`ManagedAgentRunner(runner=runner, window=window)` swaps the runner's `scratchpad` for the window's `WorkingMemory`. On each `send_message`, the managed runner appends the user turn to the window, runs `window.enforce_budget()`, then rebuilds the system prompt and API messages from `window.build_system_prompt()` and `window.build_api_messages()`. Those go into a raw Anthropic call that respects the runner's `tools`, `model`, `max_tokens`, and `temperature`. Tool dispatch still runs through `AgentRunner._process_response`, so the same toolkit `@tool` handlers from Step 2 fire here unchanged. After the model replies, the managed runner mirrors that turn's tool calls into `window.tool_results()` (so progressive compaction has slots to age) and records the assistant turn.

## The scenario

`scenario.py` is a 15-message list. Reads like a real customer who keeps jumping between issues:

| Turns | Path |
|---|---|
| 1–2 | `order_status` on ORD-12345 — `lookup_order` |
| 3 | pivot to ORD-44444 — second `lookup_order` |
| 4–5 | refund on ORD-44444 — `initiate_refund` |
| 6–8 | account question on confirmation email (tool-less `account_info_flow`) |
| 9 | back to refund timing |
| 10–12 | circle back to ORD-12345 — re-check tracking, carrier, ETA |
| 13–14 | refund-shipping detail |
| 15 | summary request |

## Run it

```bash
cd tutorial/04_context
../.venv/bin/python run.py
```

Cost is about $1 against `claude-sonnet-4-5`. Confirm the spend before you start; this is a real API run.

## Results

Verbatim from one run:

```
turn user_msg                                 tokens   hist   tools  mem
---------------------------------------------------------------------------
1    Hey, I'm trying to figure out wher...    714      261    31     6
2    Yeah, that's the one. So when shou...    837      384    31     6
3    Oh and also — can you check ORD-44...    1012     527    63     6
4    OK perfect. The thing is, the item...    1174     665    87     6
5    Reason would be 'damaged_on_arriva...    1309     800    87     6
6    Thanks. While I have you — I never...    1572     1063   87     6
7    It's possible. Gmail's spam folder...    1225     716    87     6
8    Right, that's the one. OK that exp...    1304     795    87     6
9    So the refund — when does that act...    1486     977    87     6
10   Wait, going back to ORD-12345 — an...    1513     973    118    6
11   Hmm. And what carrier is it with?        1587     1047   118    6
12   Alright. If it doesn't show up by ...    1774     1234   118    6
13   That makes sense. One more thing —...    1869     1329   118    6
14   OK, that's fair.                         1970     1430   118    6
15   Thanks for all the help. Can you g...    2211     1671   118    6
```

Columns are post-turn snapshots: total tokens, history bucket, tool-results bucket, working-memory bucket. `enforce_budget` runs after the user turn lands in the window and before the API call; the assistant turn appends back into history afterward.

## What you're looking at

Three things visible in the table:

1. **The drop at turn 7.** History was 1063 tokens at turn 6, over its 1000-token share. On turn 7, `enforce_budget` triggered a `SummaryHistoryStrategy` rollover. Older turns collapsed into a summary blob, history dropped to 716, total tokens dropped from 1572 to 1225 in the same step.

2. **Two more rollovers without an obvious drop.** The event log records three `compaction` events. The second fires at turn 10: history dips slightly (977 → 973) while tool_results jump from 87 to 118 — the 4th `lookup_order` call landing in the window. The third fires somewhere in turns 12–15 but doesn't show in any column delta. Each `rollover` appends to the existing summary instead of replacing it, so by the third pass the summary itself is large enough that freeing two more turns barely moves the needle. The long final-summary reply at turn 15 (history +241) re-fills the rest.

3. **Tools column stuck at 118.** Four tool calls fired across the run: `lookup_order(ORD-12345)`, `lookup_order(ORD-44444)`, `initiate_refund(ORD-44444)`, `lookup_order(ORD-12345)` again at turn 10. Each result is ~30 tokens of JSON. The bucket never came close to its share, so the progressive compactor stayed idle.

## Final state

```
--- final window state ---
  instructions         416
  routine              0
  tool_descriptions    0
  working_memory       6
  history              1671
  skills               0
  tool_results         118
  total tokens:        2211

--- working memory ---
  loaded skills:           []
  pinned customer_id:      'CUST-42'
  memory_summary present:  False

--- tool result states ---
  full       4
  total slots:        4
  total runner.tool_calls: 4

--- history ---
  turns retained:     5
  summary present:    True
  summary preview:    "User: Hey, I'm trying to figure out where my order is — ORD-12345. It says shipped..."

--- event log summary ---
  compaction                   3
  budget_enforced              3
```

## How to read these numbers

### Two compaction mechanisms, one fired

The setup wires two strategies. `SummaryHistoryStrategy` runs on the HISTORY bucket. `ProgressiveCompactionStrategy` runs on TOOL_RESULTS. Only the history one ran here.

History compaction fired three times. Event log: `compaction: 3`, `budget_enforced: 3`. The first is the visible drop at turn 7.

Tool-result compaction stayed idle. Four tool calls, ~30 tokens of JSON each, 118 tokens at peak. The TOOL_RESULTS share was 600 tokens (0.3 × (3000 input − 1000 hard limits)). Nothing pressured it.

The mirror is wired correctly. `ManagedAgentRunner._mirror_tool_results` records each turn's tool calls into `window.tool_results()` automatically — `total slots == total runner.tool_calls == 4` confirms it. The slots stayed small because the tools return short JSON. A scenario where every tool call returned full order details, a log excerpt, or a document body would pressure the TOOL_RESULTS bucket and the compactor would fire on it.

### Compaction frees space; the space gets re-used

The intuitive picture of "compaction working" is a token chart that drops sharply and stays low. That's not what shows up here. Compaction frees space, the conversation keeps going, new turns and new tool results fill it again.

What you want to watch is the ceiling. Total tokens peaked at 2211 over 15 turns. The input budget is 3000. The trajectory climbs, but it climbs against a cap that held. Without compaction, history alone would have kept growing past it — the final summary at turn 15 added 241 tokens to the history bucket by itself.

### The pinned memory contract held

`customer_id = "CUST-42"` was set with `priority=True` before the first message. It's still there at the end of the run, after three rollovers. That's the contract for priority entries — they don't get evicted under budget pressure. The mechanism is enforced by `WorkingMemory`, not best-effort.

The agent re-called `lookup_order(ORD-12345)` at turn 10 when the customer circled back. The earlier tool result from turn 1 had already rolled into the history summary, so the agent didn't try to recite the tracking number from compacted context. It called the tool again. That's the right behavior under aging context — issue the tool call rather than hallucinate the data.

## What this proves

Four kits compose on one agent:

- **Step 1 (`agent-skill-kit`)** scaffolded `support_agent`'s prompts, manifest, and stub tool layout from a JSON spec.
- **Step 2 (`agent-tool-kit`)** replaced the stubs with `@tool` handlers carrying Pydantic schemas and structured errors.
- **Step 3 (`agent-eval-loop`)** ran the composed agent against six scenarios with four LLM judges and produced per-category scores.
- **Step 4 (`agent-context-kit`)** wraps the same `AgentRunner` in `ManagedAgentRunner` and runs it through a 15-turn multi-issue conversation under a 3000-token input budget. Compaction fired three times. The pinned customer ID survived. The agent re-issued tool calls when the data it needed had rolled into the summary.

The agent itself didn't change between Step 2, Step 3, and Step 4. The runtime around it did. That's the full four-layer claim, demonstrated rather than asserted.
