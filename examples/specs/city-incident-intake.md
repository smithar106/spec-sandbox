# City Operations Incident Intake Workflow

**Author:** Jordan Reyes, Product Lead — CivicOS Platform  
**Status:** Draft v0.2 — stakeholder review in progress  
**Last Updated:** 2026-04-01  
**Partners:** City of New Haven (pilot), Durham County, City of Madison  

---

## Product Vision

Most 311 platforms are designed around ticket submission — they stop the moment a resident hits "submit." The result is a black box: residents don't know what happened to their report, dispatchers work out of disconnected spreadsheets, and city leadership has no real-time operational picture.

This spec defines an end-to-end incident intake workflow that connects resident reporting to city dispatcher queues to field crew assignment to resident closure notification. The goal is to make a 311 report feel as trackable and responsive as an Uber ride — from the moment a pothole is reported to the moment a crew marks it repaired.

---

## User Personas

**Resident / Reporter** — A city resident submitting a complaint or service request from their phone. Not tech-savvy. English may not be their primary language. Submits and then forgets, unless proactively notified. Core need: confirmation that someone received their report, and eventual proof that it was resolved.

**311 Dispatcher** — A city employee, often in a call center or operations center, triaging incoming reports. Manages 80–200 incoming reports per shift. Core need: a queue that prioritizes by urgency and category, shows duplicates, and allows one-click assignment to a field crew or department.

**Field Crew / Department Staff** — The crew that actually fixes the problem (DPW, Parks, Sanitation). Receives assignment via mobile app or email. Core need: clear location, photo, and description — and a simple way to close the ticket when done.

**City Operations Manager** — Oversees service delivery. Monitors SLA compliance across departments. Core need: dashboard showing backlog by department, average resolution time by category, and spike alerts when volume exceeds capacity.

---

## Core Flows

### Flow 1: Resident Submission
1. Resident opens the app, selects a category (14 available: pothole, graffiti, abandoned vehicle, noise, etc.)
2. System prompts for GPS location or manual address entry.
3. Resident optionally adds a photo and free-text description.
4. Submission screen shows estimated response time based on historical category SLA.
5. System issues a tracking number and sends SMS or email confirmation within 30 seconds.
6. Report enters the dispatcher queue with status `NEW`.

### Flow 2: Dispatcher Triage
1. Dispatcher sees the incoming queue sorted by urgency score (configurable weights: category severity, time-in-queue, proximity to other open tickets of same type).
2. Dispatcher reviews the report, photo, and location map.
3. System surfaces potential duplicates (same category, within 200-meter radius, within 72 hours) and allows the dispatcher to merge.
4. Dispatcher assigns to a department or specific crew; adds internal notes if needed.
5. Status changes to `ASSIGNED`; resident receives push/SMS notification.

### Flow 3: Field Resolution
1. Field crew receives assignment on their mobile device (app notification or email with deep link).
2. Crew views photo, address, GPS pin, and any dispatcher notes.
3. On-site, crew marks `IN_PROGRESS` (optional; skippable for simple jobs).
4. Crew marks `RESOLVED`, optionally attaching a completion photo.
5. Status propagates to dispatcher queue and resident notification.

### Flow 4: Resident Closure Confirmation
1. Resident receives notification: "Your report #12345 has been resolved by Public Works."
2. Resident can confirm resolution with a thumbs-up, or reopen if the problem persists.
3. Reopened tickets re-enter the dispatcher queue with `REOPENED` status and elevated priority.

---

## Integration Requirements

- **GIS / Address Validation:** All submissions must geocode against the city's official parcel/address database (Esri ArcGIS or city-specific REST endpoint). Submissions with unresolvable addresses prompt the resident to drop a pin manually.
- **Work Order Systems:** For pilot cities, outbound webhook to the city's existing work order system (New Haven uses Cartegraph; Durham uses CityWorks). Webhooks fire on status transitions: `NEW → ASSIGNED` and `ASSIGNED → RESOLVED`.
- **SMS Gateway:** Twilio for outbound notifications. Cities provide their own Twilio account credentials; the platform is the orchestrator.
- **Data Export:** City ops managers can export all tickets in a date range as CSV or GeoJSON. Export available on-demand; no data warehouse integration in v1.
- **Authentication:** Dispatchers and field crew authenticate via the city's existing Active Directory or Google Workspace SSO. Resident-facing app uses phone number + OTP only (no passwords).

---

## Compliance Considerations

- **ADA / Section 508:** The resident-facing submission form must meet WCAG 2.1 AA. Screen reader compatibility required for all interactive elements. SMS confirmation required as fallback to push notifications.
- **Data retention:** Resident PII (name, phone, email) retained for 3 years per state public records law. After 3 years, PII is redacted but the ticket record and location data are retained indefinitely for operational analytics.
- **Personally Identifiable Submission Data:** Resident identity must not be visible to field crew — they see location and description only. Dispatcher can see resident contact info for follow-up but it is not included in work order exports.
- **Public records requests:** All ticket data is subject to FOIA. The platform must support bulk export of anonymized ticket history for public records requests within 5 business days of request.

---

## Success Metrics

| Metric | Baseline (manual / existing system) | 6-Month Target |
|---|---|---|
| Median time from submission to assignment | 48 hours | < 4 hours |
| Resident notification rate (status updates sent) | < 10% | > 90% |
| Duplicate report rate (unmerged) | ~30% of same-area reports | < 8% |
| Resident re-open rate | Unknown (no data) | Establish baseline |
| Dispatcher time-to-assign (median) | ~12 minutes | < 90 seconds |
| City operations manager weekly report prep time | 4+ hours manual | Automated dashboard |
