# Security policy

## Sensitive data

Cowork transcripts can contain credentials, personal information, customer data, and other
confidential material. The built-in redactor is best effort, not a guarantee. Review generated
files before uploading, publishing, sharing, or committing them.

`export` is read-only and creates a separate portable package. `install` writes only
`AGENTS.md`, `MEMORY.md`, `HISTORY_INDEX.md`, and `HISTORY*.md` in original single-folder
workspaces. It preserves pre-existing instructions and memory in managed blocks, is idempotent,
and refuses to replace an unrelated history file. All other workspace files remain untouched.

The exporter never copies raw metadata or JSONL transcripts. Standard mode excludes system
prompts, hidden reasoning, tool calls, and tool results. `--with-evidence` adds redacted,
size-capped tool evidence and subagent history, which can still contain confidential material or
credentials that the redactor does not recognize.

Workspace memory is read from `CLAUDE.md`, root memory/context files, and `memory/**/*.md` under
the selected working folders. Hidden cross-workspace Cowork memory is exported separately and
must not be added wholesale to unrelated projects.

Do not attach real Cowork metadata, transcripts, memory, manifests, or exports to public bug
reports. Reproduce parser problems with a minimal synthetic fixture.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for issues that could expose source data or bypass
redaction. For non-sensitive defects, open a normal GitHub issue using anonymized inputs.
