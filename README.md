# Spec Sandbox

An AI-powered spec branching simulator for product and engineering teams. Give it a product or engineering spec, define scenario variations, and it runs parallel AI agents to project how each variation plays out — then compares them so you can make a faster, better-informed decision.

> **Uses a mock LLM by default — no API key required.**

---

## 🚀 Quickstart (5–10 min)

### Option A: One command (recommended)

```bash
git clone https://github.com/smithar106/spec-sandbox
cd spec-sandbox
bash run.sh
```

Opens the Streamlit dashboard at [http://localhost:8501](http://localhost:8501) automatically. Done.

---

### Option B: Step-by-step with the CLI

Use this if you want to run your own spec through the full pipeline.

**1. Set up your environment**

```bash
git clone https://github.com/smithar106/spec-sandbox
cd spec-sandbox
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**2. Initialize the workspace** — creates `spec_sandbox.db` in the current directory

```bash
spec-sandbox init
```

**3. Import your spec** — point it at any markdown file

```bash
spec-sandbox import-spec examples/specs/feature-flag-dashboard.md
```

**4. Get your `<spec_id>`** — every spec gets a UUID; this is how you reference it in later commands

```bash
spec-sandbox list-specs
# Output example:
# abc12345-...  Feature Flag Dashboard  examples/specs/feature-flag-dashboard.md
```

Copy the ID from the first column — that's your `<spec_id>`.

**5. Create scenarios** — defines the branches (variations) to explore

```bash
spec-sandbox create-scenarios <spec_id> examples/scenarios/feature-flag-scenarios.yaml
```

**6. Run agents** — 6 AI agents analyze each branch in parallel (mock LLM by default, ~5 seconds)

```bash
spec-sandbox run-agents <spec_id>
```

**7. Compare** — generates a report: complexity scores, risk shifts, invariants, recommendation

```bash
spec-sandbox compare <spec_id>
```

**8. Choose** — interactively pick a branch and record your rationale

```bash
spec-sandbox choose <spec_id>
```

**9. Merge** — produces the final canonical spec from your chosen branch

```bash
spec-sandbox merge <spec_id>
```

**10. Launch the Streamlit UI** — explore everything visually

```bash
streamlit run app.py
# Open http://localhost:8501
```

---

## 🧠 What's happening?

```
Base Spec ──► Branch A (SMB-First)    ──► 6 Agents ──► Projection ──┐
             Branch B (Enterprise)    ──► 6 Agents ──► Projection ──┼──► Compare ──► Decide ──► Canonical Spec
             Branch C (API-First)     ──► 6 Agents ──► Projection ──┘
```

1. **Spec** — your original product or engineering specification (markdown)
2. **Branches** — variations of that spec, each with a named set of changed assumptions (e.g. SMB vs. enterprise scale, REST-only vs. GraphQL)
3. **Agents** — 6 specialized reviewers run on each branch: product coherence, architecture, UX, data model, risk/compliance, and rollout ops
4. **Comparison** — the engine surfaces what's the same across all branches (invariants), what differs materially, complexity scores, and a concrete recommendation
5. **Decision** — you pick a branch, record your rationale, and merge it into a final canonical spec

---

## Streamlit Dashboard

The dashboard has four pages, accessible from the left sidebar:

| Page | What you see |
|---|---|
| **Overview** | Spec summary, branches created, parameter mutations per branch |
| **Branch Comparison** | Complexity scores, est. days, bar chart, invariants, side-by-side dimensions |
| **Agent Outputs** | Per-branch, per-role outputs — structured JSON, markdown, cited assumptions, open questions |
| **Canonical Spec** | The merged result after a decision is recorded, with a download button |

To relaunch without re-running the pipeline:

```bash
.venv/bin/streamlit run app.py
```

---

## With a Real LLM

By default, the system uses a mock LLM that returns structured but synthetic projections — great for testing the pipeline. To use Claude for real analysis:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
spec-sandbox run-agents <spec_id>
```

Uses `claude-sonnet-4-6` by default. Override with `--model`.

---

## Scenario YAML Format

```yaml
scenarios:
  - name: "Enterprise-Ready"
    description: "Full enterprise feature set"
    parameters:
      - key: scale_target
        original_value: "10,000 flags per org"
        new_value: "100,000 flags per org"
        rationale: "Enterprise orgs have many teams and microservices"
        dimension: "scale"
```

See `examples/scenarios/` for full examples.

**Supported dimensions:** `scale` · `security` · `budget` · `platform` · `architecture` · `compliance`

---

## Agent Roles

| Role | Analyzes |
|---|---|
| `product` | Feature coherence, user story coverage, success metrics |
| `architecture` | Technical feasibility, component design, critical path |
| `ux` | User flow implications, interface complexity, accessibility |
| `data_model` | Schema changes, migration complexity, query patterns |
| `risk_compliance` | Security risks, compliance exposure, mitigation options |
| `rollout_ops` | Deployment plan, rollback strategy, monitoring requirements |

---

## Web API

```bash
uvicorn spec_sandbox.api.main:app --reload
# Docs at http://localhost:8000/docs
```

| Method | Path | Description |
|---|---|---|
| POST | `/specs` | Import a new base spec |
| POST | `/specs/{id}/scenarios` | Attach a scenario file |
| POST | `/specs/{id}/run` | Trigger agent run |
| GET | `/specs/{id}/compare` | Fetch comparison report |
| POST | `/specs/{id}/choose` | Record branch decision |
| POST | `/specs/{id}/merge` | Produce canonical spec |

---

## Why This Exists

- **Teams argue about one spec** without making implicit assumptions explicit. Spec Sandbox forces those assumptions into named, testable parameters.
- **Tradeoff analysis is expensive.** A proper "what if we build this for enterprise?" analysis normally takes a room full of people a full day. This does it in minutes.
- **Complexity is invisible until implementation.** Spec Sandbox makes architecture, data model, and compliance perspectives visible *before* any code is written.
- **Decisions are hard to trace.** All branches are preserved as artifacts so the rationale behind the chosen direction is never lost.

---

## Example Use Cases

- Architecture option evaluation before an RFC
- SMB → enterprise feature adaptation planning
- Compliance scenario planning (SOC 2 vs. HIPAA vs. standard)
- Rollout strategy comparison (canary vs. big-bang vs. feature flag)
- Stakeholder alignment workshops — replace argument with structured analysis

---

## Extending

**New LLM provider:** Implement `LLMProvider` in `src/spec_sandbox/providers/` and pass `--provider my-provider` to `run-agents`.

**New agent role:** Add to `AgentRole` enum → create prompt template → define output schema → add to `DEFAULT_AGENT_ROLES`.

**Custom scenario parameters:** Any YAML keys with `key`, `original_value`, `new_value`, `rationale`, and `dimension` work out of the box.

---

## Requirements

- Python 3.11+
- No API key needed for mock runs
- SQLite (included, no setup)
