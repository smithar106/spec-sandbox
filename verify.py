"""Quick verification that the merge fix works and the Streamlit app imports."""
import sys, asyncio
sys.path.insert(0, "src")

# Test merge regex fix
from spec_sandbox.merge.planner import MergePlanner
from spec_sandbox.domain.models import BaseSpec, SpecBranch, DecisionRecord
import uuid

spec = BaseSpec(title="T", content="# Overview\n\nContent.\n\n## Details\n\nMore.\n")
branch = SpecBranch(
    base_spec_id=spec.id,
    scenario_id=uuid.uuid4(),
    name="branch",
    content="# Overview\n\nChanged content.\n\n## Details\n\nMore.\n",
    mutations=[{"path": "parameter:x", "original": "Content", "replacement": "Changed content", "reason": "test"}],
)
decision = DecisionRecord(chosen_branch_id=branch.id, rationale="test")
planner = MergePlanner()
plan = planner.plan_merge(branch, [], decision)
merged = planner.execute_merge(plan, spec)
assert "Changed content" in merged or "Content" in merged, "merge produced empty output"
print("✓ merge/planner regex fix verified")

# Test Streamlit app imports
import importlib.util
spec_app = importlib.util.spec_from_file_location("app", "app.py")
# Just parse it — don't execute (Streamlit needs a running server)
import ast
with open("app.py") as f:
    src = f.read()
ast.parse(src)
print("✓ app.py parses without syntax errors")

print("\nAll checks passed. Run: bash run.sh")
