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
    resolve_source,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cowork2chatgpt",
        description="Export local Claude Cowork context for a ChatGPT Project.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser(
        "scan", help="Inspect local Cowork data without reading transcript contents."
    )
    add_source_argument(scan)
    scan.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    scan.add_argument(
        "--limit",
        type=positive_int,
        default=20,
        help="Maximum recent sessions to display (default: 20).",
    )

    export = subparsers.add_parser(
        "export", help="Create a portable ChatGPT Project package."
    )
    export.add_argument("output", type=Path, help="New directory to create.")
    add_source_argument(export)
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
        help="Include subagent transcripts. This can substantially increase output size.",
    )
    export.add_argument(
        "--no-redact",
        action="store_true",
        help="Disable best-effort credential redaction.",
    )
    export.add_argument(
        "--max-project-files",
        type=positive_int,
        default=20,
        help="Pack the upload folder into at most this many files (default: 20).",
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
    memory_files = discover_memory_files(source)
    with_transcripts = sum(session.main_transcript is not None for session in sessions)

    if args.json:
        payload = {
            "source": str(source),
            "sessions": len(sessions),
            "sessions_with_transcripts": with_transcripts,
            "memory_files": len(memory_files),
            "warnings": warnings,
            "recent": [
                {
                    "session_id": session.session_id,
                    "title": session.title,
                    "last_activity": (
                        session.last_activity_at.isoformat()
                        if session.last_activity_at
                        else None
                    ),
                    "archived": session.archived,
                    "has_transcript": session.main_transcript is not None,
                }
                for session in sessions[: args.limit]
            ],
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print(f"Cowork data: {source}")
    print(f"Sessions: {len(sessions)} ({with_transcripts} with transcripts)")
    print(f"Durable memory files: {len(memory_files)}")
    print(f"Discovery warnings: {len(warnings)}")
    if sessions:
        print("\nMost recent sessions:")
        for session in sessions[: args.limit]:
            marker = "archived" if session.archived else "active"
            transcript = "transcript" if session.main_transcript else "no transcript"
            print(
                f"- {format_datetime(session.last_activity_at):20}  "
                f"{session.title} [{marker}, {transcript}]"
            )
    return 0


def run_export(args: argparse.Namespace) -> int:
    source = resolve_source(args.source)
    target_chars = int(args.target_chunk_mb * 1024 * 1024)
    report = export_package(
        ExportOptions(
            source=source,
            output=args.output,
            since=args.since,
            exclude_archived=args.exclude_archived,
            include_sidechains=args.include_sidechains,
            redact=not args.no_redact,
            max_project_files=args.max_project_files,
            target_chunk_chars=target_chars,
        )
    )

    print(f"Created: {report.output}")
    print(
        f"Sessions: {report.sessions_exported} exported "
        f"({report.sessions_discovered} discovered)"
    )
    print(f"Durable memory files: {report.memory_files}")
    print(f"ChatGPT Project files: {report.project_files}")
    print(f"Transcript warnings: {report.transcript_warnings}")
    print(f"Potential secrets redacted: {report.secrets_redacted}")
    print(f"Upload this directory: {report.output / 'chatgpt'}")
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
