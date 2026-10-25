"""We need a storage mechanism for the study cards. because the MCP does not remember them on its own.
    We will use SQLite for Cards, deck, and review schedules.
    The MCP is stateless, so it relies on this storage to keep track of the study cards and their review schedules.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from pydantic import BaseModel
from . import sm2

DB_PATH = Path(os.getenv("STUDY_CARDS_DB", "study_cards.db"))

class Deck(BaseModel):
    name: str
    description: str
    cards: int
    
class Card(BaseModel):
    card_id: str
    deck: str
    front: str
    back: str
    repetitions: int
    interval_days: int
    easiness: float
    due: str
    source: str | None = None
    
class DeckStats(BaseModel):
    deck: str
    total: int
    due_today: int
    new: int # never reviewed
    learning: int # 1-2 correct answers consecutively
    mature: int # +3 correct answers consecutively
    average_easiness: float | None
    
@contextmanager
def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS decks (
                name TEXT PRIMARY KEY, description TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS cards (
                card_id TEXT PRIMARY KEY,
                deck TEXT NOT NULL REFERENCES decks(name) ON DELETE CASCADE,
                front TEXT NOT NULL, back TEXT NOT NULL,
                repetitions INTEGER NOT NULL, interval_days INTEGER NOT NULL,
                easiness REAL NOT NULL, due TEXT NOT NULL, source TEXT);
        """)
        # Migration: databases created before this version have no source column.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(cards)")}
        if "source" not in columns:
            conn.execute("ALTER TABLE cards ADD COLUMN source TEXT")
        yield conn
        conn.commit()
    finally:
        conn.close()
        
def _card(row) -> Card:
    return Card(card_id=row[0], deck=row[1], front=row[2], back=row[3],
                repetitions=row[4], interval_days=row[5], easiness=row[6], due=row[7],
                source=row[8])

def _normalize(text: str) -> str:
    """Comparison key for duplicates: case and extra spaces are ignored."""
    return " ".join(text.lower().split())

def get_card(card_id: str) -> Card | None:
    with _db() as db:
        row = db.execute("SELECT * FROM cards WHERE card_id = ?", (card_id,)).fetchone()
    return _card(row) if row else None
    
def create_deck(name: str, description: str) -> Deck:
    with _db() as db:
        db.execute("INSERT INTO decks VALUES (?, ?)", (name, description))
    return get_deck(name)


def get_deck(name: str) -> Deck | None:
    with _db() as db:
        row = db.execute("SELECT d.name, d.description, COUNT(c.card_id) FROM decks d "
                         "LEFT JOIN cards c ON c.deck = d.name WHERE d.name = ? "
                         "GROUP BY d.name", (name,)).fetchone()
    return Deck(name=row[0], description=row[1], cards=row[2]) if row else None    


def list_decks() -> list[Deck]:
    with _db() as db:
        rows = db.execute("SELECT d.name, d.description, COUNT(c.card_id) FROM decks d "
                          "LEFT JOIN cards c ON c.deck = d.name GROUP BY d.name ORDER BY d.name").fetchall()
    return [Deck(name=r[0], description=r[1], cards=r[2]) for r in rows]

def add_card(deck: str, front: str, back: str, source: str | None = None, today: date | None = None) -> Card:
    s = sm2.new_schedule(today or date.today())
    card_id = "card_" + secrets.token_urlsafe(8)
    with _db() as db:
        db.execute("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (card_id, deck, front, back, s.repetitions, s.interval_days, s.easiness, s.due.isoformat(), source))
    return get_card(card_id)

def add_cards(deck: str, items: list[tuple[str, str, str | None]],
              today: date | None = None) -> tuple[int, list[str]]:
    """Add a batch of cards (front, back, source) in a single transaction.

    Skips questions already in the deck or repeated within the batch: sending the same
    batch again creates no duplicates. Returns (cards added, questions skipped as duplicates).
    """
    s = sm2.new_schedule(today or date.today())
    added, duplicates = 0, []
    with _db() as db:
        seen = {_normalize(r[0]) for r in db.execute("SELECT front FROM cards WHERE deck = ?", (deck,))}
        for front, back, source in items:
            key = _normalize(front)
            if key in seen:
                duplicates.append(front)
                continue
            seen.add(key)
            db.execute("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", ("card_" + secrets.token_urlsafe(8), deck, front, back,
                                 s.repetitions, s.interval_days, s.easiness, s.due.isoformat(), source))
            added += 1
    return added, duplicates

def cards_in_deck(deck: str) -> list[Card]:
    with _db() as db:
        rows = db.execute("SELECT * FROM cards WHERE deck = ? ORDER BY due, card_id", (deck,)).fetchall()
    return [_card(r) for r in rows]


def due_cards(deck: str, limit: int, today: date | None = None) -> list[Card]:
    day = (today or date.today()).isoformat()
    with _db() as db:
        rows = db.execute("SELECT * FROM cards WHERE deck = ? AND due <= ? "
                          "ORDER BY due, card_id LIMIT ?", (deck, day, limit)).fetchall()
    return [_card(r) for r in rows]


def grade_card(card_id: str, grade: int, today: date | None = None) -> Card | None:
    card = get_card(card_id)
    if card is None:
        return None
    current = sm2.Schedule(card.repetitions, card.interval_days, card.easiness,
                           date.fromisoformat(card.due))
    nxt = sm2.review(current, grade, today or date.today())
    with _db() as db:
        db.execute("UPDATE cards SET repetitions=?, interval_days=?, easiness=?, due=? WHERE card_id=?",
                   (nxt.repetitions, nxt.interval_days, nxt.easiness, nxt.due.isoformat(), card_id))
    return get_card(card_id)


def stats(deck: str, today: date | None = None) -> DeckStats:
    cards = cards_in_deck(deck)
    day = (today or date.today()).isoformat()
    return DeckStats(
        deck=deck, total=len(cards),
        due_today=sum(c.due <= day for c in cards),
        new=sum(c.repetitions == 0 and c.interval_days == 0 for c in cards),
        learning=sum(1 <= c.repetitions <= 2 for c in cards),
        mature=sum(c.repetitions >= 3 for c in cards),
        average_easiness=round(sum(c.easiness for c in cards) / len(cards), 2) if cards else None)


def delete_deck(name: str) -> int:
    with _db() as db:
        n = db.execute("SELECT COUNT(*) FROM cards WHERE deck = ?", (name,)).fetchone()[0]
        cur = db.execute("DELETE FROM decks WHERE name = ?", (name,))
    return n if cur.rowcount else -1    