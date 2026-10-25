# study-cards-mcp

An [MCP](https://modelcontextprotocol.io) server for studying with flashcards and **spaced repetition** (the SM-2 algorithm).
Create decks, add cards and review them right in the chat: the model shows you the question, grades your answer and schedules the next review. Decks and cards are stored in a local SQLite database.

## What it exposes

| Type | Name | Purpose |
|---|---|---|
| Tool | `list_decks` | Lists the decks with their card counts |
| Tool | `create_deck` | Creates an empty deck |
| Tool | `deck_stats` | Cards due today, new, learning and mature |
| Tool | `add_card` | Adds a single card, with an optional source |
| Tool | `add_cards` | Saves a batch of up to 50 cards written by Claude (e.g. from a PDF), each with its source; skips duplicates |
| Tool | `import_cards` | Imports many cards from text (`question :: answer`, one per line), with progress notifications |
| Tool | `due_cards` | Cards due today, most overdue first |
| Tool | `grade_card` | Records a 0–5 grade and reschedules the card |
| Tool | `delete_deck` | Deletes a deck after the user types its name to confirm (elicitation) |
| Resource | `guide://sm2` | Guide to the grades and how SM-2 computes intervals |
| Resource | `deck://{name}` | Full content of a deck, with sources and review dates |
| Prompt | `study_session` | Starts a guided study session on a deck |
| Prompt | `cards_from_document` | Turns an attached document (PDF, notes, slides) into flashcards |

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

## Connecting it to Claude Desktop

Claude Desktop starts the server on your own computer, just like Claude Code, so nothing has to be published online.

1. Install Claude Desktop from [claude.ai/download](https://claude.ai/download) and sign in.
2. Open **Settings → Developer → Edit Config**. This opens the folder that contains `claude_desktop_config.json`.
3. Add a top-level `"mcpServers"` key with the `study-cards` entry, next to the keys already in the file (such as `"preferences"`), not inside them:

   ```json
   {
     "preferences": { "...": "..." },
     "mcpServers": {
       "study-cards": {
         "command": "C:\\Users\\<you>\\.local\\bin\\uv.exe",
         "args": ["run", "--directory", "D:\\path\\to\\study-cards-mcp", "study-cards-mcp"],
         "env": { "STUDY_CARDS_DB": "D:\\path\\to\\study-cards-mcp\\study_cards.db" }
       }
     }
   }
   ```

   - Remember the comma after the `}` that closes the key before `"mcpServers"`. If the JSON is invalid, Claude Desktop loads no MCP servers at all.
   - Use the **full path to `uv`**: Claude Desktop does not always see the same `PATH` as your terminal. Find it with `where uv` on Windows or `which uv` on macOS/Linux. On macOS/Linux, use normal forward-slash paths.
   - If `STUDY_CARDS_DB` points to the same file you use in Claude Code, both apps share the same decks.
4. **Quit Claude Desktop completely** (on Windows, right-click the tray icon near the clock and choose **Quit**; closing the window is not enough) and open it again.
5. Check the connection: in a new chat, click **+ → Connectors**. `study-cards` should be listed and switched on, and **Add from study-cards** shows the *Study session* and *Cards from document* prompts and the *How spaced repetition works* resource. If the server is missing or shows an error, see **Settings → Developer** for its status and logs.

`deck://{name}` does not appear in that menu: it needs a deck name, so Claude reads it when you ask to see the cards of a deck.

### Quick test

Run through these steps in a new chat to check that everything works:

1. **Connection:** ask *"Which decks do I have?"*. The first time, Claude asks for permission to use `list_decks`; you can allow read-only tools permanently.
2. **Cards from a PDF:** attach a PDF with **+ → Upload file**, then choose **+ → Connectors → Add from study-cards → Cards from document**. Fill in `document` (the file name), `deck` (`test-pdf`) and `num_cards` (`10`). Claude shows you a draft: reply "ok" and check that it calls `create_deck` and `add_cards`.
3. **Duplicates:** repeat step 2 with the same PDF. Claude should report the cards as already present (`duplicates`).
4. **Study:** choose **Study session** with `deck` = `test-pdf`, answer 2–3 questions and look at the stats at the end.
5. **Sources:** ask *"Show me all the cards in `test-pdf`"*. The table should have a Source column with file and page.
6. **Deletion:** ask *"Delete the deck `test-pdf`"*. A form should ask you to type the deck name. If you get "cancelled" instead, your Claude Desktop version does not support this kind of request (elicitation) yet: the deck is kept, and it is not a server error.

### claude.ai in the browser

claude.ai cannot reach a server running on your computer: it only accepts MCP servers reachable from the internet, added as a **custom connector** in **Settings → Connectors**. You would have to run the server with `--transport http` and expose it through a tunnel such as `ngrok` or `cloudflared`. The server has no authentication, so anyone with the URL could read and delete your decks. Use Claude Desktop or Claude Code instead.

### Other MCP hosts

Any MCP client that can start a local stdio server works. Most use the same JSON shape as Claude Desktop:

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

Once the server is connected, just talk to Claude in plain language: it picks the right tool on its own. In Claude Code you can type `/mcp` to check that `study-cards` and its tools are loaded; in Claude Desktop, look under **+ → Connectors**.

### 1. Create a deck and add cards

> Create a deck called `computer-networks` for my networking exam.

> Add these cards to `computer-networks`:
> What does ARP do? :: Maps an IP address to a MAC address
> Default HTTPS port? :: 443
> What does TCP guarantee over UDP? :: Reliable, ordered delivery

For a few cards Claude uses `add_card`; for a longer list it uses `import_cards`, one `question :: answer` per line. Blank lines and lines starting with `#` are ignored, and malformed lines are reported back to you.

### 2. Create cards from a PDF

Claude can read a PDF (or slides, or notes) and write the flashcards for you. The server never opens the file itself: Claude reads the document, writes the cards and saves them with `add_cards`, storing for each card the file and page it came from.

**1. Give Claude the document.**

- In **Claude Code**, reference the file with `@`, for example `@notes/networks-lecture-3.pdf`, or drag it into the prompt.
- In **Claude Desktop**, attach the PDF with **+ → Upload file**.

**2. Ask for the cards** using the built-in prompt. Its arguments are, in order: the document name, the deck, the number of cards (default 20) and an optional topic to focus on.

```
/study-cards:cards_from_document networks-lecture-3.pdf computer-networks 30 routing
```

In Claude Desktop, choose **+ → Connectors → Add from study-cards → Cards from document** and fill in the fields. You can also just ask in your own words:

> Read @notes/networks-lecture-3.pdf and make about 30 flashcards for the `computer-networks` deck, focusing on routing.

**3. Review the draft.** Claude first shows you the list of cards and waits. Ask for changes before anything is saved, for example *"drop cards 4 and 9"*, *"make the answer to card 12 shorter"* or *"add more cards on chapter 2"*.

**4. Confirm.** When you say ok, Claude creates the deck if it does not exist yet, saves the cards in batches of up to 50 and tells you how many were added.

Each card follows a few rules from the prompt: one idea per card, questions that make sense without the document, answers taken from the document only, and coverage of the whole document rather than just the first pages.

You can run the same PDF again, or a new version of it: questions already in the deck are skipped as duplicates (ignoring case and extra spaces), so you only get the new ones. To see where each card came from, ask Claude to *"show me all the cards in `computer-networks`"*: the table includes a **Source** column, such as `networks-lecture-3.pdf, p. 12`.

> **Tip:** for long documents (100+ pages), work one chapter or topic at a time, for example *"make 25 flashcards from chapter 4 of @textbook.pdf for `computer-networks`"*. You get better cards than asking for 200 at once.

### 3. Study

Start a session with the built-in prompt:

```
/study-cards:study_session computer-networks
```

In Claude Desktop, choose **+ → Connectors → Add from study-cards → Study session**; in other hosts, pick `study_session` from the prompt menu. Or simply ask *"Let's study `computer-networks`"*.

During the session Claude:

1. fetches the cards due today with `due_cards`;
2. shows you **only the question** of one card at a time;
3. waits for your answer, then shows the expected one;
4. grades your answer from 0 to 5 and saves it with `grade_card`, which schedules the next review;
5. at the end, summarizes your progress with `deck_stats`.

If you think a grade is wrong, say so before Claude saves it. Grading the same card again does not undo the first grade: it counts as a second review.

### 4. Check progress and manage decks

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
