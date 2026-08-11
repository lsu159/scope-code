# Scope Code：一个先思考再修改的 AI 软件工程框架

> Think Before Edit. Explain Before Change.
> 先思考，再修改。先解释，再变更。

## 为什么做这个

现在的 AI 编程工具，流程是这样的：你给需求，它直接改代码。

这有两个问题：第一，它不会告诉你为什么改这些文件，改了 5 个你只知道结果不知道原因。第二，它不会告诉你哪些文件不该碰，顺手优化了聊天模块的代码跟你的需求毫无关系。

我做了个不一样的：**AI 在写代码之前，必须先解释为什么改、改哪里、不该改哪里。**

## 流程图

普通工具：需求 → 改代码

Scope Code：需求 → 理解需求 → 分析业务 → 分析结构 → 推理范围 → 生成计划 → 你点头 → 执行修改 → 事后验证

```
第一步：看懂你要什么
第二步：找出涉及哪些业务模块
第三步：分析项目结构（谁依赖谁）
第四步：推理最小修改范围（必须改 / 建议改 / 禁止改）
第五步：生成修改计划 + 证据链 + 风险评估
第六步：你审阅、可以修改范围、确认
第七步：执行代码修改
第八步：验证有没有改多
```

## 核心原则

最小修改原则：只改必须改的，不顺手优化无关代码。

先解释再修改：每次修改都要有理由，没说清楚不准改。

范围优先：先划定边界，必须改的、建议改的、禁止碰的。

证据链：每个决策可追溯，谁调用了它、为什么受影响。

人机协作：AI 提议，你来决定。

## 实际效果

一个包含 auth、payment、chat、tests 四个模块的项目，提两个需求。

需求一，给登录加限流：

必须改：src/auth/__init__.py（1 个文件）

禁止改：src/chat/*、src/payment/*、tests/*（3 个模块全部锁定）

需求二，给支付模块加退款：

必须改：src/payment/__init__.py（1 个文件）

禁止改：src/auth/*、src/chat/*、tests/*（3 个模块全部锁定）

两次分析，每次只碰目标模块，其他全部锁死。这就是 Scope Code 跟普通 AI 工具的区别。

## 支持的大模型

框架本身模型无关，换模型只改一个参数：

DeepSeek：deepseek-chat

Google Gemini：gemini-2.0-flash

OpenAI：gpt-4o

Anthropic Claude：claude-sonnet-5

## 与其他工具的对比

Cursor / Copilot / Claude Code 能改代码，但不会告诉你为什么改这个文件，不会标记哪些不该碰，不会改完验证。Scope Code 每一项都有。

## 快速开始

git clone https://github.com/lsu159/scope-code.git
cd scope-code
pip install -e .

set SCOPE_CODE_API_KEY=你的key

python -m scope_code.cli.main analyze --provider deepseek --model deepseek-chat "你的需求" ./你的项目/

## 关于这个项目

这不是又一个 AI 编程助手，而是一个可靠软件工程智能体框架。它的核心价值不是代码生成，而是修改范围推理、最小修改原则、证据链、以及人机协商机制。框架本身模型无关，底层模型升级这套工作流依然有用。

GitHub：https://github.com/lsu159/scope-code

Think Before Edit. Explain Before Change.
