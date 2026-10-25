"""Controllo rapido: avvia il server su stdio, come farebbe un host, ed elenca cosa espone."""
import asyncio
import sys

from mcp import Client, StdioServerParameters

# Lancia il server con lo stesso Python dell'ambiente virtuale del progetto.
SERVER = StdioServerParameters(command=sys.executable, args=["-m", "study_cards_mcp.server"])


async def main() -> None:
    async with Client(SERVER) as client:
        tools = (await client.list_tools()).tools
        print(f"Tool ({len(tools)}):")
        for t in tools:
            print(f"  - {t.name}: {(t.description or '').splitlines()[0]}")

        resources = (await client.list_resources()).resources
        templates = (await client.list_resource_templates()).resource_templates
        print(f"Resource ({len(resources)}) e template ({len(templates)}):")
        for r in resources:
            print(f"  - {r.uri}")
        for t in templates:
            print(f"  - {t.uri_template}")

        prompts = (await client.list_prompts()).prompts
        print(f"Prompt ({len(prompts)}):")
        for p in prompts:
            print(f"  - /{p.name}: {p.description}")


asyncio.run(main())