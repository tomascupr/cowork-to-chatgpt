from __future__ import annotations

import json
import math
import os
import re
import shutil
import sys
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Iterable


DEFAULT_TARGET_CHARS = 1_500_000
MAX_PROJECT_TEXT_CHARS = 7_000_000


class CoworkExportError(RuntimeError):
    """Raised when Cowork data cannot be discovered or exported safely."""


@dataclass(frozen=True)
class Session:
    session_id: str
    cli_session_id: str
    title: str
    created_at: datetime | None
    last_activity_at: datetime | None
    archived: bool
    selected_folders: tuple[str, ...]
    metadata_path: Path
    workspace_path: Path
    main_transcript: Path | None
    sidechain_transcripts: tuple[Path, ...]


@dataclass(frozen=True)
class Turn:
    role: str
    text: str
    timestamp: datetime | None
    event_id: str | None


@dataclass(frozen=True)
class SessionExport:
    session: Session
    markdown: str
    turn_count: int
    artifact_names: tuple[str, ...]
    warning_count: int
    archive_filename: str


@dataclass(frozen=True)
class ExportOptions:
    source: Path
    output: Path
    since: date | None = None
    exclude_archived: bool = False
    include_sidechains: bool = False
    redact: bool = True
    max_project_files: int = 20
    target_chunk_chars: int = DEFAULT_TARGET_CHARS


@dataclass(frozen=True)
class ExportReport:
    output: Path
    sessions_discovered: int
    sessions_exported: int
    sessions_without_transcripts: int
    memory_files: int
    project_files: int
    transcript_warnings: int
    secrets_redacted: int


class Redactor:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.replacements = 0

    def redact(self, text: str) -> str:
        text = normalize_home(text)
        if not self.enabled:
            return text

        substitutions: tuple[tuple[re.Pattern[str], str], ...] = (
            (
                re.compile(
                    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?"
                    r"-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
                    re.DOTALL,
                ),
                "[REDACTED PRIVATE KEY]",
            ),
            (
                re.compile(
                    r"\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{16,}"
                    r"|github_pat_[A-Za-z0-9_]{20,}"
                    r"|gh[pousr]_[A-Za-z0-9]{20,}"
                    r"|xox[baprs]-[A-Za-z0-9-]{16,}"
                    r"|AKIA[A-Z0-9]{16}"
                    r"|AIza[A-Za-z0-9_-]{20,})\b"
                ),
                "[REDACTED TOKEN]",
            ),
            (
                re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/-]{12,}=*"),
                "Bearer [REDACTED]",
            ),
        )

        for pattern, replacement in substitutions:
            text, count = pattern.subn(replacement, text)
            self.replacements += count

        assignment = re.compile(
            r"(?im)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)"
            r"\b\s*[:=]\s*[\"']?)([A-Za-z0-9_./+=:-]{8,})([\"']?)"
        )

        def replace_assignment(match: re.Match[str]) -> str:
            self.replacements += 1
            return f"{match.group(1)}[REDACTED]{match.group(3)}"

        return assignment.sub(replace_assignment, text)


def default_source_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    override = os.environ.get("COWORK_DATA_DIR")
    if override:
        candidates.append(Path(override).expanduser())

    if sys.platform == "darwin":
        candidates.append(
            Path.home()
            / "Library"
            / "Application Support"
            / "Claude"
            / "local-agent-mode-sessions"
        )
    elif sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            candidates.append(Path(appdata) / "Claude" / "local-agent-mode-sessions")
    else:
        candidates.append(
            Path.home() / ".config" / "Claude" / "local-agent-mode-sessions"
        )

    return tuple(dict.fromkeys(candidates))


def resolve_source(explicit: Path | None = None) -> Path:
    if explicit:
        source = explicit.expanduser().resolve()
        if not source.is_dir():
            raise CoworkExportError(f"Cowork data directory not found: {source}")
        return source

    for candidate in default_source_candidates():
        if candidate.is_dir():
            return candidate.resolve()

    checked = (
        ", ".join(str(path) for path in default_source_candidates())
        or "no default paths"
    )
    raise CoworkExportError(
        "Could not find Cowork's local data directory. "
        f"Checked {checked}. Pass --source or set COWORK_DATA_DIR."
    )


def discover_sessions(source: Path) -> tuple[list[Session], list[str]]:
    if not source.is_dir():
        raise CoworkExportError(f"Cowork data directory not found: {source}")

    sessions: list[Session] = []
    warnings: list[str] = []

    for metadata_path in sorted(source.rglob("local_*.json")):
        workspace_path = metadata_path.with_suffix("")
        if not workspace_path.is_dir():
            continue

        try:
            data = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            warnings.append(f"Could not read {metadata_path}: {error}")
            continue

        if not isinstance(data, dict):
            continue

        session_id = str(data.get("sessionId") or metadata_path.stem)
        cli_session_id = str(data.get("cliSessionId") or "")
        if not session_id.startswith("local_"):
            continue

        title = clean_title(data.get("title"), data.get("initialMessage"), session_id)
        selected_folders = tuple(
            normalize_home(str(folder))
            for folder in data.get("userSelectedFolders", [])
            if isinstance(folder, str)
        )
        main, sidechains = locate_transcripts(workspace_path, cli_session_id)

        sessions.append(
            Session(
                session_id=session_id,
                cli_session_id=cli_session_id,
                title=title,
                created_at=parse_timestamp(data.get("createdAt")),
                last_activity_at=parse_timestamp(data.get("lastActivityAt")),
                archived=bool(data.get("isArchived", False)),
                selected_folders=selected_folders,
                metadata_path=metadata_path,
                workspace_path=workspace_path,
                main_transcript=main,
                sidechain_transcripts=sidechains,
            )
        )

    sessions.sort(key=session_sort_key, reverse=True)
    return sessions, warnings


def locate_transcripts(
    workspace_path: Path, cli_session_id: str
) -> tuple[Path | None, tuple[Path, ...]]:
    projects_path = workspace_path / ".claude" / "projects"
    if not projects_path.is_dir():
        return None, ()

    all_transcripts = sorted(projects_path.rglob("*.jsonl"))
    if not all_transcripts:
        return None, ()

    main_candidates = [
        path
        for path in all_transcripts
        if cli_session_id and path.stem == cli_session_id
    ]
    if not main_candidates:
        main_candidates = [
            path for path in all_transcripts if "subagents" not in path.parts
        ]

    main = (
        min(main_candidates, key=lambda path: len(path.parts))
        if main_candidates
        else None
    )
    sidechains = tuple(path for path in all_transcripts if path != main)
    return main, sidechains


def parse_session(
    session: Session, *, include_sidechains: bool, redactor: Redactor
) -> tuple[list[Turn], int]:
    if session.main_transcript is None:
        return [], 0

    paths = [session.main_transcript]
    if include_sidechains:
        paths.extend(session.sidechain_transcripts)

    ordered_turns: list[tuple[datetime, int, int, Turn]] = []
    warnings = 0
    seen_event_ids: set[str] = set()

    for path_index, transcript_path in enumerate(paths):
        try:
            lines = transcript_path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            warnings += 1
            continue

        for line_index, line in enumerate(lines):
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                warnings += 1
                continue

            turn = record_to_turn(record, redactor)
            if turn is None:
                continue
            if turn.event_id and turn.event_id in seen_event_ids:
                continue
            if turn.event_id:
                seen_event_ids.add(turn.event_id)

            timestamp = turn.timestamp or datetime.max.replace(tzinfo=UTC)
            ordered_turns.append((timestamp, path_index, line_index, turn))

    if include_sidechains:
        ordered_turns.sort(key=lambda item: (item[0], item[1], item[2]))
    else:
        ordered_turns.sort(key=lambda item: (item[1], item[2]))

    turns: list[Turn] = []
    for _, _, _, turn in ordered_turns:
        if turns and turns[-1].role == turn.role and turns[-1].text == turn.text:
            continue
        turns.append(turn)
    return turns, warnings


def record_to_turn(record: Any, redactor: Redactor) -> Turn | None:
    if not isinstance(record, dict):
        return None

    role = record.get("type")
    if role not in {"user", "assistant"}:
        return None
    if role == "user" and (
        record.get("isMeta")
        or record.get("toolUseResult") is not None
        or record.get("sourceToolUseID") is not None
        or record.get("sourceToolAssistantUUID") is not None
    ):
        return None

    message = record.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    text_parts: list[str] = []

    if isinstance(content, str) and role == "user":
        text_parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str) and role == "user":
                text_parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    text_parts.append(text)

    text = "\n\n".join(part.strip() for part in text_parts if part.strip()).strip()
    if not text:
        return None

    return Turn(
        role=role,
        text=redactor.redact(text),
        timestamp=parse_timestamp(record.get("timestamp")),
        event_id=str(record.get("uuid")) if record.get("uuid") else None,
    )


def discover_memory_files(source: Path) -> list[Path]:
    memory_files = [
        path
        for path in source.rglob("memory/*.md")
        if "spaces" in path.parts and path.is_file()
    ]
    return sorted(
        memory_files,
        key=lambda path: (path.name.upper() != "MEMORY.MD", str(path)),
    )


def render_memory(memory_files: Iterable[Path], redactor: Redactor) -> str:
    files = list(memory_files)
    lines = [
        "# Imported Cowork memory",
        "",
        "These are Cowork's durable cross-session memory notes. Treat them as source "
        "material, not as infallible facts; prefer newer dated evidence when notes conflict.",
        "",
    ]
    if not files:
        lines.extend(["No local Cowork memory files were found.", ""])
        return "\n".join(lines)

    for path in files:
        space_id = path.parent.parent.name
        try:
            content = path.read_text(encoding="utf-8").strip()
        except (OSError, UnicodeDecodeError):
            continue
        lines.extend(
            [
                f"## {escape_heading(path.name)}",
                "",
                f"Source space: `{space_id}`",
                "",
                redactor.redact(content),
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def list_artifacts(session: Session) -> tuple[str, ...]:
    outputs_path = session.workspace_path / "outputs"
    if not outputs_path.is_dir():
        return ()

    artifacts: list[str] = []
    for path in outputs_path.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(outputs_path)
        if any(part.startswith(".") for part in relative.parts):
            continue
        artifacts.append(relative.as_posix())
    return tuple(sorted(artifacts))


def render_session(
    session: Session, turns: list[Turn], artifacts: tuple[str, ...]
) -> str:
    lines = [
        f"# {escape_heading(session.title)}",
        "",
        f"- Cowork session: `{session.session_id}`",
        f"- Created: {format_datetime(session.created_at)}",
        f"- Last activity: {format_datetime(session.last_activity_at)}",
    ]
    if session.selected_folders:
        lines.append(
            f"- Working folders: {', '.join(f'`{folder}`' for folder in session.selected_folders)}"
        )
    if session.archived:
        lines.append("- Archived in Cowork: yes")
    if artifacts:
        shown = artifacts[:50]
        lines.extend(["", "## Generated artifacts", ""])
        lines.extend(f"- `{name}`" for name in shown)
        if len(artifacts) > len(shown):
            lines.append(f"- …and {len(artifacts) - len(shown)} more")

    if not turns:
        lines.extend(["", "_No readable human/assistant transcript was found._", ""])
        return "\n".join(lines)

    for turn in turns:
        label = "User" if turn.role == "user" else "Assistant"
        timestamp = f" · {format_datetime(turn.timestamp)}" if turn.timestamp else ""
        lines.extend(["", f"## {label}{timestamp}", "", turn.text, ""])
    return "\n".join(lines).rstrip() + "\n"


def export_package(options: ExportOptions) -> ExportReport:
    source = resolve_source(options.source)
    output = options.output.expanduser().resolve()
    validate_export_options(options, source, output)

    sessions, discovery_warnings = discover_sessions(source)
    selected = [session for session in sessions if session_matches(session, options)]
    redactor = Redactor(options.redact)
    session_exports: list[SessionExport] = []
    transcript_warnings = len(discovery_warnings)
    sessions_without_transcripts = 0

    for session in selected:
        turns, warnings = parse_session(
            session,
            include_sidechains=options.include_sidechains,
            redactor=redactor,
        )
        safe_session = replace(
            session,
            title=redactor.redact(session.title),
            selected_folders=tuple(
                redactor.redact(path) for path in session.selected_folders
            ),
        )
        artifacts = tuple(redactor.redact(name) for name in list_artifacts(session))
        if session.main_transcript is None:
            sessions_without_transcripts += 1
        transcript_warnings += warnings
        archive_filename = session_archive_filename(safe_session)
        session_exports.append(
            SessionExport(
                session=safe_session,
                markdown=render_session(safe_session, turns, artifacts),
                turn_count=len(turns),
                artifact_names=artifacts,
                warning_count=warnings,
                archive_filename=archive_filename,
            )
        )

    memory_files = discover_memory_files(source)
    memory_markdown = render_memory(memory_files, redactor)
    chunks = pack_documents(
        [item.markdown for item in session_exports],
        target_chars=options.target_chunk_chars,
        max_chunks=options.max_project_files - 3,
    )

    temp_output = output.parent / f".{output.name}.tmp-{uuid.uuid4().hex[:8]}"
    try:
        write_package(
            temp_output,
            source=source,
            options=options,
            session_exports=session_exports,
            memory_markdown=memory_markdown,
            memory_file_count=len(memory_files),
            chunks=chunks,
            transcript_warnings=transcript_warnings,
            redactions=redactor.replacements,
        )
        temp_output.rename(output)
    except Exception:
        shutil.rmtree(temp_output, ignore_errors=True)
        raise

    return ExportReport(
        output=output,
        sessions_discovered=len(sessions),
        sessions_exported=len(session_exports),
        sessions_without_transcripts=sessions_without_transcripts,
        memory_files=len(memory_files),
        project_files=3 + len(chunks),
        transcript_warnings=transcript_warnings,
        secrets_redacted=redactor.replacements,
    )


def validate_export_options(options: ExportOptions, source: Path, output: Path) -> None:
    if output.exists():
        raise CoworkExportError(
            f"Output already exists: {output}. Choose a new directory or remove it first."
        )
    if output == Path.home() or output == source or source in output.parents:
        raise CoworkExportError("Output must be outside Cowork's data directory.")
    if options.max_project_files < 4:
        raise CoworkExportError("--max-project-files must be at least 4.")
    if options.target_chunk_chars < 10_000:
        raise CoworkExportError("--target-chunk-mb must be at least 0.01 MiB.")


def write_package(
    output: Path,
    *,
    source: Path,
    options: ExportOptions,
    session_exports: list[SessionExport],
    memory_markdown: str,
    memory_file_count: int,
    chunks: list[str],
    transcript_warnings: int,
    redactions: int,
) -> None:
    chatgpt_path = output / "chatgpt"
    archive_path = output / "archive" / "sessions"
    chatgpt_path.mkdir(parents=True)
    archive_path.mkdir(parents=True)

    write_text(
        chatgpt_path / "00_READ_ME_FIRST.md",
        render_project_guide(
            session_exports, memory_file_count, len(chunks), options.redact
        ),
    )
    write_text(chatgpt_path / "01_COWORK_MEMORY.md", memory_markdown)
    write_text(
        chatgpt_path / "02_SESSION_INDEX.md", render_session_index(session_exports)
    )

    for index, chunk in enumerate(chunks, start=1):
        write_text(chatgpt_path / f"10_SESSIONS_{index:03d}.md", chunk)
    for item in session_exports:
        write_text(archive_path / item.archive_filename, item.markdown)

    manifest = {
        "format_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "source": normalize_home(str(source)),
        "settings": {
            "since": options.since.isoformat() if options.since else None,
            "exclude_archived": options.exclude_archived,
            "include_sidechains": options.include_sidechains,
            "redaction_enabled": options.redact,
            "max_project_files": options.max_project_files,
            "target_chunk_chars": options.target_chunk_chars,
        },
        "summary": {
            "sessions": len(session_exports),
            "memory_files": memory_file_count,
            "project_files": 3 + len(chunks),
            "transcript_warnings": transcript_warnings,
            "secrets_redacted": redactions,
        },
        "sessions": [
            {
                "session_id": item.session.session_id,
                "title": item.session.title,
                "created_at": iso_or_none(item.session.created_at),
                "last_activity_at": iso_or_none(item.session.last_activity_at),
                "archived": item.session.archived,
                "turns": item.turn_count,
                "artifacts": len(item.artifact_names),
                "warnings": item.warning_count,
                "archive_file": f"archive/sessions/{item.archive_filename}",
            }
            for item in session_exports
        ],
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def render_project_guide(
    session_exports: list[SessionExport],
    memory_file_count: int,
    chunks: int,
    redacted: bool,
) -> str:
    redaction_note = (
        "Common credential patterns were redacted, but you must still review these files for "
        "private or regulated information before uploading them."
        if redacted
        else "Automatic credential redaction was disabled. Review every file before uploading it."
    )
    return f"""# Cowork context import

This folder contains a portable, text-only snapshot of local Claude Cowork context:

- {len(session_exports)} sessions
- {memory_file_count} durable memory files
- {chunks} transcript chunks

## Use in ChatGPT

Add every file in this folder as a source in one ChatGPT Project. Suggested project instruction:

> Use `01_COWORK_MEMORY.md` as standing background and preferences. Use
> `02_SESSION_INDEX.md` to locate relevant prior work, then consult the session chunks for
> evidence. Prefer newer evidence when sources conflict. Never claim an imported task was
> completed unless the transcript or a current source confirms it.

The files under `../archive/sessions` are a human-browsable backup and do not need to be
uploaded to the Project.

## Privacy

{redaction_note} Tool credentials, system prompts, hidden reasoning, and raw tool results were
not exported.

## Limitations

This is project context, not a native ChatGPT chat-history or saved-memory import. Cowork's
local storage format is undocumented and may change; consult `../manifest.json` for parser
warnings.
"""


def render_session_index(items: list[SessionExport]) -> str:
    lines = [
        "# Cowork session index",
        "",
        "Sessions are ordered by most recent activity. The full text is in `10_SESSIONS_*.md`.",
        "",
        "| Last activity | Title | Turns | Artifacts | Session |",
        "|---|---|---:|---:|---|",
    ]
    for item in items:
        lines.append(
            "| "
            + " | ".join(
                [
                    format_datetime(item.session.last_activity_at),
                    escape_table_cell(item.session.title),
                    str(item.turn_count),
                    str(len(item.artifact_names)),
                    f"`{item.session.session_id}`",
                ]
            )
            + " |"
        )
    if not items:
        lines.extend(["", "No sessions matched the export filters."])
    return "\n".join(lines) + "\n"


def pack_documents(
    documents: list[str], *, target_chars: int, max_chunks: int
) -> list[str]:
    if not documents:
        return []
    if max_chunks < 1:
        raise CoworkExportError("No project file slots remain for session transcripts.")

    total_chars = sum(len(document) + 100 for document in documents)
    target = max(target_chars, math.ceil(total_chars / max_chunks) + 1_000)

    while target <= MAX_PROJECT_TEXT_CHARS:
        pieces = [
            piece
            for document in documents
            for piece in split_document(document, target)
        ]
        chunks: list[str] = []
        current: list[str] = []
        current_size = 0
        for piece in pieces:
            addition = len(piece) + (80 if current else 0)
            if current and current_size + addition > target:
                chunks.append(session_chunk(current, len(chunks) + 1))
                current = []
                current_size = 0
            current.append(piece)
            current_size += addition
        if current:
            chunks.append(session_chunk(current, len(chunks) + 1))

        if len(chunks) <= max_chunks and all(
            len(chunk) <= MAX_PROJECT_TEXT_CHARS for chunk in chunks
        ):
            return chunks
        target = math.ceil(target * 1.2)

    raise CoworkExportError(
        "The selected sessions cannot fit within the requested project file count. "
        "Use --since, increase --max-project-files, or omit --include-sidechains."
    )


def split_document(document: str, target: int) -> list[str]:
    if len(document) <= target:
        return [document]

    first_line = document.splitlines()[0] if document else "# Session"
    remaining = document
    pieces: list[str] = []
    while len(remaining) > target:
        boundary = remaining.rfind("\n## ", 0, target)
        if boundary < target // 2:
            boundary = remaining.rfind("\n\n", 0, target)
        if boundary < target // 2:
            boundary = target
        pieces.append(remaining[:boundary].rstrip() + "\n")
        remaining = f"{first_line} (continued)\n\n{remaining[boundary:].lstrip()}"
    pieces.append(remaining.rstrip() + "\n")
    return pieces


def session_chunk(documents: list[str], index: int) -> str:
    header = (
        f"# Imported Cowork sessions — chunk {index:03d}\n\n"
        "Each top-level heading below is one Cowork session.\n\n"
    )
    return (
        header + "\n\n---\n\n".join(document.rstrip() for document in documents) + "\n"
    )


def session_matches(session: Session, options: ExportOptions) -> bool:
    if options.exclude_archived and session.archived:
        return False
    if options.since:
        activity = session.last_activity_at or session.created_at
        if activity is None or activity.date() < options.since:
            return False
    return True


def session_archive_filename(session: Session) -> str:
    activity = session.last_activity_at or session.created_at
    prefix = activity.date().isoformat() if activity else "unknown-date"
    short_id = session.session_id.removeprefix("local_")[:8]
    return f"{prefix}-{slugify(session.title)}-{short_id}.md"


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if value > 100_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        normalized = value.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return (
            parsed.replace(tzinfo=UTC)
            if parsed.tzinfo is None
            else parsed.astimezone(UTC)
        )
    return None


def clean_title(title: Any, initial_message: Any, session_id: str) -> str:
    if isinstance(title, str) and title.strip():
        return " ".join(title.split())[:160]
    if isinstance(initial_message, str) and initial_message.strip():
        return " ".join(initial_message.split())[:120]
    return session_id


def normalize_home(value: str) -> str:
    home = str(Path.home())
    if value == home:
        return "~"
    if value.startswith(home + os.sep):
        return "~" + value[len(home) :]
    return value


def session_sort_key(session: Session) -> datetime:
    return (
        session.last_activity_at
        or session.created_at
        or datetime.min.replace(tzinfo=UTC)
    )


def format_datetime(value: datetime | None) -> str:
    if value is None:
        return "unknown"
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC")


def iso_or_none(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def escape_heading(value: str) -> str:
    return value.replace("\n", " ").strip() or "Untitled session"


def escape_table_cell(value: str) -> str:
    return " ".join(value.replace("|", "\\|").split())


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "untitled")[:60].rstrip("-")


def write_text(path: Path, content: str) -> None:
    path.write_text(content.rstrip() + "\n", encoding="utf-8")
