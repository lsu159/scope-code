# Scope Code：一个"先思考再修改"的 AI 软件工程框架

> **Think Before Edit. Explain Before Change.**
> 我们做了一个不直接改代码的 AI 编程工具。

---

## 一、为什么做这个

目前市面上几乎所有 AI 编程工具（Cursor、Copilot、Claude Code 等）的流程是：

```
用户需求 → AI 直接改代码
```

这个流程有两个致命问题：

1. **AI 不会告诉你"为什么改这个文件"**——它改了 5 个文件，你只知道改了，不知道为什么是这 5 个
2. **AI 不会告诉你"哪些文件不该碰"**——它顺手优化了聊天模块的代码？重构了支付模块的格式？这些跟你的需求毫无关系

我们做了一个流程不同的东西：

```
用户需求 → 理解需求 → 分析业务 → 分析结构 → 推理范围 → 生成计划 → 确认 → 修改 → 验证
```

**AI 在写代码之前，必须先回答：为什么改、改哪里、不改哪里。**

---

## 二、核心原则

| 原则 | 含义 |
|---|---|
| **最小修改原则** | 只改必须改的，不顺手"优化"无关代码 |
| **先解释再修改** | 每次修改都要有理由，没说清楚不准改 |
| **范围优先** | 先划定 必须改 / 建议改 / 禁止改 的边界 |
| **证据链** | 每个决策可追溯 — 谁调用了它、为什么受影响 |
| **人机协作** | AI 提议，用户决策，最终决定权永远属于人 |

---

## 三、实际效果

用同一个示例项目（包含 auth / payment / chat / tests 四个模块），分别提两个需求：

**需求 1：给登录加限流**

```
必须修改（1 个文件）：
  src/auth/__init__.py

禁止修改（3 个模块）：
  ✗ src/chat/*    — 无关，无依赖关系
  ✗ src/payment/* — 无关，无依赖关系
  ✗ tests/*       — 无关，无依赖关系
```

**需求 2：给支付模块加退款功能**

```
必须修改（1 个文件）：
  src/payment/__init__.py

禁止修改（3 个模块）：
  ✗ src/auth/*    — 无关，无依赖关系
  ✗ src/chat/*    — 无关，无依赖关系
  ✗ tests/*       — 无关，无依赖关系
```

两个不同的需求，每次都只改目标模块，其他模块全部锁定。这就是 Scope Code 的核心价值。

---

## 四、技术架构

8 阶段管线，纯 Python 实现：

```
理解需求 → 业务分析 → 结构分析 → 范围推理 → 计划生成 → 用户确认 → 代码修改 → 修改验证
```

- **Stage 1-2**（LLM）：解析自然语言需求，映射到业务功能
- **Stage 3**（确定性）：AST 解析 + 依赖图 + 跨文件调用图
- **Stage 4**（核心）：依赖图 + 调用图 + LLM 推理 → 最小修改范围 + 证据链
- **Stage 5-6**（交互）：生成计划、风险评估、用户确认/修改范围
- **Stage 7-8**（执行+审计）：生成代码变更、验证是否改多了

支持 4 种大模型（Claude / OpenAI / DeepSeek / Gemini）、7 种编程语言。

---

## 五、与其他工具的对比

| | Cursor / Copilot | Claude Code | **Scope Code** |
|---|---|---|---|
| 改代码 | ✅ | ✅ | ✅ |
| 为什么改这个文件 | ❌ | 部分 | ✅ 证据链 |
| 明确哪些不该改 | ❌ | ❌ | ✅ 禁止列表 |
| 改完验证有没有改多 | ❌ | ❌ | ✅ 自动审计 |
| 用户显式确认 | 间接 | 间接 | ✅ 显式确认 |
| 支持多模型 | — | Anthropic | ✅ 4 种 |

---

## 六、快速开始

```bash
# 安装
git clone https://github.com/lsu159/scope-code.git
cd scope-code
pip install -e .

# 设置 API Key（DeepSeek 注册送 500 万 tokens）
set SCOPE_CODE_API_KEY=sk-your-key

# 分析项目
python -m scope_code.cli.main analyze --provider deepseek --model deepseek-chat "你的需求" ./你的项目/
```

---

## 七、关于项目

这是我设计的"可靠软件工程智能体框架"。它最大的特点不是代码生成，而是：

- **修改范围推理**（Scope Inference）
- **最小修改原则**（Minimum Scope Editing）
- **修改证据链**（Evidence Chain）
- **用户与 AI 协商机制**（Human-AI Collaboration）

框架本身是模型无关的——即使未来底层模型升级，这套工作流依然有独立价值。这也是我觉得它最有竞争力的地方。

**GitHub：** [https://github.com/lsu159/scope-code](https://github.com/lsu159/scope-code)

**Think Before Edit. Explain Before Change.**
**先思考，再修改；先解释，再变更。**
