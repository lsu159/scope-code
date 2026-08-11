"""Pipeline engine — orchestrates the sequence of stages."""

import time
from typing import List, Optional

from ..llm.base import LLMAdapter
from .context import PipelineContext
from .stage import Stage
from ..models.plan import ModificationPlan


class PipelineEngine:
    """Orchestrates the Reliable SE Agent pipeline.

    Runs stages sequentially, passing the PipelineContext between them.
    Supports short-circuit (context.should_stop), error collection,
    and metadata tracking.

    Usage:
        engine = PipelineEngine(stages=[...])
        plan = await engine.run(
            requirement="Add rate limiting to login",
            project_path="/path/to/project",
            llm=llm_adapter,
        )
    """

    def __init__(self, stages: List[Stage]):
        if not stages:
            raise ValueError("At least one stage is required")
        self.stages = stages

    async def run(
        self,
        requirement: str,
        project_path: str,
        llm: Optional[LLMAdapter] = None,
        **metadata,
    ) -> PipelineContext:
        """Run the full pipeline.

        Args:
            requirement: The user's requirement in natural language.
            project_path: Absolute path to the target project.
            llm: LLM adapter for stages that need AI reasoning.
            **metadata: Arbitrary metadata to attach to the context.

        Returns:
            The final PipelineContext after all stages.

        Raises:
            RuntimeError: If a stage raises an unhandled exception.
        """
        context = PipelineContext(
            requirement=requirement,
            project_path=project_path,
            metadata=metadata,
        )

        total_start = time.monotonic()

        for stage in self.stages:
            if context.should_stop:
                break

            stage_start = time.monotonic()
            try:
                await stage.execute(context, llm)
            except Exception as e:
                context.add_error(
                    f"Stage '{stage.name}' failed: {e}"
                )
                # Re-raise — we don't silently skip failed stages
                raise RuntimeError(
                    f"Pipeline failed at stage '{stage.name}': {e}"
                ) from e
            finally:
                elapsed = time.monotonic() - stage_start
                context.metadata[f"{stage.name}_elapsed_ms"] = int(
                    elapsed * 1000
                )

        total_elapsed = time.monotonic() - total_start
        context.metadata["total_elapsed_ms"] = int(total_elapsed * 1000)

        return context

    def get_stage(self, name: str) -> Optional[Stage]:
        """Find a stage by name."""
        for s in self.stages:
            if s.name == name:
                return s
        return None

    @property
    def stage_names(self) -> List[str]:
        """Return the ordered list of stage names."""
        return [s.name for s in self.stages]

    @classmethod
    def create_default(
        cls,
        llm: Optional[LLMAdapter] = None,
        include_modify: bool = False,
    ) -> "PipelineEngine":
        """Create the default pipeline with all stages.

        Args:
            llm: Optional LLM adapter (stages will use it if provided).
            include_modify: If True, include modify+verify stages (full loop).
                           Default is False — plan-only mode.

        Returns:
            Configured PipelineEngine with the default stage sequence.
        """
        from ..stages.understand import UnderstandStage
        from ..stages.business_analysis import BusinessAnalysisStage
        from ..stages.structure_analysis import StructureAnalysisStage
        from ..stages.scope_inference import ScopeInferenceStage
        from ..stages.plan_generation import PlanGenerationStage
        from ..stages.confirmation import ConfirmationStage
        from ..stages.modify import ModifyStage
        from ..stages.verify import VerifyStage

        stages = [
            UnderstandStage(),
            BusinessAnalysisStage(),
            StructureAnalysisStage(),
            ScopeInferenceStage(),
            PlanGenerationStage(),
            ConfirmationStage(),
        ]

        if include_modify:
            stages.append(ModifyStage())
            stages.append(VerifyStage())

        return cls(stages=stages)
