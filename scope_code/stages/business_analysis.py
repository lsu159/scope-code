"""Stage 2: Business Function Analysis.

Maps the structured requirement to the project's business functions
and identifies which logical modules/submodules are affected.
"""

from typing import Optional

from ..llm.base import LLMAdapter, Message
from ..pipeline.stage import Stage
from ..pipeline.context import PipelineContext

BUSINESS_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "business_functions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "likely_modules": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "impact_level": {
                        "type": "string",
                        "enum": ["direct", "indirect", "none"],
                    },
                },
                "required": ["name", "impact_level"],
            },
        },
        "analysis_notes": {"type": "string"},
    },
    "required": ["business_functions"],
}

SYSTEM_PROMPT = """You are a Business Analyst. Your job is to map a software
requirement to the business functions and modules of a project.

Given:
1. A structured requirement (entities, actions, constraints)
2. The project's module structure (list of modules with their files)

You must:
- Identify which business functions are affected by the requirement
- Map each function to likely code modules/files
- Classify impact as 'direct' (must change), 'indirect' (may change), or 'none'
- Think in terms of business logic, not code syntax

Rules:
- Be conservative: if unsure about a module, mark it 'indirect'
- Do not invent business functions not supported by the codebase
- Respect explicit constraints from the requirement"""


class BusinessAnalysisStage(Stage):
    """Stage 2: Map requirements to business functions and modules.

    Input: context.structured_requirement + context.project_structure
    Output: context.business_functions (list of business function names)
    """

    @property
    def name(self) -> str:
        return "business-analysis"

    @property
    def label(self) -> str:
        return "Analyzing Business Functions"

    async def _run(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter] = None,
    ) -> None:
        self.log(context, "Mapping requirements to business functions...")

        # Build module summary for the LLM
        module_summary = self._build_module_summary(context)

        if llm is None:
            # Fallback: use structured requirement entities as business functions
            req = context.structured_requirement
            context.business_functions = req.get("entities", [])
            self.log(
                context,
                f"Fallback: using {len(context.business_functions)} "
                f"entities as business functions.",
            )
            return

        req = context.structured_requirement
        req_text = (
            f"Summary: {req.get('summary', '')}\n"
            f"Entities: {', '.join(req.get('entities', []))}\n"
            f"Actions: {req.get('actions', [])}\n"
            f"Constraints: {', '.join(req.get('constraints', []))}\n"
        )

        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(
                role="user",
                content=(
                    f"## Requirement\n{req_text}\n\n"
                    f"## Project Modules\n{module_summary}\n\n"
                    f"Identify the business functions affected by this "
                    f"requirement and map them to likely modules."
                ),
            ),
        ]

        try:
            result = await llm.structured_output(
                messages, BUSINESS_ANALYSIS_SCHEMA
            )
            functions = result.get("business_functions", [])
            context.business_functions = [f["name"] for f in functions]
            context.metadata["business_analysis"] = result
            self.log(
                context,
                f"Identified {len(context.business_functions)} "
                f"business functions: {context.business_functions}",
            )
        except Exception as e:
            self.log(context, f"LLM analysis failed: {e}, using fallback.")
            context.add_error(f"BusinessAnalysisStage LLM failed: {e}")
            req = context.structured_requirement
            context.business_functions = req.get("entities", [])

    def _build_module_summary(self, context: PipelineContext) -> str:
        """Build a text summary of the project's module structure."""
        ps = context.project_structure
        if ps is None:
            return "Project structure not yet analyzed."

        lines = []
        for mod_name, module in sorted(ps.modules.items()):
            file_count = len(module.all_files())
            top_symbols = []
            for f in module.files[:3]:  # Sample up to 3 files
                top_symbols.extend(f.exports[:5])

            lines.append(
                f"- {mod_name}: {file_count} files"
                + (f", symbols: {top_symbols[:5]}" if top_symbols else "")
            )

        return "\n".join(lines) if lines else "No modules found."
