# Step 2 — Wire typed `@tool` handlers into AgentRunner

The scaffolded agent from Step 1 has stub tools — `call()` returns `{}`. That's enough to prove the runner loop fires, but the model has nothing real to reason about and nothing to recover from when something goes wrong. Step 2 replaces the stubs with `agent-tool-kit` `@tool` handlers and wires them into `agent-eval-loop`'s `AgentRunner`. The result is one runnable script that exercises the full classify-input → tool-call → final-response path against the live API.

## What this step uses

- `agent_tool_kit.tool` — decorator that wraps a handler with Pydantic input validation, structured `ToolError` envelopes on failure, and an optional `AuditLog`.
- `agent_tool_kit.ToolException` / `ToolError` / `ErrorCategory` — the structured error contract.
- `agent_eval_loop.agent.runner.AgentRunner` — runs the agent's tool-use loop.
- `agent_eval_loop.models.AgentConfig` — manifest the runner reads.

The scaffolded agent's `system.j2` is loaded as the `INSTRUCTIONS` component. The classify-first dispatch from the scaffolded `runner.py` is not used here — `AgentRunner` runs a single-prompt tool-call loop, so the agent's role and constraints in `system.j2` are what shape its behavior, and the tools do the rest.

## The schema-precedence gotcha

`AgentRunner._build_tool_definitions` checks two sources for tool schemas:

1. `AgentConfig.tool_schemas` — schemas parsed from a YAML `tools` component, if present.
2. `getattr(handler, "tool_schema", None)` — for handlers (like `agent-tool-kit`'s `Tool`) that carry their own schema.

If the same tool name appears in both, **the YAML version silently wins** and the handler's `tool_schema` is dropped (see `agent-eval-loop/src/agent_eval_loop/agent/runner.py` line 224 — the trap is documented in the docstring). The `@tool` decorator carries a richer description, including the `WHEN NOT TO USE:` suffix the spec already authored. Losing that to a thin YAML override defeats the point.

`run.py` resolves the precedence by leaving `tool_schemas=[]`. The handler-side schemas reach the wire untouched. The schema dump printed at the start of the run confirms it — `initiate_refund.description` includes the `WHEN NOT TO USE:` block.

## The `@tool` decoration

Excerpt from `tools.py` — the decorator carries the spec's `when_not_to_use` guidance directly into the description the model sees:

```python
class LookupOrderInput(BaseModel):
    order_id: str = Field(description="Order number, format ORD-XXXXX.")


@tool(
    input_model=LookupOrderInput,
    name="lookup_order",
    description=(
        "Look up an order by its order number and return current status "
        "and shipping details."
    ),
    when_not_to_use=(
        "- Don't call without an order number. Ask the customer for it first.\n"
        "- Don't re-call within the same turn if you already have the "
        "order's status from a prior call."
    ),
    audit_log=audit_log,
)
def lookup_order(order_id: str) -> dict:
    _validate_order_id_format(order_id)
    if order_id not in ORDERS:
        raise ToolException(ToolError(
            category=ErrorCategory.NOT_FOUND,
            message=f"No order found with id {order_id}.",
            retryable=False,
            suggested_action=(
                "Confirm the order number with the customer; it may be a typo..."
            ),
            details={"order_id": order_id},
        ))
    return {"order_id": order_id, **ORDERS[order_id]}
```

`tools.py` defines three structured-error paths:

| Path | Trigger | Category |
|------|---------|----------|
| Malformed id (e.g. `BAD-ID`) | format check inside handler | `INVALID_INPUT` |
| Unknown id (e.g. `ORD-99999`) | not in fixture | `NOT_FOUND` |
| Refund on cancelled order (`ORD-77777`) | precondition check inside `initiate_refund` | `PRECONDITION_FAILED` |

## Run

```bash
cd tutorial/02_tools
../.venv/bin/python run.py
```

Verbatim output from one turn against `claude-sonnet-4-5`:

```
=== user input ===
Where is my order ORD-12345?

=== tool schemas reaching the wire ===
{
  "name": "lookup_order",
  "description": "Look up an order by its order number and return current status and shipping deta..."
}
{
  "name": "initiate_refund",
  "description": "Initiate a refund for a specific order. Idempotent on (order_id, reason).\n\nWHEN ..."
}

=== model final response ===
Good news! Your order **ORD-12345** has been shipped. Here are the details:

- **Status:** Shipped
- **Tracking Number:** 1Z999AA10123456784
- **Estimated Delivery:** May 15, 2026

You can use the tracking number to get real-time updates from the carrier. Your
package should arrive by the estimated delivery date. Is there anything else I
can help you with regarding this order?

=== audit log (agent-tool-kit AuditLog) ===
{
  "tool": "lookup_order",
  "args": {
    "order_id": "ORD-12345"
  },
  "result": {
    "order_id": "ORD-12345",
    "status": "shipped",
    "tracking_number": "1Z999AA10123456784",
    "estimated_delivery": "2026-05-15"
  },
  "error": null,
  "latency_ms": 0.1
}

=== runner.tool_calls (agent-eval-loop view) ===
{
  "tool": "lookup_order",
  "args": {
    "order_id": "ORD-12345"
  },
  "latency_ms": 0.2
}
```

## What this turn exercises (and what it doesn't)

This turn exercises classification → flow → tool call → tool result → final response on the `order_status` path. Both the toolkit's `AuditLog` and the eval-loop's `runner.tool_calls` record the same call — composition works in both directions.

The structured error paths (`INVALID_INPUT`, `NOT_FOUND`, `PRECONDITION_FAILED`) are implemented in `tools.py` and verified by the import-time smoke (every branch reachable from a chosen `order_id`), but only the success path runs in this single-turn live call. Step 3's eval covers error recovery across the full intent set.
