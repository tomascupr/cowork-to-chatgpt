<h1 align="center">cowork-to-chatgpt</h1>

<p align="center">
  Move Claude Cowork memory and conversation history into the original workspace folders where ChatGPT and Codex can use them.
</p>

<p align="center">
  <a href="https://github.com/tomascupr/cowork-to-chatgpt/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/tomascupr/cowork-to-chatgpt/actions/workflows/ci.yml/badge.svg"></a>
  <img alt="Python 3.11+" src="https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white">
  <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/license-MIT-green.svg"></a>
  <img alt="Runtime dependencies: zero" src="https://img.shields.io/badge/runtime_dependencies-0-brightgreen">
</p>

One command installs Cowork context into the folders where you already work:

```text
Claude Cowork                       Original workspace folder
──────────────────────              ─────────────────────────
Selected workspace folder  ─┐       existing files (preserved)
  CLAUDE.md                  ├────▶  AGENTS.md
  memory/**/*.md             │       MEMORY.md
Hidden session transcripts  ─┘       HISTORY_INDEX.md + HISTORY.md
```

Existing instructions and memory are preserved. Unrelated workspaces never get mixed. No cloud
API is required.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
uv tool install git+https://github.com/tomascupr/cowork-to-chatgpt.git

# Preview the workspace boundaries
cowork2chatgpt scan

# Install context into the original workspace folders
cowork2chatgpt install
```

`install` adds or updates the context files in every original single-folder workspace. It is
idempotent: running it again refreshes the managed sections without duplicating them. Existing
`AGENTS.md` and `MEMORY.md` content remains intact.

To run from a clone instead:

```bash
git clone https://github.com/tomascupr/cowork-to-chatgpt.git
cd cowork-to-chatgpt
uv sync --locked
uv run cowork2chatgpt scan
uv run cowork2chatgpt install
```

## What is installed

```text
your-existing-workspace/
├── your existing files...
├── AGENTS.md
├── MEMORY.md
├── HISTORY_INDEX.md
└── HISTORY.md
```

| File | Purpose |
|---|---|
| `AGENTS.md` | Existing instructions plus a managed section telling Codex how to load context |
| `MEMORY.md` | Existing memory plus workspace-owned Cowork memory and user preferences |
| `HISTORY_INDEX.md` | Searchable session index and an honest transfer-coverage report |
| `HISTORY.md` | Human and assistant conversation history |

Large histories become numbered `HISTORY_001.md`, `HISTORY_002.md`, and so on.

The installer refuses to overwrite unrelated `HISTORY.md` files. Composite workspaces remain
separate instead of being copied into each constituent folder. Sessions without a selected folder
also remain separate. Use the portable export for those contexts.

## Portable export

Use `export` when you want standalone folders for ChatGPT Projects, backup, composite workspaces,
or unassigned sessions:

```bash
cowork2chatgpt export
```

The result is written to `chatgpt-context-YYYY-MM-DD/`:

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

### Use it with Codex

After `install`, keep opening your original workspace folder. Codex reads `AGENTS.md`, which
points it to durable memory and tells it to search history only when relevant.

### Use it with ChatGPT Projects

For a ChatGPT Project, upload every Markdown file from one portable export folder. If ChatGPT asks
for Project instructions, use the contents of `AGENTS.md`.

### Keep working in your existing Cowork folder

You do not have to move anything. Cowork folders are ordinary folders, and `install` writes the
context into those folders directly. Only the four context-file families are managed. All other
workspace files remain untouched.

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
# Install one workspace shown by `scan`
cowork2chatgpt install --workspace duvo

# Only sessions active since a date
cowork2chatgpt install --since 2026-06-01

# Skip sessions archived in Cowork
cowork2chatgpt install --exclude-archived

# Add redacted, size-capped tool evidence and subagent history
cowork2chatgpt install --with-evidence

# Create portable packages instead of changing original folders
cowork2chatgpt export

# Do not export hidden global memory for review
cowork2chatgpt export ./context --no-shared-memory

# Use an explicit Cowork data location
cowork2chatgpt export ./context --source "/path/to/local-agent-mode-sessions"
```

Run `cowork2chatgpt install --help` or `cowork2chatgpt export --help` for the complete CLI
reference.

## Privacy model

The default transfer preserves durable user context without copying the entire execution trace.

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
or unreadable. Installed memory and history may be sensitive; do not commit them to a public
repository.

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
