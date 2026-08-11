"""Project structure analyzer — walks the file tree and identifies modules.

This is a fully deterministic analyzer: no LLM calls, just filesystem
traversal and AST parsing. Supports Python (via ast) and other languages
(via MultiLangAnalyzer regex patterns).
"""

import ast
import os
from pathlib import Path
from typing import List, Set

from ..models.project import (
    ProjectStructure,
    Module,
    FileNode,
    FileType,
)

# File extensions considered "source" per language
SOURCE_EXTENSIONS = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
}

CONFIG_NAMES = {
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
    "package.json", "tsconfig.json", "go.mod", "Cargo.toml",
    "pom.xml", "build.gradle", "Makefile", "Dockerfile",
    ".env", ".env.example", "docker-compose.yml",
}

TEST_DIRS = {"tests", "test", "__tests__", "spec", "specs"}
DOCS_DIRS = {"docs", "doc", "documentation"}


class ProjectAnalyzer:
    """Analyzes project structure: files, modules, entry points.

    Walks the file tree, classifies files, and builds a
    ProjectStructure model. For Python projects, parses AST
    to extract imports, exports, classes, and functions.

    Usage:
        analyzer = ProjectAnalyzer()
        structure = analyzer.analyze("/path/to/project")
    """

    def __init__(
        self,
        ignore_dirs: Set[str] | None = None,
        max_depth: int = 20,
    ):
        self.ignore_dirs = ignore_dirs or {
            "__pycache__", ".git", ".svn", ".hg",
            "node_modules", ".venv", "venv", "env",
            ".tox", ".eggs", "build", "dist",
            ".idea", ".vscode", ".DS_Store",
            ".claude", ".mypy_cache", ".pytest_cache",
            "__pypackages__", ".ruff_cache",
        }
        self.max_depth = max_depth

    # ── public API ──────────────────────────────────────────────

    def analyze(self, root_path: str) -> ProjectStructure:
        """Run full project structure analysis.

        Args:
            root_path: Absolute or relative path to project root.

        Returns:
            Populated ProjectStructure model.
        """
        root = Path(root_path).resolve()
        if not root.exists():
            raise FileNotFoundError(f"Project root not found: {root}")
        if not root.is_dir():
            raise NotADirectoryError(f"Not a directory: {root}")

        structure = ProjectStructure(
            root_path=str(root),
            name=root.name,
        )

        self._walk(root, root, structure, depth=0)
        self._detect_entry_points(root, structure)
        return structure

    # ── internal ────────────────────────────────────────────────

    def _walk(
        self,
        base: Path,
        current: Path,
        structure: ProjectStructure,
        depth: int,
        parent_module: Module | None = None,
    ):
        """Recursively walk the directory tree."""
        if depth > self.max_depth:
            return

        entries = sorted(current.iterdir(), key=lambda e: (e.is_file(), e.name))
        module = Module(
            name=current.name,
            path=str(current),
            is_package=self._is_package(current),
        )

        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.name in self.ignore_dirs:
                continue

            if entry.is_dir():
                self._walk(base, entry, structure, depth + 1, module)
            elif entry.is_file():
                file_type = self._classify_file(entry)
                language = self._detect_language(entry)

                file_node = FileNode(
                    path=str(entry),
                    name=entry.name,
                    file_type=file_type,
                    language=language,
                )

                if file_type == FileType.SOURCE:
                    if language == "python":
                        self._parse_python_file(entry, file_node)
                    elif language in ("javascript", "typescript",
                                      "go", "rust", "java", "kotlin"):
                        from .multi_lang import MultiLangAnalyzer
                        MultiLangAnalyzer().analyze(file_node, entry)

                module.files.append(file_node)
                rel_path = str(entry.relative_to(base))
                structure.files[rel_path] = file_node

        if module.files or module.submodules:
            rel_name = str(current.relative_to(base)).replace(os.sep, ".")
            if rel_name == ".":
                rel_name = current.name
            structure.modules[rel_name] = module

    def _is_package(self, path: Path) -> bool:
        """Check if a directory is a Python package (has __init__.py)."""
        return (path / "__init__.py").exists()

    def _classify_file(self, path: Path) -> FileType:
        """Classify a file by type."""
        name = path.name.lower()
        suffix = path.suffix

        # Check test directories
        for part in path.parts:
            if part.lower() in TEST_DIRS:
                return FileType.TEST

        # Check docs directories
        for part in path.parts:
            if part.lower() in DOCS_DIRS:
                return FileType.DOCS

        # Config files
        if name in CONFIG_NAMES or suffix in {".toml", ".yaml", ".yml",
                                                ".cfg", ".ini", ".json"}:
            if suffix not in {".py", ".js", ".ts", ".go"}:
                return FileType.CONFIG

        # Documentation
        if suffix in {".md", ".rst", ".txt", ".pdf"}:
            return FileType.DOCS

        # Test files
        if name.startswith("test_") or name.endswith("_test.py"):
            return FileType.TEST

        # Source files
        if suffix in SOURCE_EXTENSIONS:
            return FileType.SOURCE

        return FileType.OTHER

    def _detect_language(self, path: Path) -> str:
        """Detect programming language from file extension."""
        return SOURCE_EXTENSIONS.get(path.suffix, "unknown")

    def _parse_python_file(self, path: Path, file_node: FileNode):
        """Extract imports, classes, functions from a Python file via AST."""
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        file_node.imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        file_node.imports.append(node.module)
                elif isinstance(node, ast.ClassDef):
                    file_node.classes.append(node.name)
                elif isinstance(node, ast.FunctionDef):
                    # Skip private functions for exports
                    if not node.name.startswith("_"):
                        file_node.exports.append(node.name)
                    file_node.functions.append(node.name)
                elif isinstance(node, ast.AsyncFunctionDef):
                    if not node.name.startswith("_"):
                        file_node.exports.append(node.name)
                    file_node.functions.append(node.name)

        except (SyntaxError, UnicodeDecodeError):
            pass  # Non-Python files or syntax errors — skip AST parse

    def _detect_entry_points(
        self, root: Path, structure: ProjectStructure
    ):
        """Detect project entry points (main scripts, app factories)."""
        candidates = [
            root / "main.py",
            root / "app.py",
            root / "manage.py",
            root / "run.py",
            root / "cli.py",
        ]
        for candidate in candidates:
            if candidate.exists():
                structure.entry_points.append(str(candidate))

        # Also check for __main__.py
        main_py = root / "__main__.py"
        if main_py.exists():
            structure.entry_points.append(str(main_py))
