"""Modification scope models — what must change, what must not."""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Literal


class FileChange(BaseModel):
    """A single file change entry with rationale."""
    file_path: str
    change_type: Literal["modify", "add", "delete"]
    reason: str
    section: Optional[str] = None

    def format(self) -> str:
        """Human-readable single-line summary."""
        section_info = f" ({self.section})" if self.section else ""
        return f"[{self.change_type}] {self.file_path}{section_info}: {self.reason}"


class ModificationScope(BaseModel):
    """Defines the boundary of a code change.

    This is the core output of the scope inference engine:
        - must_modify: files that MUST be changed (evidence-backed)
        - should_modify: files that MAY benefit from changes (suggestions)
        - must_not_modify: glob patterns that MUST NOT be touched (risk boundary)
        - must_not_modify_reasons: reason for each must_not_modify entry
        - no_change: files analyzed and confirmed to need no changes
    """

    must_modify: List[FileChange] = Field(default_factory=list)
    should_modify: List[FileChange] = Field(default_factory=list)
    must_not_modify: List[str] = Field(default_factory=list)
    must_not_modify_reasons: Dict[str, str] = Field(default_factory=dict)
    no_change: List[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True if no changes are required at all."""
        return len(self.must_modify) == 0 and len(self.should_modify) == 0

    @property
    def total_modifications(self) -> int:
        """Total number of files that will be modified."""
        return len(self.must_modify) + len(self.should_modify)

    def respects_boundary(self, modified_files: List[str]) -> bool:
        """Check if actual modifications respect the scope boundary.

        Supports glob patterns in must_not_modify (e.g., 'payment/*',
        'src/chat/**').

        Args:
            modified_files: List of files that were actually modified.

        Returns:
            True if no must_not_modify file was touched.
        """
        return len(self.find_violations(modified_files)) == 0

    def find_violations(self, modified_files: List[str]) -> List[str]:
        """Return which files violated the scope boundary.

        Supports glob patterns like 'payment/*' or 'src/chat/**'.
        Strips embedded reasons (legacy format) from patterns before matching.
        """
        import fnmatch, re
        violations = []
        for mf in modified_files:
            for forbidden in self.must_not_modify:
                # Strip any embedded reason like "path/* (reason text)"
                pattern = re.sub(r'\s*\(.*\)\s*$', '', forbidden).strip()
                if fnmatch.fnmatch(mf, pattern):
                    violations.append(mf)
                    break
        return violations
