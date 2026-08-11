"""Tests for JS/TS dependency resolution and git diff verification."""

import pytest
import tempfile
from pathlib import Path


# ── JS/TS dependency resolution tests ────────────────────────────

@pytest.mark.asyncio
async def test_js_relative_import_resolution():
    """Test that JS relative imports are resolved correctly."""
    import tempfile
    from scope_code.analyzers.project import ProjectAnalyzer
    from scope_code.analyzers.dependency import DependencyAnalyzer

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        src = root / "src"
        src.mkdir()

        # Create two JS files with import relationship
        (src / "login.js").write_text('''
import { validate } from './validate';
export function login(user, pass) { return validate(user); }
''')
        (src / "validate.js").write_text('''
export function validate(user) { return user != null; }
''')

        analyzer = ProjectAnalyzer()
        structure = analyzer.analyze(str(root))

        dep = DependencyAnalyzer()
        graph = dep.build(structure)

        # login.js should depend on validate.js
        login_path = None
        validate_path = None
        for rel_path in structure.files:
            if rel_path.endswith("login.js"):
                login_path = rel_path
            if rel_path.endswith("validate.js"):
                validate_path = rel_path

        assert login_path is not None
        assert validate_path is not None

        deps = dep.get_dependencies(login_path)
        assert validate_path in deps, (
            f"login.js should depend on validate.js, got deps: {deps}"
        )

        # Reverse: validate.js should have login.js as dependent
        dependents = dep.get_dependents(validate_path)
        assert login_path in dependents


@pytest.mark.asyncio
async def test_ts_deep_import_resolution():
    """Test TypeScript nested import resolution."""
    import tempfile
    from scope_code.analyzers.project import ProjectAnalyzer
    from scope_code.analyzers.dependency import DependencyAnalyzer

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        src = root / "src"
        auth = src / "auth"
        auth.mkdir(parents=True)

        (src / "app.ts").write_text('''
import { AuthService } from './auth/service';
const auth = new AuthService();
''')
        (auth / "service.ts").write_text('''
export class AuthService {
    login() { return true; }
}
''')

        analyzer = ProjectAnalyzer()
        structure = analyzer.analyze(str(root))

        dep = DependencyAnalyzer()
        dep.build(structure)

        app_path = None
        service_path = None
        for rel_path in structure.files:
            if rel_path.endswith("app.ts"):
                app_path = rel_path
            if rel_path.endswith("service.ts"):
                service_path = rel_path

        assert app_path is not None
        assert service_path is not None

        deps = dep.get_dependencies(app_path)
        assert service_path in deps, (
            f"app.ts should depend on service.ts, got: {deps}"
        )


@pytest.mark.asyncio
async def test_js_external_package_ignored():
    """Test that external packages (node_modules) are not resolved as project files."""
    import tempfile
    from scope_code.analyzers.project import ProjectAnalyzer
    from scope_code.analyzers.dependency import DependencyAnalyzer

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        src = root / "src"
        src.mkdir()

        (src / "app.js").write_text('''
import React from 'react';
import { useState } from 'react';
export function App() { return null; }
''')

        analyzer = ProjectAnalyzer()
        structure = analyzer.analyze(str(root))

        dep = DependencyAnalyzer()
        dep.build(structure)

        app_path = None
        for rel_path in structure.files:
            if rel_path.endswith("app.js"):
                app_path = rel_path

        # External packages should not create edges
        deps = dep.get_dependencies(app_path)
        # 'react' should not resolve to any project file
        assert len(deps) == 0, (
            f"External package 'react' should not resolve, got: {deps}"
        )


@pytest.mark.asyncio
async def test_mixed_python_js_project():
    """Test dependency resolution in a mixed Python + JS project."""
    import tempfile
    from scope_code.analyzers.project import ProjectAnalyzer
    from scope_code.analyzers.dependency import DependencyAnalyzer

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        backend = root / "backend"
        frontend = root / "frontend"
        backend.mkdir()
        frontend.mkdir()

        # Python backend
        (backend / "__init__.py").write_text("")
        (backend / "auth.py").write_text("""
from .models import User
class AuthService:
    def login(self, u, p): pass
""")
        (backend / "models.py").write_text("""
class User:
    pass
""")

        # JS frontend
        (frontend / "login.js").write_text('''
import { apiCall } from './api';
export function login(u, p) { return apiCall('/login', {u, p}); }
''')
        (frontend / "api.js").write_text('''
export function apiCall(url, data) { return fetch(url, {body: JSON.stringify(data)}); }
''')

        analyzer = ProjectAnalyzer()
        structure = analyzer.analyze(str(root))

        dep = DependencyAnalyzer()
        graph = dep.build(structure)

        # Should have nodes for both Python and JS
        assert graph.number_of_nodes() >= 4

        # Python dependency should be resolved
        auth_path = None
        models_path = None
        login_path = None
        api_path = None
        for rel_path in structure.files:
            if rel_path.endswith("auth.py"):
                auth_path = rel_path
            elif rel_path.endswith("models.py"):
                models_path = rel_path
            elif rel_path.endswith("login.js"):
                login_path = rel_path
            elif rel_path.endswith("api.js"):
                api_path = rel_path

        # Python: auth.py → models.py
        if auth_path and models_path:
            deps = dep.get_dependencies(auth_path)
            assert models_path in deps

        # JS: login.js → api.js
        if login_path and api_path:
            deps = dep.get_dependencies(login_path)
            assert api_path in deps


# ── Git diff verification tests ──────────────────────────────────

@pytest.mark.asyncio
async def test_git_changed_files_non_git_repo():
    """Test that git detection gracefully handles non-git directories."""
    import tempfile
    from scope_code.stages.verify import VerifyStage

    with tempfile.TemporaryDirectory() as tmpdir:
        stage = VerifyStage()
        files = stage._get_git_changed_files(tmpdir)
        # Should return empty list for non-git repo
        assert files == []


@pytest.mark.asyncio
async def test_verify_stage_with_git_disabled():
    """Test that verification works with git disabled."""
    from scope_code.stages.verify import VerifyStage

    # use_git=False should work without errors
    stage = VerifyStage(use_git=False)
    assert stage.use_git is False
    # The _get_git_changed_files method should still exist
    files = stage._get_git_changed_files("/nonexistent")
    assert files == []
