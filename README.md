# study-cards-mcp

An [MCP](https://modelcontextprotocol.io) server for studying with flashcards and **spaced repetition** (the SM-2 algorithm).
Create decks, add cards and review them right in the chat: the model shows you the question, grades your answer and schedules the next review. Decks and cards are stored in a local SQLite database.

## What it exposes

| Type | Name | Purpose |
|---|---|---|
| Tool | `list_decks` | Lists the decks with their card counts |
| Tool | `create_deck` | Creates an empty deck |
| Tool | `deck_stats` | Cards due today, new, learning and mature |
| Tool | `add_card` | Adds a single card |
| Tool | `import_cards` | Imports many cards from text (`question :: answer`, one per line), with progress notifications |
| Tool | `due_cards` | Cards due today, most overdue first |
| Tool | `grade_card` | Records a 0–5 grade and reschedules the card |
| Tool | `delete_deck` | Deletes a deck after the user types its name to confirm (elicitation) |
| Resource | `guide://sm2` | Guide to the grades and how SM-2 computes intervals |
| Resource | `deck://{name}` | Full content of a deck, with review dates |
| Prompt | `study_session` | Starts a guided study session on a deck |

Deck names are lowercase with hyphens, 2 to 40 characters long, for example `computer-networks`.

## Requirements

- Python 3.14 or later
- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
git clone <repo-url> study-cards-mcp
cd study-cards-mcp
uv sync
```

## Connecting it to Claude Code

Replace the path with the absolute path of the project folder:

```bash
claude mcp add study-cards \
  -e STUDY_CARDS_DB=/absolute/path/study-cards-mcp/study_cards.db \
  -- uv run --directory /absolute/path/study-cards-mcp study-cards-mcp
```

On Windows, use a path like `D:/Projects/study-cards-mcp`. By default the server is added to the current project only; add `-s user` to make it available in every project.

Check with `claude mcp list`: you should see `study-cards ... ✔ Connected`. If you see `Connection closed`, the path passed to `--directory` is almost always wrong.

### Other MCP hosts

For clients configured with a JSON file (such as Claude Desktop):

```json
{
  "mcpServers": {
    "study-cards": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/study-cards-mcp", "study-cards-mcp"],
      "env": { "STUDY_CARDS_DB": "/absolute/path/study-cards-mcp/study_cards.db" }
    }
  }
}
```

## How to use it with Claude

Once the server is connected, just talk to Claude in plain language: it picks the right tool on its own. In Claude Code you can type `/mcp` to check that `study-cards` and its tools are loaded.

### 1. Create a deck and add cards

> Create a deck called `computer-networks` for my networking exam.

> Add these cards to `computer-networks`:
> What does ARP do? :: Maps an IP address to a MAC address
> Default HTTPS port? :: 443
> What does TCP guarantee over UDP? :: Reliable, ordered delivery

For a few cards Claude uses `add_card`; for a longer list it uses `import_cards`, one `question :: answer` per line. Blank lines and lines starting with `#` are ignored, and malformed lines are reported back to you. You can also ask Claude to write the cards for you, for example *"Make 20 flashcards from these lecture notes and add them to `computer-networks`"*.

### 2. Study

Start a session with the built-in prompt:

```
/study-cards:study_session computer-networks
```

In Claude Desktop and other hosts, pick `study_session` from the prompt menu, or simply ask *"Let's study `computer-networks`"*.

During the session Claude:

1. fetches the cards due today with `due_cards`;
2. shows you **only the question** of one card at a time;
3. waits for your answer, then shows the expected one;
4. grades your answer from 0 to 5 and saves it with `grade_card`, which schedules the next review;
5. at the end, summarizes your progress with `deck_stats`.

If you think a grade is wrong, say so before Claude saves it. Grading the same card again does not undo the first grade: it counts as a second review.

### 3. Check progress and manage decks

> Which decks do I have?

> How am I doing on `computer-networks`?

> Show me all the cards in `computer-networks`.

The last request reads the `deck://computer-networks` resource. In Claude Code you can also attach it directly by typing `@study-cards:deck://computer-networks`.

> Delete the `computer-networks` deck.

Before deleting, the server asks **you**, not Claude, to type the deck name to confirm. If you cancel or type a different name, nothing is deleted.

### Tips

- Study a little every day: cards only come back when they are due, so a deck with nothing due today is good news.
- Keep each card about one fact; short answers are easier to grade fairly.
- Ask Claude *"How does the grading work?"* to have it read the `guide://sm2` resource.

## Running it manually

```bash
uv run study-cards-mcp                              # stdio (default, for local hosts)
uv run study-cards-mcp --transport http --port 3001 # stateless HTTP on http://127.0.0.1:3001/mcp
```

On stdio the server logs to stderr only: stdout is reserved for protocol messages.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `STUDY_CARDS_DB` | `study_cards.db` (in the working directory) | Path to the SQLite database. Use an absolute path: the host may start the server from any folder. |
| `STUDY_CARDS_STATE_KEY` | temporary key | Key used to encrypt the state of multi-step requests, such as the `delete_deck` confirmation. Without one, a new key is generated at every start: that is fine for a single process, but if you run several instances behind HTTP, set the same key on all of them. |

## How SM-2 works

After each answer you give a grade:

| Grade | Meaning |
|---|---|
| 5 | Perfect, immediate recall |
| 4 | Correct after some hesitation |
| 3 | Correct, with difficulty |
| 2 | Wrong, but the right answer felt familiar |
| 1 | Wrong |
| 0 | No idea |

With a grade of 3 or more the interval grows: 1 day, then 6 days, then the previous interval multiplied by the card's *easiness factor* (starts at 2.5, minimum 1.3). With a grade below 3 the card starts over and comes back the next day. The grade also adjusts the easiness, so cards you often get wrong come back more frequently.

The logic lives in [`sm2.py`](src/study_cards_mcp/sm2.py), which depends on neither MCP nor the database.

## Test scripts

The `scripts/` folder contains three clients for trying the server without an LLM:

```bash
uv run python scripts/check.py              # lists the exposed tools, resources and prompts
uv run python scripts/study_cli.py demo     # creates the 'reti' deck with a few sample cards
uv run python scripts/study_cli.py study reti
uv run python scripts/study_cli.py delete reti
```

`http_check.py` sends raw JSON-RPC requests to the HTTP transport so you can see the protocol messages, including the two-round `delete_deck` confirmation. Start the server in another terminal first:

```bash
uv run study-cards-mcp --transport http --port 3001
uv run python scripts/http_check.py
```

## Tests

```bash
uv run pytest
```

## Layout

```
src/study_cards_mcp/
  server.py   MCP tools, resources and prompt; stdio or HTTP startup
  store.py    SQLite storage for decks and cards
  sm2.py      SM-2 algorithm, pure logic
scripts/      test clients
tests/        pytest tests
```
