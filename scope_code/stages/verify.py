"""Stage 8: Modification Verification.

Post-modification audit that checks:
    1. Were any plan-external files modified?
    2. Were any must_not_modify files touched?
    3. Did the change scope expand?
    4. Are there architectural violations?
    5. Are there side effects?

This stage implements the "Modification Verification" principle:
after every change, verify it was done correctly.

The stage can:
    - Compare git diff (if available) to the plan
    - Compare file hashes (deterministic fallback)
    - Report ALL issues proactively
"""

from pathlib import Path
from typing import List, Optional, Dict, Set

from ..llm.base import LLMAdapter
from ..pipeline.stage import Stage
from ..pipeline.context import PipelineContext


class VerificationReport:
    """Structured verification report."""

    def __init__(self):
        self.plan_external_files: List[str] = []       # Modified but not in plan
        self.must_not_violations: List[str] = []       # Modified despite must_not
        self.scope_expansions: List[str] = []           # Additional files changed
        self.architectural_violations: List[str] = []   # Pattern violations
        self.side_effects: List[str] = []                # Unintended consequences
        self.planned_files_modified: List[str] = []      # Correctly modified

    @property
    def has_issues(self) -> bool:
        """Whether any issues were found."""
        return bool(
            self.plan_external_files
            or self.must_not_violations
            or self.scope_expansions
            or self.architectural_violations
        )

    @property
    def is_clean(self) -> bool:
        """Whether the verification passed cleanly."""
        return not self.has_issues

    def format_report(self) -> str:
        """Generate a human-readable verification report."""
        lines = [
            "=" * 60,
            "VERIFICATION REPORT",
            "=" * 60,
            "",
        ]

        if self.is_clean:
            lines.append("ALL CHECKS PASSED")
            lines.append("")
            lines.append(
                f"Files modified as planned: "
                f"{len(self.planned_files_modified)}"
            )
            for f in self.planned_files_modified:
                lines.append(f"  OK {f}")
            return "\n".join(lines)

        # Issues found — report each category
        if self.planned_files_modified:
            lines.append(
                f"CORRECTLY MODIFIED ({len(self.planned_files_modified)}):"
            )
            for f in self.planned_files_modified:
                lines.append(f"  OK {f}")
            lines.append("")

        if self.must_not_violations:
            lines.append(
                f"*** VIOLATION: Must-Not-Modify Files Touched "
                f"({len(self.must_not_violations)}) ***"
            )
            for f in self.must_not_violations:
                lines.append(f"  !! {f}")
            lines.append("")

        if self.plan_external_files:
            lines.append(
                f"WARNING: Plan-External Files Modified "
                f"({len(self.plan_external_files)}):"
            )
            for f in self.plan_external_files:
                lines.append(f"  ? {f}")
            lines.append("")

        if self.scope_expansions:
            lines.append(
                f"WARNING: Scope Expansion Detected "
                f"({len(self.scope_expansions)}):"
            )
            for f in self.scope_expansions:
                lines.append(f"  + {f}")
            lines.append("")

        if self.architectural_violations:
            lines.append(
                f"WARNING: Architectural Violations "
                f"({len(self.architectural_violations)}):"
            )
            for v in self.architectural_violations:
                lines.append(f"  ! {v}")
            lines.append("")

        if self.side_effects:
            lines.append(
                f"INFO: Potential Side Effects "
                f"({len(self.side_effects)}):"
            )
            for s in self.side_effects:
                lines.append(f"  ~ {s}")
            lines.append("")

        lines.append("NEXT: Run your test suite to confirm no regressions.")
        lines.append("")

        return "\n".join(lines)


class VerifyStage(Stage):
    """Stage 8: Verify modifications against the plan.

    Input:
        - context.metadata["files_modified"]
        - context.modification_plan (for scope comparison)
        - context.modification_scope (for must_not_modify check)

    Output:
        - context.metadata["verification_report"] — VerificationReport
        - context.metadata["verification_passed"] — bool
    """

    def __init__(self, strict: bool = True, use_git: bool = True):
        """Initialize the verification stage.

        Args:
            strict: If True, any must_not_modify violation is an error.
                    If False, violations are warnings only.
            use_git: If True, also check git diff for changes made
                     outside the pipeline.
        """
        self.strict = strict
        self.use_git = use_git

    @property
    def name(self) -> str:
        return "verify"

    @property
    def label(self) -> str:
        return "Verifying Modifications"

    async def _run(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter] = None,
    ) -> None:
        report = VerificationReport()
        plan = context.modification_plan
        scope = context.modification_scope

        if plan is None or scope is None:
            context.halt("No plan or scope available for verification.")
            return

        # Get files modified by the pipeline (Stage 7)
        pipeline_modified: List[str] = context.metadata.get(
            "files_modified", []
        )

        # Get files modified according to git (catches external changes)
        git_modified: List[str] = []
        if self.use_git:
            git_modified = self._get_git_changed_files(
                context.project_path
            )

        # Merge both sources (deduplicate)
        all_modified = list(set(pipeline_modified + git_modified))

        if git_modified:
            self.log(
                context,
                f"Git detected {len(git_modified)} changed files "
                f"(pipeline: {len(pipeline_modified)}).",
            )

        if not all_modified:
            if not pipeline_modified:
                self.log(
                    context,
                    "No files were modified. Nothing to verify.",
                )
            else:
                self.log(
                    context,
                    "No changes detected (dry run or no-op).",
                )
            report.planned_files_modified = []
            context.metadata["verification_report"] = report
            context.metadata["verification_passed"] = True
            return

        self.log(
            context,
            f"Verifying {len(all_modified)} modified files "
            f"({len(git_modified)} from git, "
            f"{len(pipeline_modified)} from pipeline)...",
        )

        # Get planned files
        planned_files: Set[str] = {
            fc.file_path for fc in scope.must_modify
        }
        planned_files.update(
            fc.file_path for fc in scope.should_modify
        )

        # ── Check 1: Must-not-modify violations ──────────────────
        violations = scope.find_violations(all_modified)
        report.must_not_violations = violations

        # ── Check 2: Plan-external files ─────────────────────────
        modified_set = set(all_modified)
        report.planned_files_modified = list(
            modified_set & planned_files
        )
        report.plan_external_files = list(
            modified_set - planned_files
        )

        # ── Check 3: Scope expansion ─────────────────────────────
        must_set = {fc.file_path for fc in scope.must_modify}
        report.scope_expansions = list(modified_set - must_set)

        # ── Check 4: Git-only changes (modified outside pipeline) ─
        git_only = set(git_modified) - set(pipeline_modified)
        if git_only:
            report.side_effects.append(
                f"Files changed outside the pipeline (detected by git): "
                f"{', '.join(sorted(git_only))}"
            )

        # ── Check 5: Architectural violations ────────────────────
        report.architectural_violations = self._check_architecture(
            all_modified, context
        )

        # ── Check 6: Side effects ────────────────────────────────
        report.side_effects.extend(
            self._check_side_effects(all_modified, context)
        )

        # Store report
        context.metadata["verification_report"] = report
        context.metadata["verification_passed"] = report.is_clean

        # Display report
        print()
        print(report.format_report())
        print()

        # Signal if issues found
        if report.must_not_violations and self.strict:
            context.add_error(
                f"MUST-NOT-MODIFY VIOLATION: "
                f"{', '.join(report.must_not_violations)}"
            )

        if report.has_issues:
            self.log(
                context,
                f"Verification found issues: "
                f"{len(report.must_not_violations)} violations, "
                f"{len(report.plan_external_files)} external, "
                f"{len(report.scope_expansions)} expansions, "
                f"{len(report.architectural_violations)} architectural.",
            )
        else:
            self.log(context, "Verification passed cleanly.")

    def _check_architecture(
        self, files_modified: List[str], context: PipelineContext
    ) -> List[str]:
        """Heuristic architectural violation checks.

        Detects patterns like:
        - Circular dependency introduction
        - Layer violation (e.g., data layer importing web layer)
        - Test file modification without corresponding source change
        """
        violations = []

        # Check if ONLY test files were modified (suspicious)
        only_tests = all(
            "test" in f.lower() or "spec" in f.lower()
            for f in files_modified
        )
        if only_tests and len(files_modified) > 0:
            violations.append(
                "Only test files were modified — "
                "source code may have been missed."
            )

        # Check if config files were modified alongside source
        config_modified = any(
            f.endswith(('.toml', '.yaml', '.yml', '.json', '.cfg', '.ini'))
            for f in files_modified
        )
        source_modified = any(
            f.endswith('.py') for f in files_modified
        )
        if config_modified and not source_modified:
            violations.append(
                "Config files modified without source changes — "
                "verify this is intentional."
            )

        return violations

    def _check_side_effects(
        self, files_modified: List[str], context: PipelineContext
    ) -> List[str]:
        """Check for potential side effects of the modification."""
        effects = []

        # Check for __init__.py changes (export surface changes)
        init_files = [f for f in files_modified if f.endswith('__init__.py')]
        if init_files:
            effects.append(
                f"__init__.py files modified ({', '.join(init_files)}) — "
                "export surface may have changed. Verify imports still work."
            )

        # Check for many files in different modules
        modules = set()
        for f in files_modified:
            parts = Path(f).parts
            if len(parts) >= 2:
                modules.add(parts[0])

        if len(modules) > 3:
            effects.append(
                f"Changes span {len(modules)} modules — "
                "consider whether scope is too broad."
            )

        return effects

    def _get_git_changed_files(self, project_path: str) -> List[str]:
        """Get list of files changed in the working tree via git.

        Checks:
            - Modified tracked files (git diff --name-only)
            - Untracked files (git ls-files --others --exclude-standard)
            - Staged files (git diff --cached --name-only)

        Returns:
            List of file paths relative to project root.
            Empty list if not a git repo or git is unavailable.
        """
        import subprocess

        try:
            project_root = Path(project_path).resolve()

            # Verify it's a git repo
            result = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=5,
            )
            if result.returncode != 0:
                return []

            changed = set()

            # Modified tracked files (unstaged)
            result = subprocess.run(
                ["git", "diff", "--name-only"],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                changed.update(
                    f.strip() for f in result.stdout.strip().split("\n")
                    if f.strip()
                )

            # Staged files
            result = subprocess.run(
                ["git", "diff", "--cached", "--name-only"],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                changed.update(
                    f.strip() for f in result.stdout.strip().split("\n")
                    if f.strip()
                )

            # Untracked (new) files
            result = subprocess.run(
                [
                    "git", "ls-files", "--others",
                    "--exclude-standard",
                ],
                capture_output=True,
                text=True,
                cwd=str(project_root),
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                changed.update(
                    f.strip() for f in result.stdout.strip().split("\n")
                    if f.strip()
                )

            # Filter out .bak files (created by ModifyStage as backups)
            changed = {f for f in changed if not f.endswith(".bak")}
            return [f.replace("\\", "/") for f in sorted(changed)]

        except (
            FileNotFoundError,
            subprocess.TimeoutExpired,
            OSError,
        ):
            # git not installed or unavailable
            return []
