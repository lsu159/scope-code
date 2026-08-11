# Scope Code

[![Tests](https://github.com/lsu159/scope-code/actions/workflows/test.yml/badge.svg)](https://github.com/lsu159/scope-code/actions/workflows/test.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **Think Before Edit. Explain Before Change.**
> **先思考，再修改；先解释，再变更。**

**Reliable Software Engineering Agent Framework** — AI 在修改代码之前，必须先知道为什么改、改哪里、不改哪里。

---

## 与其他 AI 编程工具的区别

```
普通 AI 工具：  需求 → 改代码
Scope Code：    需求 → 理解 → 分析业务 → 分析结构 → 推理范围 → 计划 → 确认 → 修改 → 验证
                         ↑                            ↑          ↑        ↑       ↑
                    标记歧义点                    明确哪些不该改   你说了算   实际改  事后检查
```

| | Cursor / Copilot | Claude Code | Scope Code |
|---|---|---|---|
| 改代码 | ✅ | ✅ | ✅ |
| 告诉你为什么改这个文件 | ❌ | 部分 | ✅ 证据链 |
| 明确标记哪些文件不能碰 | ❌ | ❌ | ✅ 禁止修改列表 |
| 改完验证有没有改多 | ❌ | ❌ | ✅ 自动验证 |
| 修改前需用户确认 | 间接 | 间接 | ✅ 显式确认 |
| 支持中文需求 | ✅ | ✅ | ✅ |

可靠软件工程智能体框架（Reliable Software Engineering Agent Framework）—— 一个 Python 库，强制执行规范的代码修改流程：理解需求 → 分析业务 → 分析结构 → 推理范围 → 生成计划 → 用户确认 → 执行修改 → 验证结果。

## 为什么要做 Scope Code？

目前大多数 AI 编程工具的流程：

```
用户需求 → AI 直接改代码
```

Scope Code 的流程：

```
用户需求
  → 理解需求（你要什么）
  → 分析业务功能（涉及哪些业务）
  → 分析项目结构（有哪些模块、谁依赖谁）
  → 推导最小修改范围（必须改/建议改/禁止改）
  → 生成修改计划（含证据链）
  → 与用户确认（你说了算）
  → 执行代码修改
  → 验证修改结果（改对了吗？改多了吗？）
```

**AI 在写代码之前，必须先回答：为什么改、改哪里、不改哪里。**

## 核心原则

| 原则 | 含义 |
|---|---|
| **最小修改原则** | 只改必须改的。不该顺手"优化"无关代码。 |
| **先解释再修改** | 每次修改必须回答：为什么是这个文件？为什么不是别的文件？ |
| **范围优先** | 先划定必须改/建议改/禁止改的边界，再动手。 |
| **证据链** | 每个决策可追溯——谁调用了它、它调用了谁、改的理由是什么。 |
| **人机协作** | AI 提议，人类决策。最终决定权永远属于你。 |

## 安装

```bash
pip install -e .
```

带 CLI：

```bash
pip install -e ".[cli]"
```

需要 Python 3.10 以上。

## 快速开始

### 命令行

```bash
# 只分析不改代码（默认）
scope-code analyze "给登录加限流" ./my-project/

# 指定大模型
scope-code analyze --provider deepseek --model deepseek-chat \
  "修复认证bug" ./src/

# 实际修改代码
scope-code analyze --auto-confirm --execute \
  "给登录加限流" ./my-project/

# 预览修改但不写入（dry-run）
scope-code analyze --auto-confirm --execute --dry-run \
  "给登录加限流" ./my-project/

# 保存报告
scope-code analyze --output 计划.md --output-json 计划.json \
  "重构支付流程" ./app/

# 不用大模型（纯确定分析）
scope-code analyze --no-llm "加个缓存" ./my-project/
```

### Python API

```python
import asyncio
from scope_code import PipelineEngine, create_llm

async def main():
    # 创建大模型适配器（支持 claude / openai / deepseek / gemini）
    llm = create_llm(
        provider="deepseek",
        model="deepseek-chat",
        api_key="sk-你的密钥",
    )

    # 创建管线（6 阶段：只分析不修改）
    engine = PipelineEngine.create_default()
    context = await engine.run(
        requirement="给登录加限流",
        project_path="./my-project/",
        llm=llm,
    )

    # 拿到修改计划
    plan = context.modification_plan
    print(plan.format_summary())

    # 或者输出 JSON
    from scope_code.outputs import JSONOutput
    print(JSONOutput().render(plan))

asyncio.run(main())
```

完整 8 阶段管线（含代码修改 + 验证）：

```python
engine = PipelineEngine.create_default(include_modify=True)
```

### MCP Server（给 Claude Code 用）

在 Claude Code 的 MCP 设置里配置：

```json
{
    "mcpServers": {
        "scope-code": {
            "command": "python",
            "args": ["-m", "scope_code.mcp_server"],
            "env": {
                "SCOPE_CODE_API_KEY": "sk-你的密钥",
                "SCOPE_CODE_PROVIDER": "deepseek",
                "SCOPE_CODE_MODEL": "deepseek-chat"
            }
        }
    }
}
```

然后在 Claude Code 里直接说：「用 scope-code 分析一下给登录加限流要改哪些文件」。

## 管线阶段

| # | 阶段 | 做什么 | 用 LLM? |
|---|---|---|---|
| 1 | 理解需求 | 把自然语言需求解析成实体、动作、约束 | 是 |
| 2 | 业务分析 | 把需求映射到项目的业务功能和模块 | 是 |
| 3 | 结构分析 | 解析项目：文件树、模块、依赖图、调用图 | 否 |
| 4 | **范围推理** | 核心——确定必须改/建议改/禁止改，附证据链 | 是 |
| 5 | 计划生成 | 组装完整修改计划，含风险评估和验证步骤 | 是 |
| 6 | 用户确认 | 展示计划，用户决定接受/拒绝/修改 | 交互 |
| 7 | 代码修改 | 生成并写入代码变更（支持 dry-run 预览） | 是 |
| 8 | 修改验证 | 对比实际修改 vs 计划，检测违规和副作用 | 否 |

## 支持的语言

| 语言 | AST 解析 | 依赖图 | 调用图 |
|---|---|---|---|
| Python | `ast`（标准库） | 完整 | 完整（含跨文件） |
| JavaScript | 正则 | 完整 | 同文件 |
| TypeScript | 正则 | 完整 | 同文件 |
| Go | 正则 | 完整 | — |
| Rust | 正则 | 完整 | — |
| Java | 正则 | 完整 | — |
| Kotlin | 正则 | 完整 | — |

## 支持的大模型

框架本身模型无关——换模型只需改一个参数。

| 厂商 | 模型 | 用法 |
|---|---|---|
| DeepSeek | deepseek-chat / deepseek-reasoner | `--provider deepseek --model deepseek-chat` |
| Google Gemini | gemini-2.0-flash / gemini-2.5-pro | `--provider gemini --model gemini-2.0-flash` |
| OpenAI | gpt-4o | `--provider openai --model gpt-4o` |
| Anthropic Claude | claude-sonnet-5 / claude-opus-5 | `--provider claude --model claude-sonnet-5-20251001` |

添加新模型：

```python
from scope_code.llm import register_provider
from my_adapters import QwenAdapter
register_provider("qwen", QwenAdapter)
```

## 输出示例

```
============================================================
修改计划
============================================================

需求：给登录功能加限流

受影响的业务功能：
  * 身份认证
  * 安全

🔴 必须修改（1 个文件）：
  [modify] src/auth/__init__.py
    -> 直接实现了登录功能

🟡 建议修改（0 个文件）：
  （无）

🟢 禁止修改（3 个文件）：
  X src/chat/*
  X src/payment/*
  X tests/*

证据链（1 条）：
  1. [direct] src/auth/__init__.py
     调用者：LoginController
     直接实现了受影响的业务功能

风险评估：
  ! 限流太激进可能锁死正常用户
  ! 需要确定是按 IP 限流还是按用户限流

验证步骤：
  1. 写单元测试验证超过阈值后返回 429
  2. 测试正常用户不受影响
  3. 跑现有测试确保无回归
============================================================
```

## 项目结构

```
scope_code/
├── models/          # 数据模型（修改范围、修改计划、证据链、项目结构）
├── llm/             # 大模型适配器（Claude、OpenAI、DeepSeek、Gemini）
├── analyzers/       # 确定分析器（AST解析、依赖图、调用图、符号索引、多语言）
├── pipeline/        # 管线引擎、上下文、Stage 基类
├── stages/          # 8 个管线阶段
├── outputs/         # Markdown + JSON 输出
├── cli/             # 命令行入口
└── mcp_server.py    # MCP 协议服务器
```

## 项目状态

V1 功能完整。26 个测试通过。已用 DeepSeek 端到端验证。

- [x] 8 阶段完整管线
- [x] 修改范围推理 + 证据链
- [x] 4 种大模型支持
- [x] 7 种编程语言项目分析
- [x] 跨文件调用图（Python）
- [x] MCP Server（可被 Claude Code 调用）
- [x] Git diff 集成验证
- [x] DeepSeek 端到端实战验证

## License

MIT
