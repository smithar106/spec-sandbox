# Feature Flag Management Dashboard

**Author:** Priya Nair, Senior PM — Platform Team  
**Status:** Draft — awaiting eng review  
**Last Updated:** 2026-03-12  
**Target Quarter:** Q2 2026  

---

## Overview

We are building an internal Feature Flag Management Dashboard that allows engineering and product teams to create, manage, target, and audit feature flags across all of our services. This replaces a patchwork of hand-rolled config files, Notion tables, and Slack-DM-based flag coordination that has become a reliability and governance risk as the company has grown past 120 engineers.

The dashboard will be the single authoritative source of truth for all feature flags in production. It will expose a web UI for non-technical stakeholders and a REST API for CI/CD pipelines and programmatic access.

---

## Problem Statement

As of today, Fathom uses three separate mechanisms for feature gating: hardcoded environment variables in Heroku, a YAML file checked into the monorepo, and a legacy LaunchDarkly integration that was partially abandoned in 2024. This fragmentation causes real problems:

- **Incident risk:** Flags live in multiple places, so engineers don't always know which system is authoritative. In the Q1 2026 payments outage, a flag was disabled in LaunchDarkly but the app was reading from the YAML file. The feature stayed on 40 minutes longer than intended.
- **Slow releases:** Rolling out a feature to a subset of users requires an engineer to manually edit a YAML file, open a PR, get it reviewed, and wait for deploy. This is a 30–90 minute process for something that should take seconds.
- **No audit trail:** There is no reliable log of who changed what flag and when. Compliance asked for a 12-month change log during our SOC 2 Type II audit and we couldn't produce one.
- **Zero visibility for PM/Design:** Non-technical team members cannot see which features are currently live, what percentage of users are in an experiment, or when a flag was last changed.

---

## Goals

1. Give engineers a single, reliable system for creating and managing feature flags across all services.
2. Reduce flag-change time from 30–90 minutes to under 2 minutes for the common case (percentage rollout, on/off toggle).
3. Provide a complete, immutable audit log for all flag changes to satisfy SOC 2 Type II requirements.
4. Enable product managers to view flag states and experiment coverage without needing to read code or contact an engineer.
5. Integrate with our existing deploy pipeline so flag changes can be automated as part of a release.

---

## Non-Goals

- **This is not a full A/B testing platform.** We are not building metric tracking, statistical significance calculations, or holdout management. Flags are binary or percentage-based; analysis happens in our existing data warehouse.
- **We are not replacing our analytics stack.** Flag exposure events will be emitted to Segment, but the dashboard will not display experiment results.
- **Mobile SDK support is out of scope for v1.** We will support server-side and web JavaScript clients only.
- **We are not building self-serve flag creation for non-engineers in v1.** PM visibility yes, PM write access in a later release.

---

## User Stories

**As an engineer,** I want to create a feature flag with targeting rules (percentage, user ID list, environment) so I can safely roll out new code without a deploy.

**As an engineer,** I want to toggle a flag off instantly from the dashboard in an incident so I can reduce MTTR without opening a PR.

**As a tech lead,** I want to set flag ownership and expiration dates so that stale flags get cleaned up and don't accumulate indefinitely.

**As a product manager,** I want to see a read-only view of all active flags and their current rollout percentages so I can answer questions from customers and leadership without pinging an engineer.

**As a security/compliance engineer,** I want every flag change to be logged with actor, timestamp, previous value, and new value so we can satisfy audit requests without scrambling.

**As a developer advocate,** I want a REST API with good documentation so that automated deployment scripts and GitHub Actions can flip flags without human intervention.

---

## Technical Requirements

- **SDK:** Client libraries for JavaScript/TypeScript (browser + Node), Python, and Ruby. Flags evaluate locally against a cached rule set; fresh rules pushed via SSE or polling (configurable interval, default 30s).
- **API:** REST API with JWT-based authentication. Endpoints for CRUD on flags, targeting rules, environments, and audit log queries.
- **Environments:** Flags are scoped to an environment (development, staging, production). Promoting a flag from staging to production is a first-class action.
- **Targeting rules:** Support on/off, percentage rollout (0–100%), allowlist (user IDs or email domains), and attribute-based targeting (e.g., `plan == "enterprise"`).
- **SSO + RBAC:** Authenticate via our existing Okta SSO. Roles: Viewer, Editor, Admin. Editors can modify flags they own; Admins can modify any flag and manage team membership.
- **Audit log:** Every write operation appended to an immutable log table. Retention: 2 years. Exportable as CSV.
- **Performance:** Flag evaluation p99 latency under 5ms. Dashboard page load under 2s on a standard connection.
- **Storage:** PostgreSQL for flag definitions and audit log. Redis for the evaluation cache.

---

## Success Metrics

| Metric | Baseline | 90-Day Target |
|---|---|---|
| Time to change a flag in production | ~60 min (median) | < 2 min |
| Flags with no owner or expired date | ~40% | < 5% |
| Incident mitigation via flag toggle | 0 (no capability) | Capability shipped |
| Audit log coverage | 0% | 100% of write operations |
| PM satisfaction with visibility (1–5) | 1.8 (survey Q1 2026) | ≥ 4.0 |

---

## Open Questions

1. **Migration:** Do we hard-cut to the new system on launch day or run dual-write for 30 days? Engineering wants a clean cut; compliance wants no gap in audit coverage during the transition.
2. **Flag limits:** Should we enforce a per-service flag limit to prevent flag sprawl, or rely on ownership + expiration to keep things tidy?
3. **LaunchDarkly data export:** Do we attempt to import historical flag change data from LaunchDarkly, or accept that pre-launch history is lost?
4. **On-call access:** Should the on-call engineer have elevated permissions to toggle any flag during an incident, or do we require the flag owner to be paged?
5. **Stale flag enforcement:** Should expired flags auto-disable or just alert? Auto-disable is cleaner operationally but carries risk if the expiration date was set wrong.
