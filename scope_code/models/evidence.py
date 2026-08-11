"""Evidence chain models — why each file must change."""

from pydantic import BaseModel, Field
from typing import List, Literal


class Evidence(BaseModel):
    """A single piece of evidence explaining why a file must change.

    Every modification in the plan must be backed by at least one
    Evidence entry. This forms the "evidence chain" — the core of
    the Explain Before Edit principle.
    """

    file: str
    reason: str
    callers: List[str] = Field(default_factory=list)
    callees: List[str] = Field(default_factory=list)
    business_function: str = ""
    evidence_type: Literal["direct", "transitive", "interface", "config"] = (
        "direct"
    )

    @property
    def has_dependency_info(self) -> bool:
        """Whether call/caller information is available."""
        return bool(self.callers) or bool(self.callees)

    def format(self) -> str:
        """Human-readable evidence summary."""
        parts = [f"[{self.evidence_type}] {self.file}"]
        if self.business_function:
            parts.append(f"  Business: {self.business_function}")
        parts.append(f"  Reason: {self.reason}")
        if self.callers:
            parts.append(f"  Callers: {', '.join(self.callers)}")
        if self.callees:
            parts.append(f"  Callees: {', '.join(self.callees)}")
        return "\n".join(parts)


class EvidenceChain(BaseModel):
    """Ordered chain of evidence entries for a modification plan.

    Each entry explains WHY a specific file is in scope.
    The chain can be traversed to understand the full rationale
    behind a modification plan.
    """

    items: List[Evidence] = Field(default_factory=list)

    def add(self, evidence: Evidence) -> None:
        """Add an evidence item to the chain."""
        self.items.append(evidence)

    def get_for_file(self, file_path: str) -> List[Evidence]:
        """Get all evidence entries for a specific file."""
        return [e for e in self.items if e.file == file_path]

    def get_by_type(
        self, evidence_type: Literal["direct", "transitive", "interface", "config"]
    ) -> List[Evidence]:
        """Filter evidence by type."""
        return [e for e in self.items if e.evidence_type == evidence_type]

    @property
    def files_explained(self) -> List[str]:
        """List of unique files covered by the evidence chain."""
        return list({e.file for e in self.items})

    def summary(self) -> str:
        """Generate a human-readable summary of the entire chain."""
        if not self.items:
            return "No evidence recorded."
        lines = [f"Evidence Chain ({len(self.items)} items):", "-" * 40]
        for i, e in enumerate(self.items, 1):
            lines.append(f"{i}. [{e.evidence_type}] {e.file}")
            lines.append(f"   {e.reason}")
        return "\n".join(lines)
