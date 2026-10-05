# Borrowed filesystem MCP server — approved calendar documents (development only)

> This directory is the **root** for the borrowed official filesystem MCP server.
> It is used in DEVELOPMENT to load approved crop-calendar PDFs/documents.
> It is NOT exposed in production.

## Why this exists

To satisfy the challenge requirement of "one MCP server you did not write", we use the official filesystem MCP server (`@modelcontextprotocol/server-filesystem`), restricted to this directory. The custom agent does not depend on it for the demo; the demo reads calendars from the database via `get_crop_calendar`. The borrowed server exists to demonstrate MCP craft alongside our custom server.

## Justification (also in `ARCHITECTURE.md`)

> We use the official filesystem MCP server to load approved crop-calendar documents during development because it provides safe, tested file access without building a custom document loader.

## How to run it

```bash
npx -y @modelcontextprotocol/server-filesystem /home/z/my-project/majishamba/docs/calendars
```

This exposes the directory over the MCP filesystem protocol. A MCP-aware client (Claude Desktop, a partner agent) can list and read files here.

## What goes here

- Approved crop-calendar PDFs from KALRO, Migori County, or other official sources.
- README-style text versions of calendars for quick parsing.
- Nothing sensitive — this directory is treated as public within the dev environment.

## What does NOT go here

- Household or plot records (those live in the database; see `data/fixtures/`).
- Real farmer names or phone numbers.
- API keys or credentials.

## Sample placeholder

`sample_calendar.txt` is included as a placeholder so the directory is not empty.
