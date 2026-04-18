from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any
from uuid import UUID

import aiosqlite

from spec_sandbox.domain.models import (
    AgentRole,
    AgentRun,
    BaseSpec,
    BranchComparison,
    CanonicalSpecRevision,
    DecisionRecord,
    MergePlan,
    ProjectionArtifact,
    RunStatus,
    Scenario,
    ScenarioParameter,
    SpecBranch,
)


class Database:
    """Async SQLite storage layer for spec-sandbox.

    All Pydantic models are serialised to JSON TEXT and stored in a single
    ``data`` column per table.  Foreign-key columns are stored as TEXT UUIDs
    to allow fast filtering without parsing JSON on every row.

    Schema
    ------
    base_specs      (id TEXT PK, data TEXT)
    scenarios       (id TEXT PK, data TEXT)
    branches        (id TEXT PK, base_spec_id TEXT, data TEXT)
    agent_runs      (id TEXT PK, branch_id TEXT, data TEXT)
    projections     (id TEXT PK, branch_id TEXT, data TEXT)
    comparisons     (id TEXT PK, data TEXT)
    decisions       (id TEXT PK, data TEXT)
    revisions       (id TEXT PK, base_spec_id TEXT, version INTEGER, data TEXT)
    """

    def __init__(self, db_path: str = "spec_sandbox.db") -> None:
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def initialize(self) -> None:
        """Open the connection and create all tables if they do not exist."""
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._create_tables()

    async def close(self) -> None:
        """Close the underlying aiosqlite connection."""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def _db(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError(
                "Database.initialize() must be awaited before performing any operations."
            )
        return self._conn

    # ------------------------------------------------------------------
    # Schema creation
    # ------------------------------------------------------------------

    async def _create_tables(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS base_specs (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS scenarios (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS branches (
                id TEXT PRIMARY KEY,
                base_spec_id TEXT NOT NULL,
                data TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_branches_base_spec_id
                ON branches (base_spec_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                id TEXT PRIMARY KEY,
                branch_id TEXT NOT NULL,
                data TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_agent_runs_branch_id
                ON agent_runs (branch_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS projections (
                id TEXT PRIMARY KEY,
                branch_id TEXT NOT NULL,
                data TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_projections_branch_id
                ON projections (branch_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS comparisons (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS revisions (
                id TEXT PRIMARY KEY,
                base_spec_id TEXT NOT NULL,
                version INTEGER NOT NULL,
                data TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_revisions_base_spec_id
                ON revisions (base_spec_id)
            """,
        ]
        for stmt in statements:
            await self._db.execute(stmt)
        await self._db.commit()

    # ------------------------------------------------------------------
    # Serialisation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _dump(model: Any) -> str:
        """Serialise a Pydantic v2 model to a JSON string."""
        return model.model_dump_json()

    @staticmethod
    def _sid(uid: UUID) -> str:
        """Convert a UUID to its canonical string form."""
        return str(uid)

    # ------------------------------------------------------------------
    # BaseSpec CRUD
    # ------------------------------------------------------------------

    async def save_base_spec(self, spec: BaseSpec) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO base_specs (id, data) VALUES (?, ?)",
            (self._sid(spec.id), self._dump(spec)),
        )
        await self._db.commit()

    async def get_base_spec(self, spec_id: UUID) -> BaseSpec | None:
        async with self._db.execute(
            "SELECT data FROM base_specs WHERE id = ?",
            (self._sid(spec_id),),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return BaseSpec.model_validate_json(row["data"])

    async def list_base_specs(self) -> list[BaseSpec]:
        async with self._db.execute("SELECT data FROM base_specs") as cur:
            rows = await cur.fetchall()
        return [BaseSpec.model_validate_json(r["data"]) for r in rows]

    # ------------------------------------------------------------------
    # Scenario CRUD
    # ------------------------------------------------------------------

    async def save_scenario(self, scenario: Scenario) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO scenarios (id, data) VALUES (?, ?)",
            (self._sid(scenario.id), self._dump(scenario)),
        )
        await self._db.commit()

    async def get_scenario(self, scenario_id: UUID) -> Scenario | None:
        async with self._db.execute(
            "SELECT data FROM scenarios WHERE id = ?",
            (self._sid(scenario_id),),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return Scenario.model_validate_json(row["data"])

    async def list_scenarios(self) -> list[Scenario]:
        async with self._db.execute("SELECT data FROM scenarios") as cur:
            rows = await cur.fetchall()
        return [Scenario.model_validate_json(r["data"]) for r in rows]

    # ------------------------------------------------------------------
    # SpecBranch CRUD
    # ------------------------------------------------------------------

    async def save_branch(self, branch: SpecBranch) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO branches (id, base_spec_id, data) VALUES (?, ?, ?)",
            (self._sid(branch.id), self._sid(branch.base_spec_id), self._dump(branch)),
        )
        await self._db.commit()

    async def get_branch(self, branch_id: UUID) -> SpecBranch | None:
        async with self._db.execute(
            "SELECT data FROM branches WHERE id = ?",
            (self._sid(branch_id),),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return SpecBranch.model_validate_json(row["data"])

    async def list_branches_for_spec(self, base_spec_id: UUID) -> list[SpecBranch]:
        async with self._db.execute(
            "SELECT data FROM branches WHERE base_spec_id = ?",
            (self._sid(base_spec_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [SpecBranch.model_validate_json(r["data"]) for r in rows]

    # ------------------------------------------------------------------
    # AgentRun CRUD
    # ------------------------------------------------------------------

    async def save_agent_run(self, run: AgentRun) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO agent_runs (id, branch_id, data) VALUES (?, ?, ?)",
            (self._sid(run.id), self._sid(run.branch_id), self._dump(run)),
        )
        await self._db.commit()

    async def update_agent_run(self, run: AgentRun) -> None:
        """Overwrite an existing agent run record with updated state."""
        await self._db.execute(
            "INSERT OR REPLACE INTO agent_runs (id, branch_id, data) VALUES (?, ?, ?)",
            (self._sid(run.id), self._sid(run.branch_id), self._dump(run)),
        )
        await self._db.commit()

    async def get_agent_run(self, run_id: UUID) -> AgentRun | None:
        async with self._db.execute(
            "SELECT data FROM agent_runs WHERE id = ?",
            (self._sid(run_id),),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return AgentRun.model_validate_json(row["data"])

    async def list_runs_for_branch(self, branch_id: UUID) -> list[AgentRun]:
        async with self._db.execute(
            "SELECT data FROM agent_runs WHERE branch_id = ?",
            (self._sid(branch_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [AgentRun.model_validate_json(r["data"]) for r in rows]

    # ------------------------------------------------------------------
    # ProjectionArtifact CRUD
    # ------------------------------------------------------------------

    async def save_projection(self, projection: ProjectionArtifact) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO projections (id, branch_id, data) VALUES (?, ?, ?)",
            (
                self._sid(projection.id),
                self._sid(projection.branch_id),
                self._dump(projection),
            ),
        )
        await self._db.commit()

    async def get_projections_for_branch(self, branch_id: UUID) -> list[ProjectionArtifact]:
        async with self._db.execute(
            "SELECT data FROM projections WHERE branch_id = ?",
            (self._sid(branch_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [ProjectionArtifact.model_validate_json(r["data"]) for r in rows]

    # ------------------------------------------------------------------
    # BranchComparison CRUD
    # ------------------------------------------------------------------

    async def save_comparison(self, comparison: BranchComparison) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO comparisons (id, data) VALUES (?, ?)",
            (self._sid(comparison.id), self._dump(comparison)),
        )
        await self._db.commit()

    async def get_comparison(self, comparison_id: UUID) -> BranchComparison | None:
        async with self._db.execute(
            "SELECT data FROM comparisons WHERE id = ?",
            (self._sid(comparison_id),),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return BranchComparison.model_validate_json(row["data"])

    # ------------------------------------------------------------------
    # DecisionRecord CRUD
    # ------------------------------------------------------------------

    async def save_decision(self, decision: DecisionRecord) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO decisions (id, data) VALUES (?, ?)",
            (self._sid(decision.id), self._dump(decision)),
        )
        await self._db.commit()

    async def get_decision(self, decision_id: UUID) -> DecisionRecord | None:
        async with self._db.execute(
            "SELECT data FROM decisions WHERE id = ?",
            (self._sid(decision_id),),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return DecisionRecord.model_validate_json(row["data"])

    # ------------------------------------------------------------------
    # CanonicalSpecRevision CRUD
    # ------------------------------------------------------------------

    async def save_revision(self, revision: CanonicalSpecRevision) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO revisions (id, base_spec_id, version, data) VALUES (?, ?, ?, ?)",
            (
                self._sid(revision.id),
                self._sid(revision.base_spec_id),
                revision.version,
                self._dump(revision),
            ),
        )
        await self._db.commit()

    async def get_latest_revision(self, base_spec_id: UUID) -> CanonicalSpecRevision | None:
        async with self._db.execute(
            """
            SELECT data FROM revisions
            WHERE base_spec_id = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (self._sid(base_spec_id),),
        ) as cur:
            row = await cur.fetchone()
        if row is None:
            return None
        return CanonicalSpecRevision.model_validate_json(row["data"])

    async def list_revisions(self, base_spec_id: UUID) -> list[CanonicalSpecRevision]:
        async with self._db.execute(
            "SELECT data FROM revisions WHERE base_spec_id = ? ORDER BY version ASC",
            (self._sid(base_spec_id),),
        ) as cur:
            rows = await cur.fetchall()
        return [CanonicalSpecRevision.model_validate_json(r["data"]) for r in rows]
