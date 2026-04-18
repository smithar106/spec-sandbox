# Enterprise SSO: SAML 2.0 + OIDC Integration

**Author:** Marcus Delgado, Staff Engineer — Identity & Access  
**Reviewers:** Carla Okonkwo (Security), Drew Park (Backend), Lisa Tran (PM — Enterprise)  
**Status:** RFC — final review before implementation  
**Last Updated:** 2026-03-28  
**Target:** Q2 2026, GA by 2026-07-01  

---

## Background

Fathom currently supports email/password and Google OAuth for authentication. As we close deals in the enterprise segment, every prospect above $50K ACV has asked for SSO in the first two calls. We have lost at least three confirmed-verbal deals to competitors in the last 6 months because we could not provide SSO before contract signature.

The enterprise security review process at most buyers requires SAML 2.0 at minimum, with OIDC increasingly requested by companies that have moved their IdP to a cloud-native provider (Okta, Azure AD, Google Workspace). We need to support both protocols to cover the realistic buyer landscape.

This document defines the engineering scope, architecture decisions, data model changes, and rollout plan for adding enterprise SSO to Fathom's web application and API.

---

## Scope

**In scope for this release:**
- SAML 2.0 SP-initiated and IdP-initiated login flows
- OIDC Authorization Code flow with PKCE
- Organization-scoped SSO configuration (one IdP config per org)
- Just-in-time (JIT) user provisioning on first SSO login
- Domain-based routing (user types email → system determines SSO org → redirects to IdP)
- Admin UI for configuring SSO in the Organization Settings page
- Session management: SSO sessions expire with the IdP session when Single Logout (SLO) is implemented (SLO is v1.1, not this release)

**Explicitly out of scope:**
- SCIM 2.0 automated user provisioning/deprovisioning (separate RFC, Q3 2026)
- Multi-IdP per organization (single IdP per org enforced for v1)
- SSO for the mobile app (tracked separately)
- Single Logout (SLO) — users must log out from both Fathom and IdP separately

---

## Architecture Overview

```
Browser / Client
      |
      |  (1) Initiate SSO login
      v
  Fathom Auth Service  ──────────────────────────────────────────────────┐
      |                                                                   |
      |  (2a) SAML: Generate AuthnRequest, redirect to IdP SSO URL       |
      |  (2b) OIDC: Redirect to /authorize with code_challenge           |
      v                                                                   |
  Customer IdP (Okta / Azure AD / Ping / etc.)                           |
      |                                                                   |
      |  (3a) SAML: POST SAMLResponse to /auth/saml/callback             |
      |  (3b) OIDC: Redirect to /auth/oidc/callback?code=...             |
      v                                                                   |
  Fathom Auth Service                                                     |
      |                                                                   |
      |  (4) Validate assertion/token, JIT-provision user if new         |
      |  (5) Issue Fathom session cookie + JWT                           |
      v                                                                   |
  Application (normal session handling)  ◄──────────────────────────────┘
```

The Auth Service is an existing internal service. SSO will be added as a new module within it rather than a separate service. Certificate management (SP signing key, SP encryption key) will use our existing secrets management in AWS Secrets Manager.

---

## API Changes

### New Endpoints

```
POST   /auth/saml/initiate          # SP-initiated SAML login
POST   /auth/saml/callback          # Receive SAMLResponse from IdP
GET    /auth/saml/metadata          # Serve SP metadata XML to customer IT admins
GET    /auth/oidc/initiate          # OIDC authorization redirect
GET    /auth/oidc/callback          # Handle authorization code exchange
POST   /api/v1/orgs/:org_id/sso     # Create/update SSO configuration (admin only)
GET    /api/v1/orgs/:org_id/sso     # Fetch SSO configuration (admin only)
DELETE /api/v1/orgs/:org_id/sso     # Remove SSO configuration
POST   /api/v1/orgs/:org_id/sso/test  # Validate IdP config (dry-run assertion check)
```

### Modified Endpoints

`POST /auth/login` — Before password check, look up email domain against `sso_configs` table. If a match exists and `sso_required = true`, return HTTP 302 redirect to `/auth/saml/initiate` or `/auth/oidc/initiate` rather than processing the password.

---

## Data Model Changes

```sql
CREATE TABLE sso_configs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    protocol        VARCHAR(10) NOT NULL CHECK (protocol IN ('saml', 'oidc')),
    -- SAML fields
    idp_entity_id       TEXT,
    idp_sso_url         TEXT,
    idp_certificate     TEXT,          -- PEM, base64-encoded
    -- OIDC fields
    oidc_issuer         TEXT,
    oidc_client_id      TEXT,
    oidc_client_secret  TEXT,          -- encrypted at rest via KMS
    -- Common
    attribute_mapping   JSONB NOT NULL DEFAULT '{}',
    sso_required        BOOLEAN NOT NULL DEFAULT FALSE,
    domain_hints        TEXT[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          UUID REFERENCES users(id),
    UNIQUE (org_id)
);

-- Add to users table
ALTER TABLE users ADD COLUMN sso_subject_id TEXT;
ALTER TABLE users ADD COLUMN sso_provider_id UUID REFERENCES sso_configs(id);
ALTER TABLE users ADD COLUMN provisioned_via VARCHAR(20) DEFAULT 'signup';
CREATE UNIQUE INDEX ON users(sso_provider_id, sso_subject_id) WHERE sso_subject_id IS NOT NULL;
```

`attribute_mapping` stores a JSON object mapping IdP attribute names to Fathom fields, e.g. `{"email": "email", "given_name": "first_name", "family_name": "last_name", "groups": "role"}`.

---

## Security Requirements

1. **Certificate validation:** All SAML assertions must be signed. Unsigned assertions must be rejected with HTTP 400. We will not support unencrypted assertions in production.
2. **Replay attack prevention:** `InResponseTo` attribute on SAML responses must match the stored request ID. OIDC `state` and `nonce` parameters must match stored values. Both expire after 10 minutes.
3. **Redirect URI allowlist:** OIDC `redirect_uri` must exactly match a value registered in `sso_configs`. No pattern matching.
4. **JIT provisioning scope:** JIT-provisioned users default to the Member role. Role elevation requires explicit action from an org Admin; it cannot be driven by IdP attributes in v1 (reduces blast radius of IdP misconfiguration).
5. **SSO bypass:** Org admins can disable SSO for a specific user to handle break-glass scenarios. This action is logged in the audit log.
6. **Client secret storage:** OIDC client secrets encrypted with a KMS-managed key before storage. Decrypted only at runtime in the Auth Service process memory.

---

## Rollout Plan

**Phase 1 — Internal testing (weeks 1–2):** Configure Fathom's own Okta as an OIDC IdP against a staging environment. Engineering team dogfoods the login flow.

**Phase 2 — Design partner beta (weeks 3–5):** 3 enterprise customers on paid contracts configure SSO in staging, then production. Dedicated Slack channel for support. Bug SLA: P1 within 4 hours.

**Phase 3 — GA (week 6+):** SSO configuration UI available to all orgs on the Enterprise plan. Documentation published to help center. Sales and CS briefed.

**Feature flag:** The entire SSO flow will be behind the `enterprise_sso_enabled` flag gated on org ID. Rollout proceeds org-by-org during beta.

---

## Open Questions

1. **SLO timeline:** Customers in Phase 2 have asked about Single Logout. Should we commit to SLO in v1.1 (Q3) in writing, or leave the date open?
2. **Multi-IdP:** One beta customer (DataCo) has an M&A situation and needs two SAML IdPs per org. Do we scope this to Q3 or tell them it's not on the roadmap?
3. **SCIM dependency:** Some enterprise IT teams assume SCIM comes with SSO. Do we proactively communicate the deprovisioning gap, and if so, what's the mitigation (manual offboarding SOP)?
4. **Error UX:** When IdP authentication fails (wrong binding, expired certificate), what does the user see? We need to balance security (don't leak config details) with debuggability (IT admins need to troubleshoot).
