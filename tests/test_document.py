"""Test del flusso "carte da documento": add_cards, duplicati, fonte, migrazione del database."""
import sqlite3

import pytest

from mcp import Client
from study_cards_mcp import store
from study_cards_mcp.server import mcp

pytestmark = pytest.mark.anyio

BATCH = [
    {"front": "Cos'è il three-way handshake di TCP?",
     "back": "Lo scambio SYN, SYN-ACK, ACK con cui TCP apre una connessione.",
     "source": "reti.pdf, p. 2"},
    {"front": "Perché UDP è adatto allo streaming?",
     "back": "Non ritrasmette i pacchetti persi, quindi non introduce ritardi.",
     "source": "reti.pdf, p. 3"},
]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DB_PATH", tmp_path / "test.db")


async def test_add_cards_saves_source_and_skips_duplicates():
    async with Client(mcp) as client:
        await client.call_tool("create_deck", {"name": "reti"})
        first = await client.call_tool("add_cards", {"deck": "reti", "cards": BATCH})
        # stessa domanda con maiuscole e spazi diversi: deve essere riconosciuta come duplicato
        again = BATCH + [{"front": "  cos'è il THREE-WAY handshake di tcp? ", "back": "..."}]
        second = await client.call_tool("add_cards", {"deck": "reti", "cards": again})
        content = await client.read_resource("deck://reti")
    assert first.structured_content == {"deck": "reti", "added": 2, "duplicates": []}
    assert second.structured_content["added"] == 0
    assert len(second.structured_content["duplicates"]) == 3
    assert "reti.pdf, p. 2" in content.contents[0].text


async def test_add_cards_limits_batch_size():
    async with Client(mcp) as client:
        await client.call_tool("create_deck", {"name": "reti"})
        result = await client.call_tool("add_cards", {"deck": "reti", "cards": [BATCH[0]] * 51})
    assert result.is_error is True


async def test_prompt_mentions_document_and_tools():
    async with Client(mcp) as client:
        prompt = await client.get_prompt("cards_from_document",
                                         {"document": "reti.pdf", "deck": "reti", "num_cards": "15"})
    text = prompt.messages[0].content.text
    assert "reti.pdf" in text and "add_cards" in text and "15" in text


def test_old_database_is_migrated(tmp_path, monkeypatch):
    old = tmp_path / "old.db"
    conn = sqlite3.connect(old)
    conn.executescript("""
        CREATE TABLE decks (name TEXT PRIMARY KEY, description TEXT NOT NULL);
        CREATE TABLE cards (card_id TEXT PRIMARY KEY, deck TEXT NOT NULL, front TEXT NOT NULL,
            back TEXT NOT NULL, repetitions INTEGER NOT NULL, interval_days INTEGER NOT NULL,
            easiness REAL NOT NULL, due TEXT NOT NULL);
        INSERT INTO decks VALUES ('reti', '');
        INSERT INTO cards VALUES ('card_vecchia01', 'reti', 'Porta HTTPS?', '443', 0, 0, 2.5, '2026-10-01');
    """)
    conn.commit()
    conn.close()
    monkeypatch.setattr(store, "DB_PATH", old)
    cards = store.cards_in_deck("reti")
    assert cards[0].front == "Porta HTTPS?" and cards[0].source is None
    store.add_card("reti", "Porta SSH?", "22", source="appunti")
    assert {c.source for c in store.cards_in_deck("reti")} == {None, "appunti"}