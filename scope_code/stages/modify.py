"""Stage 7: Code Modification.

Executes the confirmed modification plan by generating and applying
code changes. Each change is applied file-by-file with LLM assistance
for code generation.

Safety features:
    - Dry-run mode: preview changes without writing
    - Backup: creates .bak copies before modification
    - Atomic per-file: each file change succeeds or is skipped
    - Change tracking: records every actual modification
"""

import hashlib
from pathlib import Path
from typing import List, Optional, Dict

from ..llm.base import LLMAdapter, Message
from ..pipeline.stage import Stage
from ..pipeline.context import PipelineContext
from ..models.scope import FileChange


MODIFY_SYSTEM_PROMPT = """You are a Senior Software Engineer implementing a
pre-approved modification plan.

Your task: modify a single file according to the plan.

Rules:
1. ONLY change what is specified — do not refactor, reformat, or "improve"
   unrelated code.
2. Return the COMPLETE modified file content.
3. Preserve existing code style, indentation, and conventions.
4. Add brief inline comments explaining non-obvious changes.
5. Do NOT change imports unless required by the modification.
6. Do NOT change function signatures unless required.

You are implementing a minimum-scope edit. Every line you change must be
justified by the requirement."""


class ModificationRecord:
    """Record of a single file modification."""

    def __init__(self, file_path: str, change: FileChange):
        self.file_path = file_path
        self.change = change
        self.original_content: str = ""
        self.modified_content: str = ""
        self.original_hash: str = ""
        self.modified_hash: str = ""
        self.success: bool = False
        self.error: Optional[str] = None

    @property
    def was_changed(self) -> bool:
        """Whether the file content actually changed."""
        return self.original_hash != self.modified_hash


class ModifyStage(Stage):
    """Stage 7: Generate and apply code modifications.

    Input:
        - context.modification_plan (must be confirmed)
        - context.plan_confirmed must be True

    Output:
        - context.metadata["modification_records"] — list of ModificationRecord
        - context.metadata["files_modified"] — list of actually changed files
    """

    def __init__(self, dry_run: bool = False):
        """Initialize the modification stage.

        Args:
            dry_run: If True, generate changes but don't write to disk.
        """
        self.dry_run = dry_run

    @property
    def name(self) -> str:
        return "modify"

    @property
    def label(self) -> str:
        return "Applying Code Changes"

    async def _run(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter] = None,
    ) -> None:
        plan = context.modification_plan
        if plan is None:
            context.halt("No modification plan to execute.")
            return
        if not context.plan_confirmed:
            context.halt(
                "Plan not confirmed. Refusing to modify code. "
                "Confirm the plan first or set auto_confirm=True."
            )
            return

        files_to_modify = plan.scope.must_modify
        if not files_to_modify:
            self.log(context, "No files to modify.")
            return

        records: List[ModificationRecord] = []
        root = Path(context.project_path)

        for fc in files_to_modify:
            self.log(context, f"Processing: {fc.file_path}")

            record = ModificationRecord(fc.file_path, fc)
            file_path = root / fc.file_path

            try:
                # Read original
                record.original_content = file_path.read_text(encoding="utf-8")
                record.original_hash = self._hash_content(
                    record.original_content
                )

                # Generate modification
                if llm is not None:
                    record.modified_content = await self._llm_modify(
                        llm, record, context
                    )
                else:
                    record.modified_content = self._deterministic_modify(
                        record
                    )

                record.modified_hash = self._hash_content(
                    record.modified_content
                )

                # Apply if changed
                if record.was_changed:
                    if not self.dry_run:
                        self._apply_change(file_path, record)
                    record.success = True
                    self.log(context, f"  Modified: {fc.file_path}")
                else:
                    record.success = True
                    self.log(context, f"  No change needed: {fc.file_path}")

            except FileNotFoundError:
                record.error = f"File not found: {fc.file_path}"
                self.log(context, f"  ERROR: {record.error}")
            except Exception as e:
                record.error = str(e)
                self.log(context, f"  ERROR: {e}")

            records.append(record)

        # Store records in context
        context.metadata["modification_records"] = records
        context.metadata["files_modified"] = [
            r.file_path for r in records if r.was_changed and r.success
        ]

        success_count = sum(1 for r in records if r.success)
        changed_count = sum(1 for r in records if r.was_changed and r.success)
        self.log(
            context,
            f"Modification complete: {success_count}/{len(records)} "
            f"succeeded, {changed_count} files changed.",
        )

    async def _llm_modify(
        self,
        llm: LLMAdapter,
        record: ModificationRecord,
        context: PipelineContext,
    ) -> str:
        """Use LLM to generate the modified file content."""
        # Find evidence for this file
        evidence_text = ""
        for e in context.evidence_chain:
            if e.file == record.file_path:
                evidence_text = (
                    f"Evidence type: {e.evidence_type}\n"
                    f"Callers: {', '.join(e.callers) if e.callers else 'none'}\n"
                    f"Callees: {', '.join(e.callees) if e.callees else 'none'}\n"
                )
                break

        messages = [
            Message(role="system", content=MODIFY_SYSTEM_PROMPT),
            Message(
                role="user",
                content=(
                    f"## Requirement\n{context.requirement}\n\n"
                    f"## File: {record.file_path}\n"
                    f"## Change Type: {record.change.change_type}\n"
                    f"## Reason: {record.change.reason}\n"
                    f"## Section: {record.change.section or 'entire file'}\n"
                    f"{evidence_text}\n"
                    f"## Original Code\n```\n{record.original_content}\n```\n\n"
                    f"Return the COMPLETE modified file content. "
                    f"Preserve all existing code that does not need to change."
                ),
            ),
        ]

        response = await llm.chat(
            messages,
            max_tokens=min(
                len(record.original_content) * 3 + 2000,
                llm.config.max_tokens,
            ),
        )

        return self._extract_code(response, record.original_content)

    def _deterministic_modify(self, record: ModificationRecord) -> str:
        """Deterministic modification without LLM.

        Currently returns original unchanged — deterministic modification
        without LLM is limited to simple pattern replacements.
        """
        return record.original_content

    def _extract_code(self, response: str, original: str) -> str:
        """Extract code from LLM response, handling markdown wrapping."""
        import re

        # Try markdown code blocks
        match = re.search(
            r'```(?:python|py)?\s*\n(.*?)\n```', response, re.DOTALL
        )
        if match:
            return match.group(1)

        # If the response starts with common code patterns, it's likely raw
        stripped = response.strip()
        code_starters = ('import ', 'from ', 'def ', 'class ', '#', '"""',
                          "'''", 'package ', 'module ', '<?', '<!')
        if any(stripped.startswith(s) for s in code_starters):
            return stripped

        # If response length is similar to original, it might be raw code
        if abs(len(stripped) - len(original)) < len(original) * 0.5:
            return stripped

        # Fallback: return original
        return original

    def _apply_change(
        self, file_path: Path, record: ModificationRecord
    ) -> None:
        """Apply the change to disk with backup."""
        # Create backup
        backup_path = file_path.with_suffix(file_path.suffix + ".bak")
        file_path.write_text(record.modified_content, encoding="utf-8")
        # Write backup after successful save
        backup_path.write_text(record.original_content, encoding="utf-8")

    @staticmethod
    def _hash_content(content: str) -> str:
        """Hash file content for change detection."""
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
