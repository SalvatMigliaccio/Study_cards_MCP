"""Client MCP da terminale: fai tu la parte dell'host, senza un LLM.

Uso:
    uv run python scripts/study_cli.py demo            # crea il mazzo 'reti' con alcune carte
    uv run python scripts/study_cli.py study reti      # sessione di studio
    uv run python scripts/study_cli.py delete reti     # eliminazione con conferma (elicitation)
"""
import argparse
import asyncio
import sys

import anyio
from mcp import Client, StdioServerParameters, types

SERVER = StdioServerParameters(command=sys.executable, args=["-m", "study_cards_mcp.server"])

DEMO_CARDS = """\
Quale livello OSI instrada i pacchetti? :: Il livello 3, rete
Porta standard di HTTPS? :: 443
Cosa garantisce TCP rispetto a UDP? :: Consegna affidabile e ordinata
Cosa fa il protocollo ARP? :: Traduce un indirizzo IP in un indirizzo MAC
"""


async def ask(prompt: str) -> str:
    # input() è bloccante: lo eseguiamo in un thread per non fermare il client.
    return await anyio.to_thread.run_sync(input, prompt)


async def on_elicitation(context, params: types.ElicitRequestParams) -> types.ElicitResult:
    """Chiamata dal client quando il server chiede input all'utente (MRTR)."""
    print(f"\n[il server chiede] {params.message}")
    fields = params.requested_schema.get("properties", {})
    content = {}
    for name, schema in fields.items():
        value = await ask(f"  {schema.get('description', name)}: ")
        if not value:
            return types.ElicitResult(action="decline")
        content[name] = value
    return types.ElicitResult(action="accept", content=content)


async def on_progress(progress: float, total: float | None, message: str | None) -> None:
    print(f"  avanzamento: {message}")


def show(result: types.CallToolResult) -> None:
    prefix = "ERRORE: " if result.is_error else ""
    print(prefix + result.content[0].text)


async def demo(client: Client) -> None:
    show(await client.call_tool("create_deck", {"name": "reti", "description": "Esame di reti"}))
    show(await client.call_tool("import_cards", {"deck": "reti", "text": DEMO_CARDS},
                                progress_callback=on_progress))


async def study(client: Client, deck: str) -> None:
    result = await client.call_tool("due_cards", {"deck": deck, "limit": 10})
    if result.is_error:
        return show(result)
    cards = result.structured_content["cards"]
    print(f"{len(cards)} carte da ripassare oggi.\n")
    for card in cards:
        await ask(f"DOMANDA: {card['front']}\n  la tua risposta: ")
        print(f"  risposta attesa: {card['back']}")
        grade = await ask("  voto da 0 a 5: ")
        while not grade.strip().isdigit():
            grade = await ask("  scrivi un numero da 0 a 5: ")
        graded = await client.call_tool("grade_card", {"card_id": card["card_id"], "grade": int(grade)})
        if graded.is_error:
            show(graded)
        else:
            print(f"  prossima revisione: {graded.structured_content['due']}\n")
    stats = (await client.call_tool("deck_stats", {"deck": deck})).structured_content
    print(f"Statistiche: {stats}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["demo", "study", "delete"])
    parser.add_argument("deck", nargs="?", default="reti")
    args = parser.parse_args()
    async with Client(SERVER, elicitation_callback=on_elicitation) as client:
        if args.command == "demo":
            await demo(client)
        elif args.command == "study":
            await study(client, args.deck)
        else:
            show(await client.call_tool("delete_deck", {"deck": args.deck}))


asyncio.run(main())