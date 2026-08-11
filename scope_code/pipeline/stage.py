"""Base Stage — abstract class for all pipeline stages."""

from abc import ABC, abstractmethod
from typing import Optional

from ..llm.base import LLMAdapter
from .context import PipelineContext


class Stage(ABC):
    """Abstract base class for a pipeline stage.

    Each stage in the pipeline is a single responsibility:
        - It reads from PipelineContext
        - It performs analysis (deterministic or LLM-assisted)
        - It writes results back to PipelineContext
        - It can set context.should_stop to short-circuit

    Naming convention:
        - name: kebab-case identifier (e.g., 'understand-requirements')
        - label: human-readable display name (e.g., 'Understanding Requirements')

    Override `execute()` for synchronous stages or
    `execute_async()` for stages that need an LLM.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique stage identifier."""
        ...

    @property
    @abstractmethod
    def label(self) -> str:
        """Human-readable stage label for progress display."""
        ...

    async def execute(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter] = None,
    ) -> None:
        """Execute this stage.

        Override this method for the stage's logic. By default,
        delegates to the synchronous _run method for backward
        compatibility.

        Args:
            context: The shared pipeline context.
            llm: Optional LLM adapter for stages that need AI reasoning.
        """
        await self._run(context, llm)

    async def _run(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter] = None,
    ) -> None:
        """Internal run method — override in subclasses."""
        raise NotImplementedError(
            f"Stage '{self.name}' must implement _run() or execute()"
        )

    def log(self, context: PipelineContext, message: str):
        """Log a message to the pipeline context metadata."""
        key = f"{self.name}_log"
        if key not in context.metadata:
            context.metadata[key] = []
        context.metadata[key].append(message)
