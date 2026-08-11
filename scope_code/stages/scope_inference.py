"""Stage 4: Scope Inference — THE CORE ALGORITHM.

This is the heart of the Reliable Software Engineering Agent.
It determines:
    - What files MUST be modified (with evidence)
    - What files SHOULD be modified (suggestions)
    - What files MUST NOT be modified (risk boundary)
    - What files are confirmed to need NO changes

Algorithm:
    1. Seed set = files matching business functions (via symbol index)
    2. Expand via dependency graph:
       - Callees of seed → must_modify (direct dependencies)
       - Callers of seed that need adaptation → must_modify
    3. Boundary check:
       - Files adjacent but no data/contract change → should_modify
       - Unrelated modules → must_not_modify
    4. Build evidence chain for each must_modify entry
"""

from typing import List, Optional, Set

from ..llm.base import LLMAdapter, Message
from ..pipeline.stage import Stage
from ..pipeline.context import PipelineContext
from ..models.scope import ModificationScope, FileChange
from ..models.evidence import Evidence
from ..analyzers.dependency import DependencyAnalyzer
from ..analyzers.symbol_index import SymbolIndex


SCOPE_INFERENCE_SCHEMA = {
    "type": "object",
    "properties": {
        "reasoning": {
            "type": "string",
            "description": "Detailed reasoning for the scope decision.",
        },
        "must_modify_files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "reason": {"type": "string"},
                    "evidence_type": {
                        "type": "string",
                        "enum": ["direct", "transitive", "interface", "config"],
                    },
                },
                "required": ["file", "reason"],
            },
        },
        "should_modify_files": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["file", "reason"],
            },
        },
        "must_not_modify_reasons": {
            "type": "object",
            "description": "Map of file → reason why it must NOT be touched.",
        },
        "risk_notes": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
    "required": ["must_modify_files", "must_not_modify_reasons"],
}

SYSTEM_PROMPT = """You are a Software Architecture Analyst specializing in
minimum-scope editing. Your job is to determine the EXACT set of files
that must change for a given requirement.

Core principles:
1. MINIMUM SCOPE: Only touch what MUST change. Every change is a risk.
2. EVIDENCE REQUIRED: Every must_modify file needs a concrete reason.
3. BOUNDARY ENFORCEMENT: Explicitly list files that must NOT be touched.

For each file you consider, answer:
- Why must THIS file change? (not a different file)
- What would break if I DON'T change it?
- Is there a way to avoid changing it?

Given:
- Business functions affected
- Dependency graph (who imports whom)
- Symbol index (where each class/function lives)
- Seed files that directly implement the affected functions

You must:
1. Start from the seed files
2. Follow the dependency chain ONLY as far as necessary
3. Stop at module boundaries when possible
4. Explicitly mark unrelated modules as 'must not modify'
5. Provide evidence for every decision"""


class ScopeInferenceStage(Stage):
    """Stage 4: Derive minimum modification scope with evidence chain.

    This is the most critical stage. It combines graph analysis
    with LLM reasoning to produce a precise modification boundary.

    Input:
        - context.business_functions
        - context.structured_requirement
        - context.dependency_graph
        - context.call_graph
        - context.metadata["dependency_analyzer"]
        - context.metadata["symbol_index"]

    Output:
        - context.modification_scope (ModificationScope)
        - context.evidence_chain (List[Evidence])
    """

    @property
    def name(self) -> str:
        return "scope-inference"

    @property
    def label(self) -> str:
        return "Inferring Modification Scope"

    async def _run(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter] = None,
    ) -> None:
        self.log(context, "Beginning scope inference...")

        dep_analyzer: DependencyAnalyzer = context.metadata.get(
            "dependency_analyzer"
        )
        symbol_index: SymbolIndex = context.metadata.get("symbol_index")

        if dep_analyzer is None or context.dependency_graph is None:
            context.halt("Dependency graph not available for scope inference.")
            return

        # ── Step 1: Find seed files ──────────────────────────
        seed_files = self._find_seed_files(
            context.business_functions,
            symbol_index,
            context,
        )
        self.log(context, f"Seed files ({len(seed_files)}): {seed_files}")

        if not seed_files:
            self.log(
                context,
                "No seed files found. Running LLM-guided search...",
            )
            seed_files = await self._llm_guided_seed_search(context, llm)

        if not seed_files:
            # Last resort: keyword scan of all source files
            self.log(context, "Running keyword scan as last resort...")
            seed_files = self._keyword_scan(context)

        if not seed_files:
            context.halt(
                "Could not identify any files matching the requirement. "
                "The project structure may not match the requirement's "
                "business functions."
            )
            return

        # ── Step 2: Expand via dependency graph ──────────────
        direct, transitive = dep_analyzer.get_impact_scope(seed_files)

        self.log(
            context,
            f"Impact scope: {len(direct)} direct, "
            f"{len(transitive)} transitive.",
        )

        # ── Step 2.5: Narrow via call graph (senior-engineer precision) ─
        cg_analyzer = context.metadata.get("call_graph_analyzer")
        if cg_analyzer and transitive:
            narrowed = self._narrow_by_call_graph(
                seed_files, direct, transitive, cg_analyzer
            )
            removed = transitive - narrowed
            if removed:
                self.log(
                    context,
                    f"Call graph narrowed scope: removed {len(removed)} files "
                    f"that import but don't call affected functions.",
                )
            transitive = narrowed

        # ── Step 3: LLM refines the scope ────────────────────
        if llm is not None:
            scope, evidence_chain = await self._llm_refine_scope(
                context, seed_files, direct, transitive, dep_analyzer, llm
            )
        else:
            scope, evidence_chain = self._deterministic_scope(
                context, seed_files, direct, transitive, dep_analyzer
            )

        context.modification_scope = scope
        context.evidence_chain = evidence_chain

        self.log(
            context,
            f"Scope complete: "
            f"must_modify={len(scope.must_modify)}, "
            f"should_modify={len(scope.should_modify)}, "
            f"must_not_modify={len(scope.must_not_modify)}, "
            f"no_change={len(scope.no_change)}, "
            f"evidence={len(evidence_chain)} items.",
        )

    # ── seed file discovery ────────────────────────────────────

    def _find_seed_files(
        self,
        business_functions: List[str],
        symbol_index: Optional[SymbolIndex],
        context: PipelineContext,
    ) -> Set[str]:
        """Find files that directly implement the affected business functions.

        Uses the symbol index to match business function names to
        code symbols (classes, functions, modules).
        """
        seed_files: Set[str] = set()

        if symbol_index is None:
            return seed_files

        for bf in business_functions:
            # Try exact match
            locations = symbol_index.find(bf)
            for loc in locations:
                file_path = loc.split("::")[0]
                seed_files.add(file_path)

            # Try fuzzy search
            if not locations:
                fuzzy = symbol_index.search(bf)
                for loc in fuzzy[:5]:  # Top 5 matches
                    parts = loc.split("::")
                    if len(parts) >= 1:
                        seed_files.add(parts[0])

        # Also match against module names
        ps = context.project_structure
        if ps:
            for bf in business_functions:
                bf_lower = bf.lower().replace(" ", "").replace("_", "")
                for mod_name in ps.modules:
                    if bf_lower in mod_name.lower().replace("_", ""):
                        module = ps.modules[mod_name]
                        for f in module.all_files():
                            seed_files.add(f.path)

        return seed_files

    async def _llm_guided_seed_search(
        self,
        context: PipelineContext,
        llm: Optional[LLMAdapter],
    ) -> Set[str]:
        """Use LLM to find seed files when symbol search fails."""
        if llm is None:
            return set()

        ps = context.project_structure
        if ps is None:
            return set()

        # Build a file listing for the LLM
        file_list = []
        for rel_path, file_node in sorted(ps.files.items()):
            if file_node.file_type.value == "source":
                symbols = file_node.classes + file_node.exports[:5]
                file_list.append(
                    f"{rel_path} → {symbols if symbols else '(no symbols)'}"
                )

        file_list_text = "\n".join(file_list[:200])  # Cap at 200 files

        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(
                role="user",
                content=(
                    f"Requirement: {context.requirement}\n\n"
                    f"Business functions: {context.business_functions}\n\n"
                    f"Project files:\n{file_list_text}\n\n"
                    f"Which files most likely need to be modified? "
                    f"Return ONLY the file paths, one per line."
                ),
            ),
        ]

        try:
            response = await llm.chat(messages)
            seed_files = set()
            for line in response.strip().split("\n"):
                line = line.strip().lstrip("- ").strip()
                if line and "." in line:  # Looks like a file path
                    seed_files.add(line)
            return seed_files
        except Exception:
            return set()

    def _keyword_scan(self, context: PipelineContext) -> Set[str]:
        """Last-resort scan: grep all source files for requirement keywords.

        This is used when neither symbol index nor LLM can find seed files.
        It does a simple text match of business function names against
        file contents.
        """
        from pathlib import Path

        ps = context.project_structure
        if ps is None:
            return set()

        seed_files: Set[str] = set()
        keywords = set(context.business_functions)

        # Also extract words from the original requirement
        import re
        req_words = set(
            w.lower() for w in re.findall(r'\b\w+\b', context.requirement)
            if len(w) > 2 and w.lower() not in {
                'the', 'and', 'for', 'with', 'from', 'that', 'this',
                'then', 'when', 'what', 'which', 'there', 'their',
                'into', 'onto', 'upon', 'should', 'would', 'could',
            }
        )
        keywords.update(req_words)

        root = Path(ps.root_path)
        for rel_path, file_node in ps.files.items():
            if file_node.language != "python":
                continue
            if file_node.file_type.value not in ("source",):
                continue

            try:
                content = (root / rel_path).read_text(
                    encoding="utf-8", errors="ignore"
                ).lower()
                for kw in keywords:
                    if kw.lower() in content:
                        seed_files.add(rel_path)
                        break
            except Exception:
                continue

        return seed_files

    def _narrow_by_call_graph(
        self,
        seed_files: Set[str],
        direct: Set[str],
        transitive: Set[str],
        cg_analyzer,
    ) -> Set[str]:
        """Use call graph to remove false positives from transitive scope.

        A file that imports a seed file but never CALLS any function
        from it probably doesn't need modification. This is the difference
        between 'depends on' (import-level) and 'affected by' (call-level).
        """
        affected_symbols: Set[str] = set()
        for f in seed_files | direct:
            for func_id in cg_analyzer.get_functions_in_file(f):
                affected_symbols.add(func_id.split("::")[-1])

        if not affected_symbols:
            return transitive

        kept: Set[str] = set()
        for f in transitive:
            file_funcs = cg_analyzer.get_functions_in_file(f)
            has_call = False
            for func_id in file_funcs:
                callees = cg_analyzer.get_all_callees(
                    f, func_id.split("::")[-1]
                )
                for callee in callees:
                    callee_symbol = callee.split("::")[-1]
                    if callee_symbol in affected_symbols:
                        has_call = True
                        break
                if has_call:
                    break
            if has_call:
                kept.add(f)

        return kept if kept else transitive

    # ── scope refinement ───────────────────────────────────────

    async def _llm_refine_scope(
        self,
        context: PipelineContext,
        seed_files: Set[str],
        direct: Set[str],
        transitive: Set[str],
        dep_analyzer: DependencyAnalyzer,
        llm: LLMAdapter,
    ) -> tuple[ModificationScope, List[Evidence]]:
        """Use LLM to refine and annotate the scope with reasoning."""

        # Find unrelated modules
        unrelated = dep_analyzer.find_unrelated_modules(
            list(seed_files), context.project_structure
        )

        # Build the prompt context
        scope_context = (
            f"## Requirement\n{context.requirement}\n\n"
            f"## Business Functions\n{context.business_functions}\n\n"
            f"## Seed Files (directly implement the function)\n"
            + "\n".join(f"- {f}" for f in sorted(seed_files))
            + "\n\n"
            f"## Direct Dependencies (seed → these)\n"
            + "\n".join(f"- {f}" for f in sorted(direct - seed_files))
            + "\n\n"
            f"## Transitive Dependencies (dependents of seed)\n"
            + "\n".join(f"- {f}" for f in sorted(transitive))
            + "\n\n"
            f"## Unrelated Modules (DO NOT MODIFY)\n"
            + "\n".join(f"- {m}" for m in sorted(unrelated))
        )

        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(
                role="user",
                content=(
                    f"{scope_context}\n\n"
                    f"Refine this scope: which files MUST be modified, "
                    f"which SHOULD be modified, and which must NOT be "
                    f"touched? Provide detailed reasoning for each."
                ),
            ),
        ]

        try:
            result = await llm.structured_output(
                messages, SCOPE_INFERENCE_SCHEMA
            )
            return self._build_scope_from_llm(
                result, seed_files, unrelated, dep_analyzer
            )
        except Exception as e:
            self.log(context, f"LLM scope refinement failed: {e}")
            return self._deterministic_scope(
                context, seed_files, direct, transitive, dep_analyzer
            )

    def _deterministic_scope(
        self,
        context: PipelineContext,
        seed_files: Set[str],
        direct: Set[str],
        transitive: Set[str],
        dep_analyzer: DependencyAnalyzer,
    ) -> tuple[ModificationScope, List[Evidence]]:
        """Deterministic scope inference without LLM.

        Uses graph analysis only — no AI reasoning.
        """
        scope = ModificationScope()
        evidence_chain: List[Evidence] = []

        # Must modify: seed files + direct dependencies
        all_must = seed_files | direct
        for f in sorted(all_must):
            reason = self._generate_reason(f, seed_files, dep_analyzer)
            scope.must_modify.append(FileChange(
                file_path=f,
                change_type="modify",
                reason=reason,
            ))

            callers = dep_analyzer.get_dependents(f)
            callees = dep_analyzer.get_dependencies(f)

            evidence_chain.append(Evidence(
                file=f,
                reason=reason,
                callers=callers,
                callees=callees,
                business_function=(
                    context.business_functions[0]
                    if context.business_functions else ""
                ),
                evidence_type=(
                    "direct" if f in seed_files else "transitive"
                ),
            ))

        # Should modify: transitive dependencies
        for f in sorted(transitive):
            scope.should_modify.append(FileChange(
                file_path=f,
                change_type="modify",
                reason="Transitively affected by the change. "
                       "Review for compatibility.",
            ))

        # Must not modify — store reason separately from glob pattern
        unrelated = dep_analyzer.find_unrelated_modules(
            list(seed_files), context.project_structure
        )
        for module_name in sorted(unrelated):
            pattern = f"{module_name}/*"
            scope.must_not_modify.append(pattern)
            scope.must_not_modify_reasons[pattern] = (
                "unrelated — no dependency connection to affected modules"
            )

        return scope, evidence_chain

    def _build_scope_from_llm(
        self,
        llm_result: dict,
        seed_files: Set[str],
        unrelated: Set[str],
        dep_analyzer: DependencyAnalyzer,
    ) -> tuple[ModificationScope, List[Evidence]]:
        """Convert LLM output to ModificationScope and Evidence list."""
        scope = ModificationScope()
        evidence_chain: List[Evidence] = []

        # Must modify
        for item in llm_result.get("must_modify_files", []):
            f = item["file"]
            reason = item.get("reason", "Required by scope analysis.")
            ev_type = item.get("evidence_type", "direct")

            scope.must_modify.append(FileChange(
                file_path=f,
                change_type="modify",
                reason=reason,
            ))

            callers = dep_analyzer.get_dependents(f)
            callees = dep_analyzer.get_dependencies(f)

            evidence_chain.append(Evidence(
                file=f,
                reason=reason,
                callers=callers,
                callees=callees,
                evidence_type=ev_type,
            ))

        # Should modify
        for item in llm_result.get("should_modify_files", []):
            scope.should_modify.append(FileChange(
                file_path=item["file"],
                change_type="modify",
                reason=item.get("reason", "Suggested for review."),
            ))

        # Must not modify — store reason separately from glob pattern
        must_not_reasons = llm_result.get("must_not_modify_reasons", {})
        for module_name in sorted(unrelated):
            pattern = f"{module_name}/*"
            reason = must_not_reasons.get(module_name, "unrelated — no dependency connection")
            scope.must_not_modify.append(pattern)
            scope.must_not_modify_reasons[pattern] = reason
        for f, reason in must_not_reasons.items():
            if f not in scope.must_not_modify:
                scope.must_not_modify.append(f)
                scope.must_not_modify_reasons[f] = reason

        return scope, evidence_chain

    def _generate_reason(
        self,
        file_path: str,
        seed_files: Set[str],
        dep_analyzer: DependencyAnalyzer,
    ) -> str:
        """Generate a deterministic reason for why a file must change."""
        if file_path in seed_files:
            return "Directly implements the affected business function."

        # Check if it's a dependency of a seed file
        for sf in seed_files:
            deps = dep_analyzer.get_dependencies(sf)
            if file_path in deps:
                return f"Imported by seed file '{sf}' — required dependency."

        # Check if it depends on a seed file
        for sf in seed_files:
            deps = dep_analyzer.get_dependents(sf)
            if file_path in deps:
                return f"Depends on seed file '{sf}' — may need adaptation."

        return "Within the impact scope of the change."
