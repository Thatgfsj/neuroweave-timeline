# MCP Integration

NWT ships an MCP (Model Context Protocol) server that exposes the
timeline to AI agents. The server speaks stdio transport and exposes
four tools.

## Running the server

After `pip install -e .`:

```bash
nwt-mcp                # uses cwd as the project root
NWT_ROOT=/path/to/proj nwt-mcp
```

Inside an MCP-aware client (e.g. Claude Desktop), register the server
with:

```json
{
  "mcpServers": {
    "nwt": {
      "command": "nwt-mcp",
      "args": [],
      "env": { "NWT_ROOT": "/path/to/your/project" }
    }
  }
}
```

The workspace is read from `$NWT_ROOT` if set, else the current working
directory of the MCP process.

## Tools

### `create_event`

Append a new event. The agent should call this *as it does work*, not
after the fact.

```json
{
  "task": "Add activation engine",
  "summary": "Spread activation through the graph",
  "reason": "Sequential retrieval was too slow",
  "files": ["activation.py"],
  "tags": ["memory", "optimization"],
  "parent": "000007"
}
```

### `search_history`

Substring search across the timeline.

```json
{ "query": "performance", "limit": 10 }
```

`search_files` and `search_tags` flags let the agent narrow the
search if it knows it's looking for, say, a tag.

### `get_project_story`

Returns a structured project story with:

* project name and event count
* first and last events
* the spine file (most-touched file)
* up to `max_milestones` milestone events
* all decision events (those with a `reason`)
* a `text` field pre-rendered for LLM context

This is the tool an agent should call when it wants the "big picture".

### `explain_file`

Trace a file's history.

```json
{ "file_path": "activation.py" }
```

Returns:

* `created_in` — id of the first event that touched the file
* `modified_in` — ids of subsequent events
* `reason` — the earliest recorded reason (the *why*)
* `events` — full event dicts
* `text` — pre-rendered for LLM context

This is the tool an agent should call when it sees a file it doesn't
recognize and wants to understand its origin.

## Recommended agent workflow

1. **At the start of a session**, call `get_project_story` to load
   context.
2. **For unfamiliar files**, call `explain_file` rather than reading
   the file cold.
3. **As work is done**, call `create_event` with a `reason` explaining
   *why*. This is what makes the next session faster.
4. **When uncertain**, call `search_history` with a hypothesis from
   the current code (a function name, a file path, a tag).

The goal: every NWT-using agent should leave a project a little more
self-explanatory than it found it.
