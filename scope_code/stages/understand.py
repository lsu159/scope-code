"""Stage 1: Understand Requirements.

Parses the user's natural language requirement into a structured
representation: entities, actions, constraints, and scope hints.
"""

import json
from typing import Optional

from ..llm.base import LLMAdapter, Message
from ..pipeline.stage import Stage
from ..pipeline.context import PipelineContext


REQUIREMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "One-sentence summary of the requirement.",
        },
        "entities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Business entities mentioned (e.g., User, Order, Payment).",
        },
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "target": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["action", "target"],
            },
            "description": "Actions to perform (add, modify, fix, remove, etc.).",
        },
        "constraints": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Explicit constraints or things NOT to change.",
        },
        "scope_hints": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Hints about which modules/files may be involved.",
        },
        "ambiguities": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Unclear or ambiguous parts that need clarification.",
        },
    },
    "required": ["summary", "entities", "actions"],
}

SYSTEM_PROMPT = """You are a Requirements Analyst. Your job is to parse a user's
natural language requirement into a structured format.

Rules:
1. Extract all business entities mentioned.
2. Identify every action (add, modify, fix, remove, refactor, etc.) and its target.
3. Note any explicit constraints — things the user said NOT to change.
4. Infer scope hints from the requirement's language.
5. Flag ambiguities that need clarification before proceeding.

Be precise. Do not invent entities or actions not mentioned in the requirement.
Focus on WHAT the user wants, not HOW to implement it."""


class UnderstandStage(Stage):
    """Stage 1: Parse natural language requirement into structured form.

    Input: context.requirement (raw NL)
    Output: context.structured_requirement (dict with entities, actions, etc.)
    """

    @property
    def name(self) -> str:
        return "understand-requirements"

    @property
    def label(self) -> str:
        return "Understanding Requirements"

    async def _run(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter] = None,
    ) -> None:
        self.log(context, f"Parsing requirement: {context.requirement[:100]}...")

        if llm is None:
            # Fallback: basic keyword extraction without LLM
            context.structured_requirement = self._fallback_parse(
                context.requirement
            )
            return

        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(
                role="user",
                content=f"Parse this requirement:\n\n{context.requirement}",
            ),
        ]

        try:
            result = await llm.structured_output(
                messages, REQUIREMENT_SCHEMA
            )
            context.structured_requirement = result
            self.log(
                context,
                f"Found {len(result.get('entities', []))} entities, "
                f"{len(result.get('actions', []))} actions, "
                f"{len(result.get('ambiguities', []))} ambiguities.",
            )
        except Exception as e:
            self.log(context, f"LLM parsing failed: {e}, using fallback.")
            context.add_error(f"UnderstandStage LLM failed: {e}")
            context.structured_requirement = self._fallback_parse(
                context.requirement
            )

    def _fallback_parse(self, requirement: str) -> dict:
        """Basic NL parsing without LLM. Supports Chinese and English."""
        import re

        # Action verbs (English + Chinese)
        action_verbs = {
            'add', 'create', 'modify', 'change', 'update', 'fix',
            'remove', 'delete', 'refactor', 'optimize', 'implement',
            'replace', 'improve', 'enhance', 'migrate', 'build',
            'setup', 'configure', 'deploy', 'test', 'debug',
        }
        chinese_actions = {
            '加', '添加', '增加', '修改', '改', '删', '删除', '去掉',
            '优化', '重构', '修', '修复', '实现', '加个', '做个',
        }

        # Extract entities: English capitalized words + Chinese nouns
        entities = list(set(
            w for w in re.findall(r'\b[A-Z][a-z]+\b', requirement)
            if w.lower() not in action_verbs
            and w.lower() not in {'the', 'this', 'that', 'with', 'from',
                                  'when', 'what', 'which', 'there', 'their',
                                  'then', 'than', 'into', 'onto', 'upon'}
        ))

        # English tech nouns
        tech_nouns = {
            'login', 'logout', 'auth', 'token', 'password', 'user',
            'rate', 'limit', 'api', 'endpoint',
            'database', 'cache', 'queue', 'email', 'sms',
            'payment', 'order', 'cart', 'checkout', 'invoice',
            'chat', 'message', 'notification', 'upload', 'download',
            'search', 'filter', 'sort', 'page', 'dashboard',
            'config', 'setting', 'profile', 'admin', 'role',
            'permission', 'access', 'security', 'encrypt',
        }

        # Chinese business terms → English entity mapping
        chinese_terms = {
            '登录': 'login', '登陆': 'login', '注册': 'register',
            '认证': 'auth', '权限': 'permission', '角色': 'role',
            '支付': 'payment', '退款': 'refund', '订单': 'order',
            '购物车': 'cart', '结算': 'checkout', '发票': 'invoice',
            '聊天': 'chat', '消息': 'message', '通知': 'notification',
            '上传': 'upload', '下载': 'download', '搜索': 'search',
            '过滤': 'filter', '排序': 'sort', '分页': 'page',
            '配置': 'config', '设置': 'setting', '个人资料': 'profile',
            '管理员': 'admin', '安全': 'security', '加密': 'encrypt',
            '缓存': 'cache', '队列': 'queue', '数据库': 'database',
            '令牌': 'token', '密码': 'password', '用户': 'user',
            '限流': 'rate limiting', '接口': 'api',
            '模块': 'module', '功能': 'feature',
        }

        # Detect Chinese terms in requirement
        for cn_term, en_entity in chinese_terms.items():
            if cn_term in requirement:
                entities.append(en_entity)

        # Detect Chinese action verbs
        detected_actions = []
        for cn_action in chinese_actions:
            if cn_action in requirement:
                detected_actions.append(cn_action)

        # English word matching
        words = set(re.findall(r'\b\w+\b', requirement.lower()))
        entities.extend(w for w in words if w in tech_nouns)

        # Check 2-word phrases
        for phrase in ['rate limiting', 'two factor', 'real time']:
            if phrase in requirement.lower():
                entities.append(phrase.title())

        # Detect English action verbs
        detected_actions.extend(list(words & action_verbs))

        # Deduplicate entities
        entities = list(dict.fromkeys(entities))

        # Detect constraints
        constraints = []
        if 'without' in requirement.lower():
            constraints.append(
                requirement.lower().split('without', 1)[-1].strip('. ')
            )
        if "don't" in requirement.lower() or 'do not' in requirement.lower():
            constraints.append(requirement)
        if '不改' in requirement or '不要改' in requirement:
            constraints.append(requirement)

        return {
            "summary": requirement,
            "entities": entities,
            "actions": [
                {"action": a, "target": "", "description": requirement}
                for a in detected_actions
            ] if detected_actions else [
                {"action": "modify", "target": "", "description": requirement}
            ],
            "constraints": constraints,
            "scope_hints": [],
            "ambiguities": [],
        }
