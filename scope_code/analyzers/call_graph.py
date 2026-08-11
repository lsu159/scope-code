"""Call graph analyzer — builds function/method call graphs via AST.

Goes deeper than import-level dependency analysis: this maps
which specific functions and methods call which other functions
and methods — including cross-file calls.

The analyzer works in two phases:
    1. Per-file: parse each file, record calls with local symbol names
    2. Cross-file: resolve calls across files using dependency graph + symbol index
"""

import ast
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import networkx as nx

from ..models.project import ProjectStructure
from .dependency import DependencyAnalyzer
from .symbol_index import SymbolIndex


class CallGraphAnalyzer:
    """Builds a function/method-level call graph for a project.

    Graph structure:
        - Nodes are "file_path::symbol_name" (function or method)
        - Edges A → B mean "A calls B"
        - Cross-file calls are resolved via dependency graph + symbol index

    Usage:
        cg = CallGraphAnalyzer()
        graph = cg.build(structure, dep_graph, symbol_index)

        # Who calls login()?
        callers = cg.get_callers("auth.py", "login")

        # What functions does login() call?
        callees = cg.get_callees("auth.py", "login")

        # Cross-file: who calls AuthService.login() from other files?
        all_callers = cg.get_all_callers("auth.py", "login")
    """

    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()
        self._symbol_index: Optional[SymbolIndex] = None
        self._dep_graph: Optional[nx.DiGraph] = None
        self._file_symbols: Dict[str, Set[str]] = {}  # file → set of symbols

    # ── building ────────────────────────────────────────────────

    def build(
        self,
        structure: ProjectStructure,
        dep_graph: Optional[nx.DiGraph] = None,
        symbol_index: Optional[SymbolIndex] = None,
    ) -> nx.DiGraph:
        """Build a call graph from the project structure.

        Parses every Python source file and extracts function/method
        call relationships. Resolves cross-file calls when dependency
        graph and symbol index are provided.

        Args:
            structure: Project structure from ProjectAnalyzer.
            dep_graph: Optional dependency graph for cross-file resolution.
            symbol_index: Optional symbol index for cross-file resolution.

        Returns:
            A networkx DiGraph with call edges.
        """
        self.graph = nx.DiGraph()
        self._symbol_index = symbol_index
        self._dep_graph = dep_graph
        self._file_symbols = {}

        # ── Phase 1: per-file call extraction ─────────────────
        for rel_path, file_node in structure.files.items():
            if file_node.language != "python":
                continue

            abs_path = Path(structure.root_path) / rel_path
            if not abs_path.exists():
                continue

            try:
                source = abs_path.read_text(encoding="utf-8")
                tree = ast.parse(source)
                visitor = _CallVisitor(rel_path, self.graph)
                visitor.visit(tree)

                # Record all symbols in this file
                self._file_symbols[rel_path] = set()
                for node_id in self.graph.nodes:
                    if node_id.startswith(f"{rel_path}::"):
                        symbol = node_id.split("::", 1)[1]
                        self._file_symbols[rel_path].add(symbol)

            except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
                continue

        # ── Phase 2: cross-file resolution ────────────────────
        if dep_graph is not None and symbol_index is not None:
            self._resolve_cross_file_calls(structure)

        return self.graph

    def _resolve_cross_file_calls(self, structure: ProjectStructure):
        """Resolve call targets that may be in other files.

        For each call edge where the target might be in a different file:
        1. Check if the target symbol exists in files imported by the caller
        2. Check the global symbol index
        3. Re-route edges to the correct file::symbol node
        """
        dep_analyzer = DependencyAnalyzer()
        dep_analyzer.graph = self._dep_graph

        edges_to_fix: List[Tuple[str, str, str]] = []  # (caller, local_callee, symbol)

        for caller, callee, edge_data in list(self.graph.edges(data=True)):
            caller_file = caller.split("::")[0]
            callee_symbol = callee.split("::")[-1]

            # Skip if already resolved (callee file is real, not same as caller's file)
            callee_file = callee.split("::")[0]
            if callee_file != caller_file:
                continue  # Already a cross-file edge or same-file

            # Check if this is truly a same-file call
            if callee_symbol in self._file_symbols.get(caller_file, set()):
                continue  # Correct same-file call, no fix needed

            # This might be a cross-file call — try to resolve
            resolved_file = self._find_symbol_in_imports(
                callee_symbol, caller_file
            )

            if resolved_file and resolved_file != caller_file:
                edges_to_fix.append((caller, callee, callee_symbol, resolved_file))

        # Apply fixes
        for caller, old_callee, symbol, resolved_file in edges_to_fix:
            new_callee = f"{resolved_file}::{symbol}"
            # Add the resolved node if not exists
            if new_callee not in self.graph:
                self.graph.add_node(
                    new_callee,
                    type="function",
                    name=symbol,
                    file=resolved_file,
                )
            # Remove old edge, add new edge
            if self.graph.has_edge(caller, old_callee):
                self.graph.remove_edge(caller, old_callee)
            self.graph.add_edge(caller, new_callee, type="call", resolved=True)

        # Remove orphaned "unknown" nodes
        orphaned = [
            n for n in list(self.graph.nodes)
            if self.graph.degree(n) == 0
        ]
        for n in orphaned:
            node_data = self.graph.nodes[n]
            if node_data.get("type") == "unknown":
                # Check if no edges reference it
                if self.graph.degree(n) == 0:
                    self.graph.remove_node(n)

    def _find_symbol_in_imports(
        self, symbol: str, from_file: str
    ) -> Optional[str]:
        """Find which file (imported by from_file) defines the given symbol.

        Uses the dependency graph to find imported files, then checks
        the symbol index for the symbol definition.

        Args:
            symbol: The function/method name to find.
            from_file: The file making the call.

        Returns:
            Resolved file path, or None.
        """
        if self._dep_graph is None or self._symbol_index is None:
            return None

        # Check global symbol index first
        locations = self._symbol_index.find(symbol)
        if locations:
            # Get the imported files by from_file
            imported = set()
            if from_file in self._dep_graph:
                imported = set(self._dep_graph.successors(from_file))

            # Prefer matches in imported files
            for loc in locations:
                loc_file = loc.split("::")[0]
                if loc_file in imported:
                    return loc_file

            # If no import match, return the first location if it's a different file
            for loc in locations:
                loc_file = loc.split("::")[0]
                if loc_file != from_file:
                    return loc_file

        return None

    # ── querying ────────────────────────────────────────────────

    @staticmethod
    def _node(file: str, symbol: str) -> str:
        """Create a canonical node identifier."""
        return f"{file}::{symbol}"

    @staticmethod
    def _parse_node(node_id: str) -> Tuple[str, str]:
        """Parse a node identifier back to (file, symbol)."""
        parts = node_id.split("::", 1)
        return parts[0], parts[1] if len(parts) > 1 else ""

    def get_callers(self, file: str, symbol: str) -> List[str]:
        """Get all functions/methods that call `symbol` in `file`.

        Includes cross-file callers when cross-file resolution was run.

        Returns:
            List of node IDs (file::symbol) that call the target.
        """
        node = self._node(file, symbol)
        if node not in self.graph:
            return []
        return list(self.graph.predecessors(node))

    def get_callees(self, file: str, symbol: str) -> List[str]:
        """Get all functions/methods called by `symbol` in `file`.

        Includes cross-file callees when cross-file resolution was run.

        Returns:
            List of node IDs (file::symbol) that the target calls.
        """
        node = self._node(file, symbol)
        if node not in self.graph:
            return []
        return list(self.graph.successors(node))

    def get_all_callers(self, file: str, symbol: str) -> Set[str]:
        """Get all transitive callers (the full call chain upward).

        "Who ultimately depends on this function?"
        """
        node = self._node(file, symbol)
        if node not in self.graph:
            return set()
        return set(nx.ancestors(self.graph, node))

    def get_all_callees(self, file: str, symbol: str) -> Set[str]:
        """Get all transitive callees (the full call chain downward).

        "What does this function ultimately invoke?"
        """
        node = self._node(file, symbol)
        if node not in self.graph:
            return set()
        return set(nx.descendants(self.graph, node))

    def get_functions_in_file(self, file: str) -> List[str]:
        """Get all function/method nodes defined in a file."""
        return [
            n for n in self.graph.nodes
            if n.startswith(f"{file}::")
        ]

    def get_affected_functions(
        self, seed_files: List[str]
    ) -> Dict[str, Set[str]]:
        """For each seed file, find all functions that would be affected.

        Returns:
            Dict mapping file → set of function node IDs that depend on it.
        """
        result: Dict[str, Set[str]] = {}
        for sf in seed_files:
            functions = self.get_functions_in_file(sf)
            affected: Set[str] = set()
            for func in functions:
                symbol = func.split("::")[-1]
                affected.update(self.get_all_callers(sf, symbol))
            result[sf] = affected
        return result

    def get_cross_file_callers(self, file: str, symbol: str) -> List[str]:
        """Get callers from OTHER files only (cross-file dependencies).

        This is the key metric for understanding the blast radius
        of a change to a specific function.
        """
        all_callers = self.get_callers(file, symbol)
        return [
            c for c in all_callers
            if c.split("::")[0] != file
        ]


class _CallVisitor(ast.NodeVisitor):
    """AST visitor that extracts call relationships."""

    def __init__(self, file_path: str, graph: nx.DiGraph):
        self.file = file_path
        self.graph = graph
        self._current_function: List[str] = []
        self._current_class: List[str] = []

    def _node_id(self, symbol: str) -> str:
        return f"{self.file}::{symbol}"

    def visit_FunctionDef(self, node: ast.FunctionDef):
        node_id = self._node_id(node.name)
        self.graph.add_node(node_id, type="function", name=node.name)
        self._current_function.append(node.name)
        self.generic_visit(node)
        self._current_function.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        node_id = self._node_id(node.name)
        self.graph.add_node(node_id, type="async_function", name=node.name)
        self._current_function.append(node.name)
        self.generic_visit(node)
        self._current_function.pop()

    def visit_ClassDef(self, node: ast.ClassDef):
        node_id = self._node_id(node.name)
        self.graph.add_node(node_id, type="class", name=node.name)
        self._current_class.append(node.name)
        self.generic_visit(node)
        self._current_class.pop()

    def visit_Call(self, node: ast.Call):
        """Record a call relationship if we're inside a function."""
        if not self._current_function:
            self.generic_visit(node)
            return

        caller = self._node_id(self._current_function[-1])
        callee_name = self._extract_call_name(node)

        if callee_name:
            # Store with same-file prefix initially — Phase 2 resolves cross-file
            callee = self._node_id(callee_name)
            if callee not in self.graph:
                self.graph.add_node(
                    callee,
                    type="function",
                    name=callee_name,
                    resolved=False,
                )
            self.graph.add_edge(caller, callee, type="call")

        self.generic_visit(node)

    def _extract_call_name(self, node: ast.Call) -> str | None:
        """Extract the function name from a Call AST node."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None
