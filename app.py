"""Spec Sandbox — Streamlit visualization app.

Run: streamlit run app.py
Reads from spec_sandbox.db in the current directory.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Spec Sandbox",
    page_icon="🔀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# DB helpers — thin sync wrappers so Streamlit doesn't need async
# ---------------------------------------------------------------------------

import sys
sys.path.insert(0, str(Path(__file__).parent / "src"))

from spec_sandbox.storage.database import Database
from spec_sandbox.domain.models import (
    AgentRole, AgentRun, BaseSpec, BranchComparison,
    CanonicalSpecRevision, DecisionRecord, ProjectionArtifact,
    RunStatus, Scenario, SpecBranch,
)

DB_PATH = "spec_sandbox.db"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@st.cache_resource
def get_db():
    db = Database(DB_PATH)
    _run(db.initialize())
    return db


def load_specs():
    return _run(get_db().list_base_specs())


def load_branches(spec_id):
    return _run(get_db().list_branches_for_spec(spec_id))


def load_runs(branch_id):
    return _run(get_db().list_runs_for_branch(branch_id))


def load_projections(branch_id):
    return _run(get_db().get_projections_for_branch(branch_id))


def load_scenario(scenario_id):
    return _run(get_db().get_scenario(scenario_id))


def load_latest_revision(spec_id):
    return _run(get_db().get_latest_revision(spec_id))


# ---------------------------------------------------------------------------
# Sidebar — spec selector
# ---------------------------------------------------------------------------

st.sidebar.title("🔀 Spec Sandbox")
st.sidebar.caption("Parallel spec branching & comparison")

if not Path(DB_PATH).exists():
    st.error(f"No database found at `{DB_PATH}`. Run `python demo.py` first to populate it.")
    st.stop()

specs = load_specs()
if not specs:
    st.warning("No specs in database yet. Run `python demo.py` to populate sample data.")
    st.stop()

spec_options = {s.title: s for s in specs}
selected_title = st.sidebar.selectbox("Select spec", list(spec_options.keys()))
spec: BaseSpec = spec_options[selected_title]

branches = load_branches(spec.id)
page = st.sidebar.radio(
    "View",
    ["Overview", "Branch Comparison", "Agent Outputs", "Canonical Spec"],
)

st.sidebar.markdown("---")
st.sidebar.caption(f"Spec ID: `{str(spec.id)[:8]}…`")
st.sidebar.caption(f"Branches: {len(branches)}")

# ---------------------------------------------------------------------------
# Overview page
# ---------------------------------------------------------------------------

if page == "Overview":
    st.title(f"📋 {spec.title}")
    st.caption(f"Imported from: `{spec.source_file or 'manual'}` · ID: `{spec.id}`")

    col1, col2, col3 = st.columns(3)
    col1.metric("Branches", len(branches))
    total_runs = sum(len(load_runs(b.id)) for b in branches)
    col2.metric("Agent Runs", total_runs)
    total_proj = sum(len(load_projections(b.id)) for b in branches)
    col3.metric("Projections", total_proj)

    st.markdown("---")
    st.subheader("Base Spec")
    with st.expander("Read full spec", expanded=False):
        st.markdown(spec.content)

    st.subheader("Branches Created")
    for branch in branches:
        scenario = load_scenario(branch.scenario_id)
        with st.expander(f"**{branch.name}**", expanded=True):
            col_a, col_b = st.columns([2, 1])
            with col_a:
                if scenario:
                    st.markdown(f"**Scenario:** {scenario.description or scenario.name}")
                    st.markdown("**Parameters changed:**")
                    for p in scenario.parameters:
                        st.markdown(
                            f"- `{p.key}`: ~~{p.original_value}~~ → **{p.new_value}**  "
                            f"*({p.dimension})*"
                        )
            with col_b:
                runs = load_runs(branch.id)
                complete = sum(1 for r in runs if r.status == RunStatus.COMPLETE)
                failed = sum(1 for r in runs if r.status == RunStatus.FAILED)
                st.metric("Agent Runs", f"{complete}/{len(runs)} complete")
                if failed:
                    st.error(f"{failed} failed")
                st.caption(f"Branch ID: `{str(branch.id)[:8]}…`")

    st.markdown("---")
    # Show mutations
    st.subheader("What changed in each branch")
    if branches:
        import sys; sys.path.insert(0, "src")
        from spec_sandbox.branching.engine import BranchingEngine
        engine = BranchingEngine()
        for branch in branches:
            changed = engine.list_changed_sections(branch)
            st.markdown(f"**{branch.name}:** {', '.join(changed) if changed else '*(no sections matched — overrides appended)*'}")

# ---------------------------------------------------------------------------
# Branch Comparison page
# ---------------------------------------------------------------------------

elif page == "Branch Comparison":
    st.title("⚖️ Branch Comparison")

    if not branches:
        st.info("No branches found. Run `create-scenarios` first.")
        st.stop()

    # Collect all projections
    all_projections: list[ProjectionArtifact] = []
    for b in branches:
        all_projections.extend(load_projections(b.id))

    branch_names = {str(b.id): b.name.split("@")[-1].strip() for b in branches}

    # ── Complexity scorecard ──────────────────────────────────────────
    st.subheader("Complexity & Time Estimates")

    import pandas as pd

    rows = []
    for b in branches:
        bprojs = [p for p in all_projections if p.branch_id == b.id]
        comps = sum(len(p.components) for p in bprojs)
        risks = sum(len(p.risk_areas) for p in bprojs)
        questions = sum(len(p.open_questions) for p in bprojs)
        complexity = min(10, max(1, 1 + (comps + risks) // 3))
        days = max(5, complexity * 5)
        rows.append({
            "Branch": branch_names[str(b.id)],
            "Complexity (1-10)": complexity,
            "Est. Days": days,
            "Components": comps,
            "Risks": risks,
            "Open Questions": questions,
        })

    df = pd.DataFrame(rows).set_index("Branch")
    st.dataframe(df, use_container_width=True)

    # Bar chart
    st.bar_chart(df[["Complexity (1-10)", "Risks", "Open Questions"]])

    st.markdown("---")

    # ── Invariants ────────────────────────────────────────────────────
    st.subheader("✅ Invariants — what's true across all branches")

    # Find open_questions present in 2+ branches
    from collections import Counter
    all_questions: list[str] = []
    for p in all_projections:
        all_questions.extend(p.open_questions)
    question_counts = Counter(all_questions)
    invariants = [q for q, c in question_counts.items() if c >= 2]

    all_risks: list[str] = []
    for p in all_projections:
        all_risks.extend(p.risk_areas)
    risk_counts = Counter(all_risks)
    shared_risks = [r for r, c in risk_counts.items() if c >= 2]

    if invariants or shared_risks:
        for inv in invariants[:8]:
            st.markdown(f"- {inv}")
        for r in shared_risks[:4]:
            st.markdown(f"- *(shared risk)* {r}")
    else:
        st.info("No strong invariants detected across branches — branches are quite differentiated.")

    st.markdown("---")

    # ── Side-by-side differences ──────────────────────────────────────
    st.subheader("🔀 Side-by-side: Key Dimensions")

    dimensions = [
        ("Components", "components"),
        ("API Changes", "api_changes"),
        ("UX Changes", "ux_changes"),
        ("Schema Changes", "schema_changes"),
        ("Risk Areas", "risk_areas"),
        ("Rollout Needs", "rollout_needs"),
        ("Open Questions", "open_questions"),
    ]

    for dim_label, dim_field in dimensions:
        with st.expander(dim_label, expanded=(dim_field in ("risk_areas", "open_questions"))):
            cols = st.columns(len(branches))
            for i, b in enumerate(branches):
                bprojs = [p for p in all_projections if p.branch_id == b.id]
                items: list[str] = []
                for p in bprojs:
                    items.extend(getattr(p, dim_field, []))
                # De-duplicate
                seen: set[str] = set()
                unique: list[str] = []
                for item in items:
                    key = item.lower().strip()
                    if key not in seen:
                        seen.add(key)
                        unique.append(item)
                with cols[i]:
                    st.markdown(f"**{branch_names[str(b.id)]}**")
                    if unique:
                        for item in unique[:6]:
                            st.markdown(f"• {item[:120]}")
                        if len(unique) > 6:
                            st.caption(f"…+{len(unique)-6} more")
                    else:
                        st.caption("*(none recorded)*")

    st.markdown("---")

    # ── Recommendation ────────────────────────────────────────────────
    st.subheader("💡 Recommendation")
    if df.shape[0] > 0:
        best = df["Complexity (1-10)"].idxmin()
        fewest_q = df.loc[best, "Open Questions"]
        st.success(
            f"**{best}** has the lowest complexity ({df.loc[best,'Complexity (1-10)']}/10) "
            f"with {fewest_q} open question(s). "
            "This is the lowest-risk starting point based on the current projections."
        )
        st.caption(
            "Note: With mock LLM, all branches produce identical mock outputs so scores are equal. "
            "Set ANTHROPIC_API_KEY and re-run agents for differentiated analysis."
        )

# ---------------------------------------------------------------------------
# Agent Outputs page
# ---------------------------------------------------------------------------

elif page == "Agent Outputs":
    st.title("🤖 Agent Outputs")

    if not branches:
        st.info("No branches yet.")
        st.stop()

    branch_labels = {b.id: b.name.split("@")[-1].strip() for b in branches}
    selected_branch_label = st.selectbox(
        "Select branch", [branch_labels[b.id] for b in branches]
    )
    selected_branch = next(b for b in branches if branch_labels[b.id] == selected_branch_label)

    runs = load_runs(selected_branch.id)

    role_order = [r.value for r in AgentRole]
    runs_by_role = {r.role.value: r for r in runs}

    st.markdown(f"**Branch:** {selected_branch.name}")
    st.caption(f"{len(runs)} agent runs · {sum(1 for r in runs if r.status == RunStatus.COMPLETE)} complete")
    st.markdown("---")

    for role_value in role_order:
        run: AgentRun | None = runs_by_role.get(role_value)
        status_icon = "✅" if (run and run.status == RunStatus.COMPLETE) else "❌" if (run and run.status == RunStatus.FAILED) else "⏳"

        with st.expander(f"{status_icon} **{role_value}**", expanded=False):
            if not run:
                st.info("No run recorded for this role.")
                continue

            col1, col2, col3 = st.columns(3)
            col1.metric("Status", run.status.value)
            if run.started_at and run.completed_at:
                dur = (run.completed_at - run.started_at).total_seconds()
                col2.metric("Duration", f"{dur:.1f}s")
            col3.metric("Run ID", str(run.id)[:8] + "…")

            tabs = st.tabs(["Structured Output", "Markdown", "Assumptions", "Open Questions"])

            with tabs[0]:
                if run.output_json:
                    # Show each key as its own section
                    for k, v in run.output_json.items():
                        if k in ("cited_assumptions", "confidence_notes", "open_questions"):
                            continue
                        if isinstance(v, list) and v:
                            st.markdown(f"**{k.replace('_', ' ').title()}**")
                            for item in v:
                                if isinstance(item, dict):
                                    st.markdown(f"- {json.dumps(item)}")
                                else:
                                    st.markdown(f"- {item}")
                        elif isinstance(v, str) and v:
                            st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")
                        elif isinstance(v, int):
                            st.markdown(f"**{k.replace('_', ' ').title()}:** {v}")
                else:
                    st.info("No structured JSON output.")

            with tabs[1]:
                if run.output_markdown:
                    st.markdown(run.output_markdown)
                else:
                    st.info("No markdown output.")

            with tabs[2]:
                assumptions = run.cited_assumptions or (run.output_json or {}).get("cited_assumptions", [])
                notes = (run.output_json or {}).get("confidence_notes", [])
                if assumptions:
                    st.markdown("**Cited Assumptions**")
                    for a in assumptions:
                        st.markdown(f"- {a}")
                if notes:
                    st.markdown("**Confidence Notes**")
                    for n in notes:
                        st.markdown(f"- {n}")
                if not assumptions and not notes:
                    st.info("No assumptions recorded.")

            with tabs[3]:
                questions = (run.output_json or {}).get("open_questions", [])
                if questions:
                    for q in questions:
                        st.markdown(f"- ❓ {q}")
                else:
                    st.info("No open questions recorded.")

# ---------------------------------------------------------------------------
# Canonical Spec page
# ---------------------------------------------------------------------------

elif page == "Canonical Spec":
    st.title("📄 Canonical Spec")

    revision: CanonicalSpecRevision | None = load_latest_revision(spec.id)

    if not revision:
        st.info("No canonical revision yet. Run `choose` then `merge` to create one.")
        st.markdown(
            "**Quick way:** run `python demo.py` which executes the full pipeline including merge."
        )
        st.stop()

    col1, col2, col3 = st.columns(3)
    col1.metric("Version", f"v{revision.version}")
    col2.metric("Decision ID", str(revision.decision_record_id)[:8] + "…")
    col3.metric("Created", revision.created_at.strftime("%Y-%m-%d %H:%M UTC"))

    st.markdown(f"**Summary:** {revision.revision_summary}")
    st.markdown("---")

    st.subheader("Canonical Spec Content")
    st.markdown(revision.content)

    st.markdown("---")
    st.download_button(
        label="⬇️ Download canonical spec (.md)",
        data=revision.content,
        file_name=f"{spec.title.lower().replace(' ', '-')}-v{revision.version}.md",
        mime="text/markdown",
    )
