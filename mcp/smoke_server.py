#!/usr/bin/env python3
"""연기 시험용 — 도구 하나짜리 stdio MCP 서버(표준 라이브러리만). pi가 MCP 도구를 실제로 부르는지 본다."""
import json, sys

TOOL = {"name": "lookup_secret_word", "description": "Return today's secret word. Call this when the user asks for the secret word.",
        "inputSchema": {"type": "object", "properties": {"date": {"type": "string"}}, "required": []}}


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n"); sys.stdout.flush()


for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    m = json.loads(line); mid, method = m.get("id"), m.get("method")
    print("<<", method, file=sys.stderr, flush=True)
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": mid, "result": {"protocolVersion": m["params"].get("protocolVersion", "2025-06-18"),
              "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "moonjigi-smoke", "version": "0.1"}}})
    elif method == "tools/list":
        send({"jsonrpc": "2.0", "id": mid, "result": {"tools": [TOOL]}})
    elif method == "tools/call":
        send({"jsonrpc": "2.0", "id": mid, "result": {"content": [{"type": "text", "text": "The secret word is 거북이-7341."}], "isError": False}})
    elif method == "ping":
        send({"jsonrpc": "2.0", "id": mid, "result": {}})
    elif mid is not None:
        send({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}})
