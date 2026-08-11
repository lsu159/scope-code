"""Stage 3: Project Structure Analysis.

Fully deterministic — parses the project file tree, builds
dependency and call graphs. No LLM involved.
"""

from typing import Optional

from ..llm.base import LLMAdapter
from ..pipeline.stage import Stage
from ..pipeline.context import PipelineContext
from ..analyzers.project import ProjectAnalyzer
from ..analyzers.dependency import DependencyAnalyzer
from ..analyzers.call_graph import CallGraphAnalyzer
from ..analyzers.symbol_index import SymbolIndex


class StructureAnalysisStage(Stage):
    """Stage 3: Analyze project structure — files, modules, dependencies.

    This is the only fully deterministic stage in the pipeline.
    It uses AST parsing and filesystem traversal — no LLM calls.

    Input: context.project_path
    Output:
        - context.project_structure (ProjectStructure)
        - context.dependency_graph (nx.DiGraph)
        - context.call_graph (nx.DiGraph)
    """

    @property
    def name(self) -> str:
        return "structure-analysis"

    @property
    def label(self) -> str:
        return "Analyzing Project Structure"

    async def _run(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter] = None,
    ) -> None:
        self.log(context, "Walking file tree...")

        # 1. Project structure analysis
        project_analyzer = ProjectAnalyzer()
        context.project_structure = project_analyzer.analyze(
            context.project_path
        )
        ps = context.project_structure
        self.log(
            context,
            f"Found {len(ps.modules)} modules, "
            f"{len(ps.files)} files, "
            f"{len(ps.entry_points)} entry points.",
        )

        # 2. Dependency graph
        self.log(context, "Building dependency graph...")
        dep_analyzer = DependencyAnalyzer()
        context.dependency_graph = dep_analyzer.build(ps)
        self.log(
            context,
            f"Dependency graph: {context.dependency_graph.number_of_nodes()} "
            f"nodes, {context.dependency_graph.number_of_edges()} edges.",
        )

        # 3. Symbol index (must build before call graph for cross-file resolution)
        self.log(context, "Building symbol index...")
        index = SymbolIndex()
        index.build(ps)
        context.metadata["symbol_count"] = index.total_symbols
        context.metadata["symbol_index"] = index
        self.log(context, f"Indexed {index.total_symbols} symbols.")

        # 4. Call graph (uses dep graph + symbol index for cross-file resolution)
        self.log(context, "Building call graph (with cross-file resolution)...")
        cg_analyzer = CallGraphAnalyzer()
        context.call_graph = cg_analyzer.build(
            ps,
            dep_graph=context.dependency_graph,
            symbol_index=index,
        )
        self.log(
            context,
            f"Call graph: {context.call_graph.number_of_nodes()} "
            f"functions/methods, "
            f"{context.call_graph.number_of_edges()} calls.",
        )

        # Store analyzers in metadata for downstream stages
        context.metadata["dependency_analyzer"] = dep_analyzer
        context.metadata["call_graph_analyzer"] = cg_analyzer
        context.metadata["symbol_index"] = index
