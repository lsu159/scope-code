"""MCP Server — expose Scope Code as tools for LLM agents.

Implements the Model Context Protocol (MCP) over stdio, allowing
Claude Code and other MCP-compatible agents to use Scope Code
as a tool.

Tools exposed:
    - analyze_scope: Analyze a requirement and return a modification plan.
    - analyze_and_execute: Full pipeline including code modification.
    - get_evidence: Get detailed evidence chain for a file.

Usage:
    # As a standalone server (stdio transport)
    python -m scope_code.mcp_server

    # Configure in Claude Code's MCP settings
    {
        "mcpServers": {
            "scope-code": {
                "command": "python",
                "args": ["-m", "scope_code.mcp_server"],
                "env": {
                    "SCOPE_CODE_API_KEY": "sk-ant-...",
                    "SCOPE_CODE_PROVIDER": "claude"
                }
            }
        }
    }
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional


# ── Tool definitions (MCP format) ────────────────────────────────

TOOLS = [
    {
        "name": "analyze_scope",
        "description": (
            "Analyze a software requirement and determine the minimum "
            "modification scope. Returns a structured plan with:\n"
            "- must_modify: files that MUST change (with reasons)\n"
            "- should_modify: files that SHOULD be reviewed\n"
            "- must_not_modify: files that MUST NOT be touched\n"
            "- evidence_chain: traceable reasons for every decision\n\n"
            "Core principle: Think Before Edit. Explain Before Change.\n"
            "先思考，再修改；先解释，再变更。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "requirement": {
                    "type": "string",
                    "description": "The requirement in natural language.",
                },
                "project_path": {
                    "type": "string",
                    "description": "Absolute path to the project directory.",
                },
            },
            "required": ["requirement", "project_path"],
        },
    },
    {
        "name": "analyze_and_execute",
        "description": (
            "Analyze a requirement AND execute the modification plan. "
            "This is the full pipeline: understand → analyze → scope → "
            "plan → confirm → modify → verify.\n"
            "WARNING: This actually modifies code. Use analyze_scope first "
            "to preview changes, then call this to execute."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "requirement": {
                    "type": "string",
                    "description": "The requirement in natural language.",
                },
                "project_path": {
                    "type": "string",
                    "description": "Absolute path to the project directory.",
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true, preview changes without writing.",
                    "default": False,
                },
                "plan_hash": {
                    "type": "string",
                    "description": (
                        "REQUIRED: The plan_hash from analyze_scope output. "
                        "You MUST call analyze_scope first, review the plan, "
                        "then pass its plan_hash here. The hash proves you "
                        "reviewed THIS plan — not a different one."
                    ),
                },
            },
            "required": ["requirement", "project_path"],
        },
    },
    {
        "name": "get_evidence",
        "description": (
            "Get the detailed evidence chain for a specific file — "
            "why it was included in the modification plan, what calls it, "
            "what it calls, and the traceable reasoning."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "The file path to get evidence for.",
                },
            },
            "required": ["file_path"],
        },
    },
]


# ── MCP Server ───────────────────────────────────────────────────

class MCPServer:
    """MCP server over stdio transport.

    Implements the JSON-RPC 2.0 based MCP protocol.
    """

    def __init__(self):
        self._tools: Dict[str, Dict] = {t["name"]: t for t in TOOLS}
        self._initialized = False
        self._last_context = None  # Store last pipeline context for get_evidence

    # ── main loop ─────────────────────────────────────────────

    async def run(self):
        """Run the MCP server on stdio (cross-platform).

        Uses synchronous stdin/stdout I/O wrapped in asyncio threads
        to avoid Windows pipe transport issues.
        """
        import functools

        loop = asyncio.get_event_loop()

        while True:
            try:
                # Read line synchronously (works on Windows)
                line = await loop.run_in_executor(
                    None, sys.stdin.readline
                )
                if not line:
                    break

                line_text = line.strip()
                if not line_text:
                    continue

                request = json.loads(line_text)
                response = await self._handle_request(request)

                if response is not None:
                    response_text = json.dumps(response, ensure_ascii=False) + "\n"
                    # Write synchronously (works on Windows)
                    await loop.run_in_executor(
                        None,
                        functools.partial(sys.stdout.write, response_text),
                    )
                    await loop.run_in_executor(None, sys.stdout.flush)

            except json.JSONDecodeError:
                continue
            except EOFError:
                break
            except Exception as e:
                error_response = self._error_response(
                    None, -32603, str(e)
                )
                response_text = json.dumps(error_response, ensure_ascii=False) + "\n"
                await loop.run_in_executor(
                    None, functools.partial(sys.stdout.write, response_text)
                )
                await loop.run_in_executor(None, sys.stdout.flush)

    async def _handle_request(self, request: Dict) -> Optional[Dict]:
        """Route a JSON-RPC request to the appropriate handler."""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})

        # Handle notifications (no id)
        if req_id is None:
            await self._handle_notification(method, params)
            return None

        try:
            result = await self._handle_method(method, params)
            return self._success_response(req_id, result)
        except Exception as e:
            return self._error_response(req_id, -32603, str(e))

    async def _handle_notification(self, method: str, params: Dict):
        """Handle JSON-RPC notifications (no response)."""
        if method == "notifications/initialized":
            pass  # Client is ready
        elif method == "initialized":
            pass

    async def _handle_method(self, method: str, params: Dict) -> Any:
        """Dispatch method calls."""
        if method == "initialize":
            return {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "scope-code",
                    "version": "0.1.0",
                },
            }
        elif method == "tools/list":
            return {"tools": list(self._tools.values())}
        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            return await self._call_tool(tool_name, arguments)
        else:
            raise ValueError(f"Unknown method: {method}")

    async def _call_tool(self, name: str, args: Dict) -> Dict:
        """Execute a tool call."""
        if name == "analyze_scope":
            result = await self._run_analyze_scope(args)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": result,
                    }
                ]
            }
        elif name == "analyze_and_execute":
            result = await self._run_analyze_and_execute(args)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": result,
                    }
                ]
            }
        elif name == "get_evidence":
            result = await self._run_get_evidence(args)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": result,
                    }
                ]
            }
        else:
            raise ValueError(f"Unknown tool: {name}")

    # ── tool implementations ───────────────────────────────────

    async def _run_analyze_scope(self, args: Dict) -> str:
        """Run the scope analysis pipeline."""
        requirement = args["requirement"]
        project_path = args["project_path"]

        llm = self._get_llm()
        import sys as _sys
        _sys.stderr.write(f"[DEBUG] has_llm={llm is not None}, provider={llm.provider_name if llm else 'N/A'}\n")
        _sys.stderr.flush()

        engine = self._create_pipeline(include_modify=False)

        # Analyze mode: auto-confirm is safe (no code modification)
        from .stages.confirmation import ConfirmationStage
        for i, stage in enumerate(engine.stages):
            if stage.name == "confirmation":
                engine.stages[i] = ConfirmationStage(auto_confirm=True)
                break

        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            context = await engine.run(
                requirement=requirement,
                project_path=project_path,
                llm=llm,
            )

        self._last_context = context

        plan = context.modification_plan
        if plan is None:
            return json.dumps({
                "error": "No plan generated.",
                "details": {
                    "errors": context.errors,
                    "should_stop": context.should_stop,
                    "business_functions": context.business_functions,
                    "entities": context.structured_requirement.get("entities", []),
                    "modules_found": (
                        len(context.project_structure.modules)
                        if context.project_structure else 0
                    ),
                }
            })

        from .outputs.json_output import JSONOutput
        import hashlib
        plan_json = JSONOutput().render(plan, indent=2)
        plan_hash = hashlib.sha256(plan_json.encode()).hexdigest()[:16]
        self._last_plan_hash = plan_hash

        # Embed hash in the response so caller must use it for execute
        result = json.loads(plan_json)
        result["plan_hash"] = plan_hash
        result["_instruction"] = (
            "Review the plan above. To execute, call analyze_and_execute "
            f"with plan_hash='{plan_hash}' to prove you reviewed this plan."
        )
        return json.dumps(result, indent=2, ensure_ascii=False)

    async def _run_analyze_and_execute(self, args: Dict) -> str:
        """Run the full pipeline including code modification.

        TWO-STEP SAFETY: Requires plan_hash from a prior analyze_scope call.
        This proves you reviewed the plan before authorizing execution.
        """
        requirement = args["requirement"]
        project_path = args["project_path"]
        dry_run = args.get("dry_run", False)
        plan_hash = args.get("plan_hash", "")

        llm = self._get_llm()

        # Safety gate: must provide plan_hash from a prior analyze_scope call
        if not plan_hash:
            return json.dumps({
                "error": "Missing plan_hash.",
                "instruction": (
                    "Call analyze_scope first to generate a plan. "
                    "Review it, then call analyze_and_execute with the "
                    "plan_hash from that plan's output. "
                    "This ensures you reviewed the plan before execution."
                ),
            })

        # Verify hash: re-run analysis and check the hash matches
        expected_hash = getattr(self, "_last_plan_hash", None)
        if not expected_hash:
            return json.dumps({
                "error": "No plan has been generated yet.",
                "instruction": "Call analyze_scope first, review the plan, then retry."
            })

        if plan_hash != expected_hash:
            return json.dumps({
                "error": "Plan hash mismatch.",
                "detail": (
                    f"The provided hash '{plan_hash}' does not match "
                    f"the last generated plan '{expected_hash}'. "
                    "Call analyze_scope again to generate a fresh plan, "
                    "review it, and use its plan_hash."
                ),
            })

        # Hash verified: execute the EXACT plan the user reviewed.
        # We reuse the saved context from analyze_scope — do NOT re-run
        # stages 1-6, because LLM non-determinism could produce a different plan.
        saved_ctx = self._last_context
        if saved_ctx is None:
            return json.dumps({
                "error": "No saved plan context.",
                "instruction": "Call analyze_scope first."
            })

        saved_ctx.plan_confirmed = True  # Already confirmed via hash

        # Only run ModifyStage + VerifyStage on the saved context
        from .stages.modify import ModifyStage
        from .stages.verify import VerifyStage

        import contextlib, io
        with contextlib.redirect_stdout(io.StringIO()) as captured:
            await ModifyStage(dry_run=dry_run).execute(saved_ctx, llm)
            if not saved_ctx.should_stop:
                await VerifyStage().execute(saved_ctx, llm)

        context = saved_ctx

        self._last_context = context

        plan = context.modification_plan
        if plan is None:
            return json.dumps({
                "error": "No plan generated.",
                "details": {
                    "errors": context.errors,
                    "should_stop": context.should_stop,
                    "business_functions": context.business_functions,
                    "modules_found": (
                        len(context.project_structure.modules)
                        if context.project_structure else 0
                    ),
                    "has_llm": llm is not None,
                }
            })

        from .outputs.json_output import JSONOutput

        result = {
            "plan": plan.model_dump(),
            "execution": {
                "files_modified": context.metadata.get("files_modified", []),
                "verification_passed": context.metadata.get(
                    "verification_passed", False
                ),
                "errors": context.errors,
            },
        }

        if "verification_report" in context.metadata:
            result["execution"]["verification_report"] = (
                context.metadata["verification_report"].format_report()
            )

        return json.dumps(result, indent=2, ensure_ascii=False)

    async def _run_get_evidence(self, args: Dict) -> str:
        """Get evidence chain for a specific file."""
        file_path = args["file_path"]

        if self._last_context is None:
            return json.dumps({
                "error": "No analysis has been run yet. Run analyze_scope first."
            })

        evidence_chain = self._last_context.evidence_chain
        matching = [e for e in evidence_chain if e.file == file_path]

        if not matching:
            return json.dumps({
                "file": file_path,
                "evidence": [],
                "message": f"No evidence found for '{file_path}'. "
                           f"Files with evidence: "
                           f"{[e.file for e in evidence_chain]}",
            })

        return json.dumps(
            [e.model_dump() for e in matching],
            indent=2,
            ensure_ascii=False,
        )

    # ── helpers ─────────────────────────────────────────────────

    def _get_llm(self):
        """Get LLM adapter from environment config."""
        from .llm.factory import create_llm

        api_key = os.environ.get("SCOPE_CODE_API_KEY", "")
        provider = os.environ.get("SCOPE_CODE_PROVIDER", "claude")
        model = os.environ.get("SCOPE_CODE_MODEL", "")
        api_base = os.environ.get("SCOPE_CODE_API_BASE")

        if not api_key:
            return None

        if not model:
            defaults = {
                "claude": "claude-sonnet-5-20251001",
                "anthropic": "claude-sonnet-5-20251001",
                "openai": "gpt-4o",
                "gpt": "gpt-4o",
                "gemini": "gemini-2.0-flash",
                "deepseek": "deepseek-chat",
            }
            model = defaults.get(provider, "claude-sonnet-5-20251001")

        return create_llm(
            provider=provider,
            model=model,
            api_key=api_key,
            api_base=api_base,
        )

    def _create_pipeline(self, include_modify: bool = False):
        """Create a pipeline engine."""
        from .pipeline.engine import PipelineEngine
        return PipelineEngine.create_default(include_modify=include_modify)

    # ── JSON-RPC helpers ────────────────────────────────────────

    @staticmethod
    def _success_response(req_id: Any, result: Any) -> Dict:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": result,
        }

    @staticmethod
    def _error_response(
        req_id: Any, code: int, message: str
    ) -> Dict:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": code,
                "message": message,
            },
        }


# ── CLI entry ────────────────────────────────────────────────────

def main():
    """MCP server entry point."""
    server = MCPServer()
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
