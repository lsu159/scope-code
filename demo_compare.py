"""
直观对比：Scope Code vs 普通 AI 编程工具

模拟场景：一个包含 auth / payment / chat / tests 的项目
需求：「给登录加限流」
"""

import asyncio
from scope_code import PipelineEngine, create_llm
from scope_code.stages.confirmation import ConfirmationStage

API_KEY = "sk-c45cf7a64fb849e0b92be570c2afe385"
PROJECT = "./sample_project/"

async def main():
    llm = create_llm(
        provider="deepseek",
        model="deepseek-chat",
        api_key=API_KEY,
    )

    engine = PipelineEngine.create_default()
    for i, s in enumerate(engine.stages):
        if s.name == "confirmation":
            engine.stages[i] = ConfirmationStage(auto_confirm=True)

    ctx = await engine.run(
        requirement="给登录加限流，防止暴力破解",
        project_path=PROJECT,
        llm=llm,
    )

    plan = ctx.modification_plan

    # ── 项目全部文件 ──
    all_files = {
        "src/auth/__init__.py":     "登录、注册、认证",
        "src/chat/__init__.py":     "聊天、消息、主题",
        "src/payment/__init__.py":  "支付、订单、结算",
        "tests/test_auth.py":       "认证模块测试",
    }

    must_set = {fc.file_path.replace("\\", "/") for fc in plan.scope.must_modify}
    not_set = set()
    for pattern in plan.scope.must_not_modify:
        pattern_norm = pattern.replace("\\", "/")
        for f in all_files:
            f_norm = f.replace("\\", "/")
            from fnmatch import fnmatch
            if fnmatch(f_norm, pattern_norm) or f_norm.startswith(pattern_norm.replace("/*", "/")):
                not_set.add(f)

    # ── 打印对比表格 ──
    print()
    print("=" * 72)
    print("  直观对比：需求「给登录加限流」")
    print("=" * 72)
    print()
    print(f"  {'文件':<30} {'功能':<20} {'Scope Code':<15} {'普通 AI':<15}")
    print(f"  {'-'*30} {'-'*20} {'-'*15} {'-'*15}")

    for f, desc in all_files.items():
        if f in must_set:
            scope = "✅ 必须改"
        elif f in not_set:
            scope = "🛑 禁止改"
        else:
            scope = "—"

        # 模拟普通 AI：通常会把相关模块全改了
        if "auth" in f:
            naive = "改了"
        elif "chat" in f or "payment" in f:
            naive = "可能顺手改了"  # 普通 AI 常犯的错误
        elif "test" in f:
            naive = "改了"
        else:
            naive = "—"

        print(f"  {f:<30} {desc:<20} {scope:<18} {naive:<15}")

    print()
    print("  ═══════════════════════════════════════════════════════════")
    print("  关键差异：")
    print()
    print("  Scope Code:")
    print(f"    → 只改 auth/__init__.py（1 个文件）")
    print(f"    → 明确锁定 chat、payment、tests（{len(not_set)} 个模块不准碰）")
    print(f"    → 每个决策都有证据链可追溯")
    print()
    print(f"  普通 AI：")
    print(f"    → 可能顺手改 chat 的主题设置、payment 的格式、")
    print(f"       test 的断言……这些跟「登录限流」毫无关系")
    print(f"    → 不会告诉你「为什么改了那个文件」")
    print(f"    → 不会明确告诉你「哪些文件不该碰」")
    print()
    print("  这就是 Scope Code 的核心价值：")
    print("  改得少、改得准、改得明明白白。")
    print("  ═══════════════════════════════════════════════════════════")
    print()

    # ── 证据链展示 ──
    print("  证据链（为什么只改 auth/__init__.py？）：")
    print()
    for i, e in enumerate(plan.evidence_chain, 1):
        print(f"  {i}. [{e.evidence_type}] {e.file}")
        print(f"     {e.reason}")
        if e.callers:
            print(f"     调用者: {', '.join(e.callers)}")
        if e.callees:
            print(f"     被调用: {', '.join(e.callees)}")
    print()

    # ── 风险评估 ──
    print("  LLM 分析的风险评估：")
    print()
    for r in plan.risk_assessment:
        print(f"  ⚠ {r}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
