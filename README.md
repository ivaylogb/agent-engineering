# agent-engineering

An engineering system for production-grade LLM agents.

## Thesis

Most production agents fail in predictable ways: brittle tool calls, stale context, behavior regressions after prompt edits, inconsistent reviews. These aren't prompt problems. They're system problems.

This is a set of four open-source kits that together codify what production agents need: evaluation loops, reliable tool contracts, runtime context management, and repeatable development workflows. Each kit is independently useful. Together they form an engineering discipline for shipping agents that behave predictably at scale.

## The four-layer model

Production agents need four things working in concert:

| Layer | The question it answers | Repo |
|-------|-------------------------|------|
| Evaluation | How do we know the agent got better? | agent-eval-loop |
| Tool contracts | How do we make agent actions reliable? | agent-tool-kit |
| Context runtime | How do we keep the model focused? | agent-context-kit |
| Development workflows | How do we make agent-building repeatable? | agent-skill-kit |

## Failure modes and system responses

| Failure mode | System response |
|--------------|-----------------|
| Prompt edits silently regress behavior | simulate → evaluate → improve loop with calibrated judges |
| Tools cause hallucinated parameters and brittle multi-step orchestration | typed schemas, fat tools, structured errors, capability registries |
| Context fills with stale results, irrelevant history, the wrong instructions | token budgets, dynamic skill loading, tool-result compaction, sub-agent isolation |
| Agent reviews are inconsistent and depend on who's reviewing | reusable Claude Code skills that encode review and scaffolding workflows |

## Repo map

| Layer | Repo | What it does | Where to start |
|-------|------|--------------|----------------|
| Evaluation | [agent-eval-loop](https://github.com/ivaylogb/agent-eval-loop) | Simulated multi-turn conversations, calibrated LLM-as-judge, regression-tested improvement | `examples/customer_support/run.py` |
| Tools | [agent-tool-kit](https://github.com/ivaylogb/agent-tool-kit) | Tool base classes, capability registry, structured error envelopes, audit logs | `examples/ecommerce/run.py` |
| Context | [agent-context-kit](https://github.com/ivaylogb/agent-context-kit) | Token-budgeted context window, skill router, compaction strategies, sub-agent isolation | `examples/multi_skill_support/run.py` |
| Workflows | [agent-skill-kit](https://github.com/ivaylogb/agent-skill-kit) | Reference agent, audit skills, meta-agent that scaffolds new agents from a description | `python -m scaffold_agent describe "..."` |

## How to use this set

Each kit stands on its own. Pick the layer matching your immediate pain:

- Behavior keeps drifting after prompt changes? Start with **agent-eval-loop**.
- Tools are flaky and the agent can't recover? Start with **agent-tool-kit**.
- The context window is the bottleneck? Start with **agent-context-kit**.
- Reviewing new agents is inconsistent and slow? Start with **agent-skill-kit**.

The four kits are designed to compose. The toolkit's `tool_handlers` slot into the eval loop's `AgentRunner` directly. The context kit's `ContextWindow` wraps the same runner. The skill kit's reference agent is built on the same SDK patterns.

## License

MIT.
