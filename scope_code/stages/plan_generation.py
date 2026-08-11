"""Stage 5: Plan Generation.

Assembles the ModificationScope and EvidenceChain into a complete,
human-readable ModificationPlan ready for user review.
"""

from typing import Optional

from ..llm.base import LLMAdapter, Message
from ..pipeline.stage import Stage
from ..pipeline.context import PipelineContext
from ..models.plan import ModificationPlan
from ..models.scope import ModificationScope
from ..models.evidence import Evidence


PLAN_GENERATION_SCHEMA = {
    "type": "object",
    "properties": {
        "requirement_summary": {
            "type": "string",
            "description": "Concise summary of what the user wants.",
        },
        "risk_assessment": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Potential risks and side effects.",
        },
        "verification_steps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Steps to verify the changes are correct.",
        },
    },
    "required": ["requirement_summary", "risk_assessment", "verification_steps"],
}

SYSTEM_PROMPT = """You are a Senior Software Engineer reviewing a modification
plan before presenting it to the team.

Your job:
1. Summarize the requirement clearly and concisely
2. Assess risks: what could go wrong with these changes?
3. Define verification steps: how to confirm the changes are correct?

Be specific. Vague risks like "might break something" are not useful.
Each risk should mention a concrete scenario.
Each verification step should be actionable."""


class PlanGenerationStage(Stage):
    """Stage 5: Generate the complete modification plan.

    Input:
        - context.modification_scope
        - context.evidence_chain
        - context.business_functions
        - context.structured_requirement

    Output:
        - context.modification_plan (ModificationPlan)
    """

    @property
    def name(self) -> str:
        return "plan-generation"

    @property
    def label(self) -> str:
        return "Generating Modification Plan"

    async def _run(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter] = None,
    ) -> None:
        scope = context.modification_scope
        if scope is None:
            context.halt("No modification scope available for plan generation.")
            return

        self.log(
            context,
            f"Generating plan: {len(scope.must_modify)} must-modify, "
            f"{len(scope.should_modify)} should-modify...",
        )

        # Build scope summary for LLM
        scope_summary = self._build_scope_summary(scope, context.evidence_chain)

        if llm is not None:
            try:
                messages = [
                    Message(role="system", content=SYSTEM_PROMPT),
                    Message(
                        role="user",
                        content=(
                            f"## Original Requirement\n{context.requirement}\n\n"
                            f"## Business Functions\n"
                            + "\n".join(f"- {bf}" for bf in context.business_functions)
                            + f"\n\n"
                            f"## Modification Scope\n{scope_summary}\n\n"
                            f"Generate the summary, risk assessment, and "
                            f"verification steps for this plan."
                        ),
                    ),
                ]

                result = await llm.structured_output(
                    messages, PLAN_GENERATION_SCHEMA
                )
                risk_assessment = result.get("risk_assessment", [])
                verification_steps = result.get("verification_steps", [])
                requirement_summary = result.get(
                    "requirement_summary", context.requirement
                )
            except Exception as e:
                self.log(context, f"LLM plan generation failed: {e}")
                risk_assessment = self._default_risks(scope)
                verification_steps = self._default_verification(scope)
                requirement_summary = context.requirement
        else:
            risk_assessment = self._default_risks(scope)
            verification_steps = self._default_verification(scope)
            requirement_summary = context.requirement

        context.modification_plan = ModificationPlan(
            requirement_summary=requirement_summary,
            business_functions=context.business_functions,
            scope=scope,
            evidence_chain=context.evidence_chain,
            risk_assessment=risk_assessment,
            verification_steps=verification_steps,
        )

        self.log(
            context,
            f"Plan generated: {context.modification_plan.total_changes} "
            f"total changes, {len(risk_assessment)} risks, "
            f"{len(verification_steps)} verification steps.",
        )

    def _build_scope_summary(
        self, scope: ModificationScope, evidence_chain: list[Evidence]
    ) -> str:
        """Build a text summary of the scope for the LLM."""
        lines = []

        lines.append("### MUST MODIFY")
        for fc in scope.must_modify:
            lines.append(f"- [{fc.change_type}] {fc.file_path}")
            lines.append(f"  Reason: {fc.reason}")

        lines.append("\n### SHOULD MODIFY")
        for fc in scope.should_modify:
            lines.append(f"- [{fc.change_type}] {fc.file_path}")
            lines.append(f"  Reason: {fc.reason}")

        lines.append("\n### MUST NOT MODIFY")
        for f in scope.must_not_modify:
            lines.append(f"- {f}")

        lines.append(f"\n### Evidence Chain ({len(evidence_chain)} items)")
        for e in evidence_chain[:10]:  # Cap at 10 for readability
            lines.append(f"- [{e.evidence_type}] {e.file}: {e.reason[:80]}")

        return "\n".join(lines)

    def _default_risks(self, scope: ModificationScope) -> list[str]:
        """Generate default risks when no LLM is available."""
        risks = []
        if scope.must_modify:
            risks.append(
                f"Modifying {len(scope.must_modify)} files — "
                f"each change carries regression risk."
            )
        if scope.should_modify:
            risks.append(
                f"{len(scope.should_modify)} additional files "
                f"flagged for review — scope may expand."
            )
        risks.append(
            "Verify that no 'must_not_modify' files are accidentally changed."
        )
        return risks

    def _default_verification(self, scope: ModificationScope) -> list[str]:
        """Generate default verification steps."""
        steps = []
        for fc in scope.must_modify:
            steps.append(
                f"Review changes in {fc.file_path}: {fc.reason}"
            )
        steps.append("Run existing test suite.")
        steps.append(
            "Verify git diff contains ONLY the planned files "
            "and no 'must_not_modify' files."
        )
        return steps
