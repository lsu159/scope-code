"""Modification plan model — the complete plan output."""

from pydantic import BaseModel, Field
from typing import List

from .scope import ModificationScope
from .evidence import Evidence


class ModificationPlan(BaseModel):
    """A complete modification plan ready for user review.

    This is the output of Stage 5 (Plan Generation) and the input
    to Stage 6 (User Confirmation). It bundles the scope, evidence,
    risks, and verification steps into one reviewable artifact.
    """

    requirement_summary: str
    business_functions: List[str] = Field(default_factory=list)
    scope: ModificationScope = Field(default_factory=ModificationScope)
    evidence_chain: List[Evidence] = Field(default_factory=list)
    risk_assessment: List[str] = Field(default_factory=list)
    verification_steps: List[str] = Field(default_factory=list)

    @property
    def total_changes(self) -> int:
        """Total number of files in the modification scope."""
        return self.scope.total_modifications

    @property
    def is_safe(self) -> bool:
        """Check if the plan respects the minimum scope principle.

        A plan is 'safe' when it explicitly declares files that
        must NOT be modified — this shows the scope inference
        engine has considered boundaries.
        """
        return len(self.scope.must_not_modify) > 0

    @property
    def has_evidence(self) -> bool:
        """Whether every must_modify entry has evidence backing."""
        return len(self.evidence_chain) >= len(self.scope.must_modify)

    def format_summary(self) -> str:
        """Render the complete plan as a human-readable report."""
        sep = "=" * 60
        lines = [
            sep,
            "Modification Plan",
            sep,
            "",
            f"Requirement: {self.requirement_summary}",
            "",
        ]

        if self.business_functions:
            lines.append("Business Functions Affected:")
            for bf in self.business_functions:
                lines.append(f"  * {bf}")
            lines.append("")

        lines.append(f"MUST MODIFY ({len(self.scope.must_modify)} files):")
        if self.scope.must_modify:
            for fc in self.scope.must_modify:
                lines.append(f"  [{fc.change_type}] {fc.file_path}")
                if fc.section:
                    lines.append(f"    Section: {fc.section}")
                lines.append(f"    -> {fc.reason}")
        else:
            lines.append("  (none)")
        lines.append("")

        lines.append(f"SHOULD MODIFY ({len(self.scope.should_modify)} files):")
        if self.scope.should_modify:
            for fc in self.scope.should_modify:
                lines.append(f"  [{fc.change_type}] {fc.file_path}")
                lines.append(f"    -> {fc.reason}")
        else:
            lines.append("  (none)")
        lines.append("")

        lines.append(f"MUST NOT MODIFY ({len(self.scope.must_not_modify)} files):")
        for f in self.scope.must_not_modify:
            reason = self.scope.must_not_modify_reasons.get(f, "")
            reason_text = f" — {reason}" if reason else ""
            lines.append(f"  X {f}{reason_text}")
        lines.append("")

        lines.append(f"NO CHANGE CONFIRMED ({len(self.scope.no_change)} files):")
        for f in self.scope.no_change:
            lines.append(f"  OK {f}")
        lines.append("")

        if self.evidence_chain:
            lines.append(f"Evidence Chain ({len(self.evidence_chain)} items):")
            lines.append("-" * 40)
            for i, e in enumerate(self.evidence_chain, 1):
                lines.append(f"  {i}. [{e.evidence_type}] {e.file}")
                lines.append(f"     {e.reason}")
            lines.append("")

        if self.risk_assessment:
            lines.append("Risk Assessment:")
            for r in self.risk_assessment:
                lines.append(f"  ! {r}")
            lines.append("")

        if self.verification_steps:
            lines.append("Verification Steps:")
            for i, step in enumerate(self.verification_steps, 1):
                lines.append(f"  {i}. {step}")
            lines.append("")

        lines.append(sep)
        return "\n".join(lines)
