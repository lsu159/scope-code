"""Stage 6: User Confirmation.

Presents the modification plan to the user for review and approval.
The user can accept, reject, or modify the scope.

This stage implements the "Human-AI Collaboration" principle:
AI proposes, human decides.
"""

import sys
from typing import Optional, Callable, Awaitable

from ..llm.base import LLMAdapter
from ..pipeline.stage import Stage
from ..pipeline.context import PipelineContext


# Callback type for programmatic confirmation
ConfirmationCallback = Callable[
    [PipelineContext], Awaitable[bool]
]


class ConfirmationStage(Stage):
    """Stage 6: Present plan to user and get confirmation.

    Supports two modes:
    1. Interactive CLI (default): uses rich console to display the plan
       and prompt the user.
    2. Programmatic callback: the caller provides an async callback
       that receives the context and returns True/False.

    Input: context.modification_plan
    Output: context.plan_confirmed (bool)

    The pipeline stops if the user rejects the plan.
    """

    def __init__(
        self,
        callback: Optional[ConfirmationCallback] = None,
        auto_confirm: bool = False,
    ):
        """Initialize the confirmation stage.

        Args:
            callback: Optional async callback for programmatic use.
                      Receives context, returns True (approved) or False.
            auto_confirm: If True, skip user interaction and auto-approve.
                          Useful for CI/CD or automated pipelines.
        """
        self._callback = callback
        self._auto_confirm = auto_confirm

    @property
    def name(self) -> str:
        return "confirmation"

    @property
    def label(self) -> str:
        return "Awaiting User Confirmation"

    async def _run(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter] = None,
    ) -> None:
        plan = context.modification_plan
        if plan is None:
            context.halt("No modification plan to confirm.")
            return

        if self._auto_confirm:
            context.plan_confirmed = True
            self.log(context, "Auto-confirmed (auto_confirm=True).")
            return

        # Display the plan
        self._display_plan(plan)

        # Get user decision
        if self._callback is not None:
            # Programmatic mode
            try:
                approved = await self._callback(context)
                context.plan_confirmed = approved
                self.log(
                    context,
                    f"Callback returned: {'approved' if approved else 'rejected'}.",
                )
            except Exception as e:
                self.log(context, f"Confirmation callback error: {e}")
                context.plan_confirmed = False
        else:
            # Interactive CLI mode
            self._context = context  # Store for _interactive_confirm
            approved = self._interactive_confirm()
            context.plan_confirmed = approved

        if not context.plan_confirmed:
            context.halt("User rejected the modification plan.")
            self.log(context, "Plan rejected by user.")
        else:
            self.log(context, "Plan approved by user.")

    def _display_plan(self, plan) -> None:
        """Display the plan in a human-readable format."""
        print()
        print(plan.format_summary())
        print()

    def _interactive_confirm(self) -> bool:
        """Interactive CLI confirmation loop.

        Returns True if the user approves, False if they reject.
        """
        print("-" * 60)
        print("Review the modification plan above.")
        print()
        print("Options:")
        print("  [y] Accept the plan and proceed")
        print("  [n] Reject the plan (stop here)")
        print("  [s] Show evidence chain details")
        print("  [m] Modify scope (remove files from must-modify)")
        print("  [q] Quit")
        print("-" * 60)

        while True:
            try:
                choice = input("Your choice [y/n/s/m/q]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print("\nInterrupted. Treating as rejection.")
                return False

            if choice in ("y", "yes"):
                return True
            elif choice in ("n", "no"):
                return False
            elif choice in ("s", "show"):
                # Show detailed evidence
                print()
                print("Detailed Evidence Chain:")
                print("-" * 40)
                for i, e in enumerate(self._context.evidence_chain, 1):
                    print(e.format())
                    print()
                continue
            elif choice in ("m", "modify"):
                self._interactive_modify_scope()
                # Re-display the plan after modification
                self._display_plan(self._context.modification_plan)
                continue
            elif choice in ("q", "quit", "exit"):
                print("Exiting.")
                sys.exit(0)
            else:
                print(f"Unknown option: '{choice}'. Please choose y/n/s/m/q.")
                continue

    def _interactive_modify_scope(self):
        """Allow user to modify the scope interactively.

        Supports: remove files, downgrade to should-modify, add new files,
        and add files to must-not-modify list.
        """
        scope = self._context.modification_plan.scope
        must_list = scope.must_modify

        print()
        if must_list:
            print("Files currently marked MUST MODIFY:")
            for i, fc in enumerate(must_list, 1):
                print(f"  [{i}] {fc.file_path} — {fc.reason[:60]}")
        else:
            print("No files in must-modify list.")

        print()
        print("Options:")
        print("  [number]     Move file from must → should-modify")
        print("  [r number]   Remove file from scope entirely")
        print("  [a path]     Add a file to must-modify (e.g., a src/auth.py)")
        print("  [x path]     Add a file to must-NOT-modify (e.g., x src/chat/*)")
        print("  [d]          Done, return to main menu")
        print()

        while True:
            try:
                choice = input("Action: ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if choice.lower() in ("d", "done", ""):
                break
            elif choice.lower().startswith("r "):
                try:
                    idx = int(choice.split()[1]) - 1
                    if 0 <= idx < len(must_list):
                        removed = must_list.pop(idx)
                        print(f"  Removed from scope: {removed.file_path}")
                    else:
                        print(f"  Invalid index: {idx + 1}")
                except (ValueError, IndexError):
                    print("  Invalid choice. Use: r <number>")
            elif choice.lower().startswith("a "):
                path = choice[2:].strip()
                reason = input(f"  Reason for adding {path}: ").strip()
                if path and reason:
                    from ..models.scope import FileChange
                    scope.must_modify.append(FileChange(
                        file_path=path, change_type="modify", reason=reason
                    ))
                    print(f"  Added to must-modify: {path}")
            elif choice.lower().startswith("x "):
                path = choice[2:].strip()
                reason = input(f"  Reason for blocking {path}: ").strip()
                if path:
                    scope.must_not_modify.append(path)
                    scope.must_not_modify_reasons[path] = reason or "user-specified exclusion"
                    print(f"  Added to must-NOT-modify: {path}")
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(must_list):
                        fc = must_list.pop(idx)
                        scope.should_modify.append(fc)
                        print(f"  Moved to should-modify: {fc.file_path}")
                    else:
                        print(f"  Invalid index: {idx + 1}")
                except (ValueError, IndexError):
                    print("  Invalid choice. Enter a number, 'r N', 'a path', 'x path', or 'd'.")
