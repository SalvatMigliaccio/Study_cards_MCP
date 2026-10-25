"""Parla con il server HTTP a mano, con richieste JSON-RPC grezze, per vedere il protocollo sul wire.

Prima avvia il server in un altro terminale:
    uv run study-cards-mcp --transport http --port 3001
Poi:
    uv run python scripts/http_check.py
"""
import json
import urllib.error
import urllib.request

URL = "http://127.0.0.1:3001/mcp"
META = {  # viaggia in OGNI richiesta: non c'è handshake né sessione
    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
    "io.modelcontextprotocol/clientCapabilities": {"elicitation": {}},
    "io.modelcontextprotocol/clientInfo": {"name": "http-check", "version": "1.0.0"},
}
_next_id = 0


def rpc(method: str, params: dict | None = None, name: str | None = None) -> dict:
    global _next_id
    _next_id += 1
    body = {"jsonrpc": "2.0", "id": _next_id, "method": method,
            "params": {**(params or {}), "_meta": META}}
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": method}
    if name:
        headers["Mcp-Name"] = name                      # obbligatorio per tools/call
    request = urllib.request.Request(URL, data=json.dumps(body).encode(), headers=headers)
    try:
        return json.load(urllib.request.urlopen(request))
    except urllib.error.HTTPError as e:
        return json.load(e)


def call_tool(tool: str, arguments: dict, **extra) -> dict:
    return rpc("tools/call", {"name": tool, "arguments": arguments, **extra}, name=tool)


def show(title: str, message: dict) -> None:
    print(f"\n===== {title} =====")
    print(json.dumps(message, indent=2, ensure_ascii=False))


show("server/discover", rpc("server/discover"))
call_tool("create_deck", {"name": "http-demo", "description": "creato via HTTP"})
show("tools/call import_cards", call_tool("import_cards", {"deck": "http-demo", "text": "Porta SSH? :: 22"}))

first = call_tool("delete_deck", {"deck": "http-demo"})
show("delete_deck, primo giro (input_required)", first)

result = first["result"]
key = next(iter(result["inputRequests"]))
second = call_tool("delete_deck", {"deck": "http-demo"},
                   inputResponses={key: {"action": "accept", "content": {"typed_name": "http-demo"}}},
                   requestState=result["requestState"])          # rimandato identico
show("delete_deck, secondo giro (complete)", second)