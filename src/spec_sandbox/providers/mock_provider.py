"""Mock LLM provider for local development and testing — no API key required."""
from __future__ import annotations

import textwrap

from spec_sandbox.domain.models import (
    AgentRole,
    AgentRun,
    SpecBranch,
    ProjectionArtifact,
    BranchComparison,
    BaseSpec,
    Scenario,
)
from spec_sandbox.providers.base import LLMProvider

# ---------------------------------------------------------------------------
# Role detection
# ---------------------------------------------------------------------------

_ROLE_KEYWORDS: dict[str, list[str]] = {
    "product": ["product", "user stor", "stakeholder", "feature scope", "success metric"],
    "architecture": ["architect", "component", "dependency", "api surface", "scalab"],
    "ux": ["ux", "user experience", "user flow", "ui component", "accessib", "platform"],
    "data_model": ["data model", "entity", "schema", "migration", "storage", "relationship"],
    "risk_compliance": ["risk", "compliance", "security", "audit", "regulation", "mitigation"],
    "rollout_ops": ["rollout", "deployment", "feature flag", "rollback", "monitoring", "infra"],
}


def _detect_role(system_prompt: str) -> str:
    lower = system_prompt.lower()
    for role, keywords in _ROLE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return role
    return "product"


# ---------------------------------------------------------------------------
# Mock text templates (markdown analysis, ~300 words each)
# ---------------------------------------------------------------------------

_MOCK_ANALYSIS: dict[str, str] = {
    "product": textwrap.dedent("""\
        ## Product Analysis

        Based on the specification provided, this scenario introduces meaningful changes
        to the product surface that will affect multiple user segments.

        **New User Stories Identified**
        The spec implies at least three net-new user stories: (1) users must be able to
        configure their notification cadence, (2) admin users require a bulk-export
        capability, and (3) guest users need a read-only view mode. Each of these is
        driven by the assumption that the platform targets both self-serve and
        enterprise buyers simultaneously.

        **Feature Scope Changes**
        The onboarding flow expands significantly under this scenario. The spec assumes
        users arrive with some domain knowledge, which reduces the need for contextual
        tooltips but increases the need for a "quick start" wizard. The dashboard feature
        scope contracts slightly: the advanced filtering panel is deferred to a later
        milestone per the spec's phased delivery assumption.

        **Success Metrics Impact**
        Time-to-first-value (TTFV) is directly affected by the onboarding changes.
        The spec cites a 48-hour TTFV target; achieving this will require the quick-start
        wizard to be gated behind a feature flag until QA validates the flow end-to-end.
        Monthly active user retention may also shift, since the guest-view mode could
        attract low-intent users who inflate MAU without contributing to revenue.

        **Stakeholder Impacts**
        Customer Success will need updated runbooks to handle the new configuration
        options. Sales Engineering will benefit from the read-only demo mode, which
        reduces the overhead of provisioning sandbox accounts for prospects.

        **Open Questions**
        It is unclear whether the notification cadence feature requires a carrier-grade
        SMS gateway or whether email-only is acceptable for the initial release. This
        assumption drives both the architecture and the compliance posture for this
        scenario and should be resolved before sprint planning.
    """),

    "architecture": textwrap.dedent("""\
        ## Architecture Analysis

        The scenario described in the spec introduces several structural changes that
        propagate across the service mesh and data pipeline.

        **New Components**
        A dedicated notification service will be required to support the configurable
        cadence feature. This service must be stateless and horizontally scalable,
        backed by a durable message queue (the spec cites SQS-compatible semantics).
        Additionally, a read-replica of the primary data store is implied to support
        the guest read-only mode without impacting write-path latency.

        **Modified Components**
        The API gateway must be updated to enforce the new guest-vs-authenticated
        permission boundary. The current monolithic auth middleware is not granular
        enough; the spec assumption that "auth is a solved problem" needs revisiting.
        The existing ETL pipeline will need a new fan-out stage to populate the
        notification queue on qualifying events.

        **API Surface Changes**
        Three new endpoints are implied: POST /notifications/preferences,
        GET /export/bulk, and GET /view/{resource_id}?mode=readonly. The last one
        requires the API gateway to pass a read-only context token downstream.

        **Scalability Implications**
        The notification service is the primary new scaling bottleneck. Under peak load
        the spec estimates 50k events/hour; at that rate a single-threaded consumer
        will create > 30-second delivery lag, violating the stated SLA.

        **Open Questions**
        The spec does not specify whether the bulk export endpoint should be synchronous
        or async (job-based). This decision affects both the API contract and the
        infrastructure cost model and must be resolved before the architecture is
        finalized.
    """),

    "ux": textwrap.dedent("""\
        ## UX Analysis

        The spec introduces a set of flow changes that touch the onboarding journey,
        the main dashboard, and the new read-only guest experience.

        **New User Flows**
        A quick-start wizard is the most significant new flow. It consists of four
        steps: workspace naming, invite teammates, select a template, and confirm
        billing. The spec assumes users are familiar with SaaS workspace conventions,
        so the wizard should be lightweight rather than educational.

        The guest/read-only flow is a second new flow. Guests arrive via a shareable
        link and see a locked-down version of the resource. They should be able to
        comment but not edit, and a persistent "Request access" CTA must be visible
        without being intrusive.

        **Modified Flows**
        The existing settings flow gains a Notifications tab. Current tab order is
        Profile → Security → Billing; the spec does not prescribe where Notifications
        should land, but user research conventions suggest placing it second.

        **New UI Components**
        The quick-start wizard requires a multi-step modal with progress indicators.
        The guest view requires a read-only banner component and a locked-state overlay
        for interactive elements. Both components must be accessible (WCAG 2.1 AA).

        **Accessibility Implications**
        The locked-state overlay on the guest view must convey its state to screen
        readers via aria-disabled and a descriptive aria-label. The quick-start wizard
        must trap focus within the modal until dismissed.

        **Open Questions**
        The spec does not address mobile breakpoints for the bulk-export trigger. On
        narrow viewports a floating action button may conflict with the existing bottom
        navigation bar, and this needs design validation before implementation begins.
    """),

    "data_model": textwrap.dedent("""\
        ## Data Model Analysis

        This scenario requires three net-new entities and modifications to two existing
        ones. Migration complexity is moderate.

        **New Entities**
        NotificationPreference stores user-scoped cadence settings (frequency, channel,
        quiet hours). GuestAccessToken stores the shareable link metadata including
        expiry, resource ID, and permission scope. BulkExportJob records the status and
        S3 key for async export requests.

        **Schema Changes**
        The User entity gains a guest_access_enabled boolean column (default false) to
        distinguish guest-capable accounts. The Resource entity gains a
        shareable_link_active boolean and a last_exported_at timestamp to support the
        export audit trail implied by the spec.

        **New Relationships**
        NotificationPreference has a many-to-one relationship with User (one preference
        record per notification channel per user). GuestAccessToken has a many-to-one
        relationship with Resource. BulkExportJob has a many-to-one relationship with
        User (the requester).

        **Migration Needs**
        Three migrations are required: add columns to User and Resource, create the
        three new tables. All migrations are additive and non-breaking; no existing rows
        need backfilling beyond setting sensible defaults for the new boolean columns.

        **Storage Implications**
        BulkExportJob artifacts will be stored in object storage (S3 or equivalent),
        not in the relational database. The spec assumes a 30-day retention window for
        export artifacts, which will require a lifecycle policy on the storage bucket.

        **Open Questions**
        The spec does not specify whether NotificationPreference should be indexed by
        (user_id, channel) or whether a JSONB column on the User table would suffice.
        The right choice depends on anticipated query patterns that are not yet defined.
    """),

    "risk_compliance": textwrap.dedent("""\
        ## Risk & Compliance Analysis

        This scenario introduces a meaningful expansion of the attack surface and
        creates several new compliance obligations that must be addressed before launch.

        **New Risks**
        Shareable guest links represent an access-control risk: if a link is shared
        beyond the intended audience, unauthorized users may view sensitive resources.
        Severity is high; mitigation is time-bounded expiry plus an access revocation
        API. The bulk export feature creates a data-exfiltration vector; severity is
        medium; mitigation is rate-limiting plus audit logging of all export requests.

        **Compliance Requirements**
        If the platform handles personal data (the spec is ambiguous on this point),
        GDPR Article 17 (right to erasure) applies to the new entities: guest access
        tokens and export job records must be purged on user deletion. CCPA equivalents
        apply for California-based users. The notification cadence feature may trigger
        CAN-SPAM or GDPR consent requirements if email is used as a channel.

        **Security Implications**
        Guest access tokens must be cryptographically random (min 128 bits) and stored
        as hashes rather than plaintext. The export endpoint must validate that the
        requesting user owns the resource being exported; IDOR is the primary concern.

        **Audit Trail Needs**
        All guest link creation, revocation, and access events must be written to an
        immutable audit log. Export job initiation and completion events must also be
        logged with the requesting user identity and the export scope.

        **Open Questions**
        The spec does not state whether the platform has completed a SOC 2 Type II audit
        or is pursuing one. If so, the new features must be reviewed against the CC6
        logical access controls before launch.
    """),

    "rollout_ops": textwrap.dedent("""\
        ## Rollout & Operations Analysis

        This scenario requires a staged rollout across three weeks to manage risk and
        validate each new capability before broad release.

        **Deployment Steps**
        Week 1: deploy schema migrations (additive only, safe to run during business
        hours); deploy the notification service in shadow mode (writes to queue but does
        not deliver); deploy API gateway changes behind the guest-access feature flag
        (off by default). Week 2: enable guest-access flag for 5% of workspaces;
        monitor error rates and latency; enable notification delivery for internal
        dogfood users only. Week 3: ramp guest-access to 100%; enable bulk export for
        all users; decommission the legacy export endpoint after 14 days.

        **Feature Flag Needs**
        Three flags are required: guest_access_enabled (boolean, workspace-scoped),
        bulk_export_enabled (boolean, user-scoped), notification_cadence_enabled
        (boolean, user-scoped). All flags should default to false and be controllable
        via the existing LaunchDarkly integration assumed by the spec.

        **Rollback Plan**
        Schema migrations are additive and rollback-safe. The notification service can
        be scaled to zero without affecting core functionality. The API gateway changes
        are gated by feature flags and can be disabled instantly. No destructive rollback
        is required for any component in this scenario.

        **Monitoring Additions**
        New alerts: notification delivery lag > 60s (P95), export job queue depth > 500,
        guest link 403 error rate > 2% over 5 minutes. New dashboards: notification
        throughput, export job completion rate, guest session duration.

        **Open Questions**
        The spec does not address the on-call rotation for the new notification service.
        Ownership must be assigned before the Week 2 ramp begins to ensure there is a
        clear escalation path if delivery failures occur in production.
    """),
}


# ---------------------------------------------------------------------------
# Mock JSON responses per role
# ---------------------------------------------------------------------------

_MOCK_JSON: dict[str, dict] = {
    "product": {
        "user_stories_added": [
            "As a user, I can configure my notification cadence so I receive alerts at my preferred frequency",
            "As an admin, I can bulk-export workspace data so I can perform offline analysis",
            "As a guest, I can view shared resources in read-only mode so I can review content without an account",
        ],
        "user_stories_removed": [
            "As a new user, I am shown contextual tooltips throughout onboarding (deferred — replaced by quick-start wizard)",
        ],
        "feature_scope_changes": [
            {
                "feature": "Onboarding flow",
                "change": "Replaced contextual tooltip tour with a 4-step quick-start wizard",
                "driven_by": "Spec assumption that users arrive with domain knowledge",
            },
            {
                "feature": "Advanced filtering panel",
                "change": "Deferred to later milestone per phased delivery assumption",
                "driven_by": "Phased delivery roadmap in spec section 3.2",
            },
        ],
        "success_metrics_affected": [
            "Time-to-first-value (TTFV) — target 48 hours, at risk if wizard is not gated properly",
            "Monthly active users — may be inflated by low-intent guest users",
            "Feature adoption rate for notification cadence — new metric required",
        ],
        "stakeholder_impacts": [
            {
                "stakeholder": "Customer Success",
                "impact": "Must update runbooks to cover new notification configuration options",
            },
            {
                "stakeholder": "Sales Engineering",
                "impact": "Benefits from read-only guest mode for prospect demos",
            },
        ],
        "cited_assumptions": [
            "Platform targets both self-serve and enterprise buyers simultaneously",
            "Users arrive with domain knowledge (spec section 2.1)",
            "48-hour TTFV target (spec section 4.3)",
        ],
        "confidence_notes": [
            "High confidence: user story additions are directly implied by the scenario parameters",
            "Medium confidence: MAU inflation risk depends on guest usage patterns not yet measured",
            "Low confidence: TTFV impact depends on wizard UX quality not yet validated",
        ],
        "open_questions": [
            "Does notification cadence feature require SMS gateway or email-only for initial release?",
            "Should guest users be counted in MAU for billing purposes?",
            "What is the maximum number of guest links per resource?",
        ],
    },

    "architecture": {
        "new_components": [
            "NotificationService — stateless, horizontally scalable, SQS-compatible message queue backend",
            "ReadReplicaDataStore — read-only replica of primary DB for guest view workloads",
            "GuestAccessTokenStore — fast lookup store (Redis or equivalent) for shareable link validation",
        ],
        "removed_components": [
            "LegacyExportEndpoint — decommissioned after 14-day migration window",
        ],
        "modified_components": [
            {
                "component": "APIGateway",
                "change": "Add guest-vs-authenticated permission boundary; new read-only context token passing",
            },
            {
                "component": "AuthMiddleware",
                "change": "Refactor from monolithic to granular permission checks to support guest role",
            },
            {
                "component": "ETLPipeline",
                "change": "Add fan-out stage to populate notification queue on qualifying events",
            },
        ],
        "new_dependencies": [
            "SQS-compatible message queue (AWS SQS or RabbitMQ)",
            "Object storage (S3 or equivalent) for bulk export artifacts",
            "Redis (or equivalent) for guest access token fast-path lookup",
        ],
        "api_surface_changes": [
            {"endpoint": "POST /notifications/preferences", "change": "New endpoint — upsert user notification cadence settings"},
            {"endpoint": "GET /export/bulk", "change": "New endpoint — initiate or poll async bulk export job"},
            {"endpoint": "GET /view/{resource_id}?mode=readonly", "change": "New endpoint — guest read-only resource view"},
        ],
        "scalability_implications": [
            "NotificationService bottleneck at 50k events/hour — single-threaded consumer creates >30s delivery lag",
            "Read replica must be in same AZ as primary to keep replication lag under 5 seconds",
            "Export jobs are CPU-intensive; must be isolated from the API request path",
        ],
        "cited_assumptions": [
            "SQS-compatible semantics for message queue (spec section 5.1)",
            "Auth is a solved problem — this assumption is challenged by the guest role requirement",
            "S3 or equivalent object storage available in the deployment environment",
        ],
        "confidence_notes": [
            "High confidence: new components are directly required by the scenario parameters",
            "Medium confidence: read replica necessity depends on actual guest traffic volume",
            "Low confidence: Redis fast-path may be overengineering if guest token volume is low",
        ],
        "open_questions": [
            "Should bulk export endpoint be synchronous or async (job-based)?",
            "What is the acceptable guest link validation latency SLA?",
            "Does the message queue need exactly-once delivery semantics?",
        ],
    },

    "ux": {
        "new_user_flows": [
            "Quick-start wizard: 4 steps — workspace naming → invite teammates → select template → confirm billing",
            "Guest read-only flow: arrive via shareable link → view resource → comment → request access CTA",
            "Notification preferences flow: Settings → Notifications tab → configure cadence per channel",
        ],
        "removed_user_flows": [
            "Contextual tooltip onboarding tour (replaced by quick-start wizard)",
        ],
        "modified_flows": [
            {
                "flow": "Settings navigation",
                "change": "Add Notifications tab between Profile and Security tabs",
            },
            {
                "flow": "Resource view",
                "change": "Add locked-state overlay and read-only banner for guest users",
            },
        ],
        "new_ui_components": [
            "MultiStepModal — progress indicator, step content, back/next/finish controls",
            "ReadOnlyBanner — persistent top banner indicating view-only mode with Request Access CTA",
            "LockedStateOverlay — aria-disabled overlay for interactive elements in guest view",
            "NotificationCadenceForm — channel selector, frequency picker, quiet-hours range input",
        ],
        "accessibility_implications": [
            "LockedStateOverlay must use aria-disabled and descriptive aria-label on each locked element",
            "MultiStepModal must trap focus within the modal dialog until dismissed (WCAG 2.1 AA)",
            "ReadOnlyBanner must be announced by screen readers on page load via aria-live region",
            "NotificationCadenceForm quiet-hours time inputs must support keyboard navigation",
        ],
        "platform_considerations": [
            "Quick-start wizard should be responsive — single-column layout on mobile (<768px)",
            "Bulk export trigger placement conflicts with bottom navigation bar on mobile — needs design review",
            "Guest view shareable links must work without the native app installed (web fallback required)",
        ],
        "cited_assumptions": [
            "Users arrive with domain knowledge — drives lightweight wizard design",
            "Guests can comment but not edit (spec section 2.4)",
            "WCAG 2.1 AA is the accessibility target (spec section 6.1)",
        ],
        "confidence_notes": [
            "High confidence: wizard flow steps are directly specified in scenario parameters",
            "Medium confidence: Notifications tab position is a UX convention, not mandated by spec",
            "Low confidence: mobile bulk-export placement requires validation — conflict is inferred",
        ],
        "open_questions": [
            "What breakpoints should the quick-start wizard support on mobile?",
            "Should the ReadOnlyBanner be dismissible or always visible during guest sessions?",
            "Is there a dark mode requirement for the new components?",
        ],
    },

    "data_model": {
        "new_entities": [
            "NotificationPreference — stores user-scoped cadence settings (frequency, channel, quiet_hours)",
            "GuestAccessToken — stores shareable link metadata (resource_id, token_hash, expiry, scope)",
            "BulkExportJob — records async export job status, requester, S3 key, and completion timestamp",
        ],
        "removed_entities": [],
        "schema_changes": [
            {
                "entity": "User",
                "change": "Add guest_access_enabled boolean column (default false)",
            },
            {
                "entity": "Resource",
                "change": "Add shareable_link_active boolean and last_exported_at timestamp",
            },
        ],
        "new_relationships": [
            "NotificationPreference many-to-one User (one record per channel per user)",
            "GuestAccessToken many-to-one Resource",
            "BulkExportJob many-to-one User (the requester)",
        ],
        "migration_needs": [
            "Migration 001: ALTER TABLE users ADD COLUMN guest_access_enabled BOOLEAN DEFAULT FALSE",
            "Migration 002: ALTER TABLE resources ADD COLUMN shareable_link_active BOOLEAN DEFAULT FALSE, ADD COLUMN last_exported_at TIMESTAMPTZ",
            "Migration 003: CREATE TABLE notification_preferences (...)",
            "Migration 004: CREATE TABLE guest_access_tokens (...)",
            "Migration 005: CREATE TABLE bulk_export_jobs (...)",
        ],
        "storage_implications": [
            "BulkExportJob artifacts stored in object storage (S3) — 30-day lifecycle policy required",
            "GuestAccessToken table will grow unbounded without a cleanup job for expired tokens",
            "NotificationPreference rows are small (~50 bytes) — no storage concern at anticipated scale",
        ],
        "cited_assumptions": [
            "30-day retention for export artifacts (spec section 7.2)",
            "Tokens stored as hashes — plaintext never persisted (spec security requirements)",
            "Relational database is PostgreSQL (spec section 5.3)",
        ],
        "confidence_notes": [
            "High confidence: new entities are directly required by scenario features",
            "Medium confidence: JSONB alternative for NotificationPreference not ruled out",
            "Low confidence: token cleanup job interval depends on token volume projections not in spec",
        ],
        "open_questions": [
            "Should NotificationPreference use a dedicated table or JSONB column on User?",
            "What is the maximum token lifetime — spec says 'time-bounded' but gives no duration",
            "Does BulkExportJob need a soft-delete mechanism for GDPR compliance?",
        ],
    },

    "risk_compliance": {
        "new_risks": [
            {
                "risk": "Guest link over-sharing — shareable link accessed by unintended audiences",
                "severity": "high",
                "mitigation": "Time-bounded expiry + one-click revocation API + access audit log",
            },
            {
                "risk": "Bulk export data exfiltration — large-scale extraction of sensitive data",
                "severity": "medium",
                "mitigation": "Rate limiting (1 export per user per hour) + audit log of all export events",
            },
            {
                "risk": "IDOR on export endpoint — user exports resources they do not own",
                "severity": "high",
                "mitigation": "Server-side ownership validation before job creation; never trust client-supplied resource IDs",
            },
            {
                "risk": "Notification channel spam compliance — email notifications may trigger CAN-SPAM or GDPR consent requirements",
                "severity": "medium",
                "mitigation": "Double opt-in for email notifications; include unsubscribe link in all emails",
            },
        ],
        "mitigated_risks": [
            "Onboarding drop-off risk reduced by quick-start wizard replacing tooltip tour",
        ],
        "compliance_requirements": [
            "GDPR Article 17: GuestAccessToken and BulkExportJob records must be purged on user deletion",
            "CCPA: California users must be able to request deletion of export artifacts",
            "CAN-SPAM / GDPR: email notification opt-in and unsubscribe mechanism required",
        ],
        "security_implications": [
            "GuestAccessToken must use cryptographically random values (min 128 bits), stored as SHA-256 hash",
            "Bulk export endpoint must validate resource ownership server-side to prevent IDOR",
            "Auth middleware refactor must be reviewed for privilege escalation before deployment",
        ],
        "audit_trail_needs": [
            "Immutable log: guest link created, accessed, revoked — with actor identity and timestamp",
            "Immutable log: export job initiated and completed — with requester identity and resource scope",
            "Immutable log: notification preference changes — with actor identity and before/after values",
        ],
        "cited_assumptions": [
            "Platform handles personal data (spec is ambiguous — this risk is flagged as uncertain)",
            "SOC 2 Type II audit status unknown — must be confirmed before launch",
            "Email is a notification channel option (spec section 3.4)",
        ],
        "confidence_notes": [
            "High confidence: IDOR and guest link risks are directly introduced by scenario features",
            "Medium confidence: GDPR applicability depends on user geography — not specified in spec",
            "Low confidence: SOC 2 CC6 impact depends on audit scope not yet confirmed",
        ],
        "open_questions": [
            "Has the platform completed a SOC 2 Type II audit? If so, do new features require re-assessment?",
            "What is the maximum guest link lifetime — legal minimum for time-bounded expiry?",
            "Is SMS a supported notification channel? If so, TCPA compliance is required in the US.",
        ],
    },

    "rollout_ops": {
        "deployment_steps": [
            "Week 1 Day 1: Run additive schema migrations (safe during business hours)",
            "Week 1 Day 2: Deploy NotificationService in shadow mode (queue writes, no delivery)",
            "Week 1 Day 3: Deploy API gateway changes with guest_access_enabled flag set to OFF",
            "Week 2 Day 1: Enable guest_access_enabled flag for 5% of workspaces; monitor error rates",
            "Week 2 Day 3: Enable notification delivery for internal dogfood users only",
            "Week 3 Day 1: Ramp guest_access_enabled to 100% of workspaces",
            "Week 3 Day 2: Enable bulk_export_enabled for all users",
            "Week 3 Day 14: Decommission legacy export endpoint after 14-day migration window",
        ],
        "feature_flag_needs": [
            "guest_access_enabled — boolean, workspace-scoped, default false (LaunchDarkly)",
            "bulk_export_enabled — boolean, user-scoped, default false (LaunchDarkly)",
            "notification_cadence_enabled — boolean, user-scoped, default false (LaunchDarkly)",
        ],
        "rollback_plan": (
            "All schema migrations are additive and backward-compatible — no rollback required. "
            "NotificationService can be scaled to zero without impacting core product. "
            "All new API surface is gated by feature flags — disable flags to instant-rollback. "
            "No destructive rollback steps are required for any component in this scenario."
        ),
        "monitoring_additions": [
            "Alert: notification delivery lag P95 > 60 seconds",
            "Alert: export job queue depth > 500 items",
            "Alert: guest link 403 error rate > 2% over 5-minute window",
            "Dashboard: notification throughput (events/min, delivery success rate)",
            "Dashboard: export job completion rate and P95 duration",
            "Dashboard: guest session duration and request-access conversion rate",
        ],
        "infrastructure_changes": [
            "Provision SQS-compatible message queue with dead-letter queue and 14-day retention",
            "Provision S3 bucket for export artifacts with 30-day lifecycle policy",
            "Provision read replica of primary database (same AZ for low replication lag)",
            "Add Redis node (or equivalent) for guest access token fast-path lookups",
        ],
        "migration_scripts_needed": [
            "001_add_user_guest_access_enabled.sql",
            "002_add_resource_shareable_and_export_fields.sql",
            "003_create_notification_preferences.sql",
            "004_create_guest_access_tokens.sql",
            "005_create_bulk_export_jobs.sql",
            "cleanup_expired_guest_tokens.py — scheduled daily cron",
        ],
        "estimated_rollout_days": 21,
        "cited_assumptions": [
            "LaunchDarkly is the existing feature flag system (spec section 8.1)",
            "Deployments happen during business hours (spec ops requirements)",
            "14-day migration window for legacy endpoint (spec transition plan)",
        ],
        "confidence_notes": [
            "High confidence: feature flags and migration scripts are directly required",
            "Medium confidence: 21-day timeline assumes no blocking dependencies — may compress to 14",
            "Low confidence: Redis provisioning timeline depends on infrastructure team capacity",
        ],
        "open_questions": [
            "Who owns the on-call rotation for the new NotificationService?",
            "What is the approved maintenance window for schema migrations in production?",
            "Is there a cost approval required for the new infrastructure components?",
        ],
    },
}


def _mock_json_for_role(role: str) -> dict:
    return _MOCK_JSON.get(role, _MOCK_JSON["product"])


class MockProvider(LLMProvider):
    """Returns realistic hard-coded responses. No API key or network call needed."""

    async def complete(self, system: str, user: str, max_tokens: int = 4096) -> str:
        """Return a role-appropriate ~300-word markdown analysis.

        The analysis references spec content from `user` by echoing the first
        meaningful noun phrase it can extract, making the output feel grounded.
        """
        role = _detect_role(system)
        base_analysis = _MOCK_ANALYSIS.get(role, _MOCK_ANALYSIS["product"])

        # Append a brief note that references something from the user content
        spec_snippet = _extract_snippet(user)
        addendum = (
            f"\n\n---\n*Analysis grounded on spec content: \"{spec_snippet}\"*\n"
            if spec_snippet
            else ""
        )
        return base_analysis + addendum

    async def complete_json(self, system: str, user: str, max_tokens: int = 4096) -> dict:
        """Return a realistic, fully-populated JSON dict for the detected role."""
        role = _detect_role(system)
        return _mock_json_for_role(role)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_snippet(text: str, max_length: int = 80) -> str:
    """Extract the first non-empty, non-header line from a spec for grounding."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("```"):
            return stripped[:max_length] + ("..." if len(stripped) > max_length else "")
    return ""
