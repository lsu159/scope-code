"""
Scope Code — Reliable Software Engineering Agent Framework.

Think Before Edit. Explain Before Change.
先思考，再修改；先解释，再变更。

A Python library/SDK that implements a disciplined pipeline for code
modification: understand → analyze → infer scope → plan → confirm →
modify → verify.

Core principles:
    - Minimum Scope Editing
    - Explain Before Edit
    - Scope First
    - Evidence Chain
    - Human-AI Collaboration
"""

__version__ = "0.1.0"
__author__ = "Scope Code Team"

from .pipeline.engine import PipelineEngine
from .pipeline.context import PipelineContext
from .models.scope import ModificationScope, FileChange
from .models.plan import ModificationPlan
from .models.evidence import Evidence, EvidenceChain
from .models.project import ProjectStructure, Module, FileNode
from .llm.base import LLMAdapter, LLMConfig, Message
from .llm.factory import create_llm

__all__ = [
    # Pipeline
    "PipelineEngine",
    "PipelineContext",
    # Models
    "ModificationScope",
    "FileChange",
    "ModificationPlan",
    "Evidence",
    "EvidenceChain",
    "ProjectStructure",
    "Module",
    "FileNode",
    # LLM
    "LLMAdapter",
    "LLMConfig",
    "Message",
    "create_llm",
]
