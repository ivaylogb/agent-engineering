"""15-turn multi-issue support conversation for Step 4.

The customer raises an order-status question (ORD-12345), pivots to a
second order (ORD-44444), asks for a refund on it, asks an account
question, eventually circles back to ORD-12345, and ends with a summary
request. Messages are written conversationally — the runner owns history,
so each entry is just the customer's next utterance.
"""

from __future__ import annotations


SCENARIO: list[str] = [
    # ---- Issue 1: order_status on ORD-12345 ---------------------------
    "Hey, I'm trying to figure out where my order is — ORD-12345. "
    "It says shipped but I haven't seen any tracking updates lately.",
    "Yeah, that's the one. So when should I actually expect it?",
    # ---- Pivot: second order ORD-44444 --------------------------------
    "Oh and also — can you check ORD-44444 for me? "
    "I think that one already arrived but I'm not 100% sure.",
    "OK perfect. The thing is, the item in 44444 was kind of damaged "
    "when it got here. Can I get a refund on that one?",
    "Reason would be 'damaged_on_arrival' I guess. Go ahead.",
    # ---- Account question (no tools; account_info_flow) ---------------
    "Thanks. While I have you — I never got the confirmation email when "
    "I set up my account last month. Did it ever send?",
    "It's possible. Gmail's spam folder is always a mess. "
    "What email do you have on file for me?",
    "Right, that's the one. OK that explains it then.",
    # ---- Back to the refund -------------------------------------------
    "So the refund — when does that actually hit my card usually?",
    # ---- Circle back to ORD-12345 -------------------------------------
    "Wait, going back to ORD-12345 — any chance you can re-check the "
    "tracking on that? It's been a couple days now.",
    "Hmm. And what carrier is it with?",
    "Alright. If it doesn't show up by the estimated date, what do I do?",
    # ---- One more refund detail ---------------------------------------
    "That makes sense. One more thing — the refund for 44444, "
    "does that include shipping or just the item?",
    "OK, that's fair.",
    # ---- Summary request ----------------------------------------------
    "Thanks for all the help. Can you give me a quick summary of "
    "everything we sorted out today?",
]
