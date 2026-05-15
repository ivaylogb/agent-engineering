# agent-engineering

An engineering system for production-grade LLM agents.

This is a set of four open-source kits that together codify what production agents need: evaluation loops, reliable tool contracts, runtime context management, and repeatable development workflows. Each kit can be used independently. 
Together they form an engineering discipline for shipping agents that behave predictably at scale.

## Common failure modes

Most production agents fail in predictable ways: brittle tool calls, stale context, behavior regressions after prompt edits, inconsistent reviews.

Pick the one you're seeing and go straight to the kit that addresses it.

| You're seeing | Use this kit |
|---|---|
| Behavior regresses after prompt edits and you can't tell if changes help | [agent-eval-loop](https://github.com/ivaylogb/agent-eval-loop) |
| The model picks the wrong tool, hallucinates parameters, or can't recover from tool errors | [agent-tool-kit](https://github.com/ivaylogb/agent-tool-kit) |
| Context fills with stale tool results, irrelevant history, or instructions the model has stopped reading | [agent-context-kit](https://github.com/ivaylogb/agent-context-kit) |
| Agent reviews are inconsistent — depend on whoever happens to be reviewing | [agent-skill-kit](https://github.com/ivaylogb/agent-skill-kit) |
| You're starting a new agent and want patterns that work out of the box | [agent-skill-kit](https://github.com/ivaylogb/agent-skill-kit) — meta-agent scaffolds new agents from a description |

The four kits are independent. Pick one. The four-layer model below explains how they fit together if you want the full system.

---

## The four-layer model

Production agents need four things working in concert:

| Layer | The question it answers | Repo |
|-------|-------------------------|------|
| Evaluation | How do we know the agent got better? | agent-eval-loop |
| Tool contracts | How do we make agent actions reliable? | agent-tool-kit |
| Context runtime | How do we keep the model focused? | agent-context-kit |
| Development workflows | How do we make agent-building repeatable? | agent-skill-kit |

## The diagnostic spec

The four-layer model and structured edit format used across the diagnostic tools (agent-researcher, funnel-researcher, integration-watcher) are documented externally at [agent-diagnosis-spec](https://github.com/ivaylogb/agent-diagnosis-spec). The kit is the methodology; the spec is the structural opinion that makes implementations interoperate.

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

## Recipes — which layers matter for your agent shape

The four kits are independent but agent shapes have characteristic patterns. These recipes name which kits matter most for a given shape.

**Customer support / triage agent.** Routes incoming requests by intent, calls tools to look up customer/account data, escalates out-of-scope.

- **Critical:** agent-skill-kit (calibrated routing, structured handoff, scaffolder for the agent shape itself), agent-tool-kit (lookup tools must not fabricate when records are missing)
- **Matters:** agent-eval-loop (routing accuracy must hold across prompt changes)
- **Less critical:** agent-context-kit (conversations are typically short)

**Long-running research agent.** Multi-step planning, many tool calls, accumulating findings, may span many turns.

- **Critical:** agent-context-kit (context will blow up without budget/compaction/sub-agent isolation), agent-tool-kit (tools that return verbose data must compress before reaching the model)
- **Matters:** agent-eval-loop (multi-step trajectories are hard to evaluate by inspection)
- **Less critical:** agent-skill-kit at first (more critical once you have multiple research agents to compare)

**Coding / dev-tool agent.** Reads code, edits files, runs commands, operates in a repo.

- **Critical:** agent-skill-kit (skills encode review and audit workflows; broken-candidate-style audits work well here), agent-tool-kit (file-edit and shell tools need typed contracts and idempotency)
- **Matters:** agent-context-kit (codebases are large; selective context loading is the difference between useful and useless)
- **Less critical:** agent-eval-loop early on; matters once the agent has stable enough behavior to regression-test

**Internal automation agent.** Triggered by webhook or schedule, performs deterministic workflow, structured output for downstream systems.

- **Critical:** agent-tool-kit (output is consumed by automation, so structured errors and typed schemas are mandatory)
- **Matters:** agent-eval-loop (failures are silent — the eval is your only signal)
- **Less critical:** agent-context-kit (typically single-turn), agent-skill-kit (less iteration cycle on a stable workflow)

**Greenfield agent — you're starting from scratch.** Don't know yet which failures you'll hit.

- **Start here:** agent-skill-kit's `scaffold_agent` produces an agent matching the methodology. Then add the other layers as failures appear: agent-tool-kit when you find your tools are brittle, agent-eval-loop when you can't tell if a prompt change helped, agent-context-kit when the window is the bottleneck.

The four kits are designed to compose — adopt them as the agent's failure modes emerge, rather than all at once.

---

## License

MIT.
