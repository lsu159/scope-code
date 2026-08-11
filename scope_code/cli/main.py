"""CLI entry point for Scope Code.

Usage:
    scope-code analyze "Add rate limiting to login" ./my-project/
    scope-code analyze --auto-confirm "Fix auth bug" ./src/
    scope-code --version
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from .. import __version__
from ..pipeline.engine import PipelineEngine
from ..pipeline.context import PipelineContext
from ..llm.factory import create_llm
from ..outputs.markdown import MarkdownReport
from ..outputs.json_output import JSONOutput


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="scope-code",
        description=(
            "Scope Code — Reliable Software Engineering Agent Framework.\n"
            "Think Before Edit. Explain Before Change.\n"
            "先思考，再修改；先解释，再变更。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  scope-code analyze "Add rate limiting to login" ./my-project/
  scope-code analyze --provider openai --model gpt-4 "Fix auth bug" ./src/
  scope-code analyze --output plan.md "Refactor payment flow" ./app/
  scope-code analyze --output-json plan.json --auto-confirm "..." ./src/
""",
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"scope-code {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # 'analyze' subcommand
    analyze = subparsers.add_parser(
        "analyze",
        help="Analyze a requirement and generate a modification plan",
    )
    analyze.add_argument(
        "requirement",
        help="The requirement in natural language (e.g., 'Add rate limiting to login')",
    )
    analyze.add_argument(
        "project_path",
        help="Path to the project to analyze",
    )
    analyze.add_argument(
        "--provider",
        default="claude",
        choices=["claude", "openai", "deepseek", "gemini", "anthropic", "gpt"],
        help="LLM provider (default: claude)",
    )
    analyze.add_argument(
        "--model",
        default=None,
        help="Model name (default: provider-specific)",
    )
    analyze.add_argument(
        "--api-key",
        default=None,
        help="API key (or set SCOPE_CODE_API_KEY env var)",
    )
    analyze.add_argument(
        "--api-base",
        default=None,
        help="Custom API base URL",
    )
    analyze.add_argument(
        "--output", "-o",
        default=None,
        help="Save the plan as a Markdown report",
    )
    analyze.add_argument(
        "--output-json",
        default=None,
        help="Save the plan as a JSON file",
    )
    analyze.add_argument(
        "--auto-confirm",
        action="store_true",
        help="Skip user confirmation (for CI/CD)",
    )
    analyze.add_argument(
        "--execute",
        action="store_true",
        help="Execute the modification plan (actually change code)",
    )
    analyze.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing (implies --execute)",
    )
    analyze.add_argument(
        "--no-llm",
        action="store_true",
        help="Run without LLM (deterministic analysis only)",
    )
    analyze.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output",
    )

    return parser


def get_default_model(provider: str) -> str:
    """Get the default model for a provider."""
    defaults = {
        "claude": "claude-sonnet-5-20251001",
        "anthropic": "claude-sonnet-5-20251001",
        "openai": "gpt-4o",
        "gpt": "gpt-4o",
    }
    return defaults.get(provider, "claude-sonnet-5-20251001")


async def run_analyze(args: argparse.Namespace) -> int:
    """Run the 'analyze' command."""
    # Validate project path
    project_path = Path(args.project_path).resolve()
    if not project_path.exists():
        print(f"Error: Project path not found: {project_path}", file=sys.stderr)
        return 1
    if not project_path.is_dir():
        print(f"Error: Not a directory: {project_path}", file=sys.stderr)
        return 1

    # Set up LLM
    llm = None
    if not args.no_llm:
        api_key = args.api_key or os.environ.get("SCOPE_CODE_API_KEY")
        if not api_key:
            print(
                "Warning: No API key provided. Set --api-key or "
                "SCOPE_CODE_API_KEY env var. Running without LLM.",
                file=sys.stderr,
            )
        else:
            model = args.model or get_default_model(args.provider)
            try:
                llm = create_llm(
                    provider=args.provider,
                    model=model,
                    api_key=api_key,
                    api_base=args.api_base,
                )
                if args.verbose:
                    print(f"Using {args.provider}/{model}")
            except ValueError as e:
                print(f"Error: {e}", file=sys.stderr)
                return 1

    # Build pipeline
    include_modify = args.execute or args.dry_run
    engine = PipelineEngine.create_default(
        llm=llm,
        include_modify=include_modify,
    )

    # Override confirmation stage if auto-confirm
    if args.auto_confirm:
        from scope_code.stages.confirmation import ConfirmationStage
        for i, stage in enumerate(engine.stages):
            if stage.name == "confirmation":
                engine.stages[i] = ConfirmationStage(auto_confirm=True)
                break

    # Set dry-run mode on modify stage
    if args.dry_run:
        from scope_code.stages.modify import ModifyStage
        for i, stage in enumerate(engine.stages):
            if stage.name == "modify":
                engine.stages[i] = ModifyStage(dry_run=True)
                break

    if args.verbose:
        print(f"Pipeline stages: {' → '.join(engine.stage_names)}")
        print(f"Analyzing: {args.project_path}")
        print(f"Requirement: {args.requirement}")
        print()

    # Run pipeline
    try:
        context = await engine.run(
            requirement=args.requirement,
            project_path=str(project_path),
            llm=llm,
        )
    except RuntimeError as e:
        print(f"Pipeline error: {e}", file=sys.stderr)
        return 1

    # Output results
    plan = context.modification_plan
    if plan is None:
        print("Error: No plan was generated.", file=sys.stderr)
        return 1

    # Save JSON
    if args.output_json:
        json_output = JSONOutput()
        saved = json_output.save(plan, args.output_json)
        print(f"JSON plan saved to: {saved}")

    # Save Markdown
    if args.output:
        report = MarkdownReport()
        saved = report.save(plan, args.output)
        print(f"Report saved to: {saved}")

    # Print summary
    print(plan.format_summary())

    # Status
    if context.plan_confirmed:
        print("\n✓ Plan confirmed by user.")
    elif context.should_stop:
        print("\n✗ Plan was not confirmed. No changes will be made.")
    else:
        print("\n⚠ Plan generated but not confirmed (auto-confirm mode).")

    return 0


def main():
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "analyze":
        return asyncio.run(run_analyze(args))

    return 0


if __name__ == "__main__":
    sys.exit(main())
