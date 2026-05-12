"""Typed @tool handlers for the support_agent tools.

Replaces the scaffolded stubs (call() returning {}) with agent-tool-kit
@tool-decorated handlers: Pydantic input validation, structured ToolError
envelopes on failure, shared AuditLog. The tool_schema each Tool exposes is
the source of truth for the schema on the wire — AgentRunner reads it via
getattr(handler, "tool_schema", None).
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from agent_tool_kit import AuditLog, ErrorCategory, ToolError, ToolException, tool


# One shared AuditLog for this step. In production each session/conversation
# would get its own with a session_id and a JSONL path.
audit_log = AuditLog()


# Fake in-memory fixture. Includes one of each status so every branch of
# the tool logic is reachable from a chosen order_id.
ORDERS: dict[str, dict] = {
    "ORD-12345": {
        "status": "shipped",
        "tracking_number": "1Z999AA10123456784",
        "estimated_delivery": "2026-05-15",
    },
    "ORD-44444": {
        "status": "delivered",
        "tracking_number": "1Z999AA10444444448",
        "estimated_delivery": "2026-05-09",
    },
    "ORD-55555": {
        "status": "placed",
        "tracking_number": None,
        "estimated_delivery": "2026-05-20",
    },
    "ORD-77777": {
        "status": "cancelled",
        "tracking_number": None,
        "estimated_delivery": None,
    },
}


def _validate_order_id_format(order_id: str) -> None:
    """Raise a structured INVALID_INPUT error if order_id isn't ORD-XXXXX shape.

    Pydantic catches type errors at the boundary; this is the semantic
    format check the model needs to learn to recover from.
    """
    if not (order_id.startswith("ORD-") and len(order_id) == 9 and order_id[4:].isdigit()):
        raise ToolException(ToolError(
            category=ErrorCategory.INVALID_INPUT,
            message=(
                f"order_id {order_id!r} doesn't match the expected format. "
                f"Order numbers are 'ORD-' followed by exactly 5 digits."
            ),
            retryable=True,
            suggested_action=(
                "Ask the customer to confirm their order number — it should "
                "look like ORD-12345."
            ),
            details={"received": order_id, "expected_pattern": "ORD-NNNNN"},
        ))


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
                "Confirm the order number with the customer; it may be a typo, "
                "or the order may belong to a different account."
            ),
            details={"order_id": order_id},
        ))
    return {"order_id": order_id, **ORDERS[order_id]}


class InitiateRefundInput(BaseModel):
    order_id: str = Field(description="Order number, format ORD-XXXXX.")
    reason: str = Field(
        description=(
            "Short reason for the refund, e.g. 'damaged_on_arrival', "
            "'wrong_item', 'never_arrived'."
        )
    )


@tool(
    input_model=InitiateRefundInput,
    name="initiate_refund",
    description=(
        "Initiate a refund for a specific order. Idempotent on (order_id, reason)."
    ),
    when_not_to_use=(
        "- Don't call until lookup_order has confirmed the order exists "
        "and is refundable.\n"
        "- Don't call on cancelled orders — refunds don't apply."
    ),
    audit_log=audit_log,
)
def initiate_refund(order_id: str, reason: str) -> dict:
    _validate_order_id_format(order_id)
    if order_id not in ORDERS:
        raise ToolException(ToolError(
            category=ErrorCategory.NOT_FOUND,
            message=f"No order found with id {order_id}.",
            retryable=False,
            suggested_action="Call lookup_order first to confirm the order exists.",
            details={"order_id": order_id},
        ))
    if ORDERS[order_id]["status"] == "cancelled":
        raise ToolException(ToolError(
            category=ErrorCategory.PRECONDITION_FAILED,
            message=f"Order {order_id} is cancelled — refunds don't apply.",
            retryable=False,
            suggested_action=(
                "Tell the customer their order was already cancelled and no "
                "refund is needed (or applicable)."
            ),
            details={"order_id": order_id, "status": "cancelled"},
        ))
    return {
        "refund_id": f"REF-{order_id[-5:]}",
        "order_id": order_id,
        "status": "initiated",
        "amount_cents": 4299,
    }
