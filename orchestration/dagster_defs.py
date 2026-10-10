"""Optional orchestration seam.

Dagster is intentionally not a runtime dependency in the foundation milestone.
The direct CLI remains the source of truth; Dagster assets can call the same
pipeline functions once the approved deployment runtime is selected.
"""

try:
    from dagster import Definitions
except ImportError:  # pragma: no cover - optional dependency
    Definitions = None


defs = Definitions() if Definitions is not None else None
