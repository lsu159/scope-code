"""Symbol index — maps symbol names to their file locations.

A fast lookup structure that answers: "Where is the User model defined?"
or "Which file contains the login() function?"
"""

import ast
from pathlib import Path
from typing import Dict, List, Optional

from ..models.project import ProjectStructure


class SymbolIndex:
    """Inverted index from symbol names to file locations.

    Built from ProjectStructure — no re-parsing of files needed
    if ProjectAnalyzer already extracted classes and functions.

    Usage:
        index = SymbolIndex()
        index.build(structure)

        # Find where a symbol is defined
        locations = index.find("login")
        # → ["src/auth/service.py::login", "src/api/views.py::login"]
    """

    def __init__(self):
        # symbol_name → [(file_path, symbol_type), ...]
        self._index: Dict[str, List[tuple]] = {}

    # ── building ────────────────────────────────────────────────

    def build(self, structure: ProjectStructure) -> "SymbolIndex":
        """Build the symbol index from a project structure.

        Args:
            structure: Populated ProjectStructure.

        Returns:
            Self for chaining.
        """
        self._index.clear()

        for rel_path, file_node in structure.files.items():
            if file_node.language != "python":
                continue

            for cls in file_node.classes:
                self._add(rel_path, cls, "class")

            for func in file_node.functions:
                self._add(rel_path, func, "function")

            for exp in file_node.exports:
                # exports may overlap with functions; avoid duplicates
                if exp not in file_node.functions:
                    self._add(rel_path, exp, "export")

        return self

    def _add(self, file_path: str, symbol: str, symbol_type: str):
        """Add a symbol to the index."""
        entry = (file_path, symbol_type)
        if symbol not in self._index:
            self._index[symbol] = []
        # Avoid exact duplicates
        if entry not in self._index[symbol]:
            self._index[symbol].append(entry)

    # ── querying ────────────────────────────────────────────────

    def find(self, name: str) -> List[str]:
        """Find all files defining a symbol.

        Case-insensitive match.

        Args:
            name: Symbol name (class, function, or export).

        Returns:
            List of "file_path::type" strings.
        """
        # Try exact match first
        if name in self._index:
            return [f"{f}::{t}" for f, t in self._index[name]]
        # Case-insensitive fallback
        name_lower = name.lower()
        for symbol, entries in self._index.items():
            if symbol.lower() == name_lower:
                return [f"{f}::{t}" for f, t in entries]
        return []

    def find_exact(
        self, name: str, symbol_type: Optional[str] = None
    ) -> List[str]:
        """Find symbols, optionally filtering by type.

        Args:
            name: Symbol name.
            symbol_type: Filter by 'class', 'function', or 'export'.

        Returns:
            Filtered list of "file_path::type".
        """
        results = self.find(name)
        if symbol_type:
            results = [r for r in results if r.endswith(f"::{symbol_type}")]
        return results

    def search(self, query: str) -> List[str]:
        """Fuzzy search for symbols containing the query string.

        Case-insensitive partial match.

        Args:
            query: Search substring.

        Returns:
            List of "file_path::symbol::type" strings.
        """
        results = []
        query_lower = query.lower()
        for symbol, entries in self._index.items():
            if query_lower in symbol.lower():
                for file_path, stype in entries:
                    results.append(f"{file_path}::{symbol}::{stype}")
        return sorted(results)

    def search_by_file_prefix(self, prefix: str) -> Dict[str, List[str]]:
        """Get all symbols in files whose path starts with a prefix.

        Args:
            prefix: File path prefix (e.g., 'src/auth/').

        Returns:
            Dict mapping file → list of symbols.
        """
        result: Dict[str, List[str]] = {}
        for symbol, entries in self._index.items():
            for file_path, _ in entries:
                if file_path.startswith(prefix):
                    result.setdefault(file_path, []).append(symbol)
        return result

    @property
    def total_symbols(self) -> int:
        """Total number of unique symbols indexed."""
        return len(self._index)

    @property
    def all_symbols(self) -> List[str]:
        """List all indexed symbol names."""
        return sorted(self._index.keys())

    def symbols_in_file(self, file_path: str) -> List[str]:
        """Get all symbols defined in a specific file."""
        result = []
        for symbol, entries in self._index.items():
            for fp, _ in entries:
                if fp == file_path:
                    result.append(symbol)
                    break
        return sorted(result)
