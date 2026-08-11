"""Tests for new features: Gemini adapter, multi-language, MCP server."""

import pytest
import tempfile
import os
from pathlib import Path


# ── Multi-language analyzer tests ────────────────────────────────

@pytest.mark.asyncio
async def test_multilang_javascript():
    """Test JS file analysis."""
    from scope_code.analyzers.multi_lang import MultiLangAnalyzer
    from scope_code.models.project import FileNode, FileType

    js_code = '''
import { useState } from 'react';
import api from './api';
const LoginForm = () => {
    const handleSubmit = async (data) => { await api.login(data); };
    return null;
};
export default LoginForm;
export const validateEmail = (email) => /@/.test(email);
'''
    tmp = Path(tempfile.gettempdir()) / "_sc_test.js"
    tmp.write_text(js_code)

    node = FileNode(
        path=str(tmp), name="test.js",
        file_type=FileType.SOURCE, language="javascript",
    )
    MultiLangAnalyzer().analyze(node, tmp)

    assert "react" in node.imports or any(
        "react" in imp for imp in node.imports
    )
    assert "LoginForm" in node.exports
    assert "validateEmail" in node.exports
    assert "handleSubmit" in node.functions

    tmp.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_multilang_typescript():
    """Test TS file analysis."""
    from scope_code.analyzers.multi_lang import MultiLangAnalyzer
    from scope_code.models.project import FileNode, FileType

    ts_code = '''
import { AuthService } from './auth';
import type { User } from './types';
interface LoginProps { username: string; }
export class LoginController {
    async login(username: string, password: string) { }
}
export const apiBase = '/api';
'''
    tmp = Path(tempfile.gettempdir()) / "_sc_test.ts"
    tmp.write_text(ts_code)

    node = FileNode(
        path=str(tmp), name="test.ts",
        file_type=FileType.SOURCE, language="typescript",
    )
    MultiLangAnalyzer().analyze(node, tmp)

    assert any("auth" in imp for imp in node.imports)
    assert "LoginController" in node.exports
    assert "LoginProps" in node.classes or any(
        "LoginProps" in c for c in node.classes
    )

    tmp.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_multilang_go():
    """Test Go file analysis."""
    from scope_code.analyzers.multi_lang import MultiLangAnalyzer
    from scope_code.models.project import FileNode, FileType

    go_code = '''
package auth
import (
    "fmt"
    "net/http"
)
type AuthService struct { }
func (s *AuthService) Login(username string) bool { return true }
func NewAuthService() *AuthService { return &AuthService{} }
'''
    tmp = Path(tempfile.gettempdir()) / "_sc_test.go"
    tmp.write_text(go_code)

    node = FileNode(
        path=str(tmp), name="test.go",
        file_type=FileType.SOURCE, language="go",
    )
    MultiLangAnalyzer().analyze(node, tmp)

    # Go exports = uppercase-starting functions/types
    assert "AuthService" in node.exports or "NewAuthService" in node.exports

    tmp.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_multilang_rust():
    """Test Rust file analysis."""
    from scope_code.analyzers.multi_lang import MultiLangAnalyzer
    from scope_code.models.project import FileNode, FileType

    rust_code = '''
use std::collections::HashMap;
use crate::auth::User;
pub struct AuthService { users: HashMap<String, User> }
pub fn login(username: &str) -> bool { true }
fn hash_password(pw: &str) -> String { String::new() }
'''
    tmp = Path(tempfile.gettempdir()) / "_sc_test.rs"
    tmp.write_text(rust_code)

    node = FileNode(
        path=str(tmp), name="test.rs",
        file_type=FileType.SOURCE, language="rust",
    )
    MultiLangAnalyzer().analyze(node, tmp)

    assert "AuthService" in node.exports
    assert "login" in node.exports
    assert "hash_password" in node.functions

    tmp.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_multilang_java():
    """Test Java file analysis."""
    from scope_code.analyzers.multi_lang import MultiLangAnalyzer
    from scope_code.models.project import FileNode, FileType

    java_code = '''
package com.example.auth;
import java.util.List;
import com.example.payment.PaymentService;
public class AuthService {
    private List<String> sessions;
    public boolean login(String username, String password) { return true; }
    private String hashPassword(String pw) { return pw; }
}
'''
    tmp = Path(tempfile.gettempdir()) / "_sc_test.java"
    tmp.write_text(java_code)

    node = FileNode(
        path=str(tmp), name="test.java",
        file_type=FileType.SOURCE, language="java",
    )
    MultiLangAnalyzer().analyze(node, tmp)

    assert "AuthService" in node.classes
    assert any("util" in imp or "payment" in imp for imp in node.imports)

    tmp.unlink(missing_ok=True)


# ── LLM factory tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_gemini_registered():
    """Test that Gemini is registered in the factory."""
    from scope_code.llm.factory import list_providers, _PROVIDERS
    providers = list_providers()
    assert "gemini" in providers
    assert "google" in providers
    assert _PROVIDERS["gemini"].__name__ == "GeminiAdapter"


# ── MCP server tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_tools_defined():
    """Test that MCP server tools are properly defined."""
    from scope_code.mcp_server import TOOLS

    tool_names = {t["name"] for t in TOOLS}
    assert "analyze_scope" in tool_names
    assert "analyze_and_execute" in tool_names
    assert "get_evidence" in tool_names

    for tool in TOOLS:
        assert "inputSchema" in tool
        assert "required" in tool["inputSchema"]
        assert "properties" in tool["inputSchema"]


@pytest.mark.asyncio
async def test_mcp_server_initialize():
    """Test MCP server initialization handshake."""
    from scope_code.mcp_server import MCPServer

    server = MCPServer()

    # Simulate initialize request
    result = await server._handle_method("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
    })

    assert result["protocolVersion"] == "2024-11-05"
    assert "tools" in result["capabilities"]
    assert result["serverInfo"]["name"] == "scope-code"


@pytest.mark.asyncio
async def test_mcp_server_tools_list():
    """Test tools/list returns all tools."""
    from scope_code.mcp_server import MCPServer

    server = MCPServer()
    result = await server._handle_method("tools/list", {})

    assert "tools" in result
    assert len(result["tools"]) == 3  # analyze_scope, analyze_and_execute, get_evidence


# ── Project analyzer multi-language test ────────────────────────

@pytest.mark.asyncio
async def test_project_analyzer_detects_js():
    """Test that ProjectAnalyzer classifies and parses JS files."""
    import tempfile
    from scope_code.analyzers.project import ProjectAnalyzer
    from scope_code.models.project import FileType

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        src = root / "src"
        src.mkdir()

        js_file = src / "login.js"
        js_file.write_text('''
import { useState } from 'react';
export function login(username, password) { }
export default function validate(input) { }
''')

        analyzer = ProjectAnalyzer()
        structure = analyzer.analyze(str(root))

        # Find the JS file in the structure
        found = False
        for rel_path, file_node in structure.files.items():
            if file_node.name == "login.js":
                found = True
                assert file_node.language == "javascript"
                assert file_node.file_type == FileType.SOURCE
                assert len(file_node.exports) > 0
                break

        assert found, "JS file not found in structure"
