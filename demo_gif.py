"""Scope Code Demo — clean output for GIF recording.

Run: python demo_gif.py
"""

import asyncio, os, sys, time
from scope_code import PipelineEngine, create_llm
from scope_code.stages.confirmation import ConfirmationStage

API_KEY = os.environ.get("SCOPE_CODE_API_KEY", "")

HEADER = """
  Scope Code
  Think Before Edit. Explain Before Change.
"""

SEP = "─" * 60

async def demo_step(requirement, project):
    llm = create_llm(provider="deepseek", model="deepseek-chat", api_key=API_KEY) if API_KEY else None
    engine = PipelineEngine.create_default()
    for i, s in enumerate(engine.stages):
        if s.name == "confirmation":
            engine.stages[i] = ConfirmationStage(auto_confirm=True)

    print(f"  $ scope-code analyze \"{requirement}\" {project}")
    print()
    print("  Analyzing...", end="", flush=True)

    ctx = await engine.run(requirement=requirement, project_path=project, llm=llm)
    plan = ctx.modification_plan

    print("\r" + " " * 30 + "\r", end="")

    # ── Compact output ──
    must = plan.scope.must_modify
    not_mod = plan.scope.must_not_modify
    reasons = plan.scope.must_not_modify_reasons

    print(f"  Business Functions: {', '.join(plan.business_functions)}")
    print()
    print(f"  MUST MODIFY ({len(must)} file{'s' if len(must) != 1 else ''}):")
    for fc in must:
        print(f"    [{fc.change_type}] {fc.file_path}")
        print(f"          {fc.reason}")
    print()
    print(f"  SHOULD MODIFY ({len(plan.scope.should_modify)} file{'s' if len(plan.scope.should_modify) != 1 else ''}):")
    for fc in plan.scope.should_modify:
        print(f"    [{fc.change_type}] {fc.file_path}")
    print()
    print(f"  MUST NOT MODIFY ({len(not_mod)} module{'s' if len(not_mod) != 1 else ''}):")
    for f in not_mod:
        r = reasons.get(f, "")
        reason_str = f" — {r}" if r else ""
        print(f"    X {f}{reason_str}")
    print()
    print(f"  Risks: {len(plan.risk_assessment)} identified")
    print(f"  Evidence: {len(plan.evidence_chain)} items")
    print(f"  Verification Steps: {len(plan.verification_steps)} defined")
    print()

    return plan


async def main():
    if not API_KEY:
        print("Set SCOPE_CODE_API_KEY to run live demo.")
        print("Running without LLM (deterministic mode)...")
        print()

    print(HEADER)
    print(SEP)
    print()

    # Step 1
    print("  Demo 1: Minimum Scope Editing")
    print(SEP)
    print()
    await demo_step("Add rate limiting to login to prevent brute force", "./sample_project/")

    # Step 2
    print("  Demo 2: Cross-module Isolation")
    print(SEP)
    print()
    await demo_step("Add refund feature to the payment module", "./sample_project/")

    # Summary
    print(SEP)
    print()
    print("  Key Takeaways:")
    print()
    print("  1. Only files that MUST change are identified")
    print("  2. Unrelated modules are EXPLICITLY locked — no accidental changes")
    print("  3. Every decision has traceable evidence")
    print("  4. Risks and verification steps come with every plan")
    print("  5. User must confirm before any code is touched")
    print()
    print(SEP)
    print()


if __name__ == "__main__":
    asyncio.run(main())
