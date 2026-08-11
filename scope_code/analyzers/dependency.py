"""Dependency analyzer — builds import dependency graphs.

Supports Python (via ast) and JavaScript/TypeScript (via regex import
resolution). The graph is language-agnostic: nodes are file paths,
edges represent import relationships.
"""

import ast
from pathlib import Path
from typing import Dict, List, Set, Tuple

import networkx as nx

from ..models.project import ProjectStructure, FileNode

# Languages that support dependency analysis
SUPPORTED_LANGUAGES = {
    "python", "javascript", "typescript", "go", "rust", "java", "kotlin"
}

# JS/TS extensions to try when resolving bare imports
JS_EXTENSIONS = (".js", ".jsx", ".ts", ".tsx", "/index.js",
                 "/index.ts", "/index.jsx", "/index.tsx")

# Go standard library packages (not project files)
GO_STDLIB = {
    "fmt", "net", "net/http", "os", "io", "strings", "strconv",
    "time", "sync", "context", "errors", "log", "encoding/json",
    "bytes", "bufio", "crypto", "math", "sort", "path", "reflect",
    "regexp", "runtime", "testing", "unicode", "database/sql",
}
GO_STDLIB_PREFIXES = ("golang.org", "google.golang.org", "github.com")


class DependencyAnalyzer:
    """Builds and queries the import dependency graph of a project.

    The graph is a directed graph where:
        - Nodes are file paths (relative to project root)
        - Edges A → B mean "file A imports file/module B"

    Supports: Python (.py), JavaScript (.js/.jsx), TypeScript (.ts/.tsx)

    Usage:
        dep_analyzer = DependencyAnalyzer()
        graph = dep_analyzer.build(structure)

        # Who depends on auth.py?
        dependents = dep_analyzer.get_dependents("src/auth.py")
    """

    def __init__(self):
        self.graph: nx.DiGraph = nx.DiGraph()
        self._module_to_files: Dict[str, List[str]] = {}
        self._path_index: Dict[str, str] = {}  # bare name → resolved path

    # ── building ────────────────────────────────────────────────

    def build(self, structure: ProjectStructure) -> nx.DiGraph:
        """Build the dependency graph from a project structure.

        Args:
            structure: Populated ProjectStructure from ProjectAnalyzer.

        Returns:
            A networkx DiGraph where edges represent imports.
        """
        self.graph = nx.DiGraph()
        self._module_to_files = self._build_module_index(structure)
        self._path_index = self._build_path_index(structure)

        # Add all source files as nodes (Python + JS/TS)
        for rel_path, file_node in structure.files.items():
            if file_node.language in SUPPORTED_LANGUAGES:
                self.graph.add_node(
                    rel_path,
                    name=file_node.name,
                    language=file_node.language,
                    exports=file_node.exports,
                    classes=file_node.classes,
                    functions=file_node.functions,
                )

        # Add edges for imports (dispatch by language)
        for rel_path, file_node in structure.files.items():
            lang = file_node.language
            if lang not in SUPPORTED_LANGUAGES:
                continue
            for imp in file_node.imports:
                resolved = self._resolve_import_by_lang(
                    imp, rel_path, lang, structure
                )
                if resolved and resolved != rel_path:
                    self.graph.add_edge(
                        rel_path, resolved, import_name=imp
                    )

        return self.graph

    # ── import resolution dispatcher ─────────────────────────

    def _resolve_import_by_lang(
        self,
        import_name: str,
        from_file: str,
        language: str,
        structure: ProjectStructure,
    ) -> str | None:
        """Dispatch import resolution to the appropriate language handler."""
        if language == "python":
            return self._resolve_python_import(import_name, from_file, structure)
        elif language in ("javascript", "typescript"):
            return self._resolve_js_import(import_name, from_file, structure)
        elif language == "go":
            return self._resolve_go_import(import_name, from_file, structure)
        elif language == "rust":
            return self._resolve_rust_import(import_name, from_file, structure)
        elif language in ("java", "kotlin"):
            return self._resolve_java_import(import_name, from_file, structure)
        return None

    # ── module index ────────────────────────────────────────────

    def _build_module_index(
        self, structure: ProjectStructure
    ) -> Dict[str, List[str]]:
        """Build a map of module name → list of file paths."""
        index: Dict[str, List[str]] = {}
        for rel_path, file_node in structure.files.items():
            if file_node.language not in SUPPORTED_LANGUAGES:
                continue
            if file_node.language == "python":
                module_name = self._path_to_python_module(rel_path)
            elif file_node.language in ("javascript", "typescript"):
                module_name = self._path_to_js_module(rel_path)
            elif file_node.language == "go":
                module_name = self._path_to_go_module(rel_path)
            elif file_node.language == "rust":
                module_name = self._path_to_rust_module(rel_path)
            else:
                # Java/Kotlin: use path without extension
                module_name = Path(rel_path).as_posix()
                for ext in (".java", ".kt"):
                    if module_name.endswith(ext):
                        module_name = module_name[:-len(ext)]
                        break
                module_name = module_name.replace("/", ".")
            index.setdefault(module_name, []).append(rel_path)
        return index

    def _build_path_index(
        self, structure: ProjectStructure
    ) -> Dict[str, str]:
        """Build a bare-name → relative-path index for JS/TS resolution.

        All keys are normalized to forward slashes for cross-platform matching.
        """
        idx: Dict[str, str] = {}
        for rel_path, file_node in structure.files.items():
            if file_node.language not in SUPPORTED_LANGUAGES:
                continue
            rel_norm = rel_path.replace("\\", "/")
            # Index by filename without extension
            stem = Path(rel_norm).stem
            if stem not in idx:
                idx[stem] = rel_path
            # Index by full path without extension (forward-slash normalized)
            no_ext = Path(rel_norm).as_posix()
            no_ext = no_ext.rsplit(".", 1)[0] if "." in no_ext.split("/")[-1] else no_ext
            idx[no_ext] = rel_path
            # Also index with original path
            idx[rel_norm] = rel_path
        return idx

    # ── Python import resolution ────────────────────────────────

    def _resolve_python_import(
        self,
        import_name: str,
        from_file: str,
        structure: ProjectStructure,
    ) -> str | None:
        """Resolve a Python import to a concrete file path."""
        # Exact module match
        if import_name in self._module_to_files:
            return self._module_to_files[import_name][0]

        # Relative import (starts with dots)
        if import_name.startswith("."):
            return self._resolve_relative_python_import(
                import_name, from_file
            )

        # Partial match
        for module_name, files in self._module_to_files.items():
            if module_name == import_name or module_name.endswith(
                f".{import_name}"
            ):
                return files[0]
            if module_name.split(".")[-1] == import_name.split(".")[-1]:
                return files[0]

        return None

    def _resolve_relative_python_import(
        self, import_name: str, from_file: str
    ) -> str | None:
        """Resolve a Python relative import (starting with dots)."""
        dots = 0
        while dots < len(import_name) and import_name[dots] == ".":
            dots += 1
        remaining = import_name[dots:]

        from_dir = str(Path(from_file).parent)
        if from_dir == ".":
            from_dir = ""

        parts = from_dir.split("/") if from_dir else []
        if dots > len(parts):
            return None
        base_parts = parts[: len(parts) - dots + 1] if dots > 1 else parts
        if remaining:
            base_parts = list(base_parts) + remaining.split(".")
        resolved_module = ".".join(base_parts)

        if resolved_module in self._module_to_files:
            return self._module_to_files[resolved_module][0]
        return None

    # ── JS/TS import resolution ─────────────────────────────────

    def _resolve_js_import(
        self,
        import_name: str,
        from_file: str,
        structure: ProjectStructure,
    ) -> str | None:
        """Resolve a JS/TS import to a concrete file path.

        Handles:
            - './foo' → relative to importing file
            - '../bar' → relative to importing file
            - 'react' → external (node_modules), skip
            - '@/foo' → path alias (check path index)
        """
        # External package (no path prefix) — skip
        if not import_name.startswith(".") and "/" not in import_name:
            # Could be a path alias like @/ or ~/
            if import_name.startswith("@") or import_name.startswith("~"):
                pass  # Try to resolve below
            else:
                return None  # External package

        from_dir = Path(from_file).parent

        if import_name.startswith("."):
            # Relative import: './foo' or '../bar'
            # Use as_posix() for forward-slash normalization
            joined = (from_dir / import_name).as_posix()
            # Normalize: resolve '..' segments
            resolved_path = Path(joined).as_posix()
        else:
            # Absolute-ish import: 'src/foo' or '@/foo'
            clean = import_name.lstrip("@/").lstrip("~/")
            resolved_path = clean.replace("\\", "/")

        # Try exact match
        if resolved_path in self._path_index:
            return self._path_index[resolved_path]

        # Try with extensions
        for ext in JS_EXTENSIONS:
            candidate = resolved_path + ext
            if candidate in self._path_index:
                return self._path_index[candidate]

        # Try the bare filename
        stem = Path(resolved_path).stem
        if stem in self._path_index:
            return self._path_index[stem]

        # Try as prefix match
        for path_key, file_path in self._path_index.items():
            if path_key.endswith(resolved_path):
                return file_path
            if path_key.endswith("/" + resolved_path):
                return file_path

        return None

    # ── Go import resolution ──────────────────────────────────

    def _resolve_go_import(
        self,
        import_name: str,
        from_file: str,
        structure: ProjectStructure,
    ) -> str | None:
        """Resolve a Go import path to a project file.

        Go imports are package paths like:
            - "myproject/internal/auth" → internal project package
            - "fmt" → standard library (skip)
            - "github.com/foo/bar" → external (skip)

        Resolution: find directory containing .go files with matching
        package name, or match the path suffix.
        """
        # Skip standard library
        if import_name in GO_STDLIB:
            return None

        # Skip external packages
        for prefix in GO_STDLIB_PREFIXES:
            if import_name.startswith(prefix):
                return None

        # Look for matching directory in project
        # The import path "myproject/internal/auth" might map to
        # "internal/auth/" directory
        import_parts = import_name.split("/")

        # Try matching the last N parts against project paths
        for n in range(len(import_parts), 0, -1):
            suffix = "/".join(import_parts[-n:])
            for file_path in self._path_index:
                norm_path = file_path.replace("\\", "/")
                if norm_path.endswith("/" + suffix) or norm_path == suffix:
                    # Found a directory — look for .go files in it
                    for fp in structure.files:
                        fp_norm = fp.replace("\\", "/")
                        if fp_norm.startswith(norm_path + "/") and fp_norm.endswith(".go"):
                            return fp
                    # If no .go file found, try the first file in the directory
                    for fp in structure.files:
                        fp_norm = fp.replace("\\", "/")
                        if fp_norm.startswith(norm_path + "/"):
                            return fp

        return None

    # ── Rust import resolution ────────────────────────────────

    def _resolve_rust_import(
        self,
        import_name: str,
        from_file: str,
        structure: ProjectStructure,
    ) -> str | None:
        """Resolve a Rust `use` import to a project file.

        Rust imports like:
            - "crate::auth::AuthService" → src/auth.rs or src/auth/mod.rs
            - "std::collections::HashMap" → standard library (skip)
            - "super::utils" → parent module
        """
        # Skip standard library
        if import_name.startswith("std::") or import_name.startswith("std:"):
            return None

        # Skip external crates
        if not import_name.startswith("crate::") and not import_name.startswith("super::") and not import_name.startswith("self::"):
            # Could be an external crate — check if first segment matches a known project module
            first = import_name.split("::")[0]
            if first not in self._path_index:
                return None  # Probably external

        # Convert to path: crate::auth::service → auth/service
        if import_name.startswith("crate::"):
            path = import_name[7:].replace("::", "/")
        elif import_name.startswith("super::"):
            # Relative to parent
            from_dir = str(Path(from_file).parent)
            parent = str(Path(from_dir).parent) if "/" in from_dir else ""
            path = (Path(parent) / import_name[7:].replace("::", "/")).as_posix()
        else:
            path = import_name.replace("::", "/")

        # Try with .rs extension
        for suffix in [".rs", "/mod.rs"]:
            candidate = path + suffix
            norm = candidate.replace("\\", "/")
            if norm in self._path_index:
                return self._path_index[norm]
            # Try matching end of paths
            for file_path in structure.files:
                if file_path.endswith(norm) or file_path.replace("\\", "/").endswith(norm):
                    return file_path

        return None

    # ── Java/Kotlin import resolution ─────────────────────────

    def _resolve_java_import(
        self,
        import_name: str,
        from_file: str,
        structure: ProjectStructure,
    ) -> str | None:
        """Resolve a Java/Kotlin import to a project file.

        Java imports like:
            - "com.example.auth.AuthService" → AuthService.java
            - "java.util.List" → standard library (skip)
            - "com.example.auth.*" → wildcard

        Resolution: match the class name suffix against project files.
        """
        # Skip standard library
        if import_name.startswith("java.") or import_name.startswith("javax."):
            return None

        # Wildcard imports — match the package to a directory
        if import_name.endswith(".*"):
            pkg = import_name[:-2]
            pkg_path = pkg.replace(".", "/")
            for fp in structure.files:
                if pkg_path in fp.replace("\\", "/"):
                    return fp
            return None

        # Fully qualified class name
        parts = import_name.split(".")
        class_name = parts[-1]

        # Try matching class name against files
        for fp, file_node in structure.files.items():
            stem = Path(fp).stem
            if stem == class_name:
                return fp

        # Try matching the package path
        pkg_path = "/".join(parts[:-1])
        for fp in structure.files:
            if pkg_path in fp.replace("\\", "/"):
                stem = Path(fp).stem
                if stem.lower() == class_name.lower():
                    return fp

        return None

    # ── path-to-module helpers ──────────────────────────────────

    @staticmethod
    def _path_to_python_module(path: str) -> str:
        """Convert a file path to Python module notation."""
        if path.endswith(".py"):
            path = path[:-3]
        if path.endswith("__init__"):
            path = path.rsplit("/", 1)[0] if "/" in path else ""
        return path.replace("/", ".").replace("\\", ".")

    @staticmethod
    def _path_to_js_module(path: str) -> str:
        """Convert a file path to JS module notation (strip extension)."""
        for ext in (".js", ".jsx", ".ts", ".tsx"):
            if path.endswith(ext):
                path = path[:-len(ext)]
                break
        return path.replace("/", ".").replace("\\", ".")

    @staticmethod
    def _path_to_go_module(path: str) -> str:
        """Convert a Go file path to import path notation."""
        if path.endswith(".go"):
            path = path[:-3]
        # Directory of the file is the package
        parent = str(Path(path).parent)
        if parent == ".":
            parent = path
        return parent.replace("/", ".").replace("\\", ".")

    @staticmethod
    def _path_to_rust_module(path: str) -> str:
        """Convert a Rust file path to module path notation."""
        if path.endswith(".rs"):
            path = path[:-3]
        # mod.rs → parent directory
        if path.endswith("/mod") or path.endswith("\\mod"):
            path = str(Path(path).parent)
        return path.replace("/", "::").replace("\\", "::")

    # ── querying ────────────────────────────────────────────────

    def get_dependencies(self, file_path: str) -> List[str]:
        """Get all files that `file_path` depends on (direct)."""
        if file_path not in self.graph:
            return []
        return list(self.graph.successors(file_path))

    def get_dependents(self, file_path: str) -> List[str]:
        """Get all files that depend on `file_path` (direct)."""
        if file_path not in self.graph:
            return []
        return list(self.graph.predecessors(file_path))

    def get_all_dependencies(self, file_path: str) -> Set[str]:
        """Get all transitive dependencies (full closure reachable via imports)."""
        if file_path not in self.graph:
            return set()
        return set(nx.descendants(self.graph, file_path))

    def get_all_dependents(self, file_path: str) -> Set[str]:
        """Get all transitive dependents (full closure that imports this file)."""
        if file_path not in self.graph:
            return set()
        return set(nx.ancestors(self.graph, file_path))

    def get_impact_scope(
        self, seed_files: List[str]
    ) -> Tuple[Set[str], Set[str]]:
        """Calculate the impact scope for a set of seed files.

        Args:
            seed_files: Files identified as directly changed.

        Returns:
            (direct_scope, transitive_scope) — two sets of file paths.
        """
        direct = set(seed_files)
        transitive: Set[str] = set()

        for sf in seed_files:
            transitive.update(self.get_all_dependents(sf))
            transitive.update(self.get_all_dependencies(sf))

        transitive -= direct
        return direct, transitive

    def find_unrelated_modules(
        self, seed_files: List[str], structure: ProjectStructure
    ) -> Set[str]:
        """Find modules that have NO connection to the seed files.

        These are candidates for must_not_modify.
        """
        related_files: Set[str] = set(seed_files)
        for sf in seed_files:
            related_files.update(self.get_all_dependencies(sf))
            related_files.update(self.get_all_dependents(sf))

        # Normalize all related files to forward-slash relative paths
        root = str(structure.root_path)
        related_normalized: Set[str] = set()
        for f in related_files:
            f = f.replace("\\", "/")
            # Strip root prefix if present (absolute → relative)
            root_norm = root.replace("\\", "/")
            if f.startswith(root_norm):
                f = f[len(root_norm):].lstrip("/")
            related_normalized.add(f)

        unrelated = set()
        for module_name in structure.modules:
            module = structure.modules[module_name]
            module_relative: Set[str] = set()
            for fn in module.all_files():
                # fn.path may be absolute or relative — normalize to relative
                p = fn.path.replace("\\", "/")
                if p.startswith(root_norm):
                    p = p[len(root_norm):].lstrip("/")
                module_relative.add(p)

            if not (module_relative & related_normalized):
                unrelated.add(module_name)

        return unrelated
