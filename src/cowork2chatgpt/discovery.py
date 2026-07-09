from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any

from .models import Artifact, ArtifactInventory, Session, Workspace


USER_PREFERENCES_PATTERN = re.compile(
    r"<user_preferences>(.*?)</user_preferences>", re.DOTALL | re.IGNORECASE
)
DOCUMENT_EXTENSIONS = {
    ".csv",
    ".docx",
    ".epub",
    ".html",
    ".md",
    ".odt",
    ".pdf",
    ".pptx",
    ".rtf",
    ".tsv",
    ".txt",
    ".xlsx",
}
IMAGE_EXTENSIONS = {".gif", ".jpeg", ".jpg", ".png", ".svg", ".webp"}
STRUCTURED_EXTENSIONS = {".json", ".yaml", ".yml"}
VIDEO_EXTENSIONS = {".mov", ".mp4", ".webm"}
IGNORED_FILENAMES = {
    "package-lock.json",
    "package.json",
    "tsconfig.json",
}
IGNORED_DIRECTORY_NAMES = {
    "__pycache__",
    "_rels",
    "build",
    "cache",
    "caches",
    "crops",
    "dist",
    "docprops",
    "node_modules",
    "ppt",
    "preview",
    "previews",
    "qa",
    "render",
    "renders",
    "temp",
    "temporary",
    "thumbnails",
    "tmp",
    "unpacked",
    "unpacked2",
    "vendor",
    "venv",
    "word",
    "xl",
}


class CoworkExportError(RuntimeError):
    """Raised when Cowork data cannot be discovered or exported safely."""


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
        ", ".join(str(path) for path in default_source_candidates()) or "no defaults"
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
        if not session_id.startswith("local_"):
            continue
        cli_session_id = str(data.get("cliSessionId") or "")
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
                title=clean_title(
                    data.get("title"), data.get("initialMessage"), session_id
                ),
                created_at=parse_timestamp(data.get("createdAt")),
                last_activity_at=parse_timestamp(data.get("lastActivityAt")),
                archived=bool(data.get("isArchived", False)),
                selected_folders=selected_folders,
                metadata_path=metadata_path,
                workspace_path=workspace_path,
                main_transcript=main,
                sidechain_transcripts=sidechains,
                system_prompt_present=bool(data.get("systemPrompt")),
                user_preferences=extract_user_preferences(data),
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
    return main, tuple(path for path in all_transcripts if path != main)


def group_sessions(sessions: list[Session]) -> list[Workspace]:
    grouped: dict[tuple[str, ...], list[Session]] = defaultdict(list)
    unassigned: list[Session] = []
    for session in sessions:
        folders = tuple(sorted(set(session.selected_folders)))
        if folders:
            grouped[folders].append(session)
        else:
            unassigned.append(session)

    names = {folders: workspace_name(folders) for folders in grouped}
    base_ids = {folders: slugify(name) for folders, name in names.items()}
    collisions = Counter(base_ids.values())
    workspaces: list[Workspace] = []
    for folders, grouped_sessions in grouped.items():
        base_id = base_ids[folders]
        if collisions[base_id] > 1:
            digest = hashlib.sha256("\0".join(folders).encode()).hexdigest()[:8]
            workspace_id = f"{base_id}-{digest}"
        else:
            workspace_id = base_id
        workspaces.append(
            Workspace(
                workspace_id=workspace_id,
                name=names[folders],
                folders=folders,
                sessions=tuple(
                    sorted(grouped_sessions, key=session_sort_key, reverse=True)
                ),
            )
        )
    for session in unassigned:
        short_id = session.session_id.removeprefix("local_")[:8]
        workspaces.append(
            Workspace(
                workspace_id=f"unassigned-{slugify(session.title)}-{short_id}",
                name=f"Unassigned — {session.title}",
                folders=(),
                sessions=(session,),
            )
        )
    return sorted(
        workspaces,
        key=lambda item: (
            not item.folders,
            (
                -len(item.sessions)
                if item.folders
                else -session_sort_key(item.sessions[0]).timestamp()
            ),
            item.name.lower(),
        ),
    )


def discover_memory_files(source: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in source.rglob("memory/*.md")
            if "spaces" in path.parts and path.is_file()
        ],
        key=lambda path: (path.name.upper() != "MEMORY.MD", str(path)),
    )


def inspect_artifacts(session: Session) -> ArtifactInventory:
    outputs_path = session.workspace_path / "outputs"
    if not outputs_path.is_dir():
        return ArtifactInventory(total_files=0, candidates=())

    total = 0
    candidates: list[Artifact] = []
    for path in outputs_path.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        total += 1
        relative = path.relative_to(outputs_path)
        if not is_user_facing_artifact(relative):
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        candidates.append(
            Artifact(
                relative_path=relative.as_posix(),
                source_path=path,
                size=size,
            )
        )
    candidates.sort(key=lambda item: item.relative_path.lower())
    return ArtifactInventory(total_files=total, candidates=tuple(candidates))


def list_artifacts(session: Session) -> tuple[str, ...]:
    return tuple(item.relative_path for item in inspect_artifacts(session).candidates)


def is_user_facing_artifact(relative: Path) -> bool:
    if any(part.startswith(".") for part in relative.parts):
        return False
    directory_parts = {part.lower() for part in relative.parts[:-1]}
    if directory_parts & IGNORED_DIRECTORY_NAMES:
        return False
    if any(is_intermediate_directory(part) for part in relative.parts[:-1]):
        return False
    if relative.name.lower() in IGNORED_FILENAMES:
        return False

    suffix = relative.suffix.lower()
    if suffix in DOCUMENT_EXTENSIONS:
        return True
    if suffix in IMAGE_EXTENSIONS or suffix in VIDEO_EXTENSIONS:
        return len(relative.parts) <= 3
    if suffix in STRUCTURED_EXTENSIONS:
        return len(relative.parts) <= 2
    return False


def is_intermediate_directory(value: str) -> bool:
    lowered = value.lower().strip("._-")
    if lowered in {"probe", "slides", "verify", "work"} or lowered.startswith("qa"):
        return True
    return any(
        marker in lowered
        for marker in ("build", "check", "crop", "preview", "render", "unpack")
    )


def extract_user_preferences(data: dict[str, Any]) -> tuple[str, ...]:
    preferences: list[str] = []
    appends = data.get("systemPromptRendererAppends")
    if not isinstance(appends, list):
        return ()
    for append in appends:
        if not isinstance(append, str):
            continue
        for match in USER_PREFERENCES_PATTERN.finditer(append):
            content = match.group(1).strip()
            if content and content not in preferences:
                preferences.append(content)
    return tuple(preferences)


def workspace_name(folders: tuple[str, ...]) -> str:
    if not folders:
        return "Unassigned"
    return " + ".join(folder_leaf(folder) for folder in folders)


def folder_leaf(folder: str) -> str:
    if "\\" in folder and "/" not in folder:
        return PureWindowsPath(folder).name or folder
    return Path(folder).name or folder


def parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        seconds = float(value) / 1000 if value > 100_000_000_000 else float(value)
        try:
            return datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
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
    for separator in (os.sep, "/", "\\"):
        prefix = home + separator
        if value.startswith(prefix):
            return "~" + value[len(home) :]
    return value


def session_sort_key(session: Session) -> datetime:
    return (
        session.last_activity_at
        or session.created_at
        or datetime.min.replace(tzinfo=UTC)
    )


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "unassigned")[:80].rstrip("-")
