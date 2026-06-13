"""MCP server API router (extracted from main.py).

JSON-RPC 2.0 endpoint that exposes CodeAgent's tool registry over MCP. Self-contained except for the
``TOOLS`` registry, which lives in ``main`` and is imported lazily inside the handlers; see
docs/MAINTAINABILITY_PLAN.md.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Request

router = APIRouter(tags=["mcp"])


@router.post("/mcp")
async def mcp_server_endpoint(request: Request):
    """
    MCPサーバーエンドポイント（JSON-RPC 2.0）。
    他エージェントからCodeAgentのツールをMCP経由で呼び出せる。
    """
    from main import TOOLS
    try:
        body = await request.json()
    except Exception:
        return {"jsonrpc": "2.0", "id": None,
                "error": {"code": -32700, "message": "Parse error"}}

    method = body.get("method", "")
    req_id = body.get("id", 1)
    params = body.get("params", {})

    def ok(result):
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def err(code, message):
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok({
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"subscribe": False, "listChanged": False},
                "prompts": {"listChanged": False}
            },
            "serverInfo": {"name": "codeagent", "version": "1.0"}
        })

    elif method == "notifications/initialized":
        return {}

    elif method == "ping":
        return ok({})

    elif method == "tools/list":
        import inspect
        tools_list = []
        for tname, fn in TOOLS.items():
            sig = inspect.signature(fn)
            props = {}
            required = []
            for pname, param in sig.parameters.items():
                if pname == "project":
                    continue
                ann = param.annotation
                ptype = "integer" if ann is int else ("boolean" if ann is bool else "string")
                props[pname] = {"type": ptype, "description": pname}
                if param.default is inspect.Parameter.empty:
                    required.append(pname)
            tools_list.append({
                "name": tname,
                "description": (fn.__doc__ or tname).strip().splitlines()[0][:120],
                "inputSchema": {"type": "object", "properties": props, "required": required}
            })
        return ok({"tools": tools_list})

    elif method == "tools/call":
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})
        if tool_name not in TOOLS:
            return err(-32601, f"Tool not found: {tool_name}")
        try:
            result = TOOLS[tool_name](**arguments)
            return ok({"content": [{"type": "text", "text": str(result)}]})
        except TypeError as e:
            return err(-32602, f"Invalid params: {e}")
        except Exception as e:
            return err(-32603, f"Internal error: {e}")

    elif method == "resources/list":
        return ok({
            "resources": [
                {
                    "uri": "codeagent://tools",
                    "name": "CodeAgent Tools",
                    "description": "Registered tool names",
                    "mimeType": "application/json"
                },
                {
                    "uri": "codeagent://health",
                    "name": "CodeAgent Health",
                    "description": "Basic health report",
                    "mimeType": "application/json"
                }
            ]
        })

    elif method == "resources/read":
        uri = params.get("uri", "")
        if uri == "codeagent://tools":
            text = json.dumps({"tool_names": list(TOOLS.keys()), "count": len(TOOLS)}, ensure_ascii=False)
            return ok({"contents": [{"uri": uri, "mimeType": "application/json", "text": text}]})
        if uri == "codeagent://health":
            text = json.dumps({"status": "ok", "service": "codeagent"}, ensure_ascii=False)
            return ok({"contents": [{"uri": uri, "mimeType": "application/json", "text": text}]})
        return err(-32602, f"Unknown resource: {uri}")

    elif method == "prompts/list":
        return ok({"prompts": []})

    else:
        return err(-32601, f"Method not found: {method}")


@router.get("/mcp/info")
def mcp_info():
    """MCPサーバー情報とツール一覧を返す"""
    from main import TOOLS
    return {
        "name": "codeagent",
        "version": "1.0",
        "protocol": "2024-11-05",
        "endpoint": "/mcp",
        "tools_count": len(TOOLS),
        "tool_names": list(TOOLS.keys()),
    }
