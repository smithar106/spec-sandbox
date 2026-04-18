"""spec-sandbox CLI — Typer app.

Entry point:  spec-sandbox = "spec_sandbox.cli.main:app"
"""
from __future__ import annotations

import asyncio
import os
import uuid
from pathlib import Path
from typing import Optional

import typer
import yaml
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from spec_sandbox.domain.models import (
    BaseSpec,
    DecisionRecord,
    Scenario,
    ScenarioParameter,
)
from spec_sandbox.merge.finalizer import SpecFinalizer
from spec_sandbox.merge.planner import MergePlanner
from spec_sandbox.orchestrator import SandboxOrchestrator
from spec_sandbox.storage.database import Database

app = typer.Typer(
    name="spec-sandbox",
    help="AI-powered spec branching and scenario comparison system.",
    add_completion=False,
)
console = Console()

DB_PATH = "spec_sandbox.db"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_db() -> Database:
    """Return a Database pointed at the local spec_sandbox.db."""
    return Database(db_path=DB_PATH)


def _get_provider(model: str | None = None):
    """Return AnthropicProvider if ANTHROPIC_API_KEY is set, else MockProvider."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        from spec_sandbox.providers.anthropic_provider import AnthropicProvider

        kwargs = {"api_key": api_key}
        if model:
            kwargs["model"] = model
        return AnthropicProvider(**kwargs)
    else:
        from spec_sandbox.providers.mock_provider import MockProvider

        return MockProvider()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def init() -> None:
    """Create spec_sandbox.db in the current working directory."""

    async def _run() -> None:
        db = _get_db()
        await db.initialize()
        await db.close()

    asyncio.run(_run())
    rprint(f"[green]Initialised database:[/green] {DB_PATH}")


@app.command("import-spec")
def import_spec(file: Path = typer.Argument(..., help="Path to a markdown spec file.")) -> None:
    """Read a markdown file and save it as a BaseSpec."""
    if not file.exists():
        rprint(f"[red]File not found:[/red] {file}")
        raise typer.Exit(code=1)

    content = file.read_text(encoding="utf-8")
    # Use the filename stem as title (no extension)
    title = file.stem.replace("-", " ").replace("_", " ").title()
    spec = BaseSpec(title=title, content=content, source_file=str(file))

    async def _run() -> None:
        db = _get_db()
        await db.initialize()
        await db.save_base_spec(spec)
        await db.close()

    asyncio.run(_run())
    rprint(f"[green]Imported spec:[/green] {spec.id}  [bold]{spec.title}[/bold]")


@app.command("list-specs")
def list_specs() -> None:
    """List all saved BaseSpecs."""

    async def _run() -> list[BaseSpec]:
        db = _get_db()
        await db.initialize()
        specs = await db.list_base_specs()
        await db.close()
        return specs

    specs = asyncio.run(_run())

    if not specs:
        rprint("[yellow]No specs found. Use 'import-spec' to add one.[/yellow]")
        return

    table = Table(title="Saved Specs", show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold")
    table.add_column("Source File")
    table.add_column("Created At")

    for spec in specs:
        table.add_row(
            str(spec.id),
            spec.title,
            spec.source_file or "",
            spec.created_at.strftime("%Y-%m-%d %H:%M UTC"),
        )

    console.print(table)


@app.command("create-scenarios")
def create_scenarios(
    spec_id: str = typer.Argument(..., help="UUID of the target BaseSpec."),
    yaml_file: Path = typer.Argument(..., help="Path to a YAML file containing scenarios."),
) -> None:
    """Read a YAML file, save Scenarios, and create branches for the given spec."""
    try:
        sid = uuid.UUID(spec_id)
    except ValueError:
        rprint(f"[red]Invalid UUID:[/red] {spec_id}")
        raise typer.Exit(code=1)

    if not yaml_file.exists():
        rprint(f"[red]YAML file not found:[/red] {yaml_file}")
        raise typer.Exit(code=1)

    raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
    scenario_defs = raw.get("scenarios", [])
    if not scenario_defs:
        rprint("[red]No 'scenarios' key found in YAML.[/red]")
        raise typer.Exit(code=1)

    # Build Scenario objects
    scenarios: list[Scenario] = []
    for sdef in scenario_defs:
        params = [
            ScenarioParameter(
                name=p.get("name", p.get("key", "")),
                key=p["key"],
                original_value=p.get("original_value", ""),
                new_value=p.get("new_value", ""),
                rationale=p.get("rationale", ""),
                dimension=p.get("dimension", "general"),
            )
            for p in sdef.get("parameters", [])
        ]
        scenarios.append(
            Scenario(
                name=sdef["name"],
                description=sdef.get("description", ""),
                parameters=params,
            )
        )

    async def _run() -> None:
        from spec_sandbox.branching.engine import BranchingEngine

        db = _get_db()
        await db.initialize()

        spec = await db.get_base_spec(sid)
        if spec is None:
            rprint(f"[red]Spec not found:[/red] {sid}")
            await db.close()
            raise typer.Exit(code=1)

        engine = BranchingEngine()
        for scenario in scenarios:
            await db.save_scenario(scenario)
            branch = await engine.create_branch(spec, scenario)
            await db.save_branch(branch)
            rprint(
                f"  [green]Branch created:[/green] {branch.id}  "
                f"[bold]{branch.name}[/bold]"
            )

        await db.close()

    asyncio.run(_run())
    rprint(f"[green]Created {len(scenarios)} scenario(s) + branch(es) for spec {sid}.[/green]")


@app.command("run-agents")
def run_agents(
    spec_id: str = typer.Argument(..., help="UUID of the BaseSpec."),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model override."),
) -> None:
    """Run all agent roles on all branches for the given spec.

    Uses MockProvider by default; uses AnthropicProvider if ANTHROPIC_API_KEY is set.
    """
    try:
        sid = uuid.UUID(spec_id)
    except ValueError:
        rprint(f"[red]Invalid UUID:[/red] {spec_id}")
        raise typer.Exit(code=1)

    provider = _get_provider(model)
    provider_name = type(provider).__name__
    rprint(f"[dim]Provider:[/dim] {provider_name}")

    async def _run() -> None:
        db = _get_db()
        await db.initialize()

        spec = await db.get_base_spec(sid)
        if spec is None:
            rprint(f"[red]Spec not found:[/red] {sid}")
            await db.close()
            raise typer.Exit(code=1)

        branches = await db.list_branches_for_spec(sid)
        if not branches:
            rprint("[yellow]No branches found. Run 'create-scenarios' first.[/yellow]")
            await db.close()
            return

        orchestrator = SandboxOrchestrator(db=db, provider=provider)

        for branch in branches:
            # Get the scenario for this branch
            scenario = await db.get_scenario(branch.scenario_id)
            if scenario is None:
                rprint(f"[yellow]Scenario not found for branch {branch.id}, skipping.[/yellow]")
                continue

            rprint(f"\n[cyan]Running agents on branch:[/cyan] {branch.name}")
            for role in orchestrator.engine.__class__.__mro__:
                pass  # just using orchestrator._run_agent directly below

            from spec_sandbox.domain.models import AgentRole

            for role in list(AgentRole):
                run, projection = await orchestrator._run_agent(branch, role)
                status_style = "green" if run.status.value == "COMPLETE" else "red"
                rprint(
                    f"  [{status_style}]{run.status.value}[/{status_style}]  "
                    f"[bold]{role.value}[/bold]  run={run.id}"
                )

        await db.close()

    asyncio.run(_run())


@app.command("compare")
def compare(
    spec_id: str = typer.Argument(..., help="UUID of the BaseSpec."),
) -> None:
    """Run comparison across all branches and print the report."""
    try:
        sid = uuid.UUID(spec_id)
    except ValueError:
        rprint(f"[red]Invalid UUID:[/red] {spec_id}")
        raise typer.Exit(code=1)

    async def _run() -> None:
        db = _get_db()
        await db.initialize()

        branches = await db.list_branches_for_spec(sid)
        if not branches:
            rprint("[yellow]No branches found.[/yellow]")
            await db.close()
            return

        # Gather all projections for these branches
        from spec_sandbox.domain.models import ProjectionArtifact

        all_projections: list[ProjectionArtifact] = []
        for branch in branches:
            projs = await db.get_projections_for_branch(branch.id)
            all_projections.extend(projs)

        # Use the orchestrator's _build_comparison helper
        provider = _get_provider()
        orchestrator = SandboxOrchestrator(db=db, provider=provider)
        comparison = await orchestrator._build_comparison(branches, all_projections)
        await db.save_comparison(comparison)

        # Print report
        rprint(f"\n[bold underline]Comparison Report[/bold underline]  (id={comparison.id})\n")

        if comparison.recommendation:
            rprint(f"[green]Recommendation:[/green] {comparison.recommendation}\n")

        if comparison.invariants:
            rprint("[bold]Invariants (shared across all branches):[/bold]")
            for inv in comparison.invariants:
                rprint(f"  • {inv}")

        if comparison.material_differences:
            rprint("\n[bold]Material Differences:[/bold]")
            for diff in comparison.material_differences:
                rprint(f"  • {diff}")

        if comparison.risk_shifts:
            rprint("\n[bold]Risk Shifts:[/bold]")
            for rs in comparison.risk_shifts:
                rprint(f"  • {rs}")

        rprint("\n[bold]Complexity & Time Estimates:[/bold]")
        table = Table(show_header=True)
        table.add_column("Branch ID", style="cyan")
        table.add_column("Branch Name")
        table.add_column("Complexity (1-10)", justify="right")
        table.add_column("Est. Days", justify="right")
        branch_by_id = {str(b.id): b for b in branches}
        for branch_id_str, score in comparison.complexity_scores.items():
            branch_name = branch_by_id.get(branch_id_str, None)
            bname = branch_name.name if branch_name else branch_id_str
            days = comparison.time_estimate_days.get(branch_id_str, "?")
            table.add_row(branch_id_str[:8] + "…", bname, str(score), str(days))
        console.print(table)

        await db.close()

    asyncio.run(_run())


@app.command("choose")
def choose(
    spec_id: str = typer.Argument(..., help="UUID of the BaseSpec."),
) -> None:
    """Interactively pick a branch and record a DecisionRecord."""
    try:
        sid = uuid.UUID(spec_id)
    except ValueError:
        rprint(f"[red]Invalid UUID:[/red] {spec_id}")
        raise typer.Exit(code=1)

    async def _load_branches():
        db = _get_db()
        await db.initialize()
        branches = await db.list_branches_for_spec(sid)
        await db.close()
        return branches

    branches = asyncio.run(_load_branches())

    if not branches:
        rprint("[yellow]No branches found for this spec.[/yellow]")
        raise typer.Exit(code=1)

    # Print numbered list
    rprint("\n[bold]Available branches:[/bold]")
    for i, branch in enumerate(branches, start=1):
        rprint(f"  [cyan]{i}[/cyan]. {branch.name}  [dim](id={branch.id})[/dim]")

    # User picks
    choice_str = typer.prompt("\nEnter branch number to choose")
    try:
        choice_idx = int(choice_str) - 1
        assert 0 <= choice_idx < len(branches)
    except (ValueError, AssertionError):
        rprint(f"[red]Invalid choice:[/red] {choice_str}")
        raise typer.Exit(code=1)

    chosen = branches[choice_idx]

    # Optionally pick hybrid branches
    hybrid_ids: list[uuid.UUID] = []
    hybrid_str = typer.prompt(
        "Hybrid branch numbers to combine (comma-separated, or leave blank)",
        default="",
    ).strip()
    if hybrid_str:
        for part in hybrid_str.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                hidx = int(part) - 1
                assert 0 <= hidx < len(branches)
                if branches[hidx].id != chosen.id:
                    hybrid_ids.append(branches[hidx].id)
            except (ValueError, AssertionError):
                rprint(f"[yellow]Skipping invalid hybrid index:[/yellow] {part}")

    rationale = typer.prompt("Rationale for this decision", default="")
    criteria_raw = typer.prompt("Criteria used (comma-separated)", default="")
    criteria = [c.strip() for c in criteria_raw.split(",") if c.strip()]

    # Build discarded alternatives
    discarded = [
        {"branch_id": str(b.id), "reason": "Not selected"}
        for b in branches
        if b.id != chosen.id and b.id not in hybrid_ids
    ]

    decision = DecisionRecord(
        chosen_branch_id=chosen.id,
        hybrid_branch_ids=hybrid_ids,
        rationale=rationale,
        criteria_used=criteria,
        discarded_alternatives=discarded,
    )

    async def _save() -> None:
        db = _get_db()
        await db.initialize()
        await db.save_decision(decision)
        await db.close()

    asyncio.run(_save())
    rprint(
        f"\n[green]Decision recorded:[/green] {decision.id}\n"
        f"  Chosen branch: [bold]{chosen.name}[/bold]\n"
        f"  Hybrid branches: {len(hybrid_ids)}"
    )


@app.command("merge")
def merge(
    spec_id: str = typer.Argument(..., help="UUID of the BaseSpec."),
) -> None:
    """Run MergePlanner + SpecFinalizer and print the canonical spec."""
    try:
        sid = uuid.UUID(spec_id)
    except ValueError:
        rprint(f"[red]Invalid UUID:[/red] {spec_id}")
        raise typer.Exit(code=1)

    async def _run() -> None:
        db = _get_db()
        await db.initialize()

        spec = await db.get_base_spec(sid)
        if spec is None:
            rprint(f"[red]Spec not found:[/red] {sid}")
            await db.close()
            raise typer.Exit(code=1)

        # Load the most recent decision
        # We fetch all decisions; pick the most recently decided one for this spec's branches
        branches = await db.list_branches_for_spec(sid)
        branch_ids = {str(b.id) for b in branches}
        branch_by_id = {str(b.id): b for b in branches}

        # Scan decisions table via low-level — we list all decisions and filter
        # by whether chosen_branch_id is one of our branches.
        # Database doesn't expose list_decisions, so we query each branch's last run
        # decisions to find one. Instead, we use a small workaround: store/recall by
        # iterating stored decisions indirectly.
        # Simplest approach: we added save_decision; we'll query the db directly.
        decision: DecisionRecord | None = None
        async with db._db.execute(
            "SELECT data FROM decisions ORDER BY rowid DESC"
        ) as cur:
            async for row in cur:
                candidate = DecisionRecord.model_validate_json(row["data"])
                if str(candidate.chosen_branch_id) in branch_ids:
                    decision = candidate
                    break

        if decision is None:
            rprint(
                "[red]No decision found for this spec. Run 'choose' first.[/red]"
            )
            await db.close()
            raise typer.Exit(code=1)

        chosen_branch = branch_by_id.get(str(decision.chosen_branch_id))
        if chosen_branch is None:
            rprint(f"[red]Chosen branch not found:[/red] {decision.chosen_branch_id}")
            await db.close()
            raise typer.Exit(code=1)

        hybrid_branches = [
            branch_by_id[str(hid)]
            for hid in decision.hybrid_branch_ids
            if str(hid) in branch_by_id
        ]

        planner = MergePlanner()
        plan = planner.plan_merge(chosen_branch, hybrid_branches, decision)

        if plan.conflicts:
            rprint(f"\n[yellow]Conflicts detected in sections:[/yellow] {plan.conflicts}")

        merged_content = planner.execute_merge(plan, spec)

        previous_revision = await db.get_latest_revision(sid)
        finalizer = SpecFinalizer()
        revision = finalizer.create_revision(spec, merged_content, decision, previous_revision)
        await db.save_revision(revision)

        rprint(f"\n[green]Canonical revision created:[/green] v{revision.version}  id={revision.id}")
        rprint(f"[dim]Summary:[/dim] {revision.revision_summary}\n")
        rprint("[bold underline]--- Canonical Spec ---[/bold underline]\n")
        rprint(merged_content)

        await db.close()

    asyncio.run(_run())


@app.command("export")
def export(
    spec_id: str = typer.Argument(..., help="UUID of the BaseSpec."),
    output_file: Path = typer.Argument(..., help="Output file path (markdown)."),
) -> None:
    """Export the latest canonical revision to a markdown file."""
    try:
        sid = uuid.UUID(spec_id)
    except ValueError:
        rprint(f"[red]Invalid UUID:[/red] {spec_id}")
        raise typer.Exit(code=1)

    async def _run() -> None:
        db = _get_db()
        await db.initialize()

        revision = await db.get_latest_revision(sid)
        if revision is None:
            rprint(
                "[red]No canonical revision found. Run 'merge' first.[/red]"
            )
            await db.close()
            raise typer.Exit(code=1)

        finalizer = SpecFinalizer()
        finalizer.export_markdown(revision, str(output_file))
        await db.close()

    asyncio.run(_run())
    rprint(
        f"[green]Exported revision to:[/green] {output_file}"
    )


if __name__ == "__main__":
    app()
