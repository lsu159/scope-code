"""Tests for MCP two-step plan_hash verification flow."""

import pytest
import json
from pathlib import Path

SAMPLE_PROJECT = str(Path(__file__).parent.parent / "sample_project")


@pytest.mark.asyncio
async def test_plan_hash_in_analyze_scope_output():
    """analyze_scope must return a plan_hash in its output."""
    from scope_code.mcp_server import MCPServer

    server = MCPServer()

    # Step 1: analyze_scope
    result = await server._call_tool("analyze_scope", {
        "requirement": "Add rate limiting to login",
        "project_path": SAMPLE_PROJECT,
    })

    content = json.loads(result["content"][0]["text"])

    # Must have plan_hash
    assert "plan_hash" in content, (
        "analyze_scope must return plan_hash"
    )
    assert len(content["plan_hash"]) == 16, (
        f"plan_hash should be 16 chars, got {len(content['plan_hash'])}"
    )

    # Must have instruction
    assert "_instruction" in content, (
        "analyze_scope must include _instruction for next step"
    )
    assert "plan_hash" in content["_instruction"], (
        "_instruction must mention plan_hash"
    )


@pytest.mark.asyncio
async def test_plan_hash_missing_rejected():
    """analyze_and_execute without plan_hash must be rejected."""
    from scope_code.mcp_server import MCPServer

    server = MCPServer()
    result = await server._call_tool("analyze_and_execute", {
        "requirement": "Test",
        "project_path": SAMPLE_PROJECT,
        "dry_run": True,
        # No plan_hash!
    })

    content = json.loads(result["content"][0]["text"])
    assert content.get("error") == "Missing plan_hash.", (
        "Must reject calls without plan_hash"
    )
    assert "instruction" in content


@pytest.mark.asyncio
async def test_plan_hash_wrong_rejected():
    """analyze_and_execute with wrong plan_hash must be rejected."""
    from scope_code.mcp_server import MCPServer

    server = MCPServer()

    # First generate a plan to set _last_plan_hash
    await server._call_tool("analyze_scope", {
        "requirement": "Test requirement",
        "project_path": SAMPLE_PROJECT,
    })

    # Then try execute with wrong hash
    result = await server._call_tool("analyze_and_execute", {
        "requirement": "Test",
        "project_path": SAMPLE_PROJECT,
        "dry_run": True,
        "plan_hash": "0000000000000000",  # Wrong!
    })

    content = json.loads(result["content"][0]["text"])
    assert content.get("error") == "Plan hash mismatch.", (
        "Must reject calls with wrong plan_hash"
    )
    assert "detail" in content


@pytest.mark.asyncio
async def test_plan_hash_correct_executes():
    """analyze_and_execute with correct hash must execute (not re-analyze)."""
    from scope_code.mcp_server import MCPServer

    server = MCPServer()

    # Step 1: generate plan
    result1 = await server._call_tool("analyze_scope", {
        "requirement": "Add rate limiting to login",
        "project_path": SAMPLE_PROJECT,
    })
    content1 = json.loads(result1["content"][0]["text"])
    plan_hash = content1["plan_hash"]

    # Step 2: execute with correct hash
    result2 = await server._call_tool("analyze_and_execute", {
        "requirement": "Add rate limiting to login",
        "project_path": SAMPLE_PROJECT,
        "dry_run": True,
        "plan_hash": plan_hash,
    })

    content2 = json.loads(result2["content"][0]["text"])

    # Must NOT have error
    assert "error" not in content2, (
        f"Correct hash should execute, got error: {content2.get('error')}"
    )

    # Must have execution results
    assert "execution" in content2, (
        "Output must contain execution results"
    )
    assert "files_modified" in content2["execution"], (
        "Must report files_modified"
    )
    assert "verification_passed" in content2["execution"], (
        "Must report verification_passed"
    )


@pytest.mark.asyncio
async def test_execute_reuses_saved_context():
    """verify that execute uses the saved context, not a fresh analysis."""
    from scope_code.mcp_server import MCPServer

    server = MCPServer()

    # Step 1: analyze_scope
    result1 = await server._call_tool("analyze_scope", {
        "requirement": "Add rate limiting",
        "project_path": SAMPLE_PROJECT,
    })
    content1 = json.loads(result1["content"][0]["text"])
    plan_hash = content1["plan_hash"]
    must_modify_before = len(content1["scope"]["must_modify"])

    # Verify _last_context is saved
    assert server._last_context is not None, (
        "analyze_scope must save context to _last_context"
    )
    assert server._last_context.modification_plan is not None, (
        "Saved context must have a plan"
    )

    # Step 2: execute with correct hash
    result2 = await server._call_tool("analyze_and_execute", {
        "requirement": "Different requirement text!",  # If re-analyzing, this would differ
        "project_path": SAMPLE_PROJECT,
        "dry_run": True,
        "plan_hash": plan_hash,
    })

    content2 = json.loads(result2["content"][0]["text"])

    # The plan in execution output should match the saved plan
    # (not the "Different requirement text!")
    plan_in_exec = content2.get("plan", {})
    must_modify_during = len(plan_in_exec.get("scope", {}).get("must_modify", []))
    assert must_modify_during == must_modify_before, (
        f"Execute must use saved plan ({must_modify_before} files), "
        f"not re-analyze ({must_modify_during} files)"
    )


@pytest.mark.asyncio
async def test_call_graph_narrowing_preserves_callers():
    """Call graph narrowing must keep files that actually call affected functions."""
    import tempfile
    from pathlib import Path
    from scope_code.analyzers.project import ProjectAnalyzer
    from scope_code.analyzers.dependency import DependencyAnalyzer
    from scope_code.analyzers.call_graph import CallGraphAnalyzer
    from scope_code.analyzers.symbol_index import SymbolIndex

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        src = root / "src"
        src.mkdir()

        # File A: defines a function
        (src / "auth.py").write_text("""
def login(user, password):
    return hash_password(password)

def hash_password(pw):
    return str(hash(pw))
""")

        # File B: imports A and CALLS login()
        (src / "controller.py").write_text("""
from src.auth import login

def handle_request():
    return login("admin", "secret")
""")

        # File C: imports A but does NOT call any function from A
        (src / "unrelated.py").write_text("""
from src.auth import hash_password  # imported but never called

def do_something():
    return "hello"
""")

        analyzer = ProjectAnalyzer()
        structure = analyzer.analyze(str(root))
        dep = DependencyAnalyzer()
        dep_graph = dep.build(structure)
        index = SymbolIndex().build(structure)
        cg = CallGraphAnalyzer()
        cg_graph = cg.build(structure, dep_graph=dep_graph, symbol_index=index)

        # Seed: auth.py
        seed_files = set()
        for rel_path in structure.files:
            if "auth.py" in rel_path:
                seed_files.add(rel_path)

        direct, transitive = dep.get_impact_scope(list(seed_files))

        # Both controller.py and unrelated.py are in transitive
        # (they both import auth.py)
        assert any("controller" in f for f in transitive), (
            "controller.py should be in transitive scope"
        )
        assert any("unrelated" in f for f in transitive), (
            "unrelated.py should be in transitive scope"
        )

        # Now apply call graph narrowing
        from scope_code.stages.scope_inference import ScopeInferenceStage
        stage = ScopeInferenceStage()
        narrowed = stage._narrow_by_call_graph(
            seed_files, direct, transitive, cg
        )

        # controller.py CALLS login() → should be kept
        assert any("controller" in f for f in narrowed), (
            "controller.py CALLS login() — must be kept in scope"
        )

        # unrelated.py imports but never CALLS → should be removed
        assert not any("unrelated" in f for f in narrowed), (
            "unrelated.py imports auth but never calls it — must be removed"
        )


@pytest.mark.asyncio
async def test_call_graph_narrowing_empty_returns_all():
    """When no call graph info, narrowing returns all transitive files."""
    from scope_code.stages.scope_inference import ScopeInferenceStage

    stage = ScopeInferenceStage()

    # Mock: no call graph info available
    class MockCG:
        def get_functions_in_file(self, f):
            return []
        def get_all_callees(self, f, s):
            return []

    narrowed = stage._narrow_by_call_graph(
        {"seed.py"}, {"seed.py"}, {"transitive.py"}, MockCG()
    )

    # Without call graph info, keep everything
    assert "transitive.py" in narrowed, (
        "Without call graph info, transitive files should be kept"
    )
