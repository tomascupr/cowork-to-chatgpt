from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .core import (
    DEFAULT_TARGET_CHARS,
    CoworkExportError,
    ExportOptions,
    discover_memory_files,
    discover_sessions,
    export_package,
    format_datetime,
    group_sessions,
    resolve_source,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cowork2chatgpt",
        description="Export isolated Claude Cowork workspaces for ChatGPT Projects.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser(
        "scan", help="List local Cowork workspaces without reading transcript contents."
    )
    add_source_argument(scan)
    scan.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    scan.add_argument(
        "--limit",
        type=positive_int,
        default=10,
        help="Maximum recent sessions and unassigned IDs to show (default: 10).",
    )

    export = subparsers.add_parser(
        "export", help="Create one isolated ChatGPT package per Cowork workspace."
    )
    export.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="New directory to create (default: cowork-export-YYYY-MM-DD).",
    )
    add_source_argument(export)
    export.add_argument(
        "--workspace",
        action="append",
        default=[],
        metavar="ID",
        help="Export only this workspace ID. Repeat to select several; scan lists IDs.",
    )
    export.add_argument(
        "--mode",
        choices=("standard", "evidence", "archive"),
        default="standard",
        help=(
            "standard=text only; evidence=redacted tool evidence and sidechains; "
            "archive=evidence plus untouched raw local backup"
        ),
    )
    export.add_argument(
        "--memory-mode",
        choices=("separate", "copy", "none"),
        default="separate",
        help=(
            "separate=review global memory separately; copy=put it in every workspace; "
            "none=omit it"
        ),
    )
    export.add_argument(
        "--since",
        type=iso_date,
        help="Only include sessions active on or after YYYY-MM-DD.",
    )
    export.add_argument(
        "--exclude-archived",
        action="store_true",
        help="Skip sessions marked archived in local metadata.",
    )
    export.add_argument(
        "--include-sidechains",
        action="store_true",
        help="Include subagent text in standard mode. Evidence/archive modes include it already.",
    )
    export.add_argument(
        "--copy-artifacts",
        action="store_true",
        help="Copy filtered user-facing artifacts outside the ChatGPT upload folders.",
    )
    export.add_argument(
        "--max-artifact-mb",
        type=positive_float,
        default=25.0,
        help="Maximum size of each copied artifact in MiB (default: 25).",
    )
    export.add_argument(
        "--no-redact",
        action="store_true",
        help="Disable best-effort credential redaction in ChatGPT upload files.",
    )
    export.add_argument(
        "--max-project-files",
        type=positive_int,
        default=20,
        help="Maximum files in each workspace's ChatGPT folder (default: 20).",
    )
    export.add_argument(
        "--target-chunk-mb",
        type=positive_float,
        default=DEFAULT_TARGET_CHARS / (1024 * 1024),
        help="Preferred transcript chunk size in approximate MiB (default: 1.43).",
    )
    return parser


def add_source_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--source",
        type=Path,
        help="Cowork local-agent-mode-sessions directory. Auto-detected by default.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "scan":
            return run_scan(args)
        if args.command == "export":
            return run_export(args)
    except CoworkExportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1


def run_scan(args: argparse.Namespace) -> int:
    source = resolve_source(args.source)
    sessions, warnings = discover_sessions(source)
    workspaces = group_sessions(sessions)
    memory_files = discover_memory_files(source)

    if args.json:
        payload = {
            "source": str(source),
            "sessions": len(sessions),
            "workspaces": [
                {
                    "workspace_id": workspace.workspace_id,
                    "name": workspace.name,
                    "folders": list(workspace.folders),
                    "sessions": len(workspace.sessions),
                    "archived_sessions": sum(
                        session.archived for session in workspace.sessions
                    ),
                    "recent": [
                        {
                            "session_id": session.session_id,
                            "title": session.title,
                            "last_activity": (
                                session.last_activity_at.isoformat()
                                if session.last_activity_at
                                else None
                            ),
                        }
                        for session in workspace.sessions[: args.limit]
                    ],
                }
                for workspace in workspaces
            ],
            "memory_files": len(memory_files),
            "warnings": warnings,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(f"Cowork data: {source}")
    print(f"Sessions: {len(sessions)}")
    print(f"Isolated workspaces: {len(workspaces)}")
    print(f"Durable memory files (kept separate by default): {len(memory_files)}")
    print(f"Discovery warnings: {len(warnings)}")
    assigned = [workspace for workspace in workspaces if workspace.folders]
    unassigned = [workspace for workspace in workspaces if not workspace.folders]
    print("\nFolder-based workspace IDs:")
    for workspace in assigned:
        folders = ", ".join(workspace.folders) or "no selected folder"
        archived = sum(session.archived for session in workspace.sessions)
        latest = workspace.sessions[0].last_activity_at if workspace.sessions else None
        print(
            f"- {workspace.workspace_id}: {len(workspace.sessions)} sessions "
            f"({archived} archived), latest {format_datetime(latest)}"
        )
        print(f"  {folders}")
    if unassigned:
        print(
            f"\nUnassigned sessions: {len(unassigned)}. Each is isolated in its own package; "
            f"showing {min(len(unassigned), args.limit)} IDs:"
        )
        for workspace in unassigned[: args.limit]:
            latest = workspace.sessions[0].last_activity_at
            print(f"- {workspace.workspace_id}: latest {format_datetime(latest)}")
        if len(unassigned) > args.limit:
            print("  Run `cowork2chatgpt scan --json` to list every unassigned ID.")
    return 0


def run_export(args: argparse.Namespace) -> int:
    source = resolve_source(args.source)
    output = args.output or Path.cwd() / f"cowork-export-{date.today().isoformat()}"
    report = export_package(
        ExportOptions(
            source=source,
            output=output,
            since=args.since,
            exclude_archived=args.exclude_archived,
            include_sidechains=args.include_sidechains,
            redact=not args.no_redact,
            max_project_files=args.max_project_files,
            target_chunk_chars=int(args.target_chunk_mb * 1024 * 1024),
            mode=args.mode,
            memory_mode=args.memory_mode,
            workspace_ids=tuple(args.workspace),
            copy_artifacts=args.copy_artifacts,
            max_artifact_bytes=int(args.max_artifact_mb * 1024 * 1024),
        )
    )

    print(f"Created: {report.output}")
    print(
        f"Sessions: {report.sessions_exported} exported "
        f"({report.sessions_discovered} discovered)"
    )
    print(f"Isolated workspaces: {len(report.workspaces)}")
    for workspace in report.workspaces:
        relative = workspace.path.relative_to(report.output)
        print(
            f"- {workspace.workspace_id}: {workspace.sessions} sessions, "
            f"{workspace.project_files} upload files -> {relative / 'chatgpt'}"
        )
    if args.memory_mode == "separate" and report.memory_files:
        print("Shared Cowork memory for selective review: shared-memory/chatgpt")
    print(f"Parser/read warnings: {report.transcript_warnings}")
    print(
        "Credential-pattern matches redacted: "
        f"{report.secrets_redacted} (not a guarantee that the export is secret-free)"
    )
    return 0


def iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from error


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


if __name__ == "__main__":
    raise SystemExit(main())
