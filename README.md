# Spec Sandbox

An AI-powered spec branching simulator for product and engineering teams. Give it a product or engineering spec, define scenario variations, and it runs parallel AI agents to project how each variation plays out — then compares them so you can make a faster, better-informed decision.

---

## What It Does

Spec Sandbox takes a single base specification and fans it out into parallel branches, each representing a different set of assumptions (SMB vs. enterprise, API-first vs. dashboard-first, tight budget vs. full investment). Specialized AI agents analyze each branch from different perspectives — architecture, UX, risk, data model, rollout operations — and produce structured projections. A comparison engine then synthesizes the projections into a report that surfaces invariants, material differences, risk shifts, complexity scores, and a concrete recommendation.

```
                              ┌─────────────────────────────────────────────────┐
                              │               Spec Sandbox Run                  │
                              │                                                 │
Base Spec ────────────────────┤                                                 │
  (feature-flag-dashboard.md) │  Branch A (SMB-First)    → Agents → Projection │
                              │                                                 │
                              │  Branch B (Enterprise)   → Agents → Projection │──► Compare ──► Decide ──► Merge ──► Canonical Spec
                              │                                                 │
                              │  Branch C (API-First)    → Agents → Projection │
                              │                                                 │
                              └─────────────────────────────────────────────────┘
```

Each agent focuses on one dimension: product coherence, architecture feasibility, UX implications, data model design, risk and compliance, or rollout and operational readiness. Agents run in parallel within each branch and sequentially across branches.

---

## Why This Exists

Writing a spec is easy. Knowing which version of the spec to commit to is hard. These are the problems Spec Sandbox addresses:

- **Teams write one spec and argue about it.** The debate is often about implicit assumptions (scale, budget, security posture) that were never made explicit. Spec Sandbox forces those assumptions into named, testable parameters.
- **Tradeoff analysis is expensive.** Running a proper "what if we build this for enterprise instead?" analysis requires pulling multiple engineers and a PM into a room for a day. This tool makes that analysis happen in minutes.
- **Complexity is invisible until implementation.** A spec looks simple until you ask an architect to think through the data model, or ask a compliance engineer to think through the audit trail. Spec Sandbox makes those perspectives visible before any code is written.
- **Decisions are hard to trace.** When a spec ships, the rejected alternatives are often lost. Spec Sandbox keeps all branches as artifacts so the decision rationale is preserved.

---

## Getting Started

### One command to run everything

```bash
git clone https://github.com/smithar106/spec-sandbox
cd spec-sandbox
bash run.sh
```

`run.sh` handles everything automatically:

1. Creates a Python virtual environment
2. Installs all dependencies
3. Runs the full pipeline against the included sample spec using a **mock LLM** (~5 seconds, no API key needed)
4. Launches a **Streamlit dashboard at [http://localhost:8501](http://localhost:8501)**

> **Requirements:** Python 3.11+ · No API key needed for the mock run

---

## Streamlit Dashboard

The dashboard has four pages, accessible from the left sidebar:

| Page | What you see |
|---|---|
| **Overview** | Spec summary, branches created, parameter mutations per branch |
| **Branch Comparison** | Complexity scores, est. days, bar chart, invariants, side-by-side dimensions (components, risks, API changes, open questions) |
| **Agent Outputs** | Per-branch, per-role outputs — structured JSON, markdown analysis, cited assumptions, open questions |
| **Canonical Spec** | The merged result after a decision is recorded, with a download button |

To relaunch the dashboard against an existing database without re-running the pipeline:

```bash
cd spec-sandbox
.venv/bin/streamlit run app.py
```

---

### Manual CLI usage

```bash
# Set up venv
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Initialize workspace (creates spec_sandbox.db)
spec-sandbox init

# Import a spec from a markdown file
spec-sandbox import-spec examples/specs/feature-flag-dashboard.md

# Create scenarios from a YAML file (uses mock LLM by default)
spec-sandbox create-scenarios <spec_id> examples/scenarios/feature-flag-scenarios.yaml

# Run all agents on all branches (mock LLM produces realistic-looking output)
spec-sandbox run-agents <spec_id>

# Compare branches and generate report
spec-sandbox compare <spec_id>

# Choose a direction and record the rationale
spec-sandbox choose <spec_id>

# Merge chosen branch parameters into a final canonical spec
spec-sandbox merge <spec_id>

# Launch the Streamlit UI against the populated database
streamlit run app.py
```

Each command accepts `--help` for detailed usage.

---

## With Real LLM

By default, the system uses a mock LLM provider that returns structured but synthetic projections. To use Claude (recommended):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
spec-sandbox run-agents <spec_id>
```

The agent orchestrator uses `claude-sonnet-4-6` by default. Override with `--model`.

---

## Web API

A FastAPI server exposes all functionality over HTTP with interactive docs:

```bash
uvicorn spec_sandbox.api.main:app --reload
# Open http://localhost:8000/docs
```

Key endpoints:

| Method | Path | Description |
|---|---|---|
| POST | `/specs` | Import a new base spec |
| POST | `/specs/{id}/scenarios` | Attach a scenario file |
| POST | `/specs/{id}/run` | Trigger agent run (async) |
| GET | `/specs/{id}/compare` | Fetch comparison report |
| POST | `/specs/{id}/choose` | Record branch decision |
| POST | `/specs/{id}/merge` | Produce canonical spec |
| GET | `/runs/{run_id}/status` | Poll agent run status |

---

## Scenario Parameters

Scenarios are defined in YAML. Each parameter describes a single axis of variation:

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

### Dimensions

| Dimension | What it covers |
|---|---|
| `scale` | Volume, throughput, storage, concurrency requirements |
| `security` | Authentication, authorization, encryption, audit posture |
| `budget` | Engineering cost, infrastructure cost, pricing model |
| `platform` | Target environment, OS, deployment model (cloud, on-prem, mobile) |
| `architecture` | System design, protocol choices, integration patterns |
| `compliance` | Regulatory requirements, data retention, privacy obligations |

Dimensions are used by the comparison engine to group differences thematically in the output report. They do not affect agent behavior; they are organizational metadata.

---

## Agent Roles

Six specialized agents analyze each branch. They run in parallel within a branch and produce structured JSON artifacts.

| Role | Analyzes | Key Outputs |
|---|---|---|
| `product` | Feature coherence, user story coverage, success metric alignment | Feature gaps, conflicting requirements, metric coverage score |
| `architecture` | Technical feasibility, component design, dependency graph | Architecture diagram sketch, critical path, infeasibility flags |
| `ux` | User flow implications, interface complexity, accessibility | Affected flows, UX friction points, screen/component count estimate |
| `data_model` | Schema changes, migration complexity, query patterns | Table/column changes, migration risk score, index recommendations |
| `risk_compliance` | Security risks, compliance exposure, operational risks | Risk register items, compliance gaps, mitigation suggestions |
| `rollout_ops` | Deployment plan, rollback strategy, monitoring requirements | Rollout phases, rollback triggers, alert definitions |

---

## Potential Use Cases

### 1. Product Spec Exploration Before Roadmap Commitment
**Starting spec:** A feature idea at the PM draft stage.  
**Scenario variations:** V1 (tight scope), V2 (full vision), V2.5 (mid-ground).  
**What the sandbox reveals:** Where V1 creates architectural debt that makes V2 harder; which V2 features are cheap additions if V1 is designed correctly.  
**Why valuable:** Prevents the common pattern of building a V1 that has to be largely rewritten for V2.

### 2. Architecture Option Evaluation Before Implementation
**Starting spec:** An engineering RFC with 2–3 design options.  
**Scenario variations:** Option A (event-sourced), Option B (CRUD + materialized views), Option C (off-the-shelf service).  
**What the sandbox reveals:** Complexity scorecard, data model implications of each, rollout risk per option.  
**Why valuable:** Reduces the time to align on an architecture decision from days of back-and-forth to a single review of the comparison report.

### 3. Compliance/Security Requirement Scenario Planning
**Starting spec:** A feature spec written before security review.  
**Scenario variations:** Standard build, SOC 2-compliant build, HIPAA-compliant build.  
**What the sandbox reveals:** Which compliance requirements change the architecture materially vs. which are additive.  
**Why valuable:** Security teams can see the cost of their requirements; PM teams can see what compliance unlocks in terms of market segment.

### 4. Enterprise Feature Adaptation of SMB Products
**Starting spec:** An existing feature built for SMB customers.  
**Scenario variations:** Current (SMB), Enterprise port, Enterprise-native rebuild.  
**What the sandbox reveals:** How much of the existing implementation can be reused vs. requires enterprise-specific redesign.  
**Why valuable:** Surfaces the hidden cost of "we can just add an enterprise tier" conversations.

### 5. Rollout Strategy Comparisons
**Starting spec:** A large, high-risk feature ready for production.  
**Scenario variations:** Big-bang launch, percentage rollout, canary by region, feature flag gate.  
**What the sandbox reveals:** Risk profile and operational complexity of each rollout strategy; monitoring requirements per approach.  
**Why valuable:** Rollout decisions are often made casually; this forces an explicit risk analysis before go/no-go.

### 6. API Design Tradeoff Exploration
**Starting spec:** An API that needs to support multiple client types.  
**Scenario variations:** REST-only, REST + GraphQL, gRPC for internal + REST for external.  
**What the sandbox reveals:** SDK complexity, documentation burden, latency characteristics, and which client types are underserved by each choice.  
**Why valuable:** API design decisions are expensive to change; upfront analysis is worth the investment.

### 7. Migration Planning for Legacy Systems
**Starting spec:** A migration from a legacy system to a new architecture.  
**Scenario variations:** Big-bang migration, strangler fig, parallel-run with reconciliation, stop-the-world cutover.  
**What the sandbox reveals:** Data model risk, rollback complexity, downtime estimates per approach.  
**Why valuable:** Migration strategies look similar in the abstract but have very different risk profiles in practice.

### 8. Stakeholder Alignment Workshops
**Starting spec:** A contested spec where engineering and product disagree.  
**Scenario variations:** Engineering's preferred approach, PM's preferred approach, negotiated middle ground.  
**What the sandbox reveals:** The actual cost/risk differences between positions, rather than the perceived ones.  
**Why valuable:** Replaces argument with analysis; makes it easier to find common ground on the facts.

### 9. Pre-RFC Option Analysis
**Starting spec:** A problem statement without a proposed solution.  
**Scenario variations:** Three different architectural approaches.  
**What the sandbox reveals:** A structured comparison that becomes the basis of an RFC.  
**Why valuable:** Writing a good RFC requires researching all the options first; this accelerates that research phase.

### 10. UX Flow Divergence Analysis
**Starting spec:** A UX spec with multiple proposed flows.  
**Scenario variations:** Flow A (wizard-style), Flow B (single-screen), Flow C (progressive disclosure).  
**What the sandbox reveals:** Component count, step count, accessibility implications, and technical implementation complexity per flow.  
**Why valuable:** UX decisions often look equivalent on a whiteboard but have very different engineering costs and accessibility profiles.

---

## Extending

### Adding a New LLM Provider

Implement the `LLMProvider` protocol in `spec_sandbox/providers/`:

```python
from spec_sandbox.providers.base import LLMProvider

class MyProvider(LLMProvider):
    def complete(self, prompt: str, **kwargs) -> str:
        # Call your provider's API
        ...

    def name(self) -> str:
        return "my-provider"
```

Register it in `spec_sandbox/providers/__init__.py` and pass `--provider my-provider` to `run-agents`.

### Adding a New Agent Role

1. Add the role name to `AgentRole` enum in `spec_sandbox/domain/models.py`.
2. Create a prompt template in `spec_sandbox/agents/prompts/<role>.txt`.
3. Define the output schema in `spec_sandbox/agents/schemas/<role>.json`.
4. Add the role to the `DEFAULT_AGENT_ROLES` list in `spec_sandbox/orchestration/runner.py`.

The orchestration layer will automatically include the new role in future runs.

### Customizing Scenario Templates

Scenario YAML files can include any keys in the `parameters` list as long as each parameter has `key`, `original_value`, `new_value`, `rationale`, and `dimension`. Additional keys are passed through to agents as context but do not affect the branching logic.

---

## Tradeoffs and Next Steps

### What's Mocked vs. Real

- **Mock LLM:** The default provider returns plausible-sounding but entirely synthetic projections. Useful for testing the pipeline without API costs. Real analysis requires a real LLM.
- **Storage:** SQLite by default. Works for local use; not suitable for multi-user or production deployment.
- **Comparison engine:** The invariant detection and complexity scoring algorithms are heuristic and work best when agents are consistent. With mock LLM output, scores are essentially random.

### What You'd Add Next

- **Persistent storage options:** PostgreSQL backend for team use; S3/GCS for artifact storage.
- **Streaming agent output:** Show agent thinking in real-time via SSE rather than waiting for full completion.
- **Web UI:** A React or Next.js frontend for the comparison report and branch management.
- **GitHub integration:** Import specs from GitHub PRs; comment comparison reports on RFCs automatically.
- **Multi-user support:** Auth, org membership, and shared spec workspaces for teams.
- **Spec versioning:** Track spec revisions over time and re-run scenarios when the base spec changes.
- **Custom agent personas:** Allow teams to define their own agent roles with custom prompts tailored to their domain (e.g., a payments-specific risk agent, a mobile-specific UX agent).
