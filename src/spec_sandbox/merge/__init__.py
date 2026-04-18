"""Merge subsystem: plan and finalise canonical spec revisions."""

from spec_sandbox.merge.finalizer import SpecFinalizer
from spec_sandbox.merge.planner import MergePlanner

__all__ = ["MergePlanner", "SpecFinalizer"]
