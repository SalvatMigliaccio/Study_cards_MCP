"""Test end-to-end: un vero client MCP collegato in-process al server."""
from datetime import date, timedelta

import pytest

from mcp import Client, types
from study_cards_mcp import store
from study_cards_mcp.server import mcp

pytestmark = pytest.mark.anyio

CARDS = """\
# Reti di calcolatori
Quale livello OSI instrada i pacchetti? :: Il livello 3, rete
Porta standard di HTTPS? :: 443
riga senza separatore
Cosa garantisce TCP rispetto a UDP? :: Consegna affidabile e ordinata
"""


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")


def type_to_confirm(text: str | None, action: str = "accept"):
    async def callback(context, params):
        if action != "accept":
            return types.ElicitResult(action=action)
        return types.ElicitResult(action="accept", content={"typed_name": text})
    return callback


async def make_deck(client):
    await client.call_tool("create_deck", {"name": "reti", "description": "Esame di reti"})
    return await client.call_tool("import_cards", {"deck": "reti", "text": CARDS})


async def test_schema_hides_server_resolved_parameters():
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert "confirmation" not in tools["delete_deck"].input_schema["properties"]
    assert "ctx" not in tools["import_cards"].input_schema["properties"]
    assert tools["delete_deck"].annotations.destructive_hint is True


async def test_import_reports_progress_and_skipped_lines():
    updates = []

    async def on_progress(progress, total, message):
        updates.append((progress, total))

    async with Client(mcp) as client:
        await client.call_tool("create_deck", {"name": "reti"})
        result = await client.call_tool("import_cards", {"deck": "reti", "text": CARDS},
                                        progress_callback=on_progress)
    report = result.structured_content
    assert report["added"] == 3
    assert report["skipped_lines"] == ["riga senza separatore"]
    assert updates[-1] == (4, 4)


async def test_study_loop_reschedules_cards():
    async with Client(mcp) as client:
        await make_deck(client)
        due = (await client.call_tool("due_cards", {"deck": "reti"})).structured_content["cards"]
        assert len(due) == 3
        graded = await client.call_tool("grade_card", {"card_id": due[0]["card_id"], "grade": 5})
        assert graded.structured_content["due"] == (date.today() + timedelta(days=1)).isoformat()
        stats = (await client.call_tool("deck_stats", {"deck": "reti"})).structured_content
    assert (stats["due_today"], stats["new"], stats["learning"]) == (2, 2, 1)


async def test_missing_deck_is_a_tool_error_with_a_hint():
    async with Client(mcp) as client:
        result = await client.call_tool("due_cards", {"deck": "storia"})
    assert result.is_error is True
    assert "create_deck" in result.content[0].text


async def test_invalid_grade_is_rejected_by_the_schema():
    async with Client(mcp) as client:
        await make_deck(client)
        card_id = store.cards_in_deck("reti")[0].card_id
        result = await client.call_tool("grade_card", {"card_id": card_id, "grade": 9})
    assert result.is_error is True


async def test_resource_template_reads_deck_content():
    async with Client(mcp) as client:
        await make_deck(client)
        content = await client.read_resource("deck://reti")
    assert "Porta standard di HTTPS?" in content.contents[0].text


@pytest.mark.parametrize("callback, deleted", [
    (type_to_confirm("reti"), True),
    (type_to_confirm("Reti!"), False),
    (type_to_confirm(None, action="decline"), False),
])
async def test_delete_requires_typing_the_name(callback, deleted):
    async with Client(mcp, elicitation_callback=callback) as client:
        await make_deck(client)
        result = await client.call_tool("delete_deck", {"deck": "reti"})
    assert (store.get_deck("reti") is None) is deleted
    assert ("deleted along with" in result.content[0].text) is deleted