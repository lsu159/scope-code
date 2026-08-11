"""Integration test — run the full pipeline on a sample project.

Tests the deterministic (no-LLM) mode to verify the pipeline
flows correctly end-to-end.
"""

import pytest
import asyncio
from pathlib import Path

from scope_code.pipeline.engine import PipelineEngine
from scope_code.pipeline.context import PipelineContext
from scope_code.stages.understand import UnderstandStage
from scope_code.stages.business_analysis import BusinessAnalysisStage
from scope_code.stages.structure_analysis import StructureAnalysisStage
from scope_code.stages.scope_inference import ScopeInferenceStage
from scope_code.stages.plan_generation import PlanGenerationStage
from scope_code.stages.confirmation import ConfirmationStage
from scope_code.outputs.markdown import MarkdownReport
from scope_code.outputs.json_output import JSONOutput

SAMPLE_PROJECT = Path(__file__).parent.parent / "sample_project"


@pytest.mark.asyncio
async def test_full_pipeline_no_llm():
    """Run the full pipeline without LLM — all deterministic stages."""
    engine = PipelineEngine(stages=[
        UnderstandStage(),
        BusinessAnalysisStage(),
        StructureAnalysisStage(),
        ScopeInferenceStage(),
        PlanGenerationStage(),
        ConfirmationStage(auto_confirm=True),
    ])

    context = await engine.run(
        requirement="Add rate limiting to the login function",
        project_path=str(SAMPLE_PROJECT),
    )

    # Basic assertions
    assert context is not None
    assert context.structured_requirement is not None
    assert context.business_functions is not None

    # Structure analysis assertions
    assert context.project_structure is not None
    assert len(context.project_structure.modules) > 0
    assert len(context.project_structure.files) > 0

    # Dependency graph assertions
    assert context.dependency_graph is not None
    assert context.dependency_graph.number_of_nodes() > 0

    # Call graph assertions
    assert context.call_graph is not None

    # Scope assertions
    assert context.modification_scope is not None
    assert context.modification_scope.total_modifications > 0, (
        "Should have at least one file to modify"
    )

    # Evidence chain assertions
    assert len(context.evidence_chain) > 0, (
        "Every must_modify should have evidence"
    )

    # Plan assertions
    assert context.modification_plan is not None
    assert context.plan_confirmed is True
    assert context.modification_plan.is_safe

    # Must not modify should include unrelated modules
    assert len(context.modification_scope.must_not_modify) > 0, (
        "Should have must_not_modify entries (unrelated modules)"
    )

    # Specific: chat and payment should be in must_not_modify
    must_not_set = set(context.modification_scope.must_not_modify)
    assert any("chat" in m or "payment" in m for m in must_not_set), (
        "Unrelated modules (chat, payment) should be in must_not_modify"
    )


@pytest.mark.asyncio
async def test_structure_analysis():
    """Test that structure analysis correctly parses the sample project."""
    engine = PipelineEngine(stages=[
        StructureAnalysisStage(),
    ])

    context = await engine.run(
        requirement="Test",
        project_path=str(SAMPLE_PROJECT),
    )

    ps = context.project_structure
    assert ps is not None

    # Check modules
    module_names = list(ps.modules.keys())
    assert any("auth" in m for m in module_names), (
        f"Should contain auth module, got: {module_names}"
    )
    assert any("payment" in m for m in module_names)
    assert any("chat" in m for m in module_names)

    # Check specific files
    assert any("auth" in f for f in ps.files), (
        "Should contain auth files"
    )

    # Check symbol extraction
    auth_file = None
    for fpath, fnode in ps.files.items():
        if "auth" in fpath:
            auth_file = fnode
            break
    assert auth_file is not None
    assert "AuthService" in auth_file.classes
    assert "User" in auth_file.classes
    assert "login" in auth_file.functions
    assert "register" in auth_file.functions


@pytest.mark.asyncio
async def test_scope_inference_boundary():
    """Test that scope inference correctly identifies modification boundaries."""
    engine = PipelineEngine(stages=[
        StructureAnalysisStage(),
        ScopeInferenceStage(),
        ConfirmationStage(auto_confirm=True),
    ])

    # Pre-set business functions to focus on auth
    class PreAuthStage:
        @property
        def name(self):
            return "pre-auth"
        @property
        def label(self):
            return "pre-auth"
        async def execute(self, context, llm=None):
            context.business_functions = ["login", "AuthService", "User"]

    engine = PipelineEngine(stages=[
        PreAuthStage(),
        StructureAnalysisStage(),
        ScopeInferenceStage(),
    ])

    context = await engine.run(
        requirement="Add rate limiting to login",
        project_path=str(SAMPLE_PROJECT),
    )

    scope = context.modification_scope
    assert scope is not None

    # Must modify should contain auth files
    must_modify_paths = [fc.file_path for fc in scope.must_modify]
    assert any("auth" in p for p in must_modify_paths), (
        f"Must modify should include auth files, got: {must_modify_paths}"
    )

    # Chat and payment modules should be in must_not_modify
    must_not_set = set(scope.must_not_modify)
    has_unrelated = any(
        "chat" in m or "payment" in m for m in must_not_set
    )
    assert has_unrelated, (
        f"Unrelated modules should be in must_not_modify, "
        f"got: {must_not_set}"
    )

    # Evidence chain should have entries
    assert len(context.evidence_chain) > 0


@pytest.mark.asyncio
async def test_output_formats():
    """Test that output formatters work correctly."""
    from scope_code.models.plan import ModificationPlan
    from scope_code.models.scope import ModificationScope, FileChange
    from scope_code.models.evidence import Evidence

    # Build a minimal plan
    plan = ModificationPlan(
        requirement_summary="Add rate limiting to login",
        business_functions=["Login", "Rate Limiting"],
        scope=ModificationScope(
            must_modify=[
                FileChange(
                    file_path="src/auth/__init__.py",
                    change_type="modify",
                    reason="Login function is here",
                ),
            ],
            should_modify=[
                FileChange(
                    file_path="src/auth/sms.py",
                    change_type="modify",
                    reason="May need rate limit for SMS too",
                ),
            ],
            must_not_modify=[
                "src/payment/*",
                "src/chat/*",
            ],
        ),
        evidence_chain=[
            Evidence(
                file="src/auth/__init__.py",
                reason="LoginController calls AuthService.login()",
                callers=["LoginController"],
                callees=[],
                business_function="Login",
                evidence_type="direct",
            ),
        ],
        risk_assessment=["Rate limit may slow down login."],
        verification_steps=["Run auth tests", "Test with high concurrency"],
    )

    # Test Markdown output
    report = MarkdownReport()
    md = report.render(plan)
    assert "# Modification Plan" in md
    assert "Add rate limiting" in md
    assert "src/auth/__init__.py" in md
    assert "src/payment/*" in md
    assert "Evidence Chain" in md

    # Test JSON output
    json_output = JSONOutput()
    json_str = json_output.render(plan)
    assert "requirement_summary" in json_str
    assert "must_modify" in json_str

    # Test JSON round-trip
    import tempfile
    import os
    tmp = os.path.join(tempfile.gettempdir(), "test_plan.json")
    try:
        saved = json_output.save(plan, tmp)
        loaded = json_output.load(saved)
        assert loaded.requirement_summary == plan.requirement_summary
        assert loaded.total_changes == plan.total_changes
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


@pytest.mark.asyncio
async def test_modification_scope_model():
    """Test the ModificationScope model methods."""
    from scope_code.models.scope import ModificationScope, FileChange

    scope = ModificationScope(
        must_modify=[
            FileChange(
                file_path="auth.py",
                change_type="modify",
                reason="Login is here",
            ),
        ],
        must_not_modify=[
            "payment/*",
            "chat/*",
        ],
    )

    # Test boundary respect
    assert scope.respects_boundary(["auth.py"]) is True
    assert scope.respects_boundary(["auth.py", "payment/gateway.py"]) is False

    # Test violation detection
    violations = scope.find_violations(["auth.py", "payment/gateway.py"])
    assert "payment/gateway.py" in violations

    # Test empty
    assert scope.is_empty is False

    # Test total
    assert scope.total_modifications == 1


@pytest.mark.asyncio
async def test_verification_report_clean():
    """Test that verification reports clean when all files are planned."""
    from scope_code.stages.verify import VerificationReport
    report = VerificationReport()
    report.planned_files_modified = ["auth.py"]
    assert report.is_clean is True
    assert report.has_issues is False
    report_text = report.format_report()
    assert "ALL CHECKS PASSED" in report_text


@pytest.mark.asyncio
async def test_verification_report_violations():
    """Test that verification reports violations correctly."""
    from scope_code.stages.verify import VerificationReport
    report = VerificationReport()
    report.planned_files_modified = ["auth.py"]
    report.must_not_violations = ["payment/__init__.py"]
    report.plan_external_files = ["config.py"]
    assert report.is_clean is False
    assert report.has_issues is True
    report_text = report.format_report()
    assert "VIOLATION" in report_text
    assert "payment/__init__.py" in report_text
    assert "config.py" in report_text


@pytest.mark.asyncio
async def test_full_pipeline_with_execute_no_llm():
    """Run the full pipeline including modify+verify stages (dry run)."""
    from scope_code.pipeline.engine import PipelineEngine
    from scope_code.stages.modify import ModifyStage
    from scope_code.stages.verify import VerifyStage

    engine = PipelineEngine(stages=[
        UnderstandStage(),
        BusinessAnalysisStage(),
        StructureAnalysisStage(),
        ScopeInferenceStage(),
        PlanGenerationStage(),
        ConfirmationStage(auto_confirm=True),
        ModifyStage(dry_run=True),
        VerifyStage(),
    ])

    context = await engine.run(
        requirement="Add rate limiting to the login function",
        project_path=str(SAMPLE_PROJECT),
    )

    # Check modification records exist
    records = context.metadata.get("modification_records", [])
    assert len(records) > 0, "Should have modification records"

    # Since it's dry run, no files should actually change
    for r in records:
        if r.success and r.was_changed:
            pass  # Previews were generated

    # Verification should have run
    report = context.metadata.get("verification_report")
    assert report is not None, "Should have verification report"

    # Check files_modified
    files_modified = context.metadata.get("files_modified", [])
    assert isinstance(files_modified, list)


@pytest.mark.asyncio
async def test_modify_stage_rejects_unconfirmed_plan():
    """Test that modify stage refuses to run on unconfirmed plans."""
    from scope_code.pipeline.engine import PipelineEngine
    from scope_code.stages.modify import ModifyStage

    engine = PipelineEngine(stages=[
        StructureAnalysisStage(),
        ScopeInferenceStage(),
        PlanGenerationStage(),
        # No confirmation stage — plan_confirmed stays False
        ModifyStage(),
    ])

    context = await engine.run(
        requirement="Test",
        project_path=str(SAMPLE_PROJECT),
    )

    # Should have halted at modify stage
    assert context.should_stop is True
    assert any(
        "not confirmed" in err.lower() for err in context.errors
    ), f"Expected 'not confirmed' error, got: {context.errors}"


@pytest.mark.asyncio
async def test_verify_stage_scope_boundary():
    """Test that verification detects must_not_modify violations."""
    from scope_code.stages.verify import VerifyStage, VerificationReport
    from scope_code.pipeline.engine import PipelineEngine
    from scope_code.models.plan import ModificationPlan
    from scope_code.models.scope import ModificationScope, FileChange
    from scope_code.models.evidence import Evidence

    # Build a pre-made context with violations
    engine = PipelineEngine(stages=[VerifyStage()])

    # We'll manually inject a bad state via a pre-stage
    class SetupViolationStage:
        @property
        def name(self):
            return "setup"
        @property
        def label(self):
            return "setup"
        async def execute(self, context, llm=None):
            context.modification_plan = ModificationPlan(
                requirement_summary="test",
                scope=ModificationScope(
                    must_modify=[
                        FileChange(
                            file_path="auth.py",
                            change_type="modify",
                            reason="test",
                        ),
                    ],
                    must_not_modify=["payment/*"],
                ),
            )
            context.modification_scope = context.modification_plan.scope
            context.metadata["files_modified"] = [
                "auth.py",
                "payment/gateway.py",  # VIOLATION!
            ]

    engine = PipelineEngine(stages=[
        SetupViolationStage(),
        VerifyStage(strict=False),  # Non-strict to avoid halting
    ])

    context = await engine.run(
        requirement="test",
        project_path=str(SAMPLE_PROJECT),
    )

    report = context.metadata.get("verification_report")
    assert report is not None
    assert report.has_issues is True
    assert "payment/gateway.py" in report.must_not_violations
