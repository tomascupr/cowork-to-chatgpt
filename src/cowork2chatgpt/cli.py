from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import __version__
from .core import (
    CoworkExportError,
    ExportOptions,
    InstallOptions,
    discover_memory_files,
    discover_sessions,
    export_package,
    format_datetime,
    group_sessions,
    install_workspaces,
    resolve_source,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cowork2chatgpt",
        description="Move isolated Claude Cowork memory and history into ChatGPT-ready files.",
    )
    parser.add_argument("--version", action="version", version=__version__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="List local Cowork workspaces.")
    add_source_argument(scan)
    scan.add_argument(
        "--json", action="store_true", help="Print machine-readable JSON."
    )
    scan.add_argument(
        "--limit",
        type=positive_int,
        default=10,
        help="Maximum unassigned workspace IDs to show (default: 10).",
    )

    export = subparsers.add_parser(
        "export", help="Create one ready-to-use context folder per workspace."
    )
    export.add_argument(
        "output",
        nargs="?",
        type=Path,
        help="New directory to create (default: chatgpt-context-YYYY-MM-DD).",
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
        "--with-evidence",
        action="store_true",
        help="Also include redacted tool evidence and subagent history.",
    )
    export.add_argument(
        "--since", type=iso_date, help="Include sessions active on or after YYYY-MM-DD."
    )
    export.add_argument(
        "--exclude-archived",
        action="store_true",
        help="Skip sessions marked archived in Cowork.",
    )
    export.add_argument(
        "--no-shared-memory",
        action="store_true",
        help="Do not export Cowork's hidden cross-workspace memory for review.",
    )

    install = subparsers.add_parser(
        "install",
        help="Install memory and history into original single-folder workspaces.",
    )
    add_source_argument(install)
    install.add_argument(
        "--workspace",
        action="append",
        default=[],
        metavar="ID",
        help="Install only this workspace ID. Repeat to select several; scan lists IDs.",
    )
    install.add_argument(
        "--with-evidence",
        action="store_true",
        help="Also include redacted tool evidence and subagent history.",
    )
    install.add_argument(
        "--since", type=iso_date, help="Include sessions active on or after YYYY-MM-DD."
    )
    install.add_argument(
        "--exclude-archived",
        action="store_true",
        help="Skip sessions marked archived in Cowork.",
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
        if args.command == "install":
            return run_install(args)
    except CoworkExportError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 1


def run_scan(args: argparse.Namespace) -> int:
    source = resolve_source(args.source)
    sessions, warnings = discover_sessions(source)
    workspaces = group_sessions(sessions)
    shared_memory = discover_memory_files(source)

    if args.json:
        print(
            json.dumps(
                {
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
                        }
                        for workspace in workspaces
                    ],
                    "shared_memory_files": len(shared_memory),
                    "warnings": warnings,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
        return 0

    print(f"Cowork data: {source}")
    print(f"Sessions: {len(sessions)}")
    print(f"Isolated workspaces: {len(workspaces)}")
    print(f"Hidden shared-memory files: {len(shared_memory)}")
    print(f"Discovery warnings: {len(warnings)}")
    assigned = [workspace for workspace in workspaces if workspace.folders]
    unassigned = [workspace for workspace in workspaces if not workspace.folders]
    print("\nWorkspace IDs:")
    for workspace in assigned:
        folders = ", ".join(workspace.folders)
        latest = workspace.sessions[0].last_activity_at if workspace.sessions else None
        print(
            f"- {workspace.workspace_id}: {len(workspace.sessions)} sessions, "
            f"latest {format_datetime(latest)}"
        )
        print(f"  {folders}")
    if unassigned:
        print(
            f"\nUnassigned sessions: {len(unassigned)}. Each stays isolated; "
            f"showing {min(len(unassigned), args.limit)} IDs:"
        )
        for workspace in unassigned[: args.limit]:
            print(f"- {workspace.workspace_id}")
        if len(unassigned) > args.limit:
            print("  Run `cowork2chatgpt scan --json` to list every ID.")
    return 0


def run_export(args: argparse.Namespace) -> int:
    source = resolve_source(args.source)
    output = args.output or Path.cwd() / f"chatgpt-context-{date.today().isoformat()}"
    report = export_package(
        ExportOptions(
            source=source,
            output=output,
            since=args.since,
            exclude_archived=args.exclude_archived,
            include_evidence=args.with_evidence,
            include_shared_memory=not args.no_shared_memory,
            workspace_ids=tuple(args.workspace),
        )
    )

    print(f"Created: {report.output}")
    print(
        f"Sessions: {report.sessions_exported} exported "
        f"({report.sessions_discovered} discovered)"
    )
    print(f"Isolated workspaces: {len(report.workspaces)}")
    for workspace in report.workspaces:
        print(
            f"- {workspace.workspace_id}: {workspace.sessions} sessions, "
            f"{workspace.memory_sources} memory sources, {workspace.files} files"
        )
    if report.shared_memory_sources:
        print(
            "Hidden shared memory is quarantined in: "
            "_shared-memory/COWORK_SHARED_MEMORY.md"
        )
    print(f"Parser/read warnings: {report.warnings}")
    print(f"Credential-pattern matches redacted: {report.secrets_redacted}")
    return 0


def run_install(args: argparse.Namespace) -> int:
    source = resolve_source(args.source)
    report = install_workspaces(
        InstallOptions(
            source=source,
            since=args.since,
            exclude_archived=args.exclude_archived,
            include_evidence=args.with_evidence,
            workspace_ids=tuple(args.workspace),
        )
    )

    print(
        f"Installed {report.sessions_installed} sessions into "
        f"{len(report.workspaces)} original workspace folders."
    )
    for workspace in report.workspaces:
        print(
            f"- {workspace.workspace_id}: {workspace.sessions} sessions -> "
            f"{workspace.path}"
        )
    if report.skipped:
        print(
            f"Kept {len(report.skipped)} composite or unassigned workspaces separate. "
            "Use `export` to create portable folders for them."
        )
    print(f"Parser/read warnings: {report.warnings}")
    print(f"Credential-pattern matches redacted: {report.secrets_redacted}")
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
