<h1 align="center">cowork-to-chatgpt</h1>

<p align="center">
  Move Claude Cowork memory and conversation history into simple, isolated files that ChatGPT and Codex understand.
</p>

<p align="center">
  <a href="https://github.com/tomascupr/cowork-to-chatgpt/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/tomascupr/cowork-to-chatgpt/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white">
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-green.svg"></a>
  <img alt="Runtime dependencies: zero" src="https://img.shields.io/badge/runtime_dependencies-0-brightgreen">
</p>

One command turns your local Cowork archive into one portable context folder per workspace:

```text
Claude Cowork                       ChatGPT-ready workspace
──────────────────────              ─────────────────────────
Selected workspace folder  ─┐       AGENTS.md
  CLAUDE.md                  ├────▶  MEMORY.md
  memory/**/*.md             │       HISTORY_INDEX.md
Hidden session transcripts  ─┘       HISTORY.md
```

Your source stays untouched. Unrelated workspaces never get mixed. No cloud API is required.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
uv tool install git+https://github.com/tomascupr/cowork-to-chatgpt.git

# Preview the workspace boundaries
cowork2chatgpt scan

# Export everything
cowork2chatgpt export
```

The result is written to `chatgpt-context-YYYY-MM-DD/`.

To run from a clone instead:

```bash
git clone https://github.com/tomascupr/cowork-to-chatgpt.git
cd cowork-to-chatgpt
uv sync --locked
uv run cowork2chatgpt scan
uv run cowork2chatgpt export
```

## The output

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

Each normal workspace folder is ready to use:

| File | Purpose |
|---|---|
| `AGENTS.md` | Tells Codex how to load the context safely |
| `MEMORY.md` | Durable workspace memory and structured user preferences |
| `HISTORY_INDEX.md` | Searchable session index and an honest transfer-coverage report |
| `HISTORY.md` | Human and assistant conversation history |

Large histories become numbered `HISTORY_001.md`, `HISTORY_002.md`, and so on.

### Use it with Codex

Open one exported workspace folder. Codex reads `AGENTS.md`, which points it to durable memory and
tells it to search history only when relevant.

### Use it with ChatGPT Projects

Upload every Markdown file from one workspace folder. If ChatGPT asks for Project instructions,
use the contents of `AGENTS.md`.

### Keep working in your existing Cowork folder

You do not have to move anything. Cowork folders are ordinary folders. You can open the same
folder in Codex, or copy/merge the exported memory and history into it. Never overwrite an
existing `AGENTS.md` or `MEMORY.md`; merge them intentionally.

## Memory that actually follows the workspace

For every selected workspace folder, the exporter looks for:

- `CLAUDE.md`
- `MEMORY.md` or `memory.md`
- `CONTEXT.md` or `context.md`
- every Markdown file under `memory/`
- structured `<user_preferences>` stored with the relevant Cowork sessions

Cowork's hidden global memory may contain facts from several projects. It is therefore exported
to `_shared-memory/MEMORY.md` for selective review and is never injected into workspace memory.

## Isolation is a hard rule

| Cowork session | Export behavior |
|---|---|
| Same canonical selected-folder set | Grouped into one workspace |
| Several selected folders | Kept as a distinct composite workspace |
| No selected folder | Kept as its own one-session workspace |
| Hidden global memory | Quarantined under `_shared-memory` |

Do not combine exported workspace folders unless you intentionally want their contexts mixed.

## Useful options

```bash
# Export one workspace shown by `scan`
cowork2chatgpt export ./context --workspace duvo

# Only sessions active since a date
cowork2chatgpt export ./recent --since 2026-06-01

# Skip sessions archived in Cowork
cowork2chatgpt export ./active --exclude-archived

# Add redacted, size-capped tool evidence and subagent history
cowork2chatgpt export ./evidence --with-evidence

# Do not export hidden global memory for review
cowork2chatgpt export ./context --no-shared-memory

# Use an explicit Cowork data location
cowork2chatgpt export ./context --source "/path/to/local-agent-mode-sessions"
```

Run `cowork2chatgpt export --help` for the complete CLI reference.

## Privacy model

The default export preserves durable user context without copying the entire execution trace.

| Data | Default | `--with-evidence` |
|---|---:|---:|
| User and assistant text | Included | Included |
| Workspace-owned memory | Included | Included |
| Tool calls and results | Excluded | Redacted and size-capped |
| Subagent history | Excluded | Included |
| Attachment descriptors | Excluded | Included |
| Hidden reasoning | Excluded | Excluded |
| System prompts | Excluded | Excluded |
| Raw metadata and JSONL | Excluded | Excluded |

Credential redaction is best effort, not a security guarantee. Review files before uploading or
sharing them. Every workspace's `HISTORY_INDEX.md` reports what was included, omitted, truncated,
or unreadable.

## Data location and support

On macOS, Cowork data is auto-detected at:

```text
~/Library/Application Support/Claude/local-agent-mode-sessions
```

Set `COWORK_DATA_DIR` or pass `--source` for custom locations. Only locally persisted Cowork
sessions can be exported; cloud-only Claude conversations may not be present.

Cowork's local format is undocumented and can change. If you find a new record shape, open an
issue with a minimal synthetic fixture. Never publish real transcripts, metadata, or memory.

## Development

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run python -m unittest discover -s tests -v
uv run python -m compileall -q src tests
uv build
```

The project has zero runtime dependencies and uses only Python's standard library.

## License

[MIT](LICENSE)
