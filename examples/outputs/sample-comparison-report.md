# Spec Comparison Report

**Spec:** Feature Flag Management Dashboard  
**Generated:** 2026-04-15T14:22:07Z  
**Agent Run ID:** `run_8f3a2c1b`  
**Branches Compared:** SMB-First Launch | Enterprise-Ready | API-First Platform  

---

## Invariants

These elements are consistent across all three branches. They should be treated as settled decisions unless a branch agent explicitly flagged one as worth revisiting.

- **Core data model** — All branches converge on flags scoped to environments, with targeting rules stored as structured conditions. The schema differs in scale constraints but not in fundamental structure.
- **REST API surface** — All branches require a REST API. The API-First branch elevates it to the primary interface, but none of the agents proposed eliminating it.
- **PostgreSQL for persistence** — All three branches retained PostgreSQL as the storage layer. Redis evaluation cache was retained in Enterprise and API-First; the SMB branch agent questioned whether it was necessary at lower scale but did not remove it.
- **Flag evaluation happens client-side** — No branch agent proposed server-side evaluation. Local SDK evaluation with cached rule sets is consistent across all projections.
- **Percentage rollout and on/off toggle** — These two targeting modes are present in all branches. More complex targeting (attribute-based, allowlists) is present in Enterprise and API-First, absent in SMB.
- **Audit logging** — All branches include audit logging. Retention duration and compliance posture differ; the logging mechanism itself does not.

---

## Material Differences

| Aspect | SMB-First Launch | Enterprise-Ready | API-First Platform |
|---|---|---|---|
| **Scale target** | 500 flags/org | 100,000 flags/org | 10,000 flags/org (unchanged) |
| **Authentication** | Email/password + admin role | SAML 2.0 SSO + per-env RBAC | API keys + optional SSO |
| **Audit log retention** | 90 days | 7 years | 1 year |
| **Environments** | Production only | Unlimited + approval gates | Named environments, no UI gates |
| **SDK languages** | JavaScript only | 9 languages (JS, TS, Py, Go, Java, Ruby, .NET, iOS, Android) | JavaScript, Python, Go, Java, Ruby |
| **Primary interface** | Web dashboard | Web dashboard | REST API + CLI |
| **Webhook/CI integration** | Not planned | Optional (flag change hooks) | Required, first-class feature |
| **Terraform provider** | Not planned | Nice-to-have (backlog) | Required |
| **Uptime SLA** | Best effort | 99.99% contractual | 99.9% (developer SLA) |
| **Data residency** | US only | US + EU | US only |
| **Estimated storage cost (yr 1)** | ~$40/mo | ~$1,200/mo | ~$180/mo |
| **Frontend engineering effort** | Medium (full dashboard) | Large (full dashboard + approval UI) | Small (read-only + docs site) |
| **Backend engineering effort** | Small-medium | Large | Medium-large |
| **Monetization** | $29/mo flat or free | Per-seat enterprise contract | Usage-based API pricing |

---

## Risk Shifts

### SMB-First Launch

**Risks reduced:**
- Infrastructure complexity is low; no SSO, no multi-region. Fewer moving parts = faster time to market and lower operational burden.
- Pricing is simple; no sales motion needed.

**Risks introduced:**
- **Ceiling risk:** If even one design partner turns out to be mid-market, the 500-flag limit and missing SSO become blockers. The flag limit is not obviously discoverable until a customer hits it.
- **Compliance debt:** A 90-day audit log is technically non-compliant for any customer that later pursues SOC 2. Retroactive log extension is difficult.
- **Migration cost:** Moving SMB customers to an Enterprise tier later requires SSO implementation, data migration for audit logs, and potential re-pricing conversations.

### Enterprise-Ready

**Risks reduced:**
- No deal-blockers for enterprise buyers. SSO, data residency, and 7-year retention address the known compliance checklist.
- Uptime SLA removes a negotiation obstacle.

**Risks introduced:**
- **Overbuilding risk:** Multi-region, 9 SDKs, and unlimited environments may take 10–14 months to build correctly. Market opportunity may shift during that window.
- **Operational complexity:** 99.99% SLA requires redundancy, on-call rotation, and runbook coverage that a team of this size may struggle to deliver on day one.
- **SDK maintenance burden:** 9 languages × ongoing maintenance = a significant long-term operational cost that compounds every year.

### API-First Platform

**Risks reduced:**
- Frontend engineering scope is dramatically reduced; the team can focus on API quality and developer experience.
- Terraform + webhooks create a natural ecosystem flywheel with developer communities.

**Risks introduced:**
- **Adoption ceiling:** Non-technical stakeholders (PMs, product ops) will not self-serve on an API-first tool. Without a PM-friendly UI, the org may face internal pressure to revert.
- **Developer market saturation:** Open-source alternatives (Flagsmith, Unleash, OpenFeature) are already strong in the API-first developer segment. The differentiation case is harder to make.
- **Revenue model mismatch:** Usage-based pricing for a feature flag system can be unpredictable and difficult to forecast; large customers may want enterprise contracts regardless.

---

## Complexity Scorecard

| Branch | Complexity | Est. Eng Days | Components | Key Risks |
|---|---|---|---|---|
| SMB-First Launch | 3/10 | 45 days | Auth, CRUD UI, JS SDK, Postgres, Redis, basic audit log | Flag limit ceiling, compliance debt |
| Enterprise-Ready | 9/10 | 280 days | All of SMB + SAML, RBAC, 8 more SDKs, EU data residency, approval workflows, SLA infrastructure | Overbuilding, SDK maintenance, operational complexity |
| API-First Platform | 6/10 | 110 days | Auth, REST API, CLI, 5 SDKs, webhooks, Terraform provider, OpenAPI spec, minimal UI | Adoption ceiling, competitive saturation |

Complexity scores are computed by the risk-compliance and architecture agents as a weighted sum of: technical dependencies (0.35), security surface area (0.25), operational requirements (0.20), and integration touchpoints (0.20). Scores are normalized to a 1–10 scale across the branches in this run.

---

## Recommendation

**Recommended branch: SMB-First Launch, with two targeted upgrades from Enterprise-Ready**

The pure SMB-First branch is the fastest and cheapest path to a working system, but it carries two risks that are not worth accepting: the 90-day audit log retention creates compliance debt that is costly to fix retroactively, and email/password-only auth will block the first serious mid-market customer.

Recommended modifications to the SMB-First spec before implementation:

1. **Raise the audit log retention to 1 year** from 90 days. The storage cost difference is negligible (~$8/mo). This satisfies SOC 2 Type I without requiring the full 7-year infrastructure of the Enterprise branch.
2. **Add a deferred SSO stub** — design the auth layer so SSO can be added later without a data migration. This costs approximately 3 additional engineering days now and avoids a major refactor when the first enterprise deal requires it.

The API-First branch is the right direction for the SDK layer. Recommend adopting the API-First parameter `webhook_support = required` and `openapi_spec = published` even within the SMB-first delivery, since these are low-cost to build correctly the first time and expensive to retrofit.

**Caveats:**
- This recommendation assumes the team prioritizes internal use and initial market validation over enterprise deal-closing in the first 6 months. If there is a committed enterprise LOI in hand, the calculus shifts toward the Enterprise-Ready branch despite its timeline.
- The Terraform provider (API-First branch) should not be in v1 scope regardless of chosen branch; it requires the API surface to be stable first.

---

## Open Questions Surfaced by Agents

The following questions were raised by branch agents during projection and were not answered by the original spec. They should be resolved before implementation begins.

1. **Flag evaluation performance budget** — All three branches assume <5ms p99 evaluation latency, but none of them model the performance implications of 100k flags (Enterprise) vs. 500 flags (SMB). The architecture agent flagged that cache invalidation strategy differs materially by scale and should be specified before the Redis layer is designed.

2. **Stale flag lifecycle** — The product spec defers this to an open question. The risk-compliance agent noted that stale flags are the single most common cause of feature flag-related incidents in the industry. Recommend making a decision on auto-disable vs. alert-only before the data model is finalized, because it affects the `expires_at` column semantics.

3. **Multi-tenancy isolation model** — The enterprise branch agent asked whether flag evaluation must be tenant-isolated at the database level (separate tables or schemas per org) or whether row-level security is sufficient. This is an architectural decision that is difficult to change after launch.

4. **SDK versioning and deprecation policy** — The API-First branch adds 5 SDKs. No branch spec mentions how SDK versions are maintained or deprecated. This needs a policy before any SDKs ship publicly.
