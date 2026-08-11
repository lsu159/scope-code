"""Markdown report — renders a modification plan as a Markdown document.

Suitable for saving to file, embedding in PR descriptions, or
rendering in a web UI.
"""

from pathlib import Path
from typing import Optional

from ..models.plan import ModificationPlan


class MarkdownReport:
    """Renders a ModificationPlan to Markdown format.

    Usage:
        report = MarkdownReport()
        md = report.render(plan)
        report.save(plan, "modification-plan.md")
    """

    def render(self, plan: ModificationPlan) -> str:
        """Render a modification plan as a Markdown string.

        Args:
            plan: The modification plan to render.

        Returns:
            Markdown formatted string.
        """
        lines = [
            f"# Modification Plan",
            "",
            f"**Requirement:** {plan.requirement_summary}",
            "",
        ]

        # Business functions
        if plan.business_functions:
            lines.append("## Business Functions Affected")
            lines.append("")
            for bf in plan.business_functions:
                lines.append(f"- **{bf}**")
            lines.append("")

        # Scope summary
        lines.append("## Scope Summary")
        lines.append("")
        lines.append("| Category | Count |")
        lines.append("|----------|-------|")
        lines.append(
            f"| 🔴 Must Modify | {len(plan.scope.must_modify)} |"
        )
        lines.append(
            f"| 🟡 Should Modify | {len(plan.scope.should_modify)} |"
        )
        lines.append(
            f"| 🟢 Must Not Modify | {len(plan.scope.must_not_modify)} |"
        )
        lines.append(
            f"| ✅ No Change | {len(plan.scope.no_change)} |"
        )
        lines.append("")

        # Must modify
        lines.append("## 🔴 Must Modify")
        lines.append("")
        if plan.scope.must_modify:
            for fc in plan.scope.must_modify:
                lines.append(f"### `{fc.file_path}`")
                lines.append("")
                lines.append(f"- **Action:** `{fc.change_type}`")
                if fc.section:
                    lines.append(f"- **Section:** `{fc.section}`")
                lines.append(f"- **Reason:** {fc.reason}")

                # Find matching evidence
                matching = [
                    e for e in plan.evidence_chain if e.file == fc.file_path
                ]
                if matching:
                    e = matching[0]
                    if e.callers:
                        lines.append(
                            f"- **Callers:** "
                            + ", ".join(f"`{c}`" for c in e.callers)
                        )
                    if e.callees:
                        lines.append(
                            f"- **Callees:** "
                            + ", ".join(f"`{c}`" for c in e.callees)
                        )
                lines.append("")
        else:
            lines.append("*(none)*")
            lines.append("")

        # Should modify
        lines.append("## 🟡 Should Modify")
        lines.append("")
        if plan.scope.should_modify:
            for fc in plan.scope.should_modify:
                lines.append(f"- **`{fc.file_path}`** — {fc.reason}")
            lines.append("")
        else:
            lines.append("*(none)*")
            lines.append("")

        # Must not modify
        lines.append("## 🟢 Must Not Modify")
        lines.append("")
        for f in plan.scope.must_not_modify:
            lines.append(f"- ✗ `{f}`")
        lines.append("")

        # Evidence chain
        lines.append("## Evidence Chain")
        lines.append("")
        lines.append(
            f"*{len(plan.evidence_chain)} evidence items — "
            f"each must-modify decision is backed by reasoning.*"
        )
        lines.append("")
        for i, e in enumerate(plan.evidence_chain, 1):
            lines.append(f"### {i}. `{e.file}`")
            lines.append("")
            lines.append(f"- **Type:** `{e.evidence_type}`")
            lines.append(f"- **Business Function:** {e.business_function or 'N/A'}")
            lines.append(f"- **Reason:** {e.reason}")
            if e.callers:
                lines.append(
                    f"- **Called by:** "
                    + ", ".join(f"`{c}`" for c in e.callers)
                )
            if e.callees:
                lines.append(
                    f"- **Calls:** "
                    + ", ".join(f"`{c}`" for c in e.callees)
                )
            lines.append("")

        # Risk assessment
        if plan.risk_assessment:
            lines.append("## ⚠ Risk Assessment")
            lines.append("")
            for r in plan.risk_assessment:
                lines.append(f"- ⚠ {r}")
            lines.append("")

        # Verification steps
        if plan.verification_steps:
            lines.append("## Verification Steps")
            lines.append("")
            for i, step in enumerate(plan.verification_steps, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append(
            "*Generated by Scope Code — "
            "Reliable Software Engineering Agent Framework.*"
        )
        lines.append(
            "*Think Before Edit. Explain Before Change.*"
        )

        return "\n".join(lines)

    def save(
        self, plan: ModificationPlan, output_path: str
    ) -> str:
        """Render and save the plan to a Markdown file.

        Args:
            plan: The modification plan.
            output_path: Path to write the Markdown file.

        Returns:
            The absolute path to the saved file.
        """
        content = self.render(plan)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path.resolve())
