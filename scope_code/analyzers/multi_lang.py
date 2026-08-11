"""Multi-language analyzer — extract symbols and imports from non-Python code.

Uses regex-based patterns for common languages. Falls back gracefully
when tree-sitter is not available.

Supported languages:
    - JavaScript / TypeScript (.js, .jsx, .ts, .tsx)
    - Go (.go)
    - Rust (.rs)
    - Java (.java)
    - Kotlin (.kt)

The ProjectAnalyzer uses this as a fallback when the file is not Python.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..models.project import FileNode


# ── Language-specific regex patterns ─────────────────────────────

# Each language defines patterns for:
#   imports: what this file imports from elsewhere
#   exports: what this file makes available (functions, classes)
#   functions: function/method definitions
#   classes: class/struct/interface definitions


LANGUAGE_PATTERNS: Dict[str, Dict[str, str]] = {
    "javascript": {
        "imports": [
            # import x from 'y'
            r'''from\s+['"]([^'"]+)['"]''',
            # import 'y'
            r'''import\s+['"]([^'"]+)['"]''',
            # require('y')
            r'''require\s*\(\s*['"]([^'"]+)['"]\s*\)''',
            # import { x } from 'y'
            r'''import\s+.*?\s*from\s*['"]([^'"]+)['"]''',
        ],
        "exports": [
            # export function foo
            r'export\s+(?:async\s+)?function\s+(\w+)',
            # export const foo
            r'export\s+(?:const|let|var)\s+(\w+)',
            # export default function foo
            r'export\s+default\s+(?:async\s+)?function\s+(\w+)',
            # export default class Foo
            r'export\s+default\s+class\s+(\w+)',
            # export default Foo (variable reference)
            r'export\s+default\s+(\w+)',
            # export class Foo
            r'export\s+class\s+(\w+)',
            # module.exports = Foo
            r'module\.exports\s*=\s*(\w+)',
            # exports.foo =
            r'exports\.(\w+)\s*=',
        ],
        "functions": [
            r'(?:async\s+)?function\s+(\w+)\s*\(',
            r'(\w+)\s*[:=]\s*(?:async\s+)?(?:function\s*)?\(',
            r'(\w+)\s*=\s*\([^)]*\)\s*=>',
        ],
        "classes": [
            r'class\s+(\w+)',
        ],
    },
    "typescript": {
        "imports": [
            r'''from\s+['"]([^'"]+)['"]''',
            r'''import\s+['"]([^'"]+)['"]''',
            r'''import\s+.*?\s*from\s*['"]([^'"]+)['"]''',
        ],
        "exports": [
            r'export\s+(?:async\s+)?function\s+(\w+)',
            r'export\s+(?:const|let|var)\s+(\w+)',
            r'export\s+(?:interface|type)\s+(\w+)',
            r'export\s+class\s+(\w+)',
            r'export\s+default\s+(?:async\s+)?function\s+(\w+)',
            r'export\s+default\s+class\s+(\w+)',
        ],
        "functions": [
            r'(?:async\s+)?function\s+(\w+)',
            r'(?:public\s+|private\s+|protected\s+)?(?:async\s+)?(\w+)\s*\([^)]*\)\s*:\s*\w+\s*{',
            r'(\w+)\s*=\s*\([^)]*\)\s*=>',
        ],
        "classes": [
            r'class\s+(\w+)',
            r'interface\s+(\w+)',
        ],
    },
    "go": {
        "imports": [
            # import "package"
            r'''import\s+['"]([^'"]+)['"]''',
            # import ( "a" \n "b" )
            r'''import\s*\(\s*((?:[^)]*?['"][^'"]+['"][^)]*?)*)\s*\)''',
        ],
        "exports": [
            # func Foo (exported = starts with uppercase)
            r'func\s+([A-Z]\w*)\s*\(',
            # type Foo struct
            r'type\s+([A-Z]\w*)\s+struct',
            # type Foo interface
            r'type\s+([A-Z]\w*)\s+interface',
            # var Foo
            r'var\s+([A-Z]\w*)',
        ],
        "functions": [
            r'func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(',
        ],
        "classes": [
            r'type\s+(\w+)\s+struct',
            r'type\s+(\w+)\s+interface',
        ],
    },
    "rust": {
        "imports": [
            # use crate::module;
            r'use\s+([\w:]+)\s*;',
            # use crate::module::{A, B};
            r'use\s+([\w:]+)::',
            # extern crate foo;
            r'extern\s+crate\s+(\w+)',
        ],
        "exports": [
            # pub fn foo
            r'pub\s+(?:async\s+)?fn\s+(\w+)',
            # pub struct Foo
            r'pub\s+struct\s+(\w+)',
            # pub enum Foo
            r'pub\s+enum\s+(\w+)',
            # pub trait Foo
            r'pub\s+trait\s+(\w+)',
            # pub mod foo
            r'pub\s+mod\s+(\w+)',
            # pub type Foo
            r'pub\s+type\s+(\w+)',
        ],
        "functions": [
            r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)',
        ],
        "classes": [
            r'(?:pub\s+)?struct\s+(\w+)',
            r'(?:pub\s+)?enum\s+(\w+)',
            r'(?:pub\s+)?trait\s+(\w+)',
        ],
    },
    "java": {
        "imports": [
            r'import\s+([\w.]+)',
        ],
        "exports": [
            # public class Foo
            r'public\s+class\s+(\w+)',
            # public interface Foo
            r'public\s+interface\s+(\w+)',
            # public static void foo
            r'public\s+(?:static\s+)?(?:\w+\s+)+(\w+)\s*\(',
        ],
        "functions": [
            r'(?:public|private|protected)?\s*(?:static\s+)?(?:\w+\s+)+(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+)?\s*\{',
        ],
        "classes": [
            r'(?:public\s+)?class\s+(\w+)',
            r'(?:public\s+)?interface\s+(\w+)',
            r'(?:public\s+)?enum\s+(\w+)',
        ],
    },
    "kotlin": {
        "imports": [
            r'import\s+([\w.]+)',
        ],
        "exports": [
            # fun foo
            r'fun\s+(\w+)\s*\(',
            # class Foo
            r'(?:data\s+)?class\s+(\w+)',
            # object Foo
            r'object\s+(\w+)',
            # interface Foo
            r'interface\s+(\w+)',
        ],
        "functions": [
            r'(?:suspend\s+)?fun\s+(\w+)\s*\(',
            r'val\s+(\w+)\s*=\s*\{[^}]*\}',
        ],
        "classes": [
            r'(?:data\s+)?class\s+(\w+)',
            r'object\s+(\w+)',
            r'interface\s+(\w+)',
        ],
    },
}


class MultiLangAnalyzer:
    """Analyze non-Python source files for symbols and imports.

    Uses regex patterns for each language. Provides a unified
    interface that mirrors Python's ast-based analysis.

    Usage:
        analyzer = MultiLangAnalyzer()
        analyzer.analyze(file_node, file_path)
    """

    def analyze(self, file_node: FileNode, file_path: Path) -> None:
        """Analyze a single file and populate the FileNode's metadata.

        Args:
            file_node: The FileNode to populate (mutated in-place).
            file_path: Path to the actual file on disk.
        """
        language = file_node.language
        if language not in LANGUAGE_PATTERNS:
            return

        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return

        patterns = LANGUAGE_PATTERNS[language]
        lines = source.split("\n")

        # Extract imports (deduplicated)
        imports = set()
        for pattern in patterns.get("imports", []):
            for match in re.finditer(pattern, source, re.MULTILINE):
                imports.add(match.group(1))
        file_node.imports = list(imports)

        # Extract exports
        exports = set()
        for pattern in patterns.get("exports", []):
            for match in re.finditer(pattern, source, re.MULTILINE):
                name = match.group(1)
                if self._is_valid_symbol(name):
                    exports.add(name)
        file_node.exports = list(exports)

        # Extract functions
        funcs = set()
        for pattern in patterns.get("functions", []):
            for match in re.finditer(pattern, source, re.MULTILINE):
                name = match.group(1)
                if self._is_valid_symbol(name):
                    funcs.add(name)
        file_node.functions = list(funcs)

        # Extract classes
        classes = set()
        for pattern in patterns.get("classes", []):
            for match in re.finditer(pattern, source, re.MULTILINE):
                name = match.group(1)
                if self._is_valid_symbol(name):
                    classes.add(name)
        file_node.classes = list(classes)

    # ── Go-specific: multi-line import blocks ──────────────────

    def _extract_go_multiline_imports(self, source: str) -> List[str]:
        """Extract imports from Go multi-line import blocks."""
        imports = []
        block_match = re.search(
            r'import\s*\(\s*(.*?)\s*\)', source, re.DOTALL
        )
        if block_match:
            block = block_match.group(1)
            for match in re.finditer(r'''['"]([^'"]+)['"]''', block):
                imports.append(match.group(1))
        return imports

    # ── utilities ──────────────────────────────────────────────

    @staticmethod
    def _is_valid_symbol(name: str) -> bool:
        """Check if a name looks like a valid code symbol."""
        if not name:
            return False
        if len(name) < 1 or len(name) > 100:
            return False
        # Exclude keywords
        keywords = {
            'if', 'else', 'for', 'while', 'return', 'break', 'continue',
            'switch', 'case', 'default', 'throw', 'try', 'catch', 'finally',
            'new', 'delete', 'typeof', 'instanceof', 'in', 'of',
            'async', 'await', 'yield', 'static', 'public', 'private',
            'protected', 'abstract', 'final', 'void', 'int', 'string',
            'bool', 'true', 'false', 'null', 'undefined', 'let', 'var',
            'const', 'function', 'import', 'export', 'from', 'as',
            'i', 'j', 'k', 'x', 'y', 'z', 'n', 's', 'v', 'e', 'err',
        }
        return name not in keywords


def get_available_languages() -> List[str]:
    """Return list of languages with regex-based analysis support."""
    return sorted(LANGUAGE_PATTERNS.keys())
