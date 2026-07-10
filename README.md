# cowork-to-chatgpt

Move Claude Cowork memory and conversation history into simple files that ChatGPT and Codex can
use immediately.

The exporter is read-only. It does not move, rename, or modify your Cowork folders. It finds the
workspace attached to each local Cowork session, keeps unrelated workspaces separate, and creates
one portable context folder for each workspace.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/tomascupr/cowork-to-chatgpt.git
cd cowork-to-chatgpt
uv sync

# See what will be exported
uv run cowork2chatgpt scan

# Export every workspace
uv run cowork2chatgpt export
```

The default output is `chatgpt-context-YYYY-MM-DD/`.

## What you get

```text
chatgpt-context-2026-07-10/
├── README.md
├── manifest.json
├── duvo/
│   ├── AGENTS.md
│   ├── MEMORY.md
│   ├── HISTORY_INDEX.md
│   └── HISTORY.md
├── another-workspace/
│   └── ...
└── _shared-memory/
    └── MEMORY.md
```

Every normal workspace folder is self-contained:

- `AGENTS.md` tells Codex how to use the imported context safely.
- `MEMORY.md` combines structured Cowork preferences with the workspace's existing `CLAUDE.md`,
  root `MEMORY.md`/`CONTEXT.md`, and `memory/**/*.md` files.
- `HISTORY_INDEX.md` lists sessions and states what was preserved or omitted.
- `HISTORY.md` contains the conversations. Large histories become numbered `HISTORY_*.md` files.

ChatGPT/Codex desktop can open the exported workspace folder directly. For ChatGPT Projects,
upload every Markdown file from one workspace folder; if asked for Project instructions, use the
contents of `AGENTS.md`.

You can also keep working in the original Cowork folder. Nothing about that folder is
Claude-specific. Copy or merge the exported memory/history files into it only if you want the old
conversations available there. Do not overwrite an existing `AGENTS.md` or `MEMORY.md`.

## Workspace isolation

Isolation is a hard rule:

- Sessions with the same canonical selected-folder set belong to one workspace.
- A session with several selected folders belongs to a distinct composite workspace.
- A session with no selected folder gets its own one-session workspace.
- Hidden cross-workspace Cowork memory is quarantined under `_shared-memory` and never copied into
  workspace memory automatically.

Do not combine exported workspace folders unless you intentionally want their contexts mixed.

## Useful options

```bash
# Export just one workspace
uv run cowork2chatgpt export ./context --workspace duvo

# Only recent sessions
uv run cowork2chatgpt export ./recent --since 2026-06-01

# Skip sessions archived in Cowork
uv run cowork2chatgpt export ./active --exclude-archived

# Add redacted, size-capped tool evidence and subagent history
uv run cowork2chatgpt export ./evidence --with-evidence

# Do not export hidden cross-workspace memory for review
uv run cowork2chatgpt export ./context --no-shared-memory

# Use an explicit Cowork data location
uv run cowork2chatgpt export ./context --source "/path/to/local-agent-mode-sessions"
```

The source is auto-detected on macOS at
`~/Library/Application Support/Claude/local-agent-mode-sessions`. Set `COWORK_DATA_DIR` or pass
`--source` for other locations.

## What is deliberately excluded

The default export contains human and assistant text. It excludes hidden reasoning, system
prompts, tool calls/results, binary attachment bodies, and operational records. These are not
durable user memory and can contain credentials, stale instructions, or large amounts of noise.

`--with-evidence` adds redacted tool calls/results, attachment descriptors, and subagent history.
It still excludes hidden reasoning and system prompts.

Credential redaction is best effort, not a security guarantee. Review files before uploading or
sharing them. The source format is undocumented and may change; `HISTORY_INDEX.md` and
`manifest.json` expose parser warnings and transfer coverage.

## Development

```bash
uv sync
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q src tests
uv build
```

Use synthetic fixtures in issues and tests. Never publish real transcripts, metadata, or memory.

## License

[MIT](LICENSE)
