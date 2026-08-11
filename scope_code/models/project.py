"""Project structure models — file tree, modules, symbols."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from enum import Enum


class FileType(str, Enum):
    """Classification of a file in the project."""
    SOURCE = "source"
    TEST = "test"
    CONFIG = "config"
    DOCS = "docs"
    OTHER = "other"


class FileNode(BaseModel):
    """A single file node with its metadata."""
    path: str
    name: str
    file_type: FileType = FileType.SOURCE
    language: str = "python"
    imports: List[str] = Field(default_factory=list)
    exports: List[str] = Field(default_factory=list)
    classes: List[str] = Field(default_factory=list)
    functions: List[str] = Field(default_factory=list)

    @property
    def symbols(self) -> List[str]:
        """All public symbols defined in this file."""
        return self.classes + self.functions + self.exports


class Module(BaseModel):
    """A logical module (package/directory) grouping related files."""
    name: str
    path: str
    files: List[FileNode] = Field(default_factory=list)
    submodules: List['Module'] = Field(default_factory=list)
    is_package: bool = False

    def all_files(self) -> List[FileNode]:
        """Recursively collect all files in this module and submodules."""
        result = list(self.files)
        for sub in self.submodules:
            result.extend(sub.all_files())
        return result


class ProjectStructure(BaseModel):
    """Complete project structure snapshot."""
    root_path: str
    name: str = ""
    modules: Dict[str, Module] = Field(default_factory=dict)
    files: Dict[str, FileNode] = Field(default_factory=dict)
    entry_points: List[str] = Field(default_factory=list)

    def get_module(self, name: str) -> Optional[Module]:
        """Find a module by name."""
        return self.modules.get(name)

    def get_file(self, path: str) -> Optional[FileNode]:
        """Find a file node by path (supports partial match)."""
        if path in self.files:
            return self.files[path]
        for fp, fn in self.files.items():
            if fp.endswith(path):
                return fn
        return None
