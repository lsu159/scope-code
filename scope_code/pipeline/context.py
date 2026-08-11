"""Pipeline context — shared state bag passed through all stages."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import networkx as nx

from ..models.project import ProjectStructure
from ..models.scope import ModificationScope
from ..models.evidence import Evidence
from ..models.plan import ModificationPlan


@dataclass
class PipelineContext:
    """Shared state that flows through each stage of the pipeline.

    Each stage reads from and writes to this context. The pipeline
    engine passes it sequentially through all stages.

    Attributes:
        requirement: The raw user requirement (NL input).
        project_path: Absolute path to the target project.
        structured_requirement: Stage 1 output — parsed entities & actions.
        business_functions: Stage 2 output — affected business functions.
        project_structure: Stage 3 output — file tree, modules, symbols.
        dependency_graph: Stage 3 output — import dependency graph.
        call_graph: Stage 3 output — function-level call graph.
        modification_scope: Stage 4 output — what must/should/must-not change.
        evidence_chain: Stage 4 output — why each file must change.
        modification_plan: Stage 5 output — the complete plan.
        plan_confirmed: Stage 6 output — whether user approved the plan.
        should_stop: Flag to short-circuit the pipeline.
        metadata: Arbitrary metadata for debugging/logging.
    """

    # ── inputs ──
    requirement: str
    project_path: str

    # ── Stage 1: Understand ──
    structured_requirement: Dict[str, Any] = field(default_factory=dict)

    # ── Stage 2: Business Analysis ──
    business_functions: List[str] = field(default_factory=list)

    # ── Stage 3: Structure Analysis ──
    project_structure: ProjectStructure | None = None
    dependency_graph: nx.DiGraph | None = None
    call_graph: nx.DiGraph | None = None

    # ── Stage 4: Scope Inference ──
    modification_scope: ModificationScope | None = None
    evidence_chain: List[Evidence] = field(default_factory=list)

    # ── Stage 5: Plan Generation ──
    modification_plan: ModificationPlan | None = None

    # ── Stage 6: Confirmation ──
    plan_confirmed: bool = False

    # ── control ──
    should_stop: bool = False
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, error: str):
        """Record a non-fatal error and continue."""
        self.errors.append(error)

    def halt(self, reason: str):
        """Stop the pipeline with a reason."""
        self.should_stop = True
        self.errors.append(reason)

    def snapshot(self) -> Dict[str, Any]:
        """Return a lightweight summary of the current context state."""
        return {
            "requirement": self.requirement,
            "project": self.project_path,
            "business_functions": self.business_functions,
            "modules_found": (
                len(self.project_structure.modules)
                if self.project_structure
                else 0
            ),
            "scope_must_modify": (
                len(self.modification_scope.must_modify)
                if self.modification_scope
                else 0
            ),
            "scope_must_not": (
                len(self.modification_scope.must_not_modify)
                if self.modification_scope
                else 0
            ),
            "evidence_count": len(self.evidence_chain),
            "plan_confirmed": self.plan_confirmed,
            "errors": len(self.errors),
        }
