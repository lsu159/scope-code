"""
Scope Code 展示脚本 — 一键演示核心能力

运行：python demo_showcase.py
前提：pip install -e .  + 设置 SCOPE_CODE_API_KEY
"""

import asyncio, sys, os
from scope_code import PipelineEngine, create_llm
from scope_code.stages.confirmation import ConfirmationStage

API_KEY = os.environ.get("SCOPE_CODE_API_KEY", "sk-c45cf7a64fb849e0b92be570c2afe385")

async def showcase(requirement, project_path, label):
    llm = create_llm(provider="deepseek", model="deepseek-chat", api_key=API_KEY)
    engine = PipelineEngine.create_default()
    for i, s in enumerate(engine.stages):
        if s.name == "confirmation":
            engine.stages[i] = ConfirmationStage(auto_confirm=True)

    ctx = await engine.run(requirement=requirement, project_path=project_path, llm=llm)
    plan = ctx.modification_plan
    req = ctx.structured_requirement

    print(f"  📋 需求：{requirement}")
    print(f"  📁 项目：{project_path}")
    print(f"  🧠 理解：{req.get('summary','')[:80]}")
    if req.get("ambiguities"):
        for a in req["ambiguities"][:3]:
            print(f"     ⚠ 歧义点：{a}")
    print(f"  🔴 必须修改：{len(plan.scope.must_modify)} 个文件")
    for fc in plan.scope.must_modify:
        print(f"     → {fc.file_path}")
    print(f"  🟢 禁止修改：{len(plan.scope.must_not_modify)} 个模块")
    for f in plan.scope.must_not_modify[:5]:
        reason = plan.scope.must_not_modify_reasons.get(f, "")
        print(f"     ✗ {f}  ({reason})")
    print()

async def main():
    print()
    print("=" * 65)
    print("  Scope Code — Reliable Software Engineering Agent")
    print("  Think Before Edit. Explain Before Change.")
    print("=" * 65)
    print()

    await showcase(
        "给登录加限流，防止暴力破解",
        "./sample_project/",
        "演示1"
    )

    await showcase(
        "给支付模块加个退款功能",
        "./sample_project/",
        "演示2"
    )

    print("=" * 65)
    print("  对比普通 AI 编程工具：")
    print()
    print("  普通工具：需求 → 改代码（可能顺手改 chat/payment/tests）")
    print("  Scope Code：需求 → 分析 → 推理范围 → 计划 → 确认 → 修改 → 验证")
    print("              ↑ 明确哪些不该改     ↑ 你说了算   ↑ 事后检查")
    print()
    print("  核心价值：改得少、改得准、改得明明白白。")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
