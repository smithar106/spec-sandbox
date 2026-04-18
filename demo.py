"""Full pipeline demo — runs without the CLI hook interference."""
import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT / "src"))

from spec_sandbox.domain.models import (
    AgentRole, BaseSpec, DecisionRecord, Scenario, ScenarioParameter
)
from spec_sandbox.branching.engine import BranchingEngine
from spec_sandbox.comparison.engine import ComparisonEngine
from spec_sandbox.merge.finalizer import SpecFinalizer
from spec_sandbox.merge.planner import MergePlanner
from spec_sandbox.orchestrator import SandboxOrchestrator
from spec_sandbox.providers.mock_provider import MockProvider
from spec_sandbox.storage.database import Database


SPEC_CONTENT = (_ROOT / "examples/specs/feature-flag-dashboard.md").read_text()

SEP = "─" * 70


async def main():
    # ── Setup ──────────────────────────────────────────────────────────
    db = Database(str(_ROOT / "spec_sandbox.db"))
    await db.initialize()

    spec = BaseSpec(title="Feature Flag Dashboard", content=SPEC_CONTENT)
    await db.save_base_spec(spec)

    print(f"\n{'═'*70}")
    print("  SPEC SANDBOX — FULL PIPELINE DEMO (mock LLM)")
    print(f"{'═'*70}")
    print(f"\n[1] Spec imported: {spec.id}")
    print(f"    Title: {spec.title}")

    # ── Define scenarios ───────────────────────────────────────────────
    scenarios = [
        Scenario(
            name="SMB-First Launch",
            description="Optimized for small teams under 500 flags",
            parameters=[
                ScenarioParameter(
                    name="scale_target", key="scale_target",
                    original_value="10,000 flags per org",
                    new_value="500 flags per org",
                    rationale="SMB orgs have fewer flags and simpler needs",
                    dimension="scale",
                ),
                ScenarioParameter(
                    name="auth_method", key="auth_method",
                    original_value="SSO and OAuth 2.0",
                    new_value="username/password + OAuth 2.0",
                    rationale="SMBs rarely have SSO infrastructure",
                    dimension="security",
                ),
            ],
        ),
        Scenario(
            name="Enterprise-Ready",
            description="Full enterprise feature set with SOC 2 compliance",
            parameters=[
                ScenarioParameter(
                    name="scale_target", key="scale_target",
                    original_value="10,000 flags per org",
                    new_value="100,000 flags per org",
                    rationale="Enterprise orgs have many teams and microservices",
                    dimension="scale",
                ),
                ScenarioParameter(
                    name="compliance", key="compliance",
                    original_value="standard security practices",
                    new_value="SOC 2 Type II compliant with full audit trail",
                    rationale="Enterprise buyers require compliance certifications",
                    dimension="compliance",
                ),
            ],
        ),
        Scenario(
            name="API-First Platform",
            description="Developer-focused API product, minimal UI",
            parameters=[
                ScenarioParameter(
                    name="delivery_model", key="delivery_model",
                    original_value="dashboard-first with REST API",
                    new_value="API-first with SDKs in 5 languages, minimal dashboard",
                    rationale="Developers want to integrate flags into CI/CD pipelines",
                    dimension="architecture",
                ),
            ],
        ),
    ]

    # ── Create branches ────────────────────────────────────────────────
    engine = BranchingEngine()
    branches = []
    print(f"\n[2] Creating branches...")
    print(SEP)

    for scenario in scenarios:
        await db.save_scenario(scenario)
        branch = await engine.create_branch(spec, scenario)
        await db.save_branch(branch)
        branches.append(branch)
        changed = engine.list_changed_sections(branch)
        print(f"  Branch: {branch.name}")
        print(f"    Mutations: {len(branch.mutations)}")
        print(f"    Changed sections: {changed or ['(appended overrides)']}")

    # ── Run agents ─────────────────────────────────────────────────────
    print(f"\n[3] Running 6 agents × {len(branches)} branches = {6*len(branches)} agent runs...")
    print(SEP)

    orchestrator = SandboxOrchestrator(db=db, provider=MockProvider())
    all_projections = []

    for branch in branches:
        print(f"\n  Branch: {branch.name}")
        for role in list(AgentRole):
            run, projection = await orchestrator._run_agent(branch, role)
            status = "✓" if run.status.value == "COMPLETE" else "✗"
            print(f"    {status} {role.value:<20}  run={str(run.id)[:8]}…")
            if projection:
                all_projections.append(projection)

    # ── Compare ────────────────────────────────────────────────────────
    print(f"\n[4] Comparing branches...")
    print(SEP)

    comparison = await orchestrator._build_comparison(branches, all_projections)
    await db.save_comparison(comparison)

    print(f"\n  Complexity & time estimates:")
    branch_map = {str(b.id): b.name for b in branches}
    for bid, score in comparison.complexity_scores.items():
        name = branch_map.get(bid, bid[:8])
        days = comparison.time_estimate_days.get(bid, "?")
        bar = "█" * score + "░" * (10 - score)
        print(f"    {name:<30} [{bar}] {score}/10  ~{days} days")

    if comparison.invariants:
        print(f"\n  Invariants (present in all branches):")
        for inv in comparison.invariants[:3]:
            print(f"    • {inv[:80]}")

    if comparison.risk_shifts:
        print(f"\n  Risk shifts across branches:")
        for rs in comparison.risk_shifts[:3]:
            print(f"    • {str(rs)[:80]}")

    if comparison.recommendation:
        print(f"\n  → Recommendation: {comparison.recommendation}")

    # ── Choose ─────────────────────────────────────────────────────────
    print(f"\n[5] Recording decision (auto-selecting Enterprise-Ready branch)...")
    print(SEP)

    chosen = branches[1]  # Enterprise-Ready
    discarded = [
        {"branch_id": str(b.id), "reason": "Not selected"}
        for b in branches if b.id != chosen.id
    ]
    decision = DecisionRecord(
        chosen_branch_id=chosen.id,
        rationale="Enterprise-Ready offers the best long-term foundation: SOC 2 compliance unlocks enterprise deals, and the 10x scale headroom prevents re-architecture within 18 months.",
        criteria_used=["compliance requirements", "scale headroom", "revenue potential"],
        discarded_alternatives=discarded,
        open_follow_ups=["Confirm SOC 2 audit timeline", "Get cost estimate for 100k flag infra"],
    )
    await db.save_decision(decision)
    print(f"  Decision recorded: {decision.id}")
    print(f"  Chosen: {chosen.name}")
    print(f"  Rationale: {decision.rationale[:80]}…")

    # ── Merge ──────────────────────────────────────────────────────────
    print(f"\n[6] Merging into canonical spec...")
    print(SEP)

    planner = MergePlanner()
    plan = planner.plan_merge(chosen, [], decision)
    merged = planner.execute_merge(plan, spec)

    if plan.conflicts:
        print(f"  ⚠ Conflicts in sections: {plan.conflicts}")
    else:
        print(f"  No conflicts detected.")

    print(f"  Merge instructions: {len(plan.merge_instructions)}")

    previous = await db.get_latest_revision(spec.id)
    finalizer = SpecFinalizer()
    revision = finalizer.create_revision(spec, merged, decision, previous)
    await db.save_revision(revision)

    print(f"  Canonical revision: v{revision.version}  id={revision.id}")
    print(f"  Summary: {revision.revision_summary[:100]}")

    # ── Export ─────────────────────────────────────────────────────────
    out_path = "demo-canonical-spec.md"
    finalizer.export_markdown(revision, out_path)
    print(f"\n[7] Exported canonical spec → {out_path}")

    # ── Print first 40 lines of canonical spec ─────────────────────────
    print(f"\n{'═'*70}")
    print("  CANONICAL SPEC (first 40 lines)")
    print(f"{'═'*70}")
    for i, line in enumerate(merged.splitlines()[:40], 1):
        print(f"  {line}")

    print(f"\n{'═'*70}")
    print("  DONE — full pipeline complete")
    print(f"{'═'*70}\n")

    await db.close()
    pass  # keep spec_sandbox.db so Streamlit can read it


asyncio.run(main())
