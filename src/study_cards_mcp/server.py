"""Study-cards-mcp: study flashcards with spaced repetition. exposed by MCP as a service.

Tool -> action decised by the model (create card, review card, list decks, get deck, delete deck, interrogate deck)
Resource -> context (guide to algorithm, content of a deck)
Prompt -> procedure chosen by the user (/study_session)
"""

from __future__ import annotations #future means that type hints can be used as forward references, allowing the use of types that are defined later in the code.

import argparse
from ast import pattern
import os
import sqlite3
import sys
from typing import Annotated

from pydantic import BaseModel, Field
from mcp.server import CacheHint, MCPServer
from mcp.server.elicitation import AcceptedElicitation, ElicitationResult  
from mcp.server.mcpserver import Context, Elicit, RequestStateSecurity, Resolve
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import store

#Config
DeckName = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]{1,39}$",
                                description="Deck name in lowercase with hyphens, e.g. computer-networks")]
CardId = Annotated[str, Field(pattern=r"^card_[A-Za-z0-9_-]{8,}$")]

_key = os.environ.get("STUDY_CARDS_STATE_KEY")
mcp = MCPServer(
    "study-cards",
    version = "0.1.0",
    
    instructions = "Flashcards with spaced repetition. For a study session: call due_cards, "
                   "show the user ONLY the front of one card at a time, wait for the user's answer, "
                   "compare it with the back, then record a grade from 0 to 5 with grade_card using the card_id.",
    
    request_state_security = (RequestStateSecurity(keys=[_key]) if _key
                              else RequestStateSecurity.ephemeral()),
    cache_hints = {
        "tools/list": CacheHint(ttl_ms=300_000, scope="public"),
        "prompts/list": CacheHint(ttl_ms=300_000, scope="public"),
        "resources/list": CacheHint(ttl_ms=300_000, scope="public"),
        "resources/read": CacheHint(ttl_ms=300_000, scope="private"),
    },
)

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False)

def _require_deck(name:str) -> store.Deck:
    deck = store.get_deck(name)
    if deck is None:
        raise ToolError(f"Deck '{name}' does not exist. Use list_decks to see the available decks"
                        f" or create_deck to create it.")
    return deck

# --Decks--
class DeckList(BaseModel):
    decks: list[store.Deck]
    
@mcp.tool(annotations=READ_ONLY)
def list_decks() -> DeckList:
     """List the flashcard decks with their card counts. Use it to find out what can be studied."""
     return DeckList(decks=store.list_decks())


@mcp.tool(annotations=WRITE)
def create_deck(name: DeckName,
                description: Annotated[str, Field(max_length=300)] = "") -> store.Deck:
    """Create a new empty deck."""
    try:
        return store.create_deck(name, description)
    except sqlite3.IntegrityError:
        raise ToolError(f"A deck named '{name}' already exists. Choose another name or add cards to it.")


@mcp.tool(annotations=READ_ONLY)
def deck_stats(deck: DeckName) -> store.DeckStats:
    """Deck statistics: cards due today, new, learning and mature."""
    _require_deck(deck)
    return store.stats(deck)

# === CARDS ===
@mcp.tool(annotations=WRITE)
def add_card(deck: DeckName,
             front: Annotated[str, Field(min_length=1, max_length=500, description="Question")],
             back: Annotated[str, Field(min_length=1, max_length=2000, description="Answer")]) -> store.Card:
    """Add a single flashcard to an existing deck. For many cards use import_cards."""
    _require_deck(deck)
    return store.add_card(deck, front.strip(), back.strip())


class ImportReport(BaseModel):
    deck: str
    added: int
    skipped_lines: list[str]


@mcp.tool(annotations=WRITE)
async def import_cards(
    deck: DeckName,
    text: Annotated[str, Field(max_length=100_000,
                               description="One card per line in the format: question :: answer")],
    ctx: Context,
) -> ImportReport:
    """Import many flashcards from text, one per line in the format 'question :: answer'.

    Blank lines and lines starting with # are ignored; malformed lines are reported in skipped_lines.
    """
    _require_deck(deck)
    lines = [l for l in text.splitlines() if l.strip() and not l.lstrip().startswith("#")]
    added, skipped = 0, []
    for i, line in enumerate(lines, start=1):
        front, sep, back = line.partition("::")
        if not sep or not front.strip() or not back.strip():
            skipped.append(line.strip()[:120])
        else:
            store.add_card(deck, front.strip()[:500], back.strip()[:2000])
            added += 1
        if i % 10 == 0 or i == len(lines):          # progress notification to the client
            await ctx.report_progress(i, len(lines), f"{i}/{len(lines)} lines processed")
    return ImportReport(deck=deck, added=added, skipped_lines=skipped)


class DueCards(BaseModel):
    deck: str
    cards: list[store.Card]


@mcp.tool(annotations=READ_ONLY)
def due_cards(deck: DeckName,
              limit: Annotated[int, Field(ge=1, le=50)] = 10) -> DueCards:
    """Return the cards due for review today, most overdue first.

    Show the user only the 'front' field; the 'back' field is for you to grade the answer.
    """
    _require_deck(deck)
    return DueCards(deck=deck, cards=store.due_cards(deck, limit))


@mcp.tool(annotations=WRITE)
def grade_card(card_id: CardId,
               grade: Annotated[int, Field(ge=0, le=5, description=(
                   "5 perfect and immediate, 4 correct with hesitation, 3 correct with difficulty, "
                   "2 wrong but recognized, 1 wrong, 0 no idea"))]) -> store.Card:
    """Record the grade of an answer and reschedule the card's next review (SM-2 algorithm)."""
    card = store.grade_card(card_id, grade)
    if card is None:
        raise ToolError(f"Card {card_id} does not exist. Use a card_id returned by due_cards.")
    return card

# === DELETION ===
class DeleteConfirmation(BaseModel):
    typed_name: str = Field(description="Type the exact deck name to confirm the deletion")


def ask_delete_confirmation(deck: str) -> Elicit[DeleteConfirmation]:
    """Resolver: asks the user to type the deck name before deleting it."""
    found = store.get_deck(deck)
    count = found.cards if found else 0
    return Elicit(f"You are about to delete the deck '{deck}' and its {count} cards. "
                  f"This cannot be undone.", DeleteConfirmation)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                      idempotentHint=True, openWorldHint=False))
def delete_deck(
    deck: DeckName,
    confirmation: Annotated[ElicitationResult[DeleteConfirmation], Resolve(ask_delete_confirmation)],
) -> str:
    """Delete a deck and all its cards. Asks the user to type the name to confirm."""
    if not isinstance(confirmation, AcceptedElicitation):
        return f"Deletion of '{deck}' cancelled by the user."
    if confirmation.data.typed_name.strip() != deck:
        return f"The typed name does not match '{deck}': deletion cancelled."
    removed = store.delete_deck(deck)
    if removed < 0:
        raise ToolError(f"Deck '{deck}' does not exist.")
    return f"Deck '{deck}' deleted along with {removed} cards."

# === RESOURCES AND PROMPTS ===
@mcp.resource("guide://sm2", name="How spaced repetition works", mime_type="text/markdown")
def sm2_guide() -> str:
    """Explanation of the 0-5 grades and how SM-2 computes the next review."""
    return ("# Spaced repetition (SM-2)\n\n"
            "Each card has an interval that grows when you answer correctly.\n\n"
            "| Grade | Meaning | Effect |\n|---|---|---|\n"
            "| 5 | perfect and immediate | long interval, easiness goes up |\n"
            "| 4 | correct with hesitation | interval grows |\n"
            "| 3 | correct with difficulty | interval grows, easiness goes down |\n"
            "| 0-2 | wrong | the card comes back tomorrow and starts over |\n\n"
            "Typical sequence with correct answers: 1 day, 6 days, then interval × easiness.\n")


@mcp.resource("deck://{name}", name="Deck content", mime_type="text/markdown")
def deck_content(name: str) -> str:
    """All the cards in a deck with their next review date."""
    deck = _require_deck(name)
    rows = "\n".join(f"| {c.front} | {c.back} | {c.due} |" for c in store.cards_in_deck(name))
    return (f"# Deck: {deck.name}\n\n{deck.description}\n\n"
            f"| Question | Answer | Next review |\n|---|---|---|\n{rows}\n")


@mcp.prompt()
def study_session(deck: str, max_cards: str = "10") -> str:
    """Start an interactive study session on a deck."""
    return (f"Let's do a study session on the deck '{deck}'. "
            f"Call due_cards with limit={max_cards}. For each card: show me ONLY the question, "
            "wait for my answer, then tell me whether it is correct and show the expected answer, "
            "assign a 0-5 grade following the guide://sm2 guide and record it with grade_card. "
            "At the end, call deck_stats and summarize my progress and what to review.")

# --Startup--
def main() -> None:
    parser = argparse.ArgumentParser(description="Study Cards MCP Server")
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--port", type=int, default=3001)
    args = parser.parse_args()
    if args.transport == "stdio":
        print("study-cards: starting on stdio", file=sys.stderr)   # NEVER on stdout
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http", port=args.port, stateless_http=True, json_response=True)


if __name__ == "__main__":
    main()