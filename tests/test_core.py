from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from cowork2chatgpt.core import (
    CoworkExportError,
    ExportOptions,
    InstallOptions,
    Redactor,
    discover_memory_files,
    discover_sessions,
    discover_workspace_memory_files,
    export_package,
    group_sessions,
    install_workspaces,
    pack_documents,
    parse_session,
)


class CoworkExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.source = self.root / "local-agent-mode-sessions"
        self.session_root = self.source / "profile-id" / "org-id"
        self.folder_a = self.root / "Example" / "Alpha"
        self.folder_b = self.root / "Example" / "Beta"
        (self.folder_a / "memory").mkdir(parents=True)
        self.folder_b.mkdir(parents=True)
        (self.folder_a / "CLAUDE.md").write_text(
            "# Alpha instructions\n\nAlpha memory only.\n", encoding="utf-8"
        )
        (self.folder_a / "AGENTS.md").write_text(
            "# Existing project instructions\n\nKeep this content.\n", encoding="utf-8"
        )
        (self.folder_a / "MEMORY.md").write_text(
            "# Existing memory\n\nKeep this memory.\n", encoding="utf-8"
        )
        (self.folder_a / "memory" / "decisions.md").write_text(
            "# Alpha decisions\n\napi_key = supersecret123\n", encoding="utf-8"
        )
        (self.folder_b / "CLAUDE.md").write_text(
            "# Beta instructions\n\nBeta memory only.\n", encoding="utf-8"
        )

        alpha_records = [
            self.record(
                "user",
                "alpha-user",
                {
                    "role": "user",
                    "content": "Alpha only. " + "sk-ant-" + "abcdefghijklmnopqrstuv",
                },
            ),
            self.record(
                "assistant",
                "alpha-thinking",
                {
                    "role": "assistant",
                    "content": [{"type": "thinking", "thinking": "private reasoning"}],
                },
            ),
            self.record(
                "assistant",
                "alpha-tool",
                {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Read",
                            "input": {"path": "/tmp/a"},
                        }
                    ],
                },
            ),
            {
                **self.record(
                    "user",
                    "alpha-result",
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "content": "File evidence"}
                        ],
                    },
                ),
                "sourceToolAssistantUUID": "alpha-tool",
                "toolUseResult": {"content": "File evidence"},
            },
            self.record(
                "assistant",
                "alpha-answer",
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "Alpha answer."}],
                },
            ),
        ]
        self.alpha = self.create_session(
            suffix="alpha",
            title="Alpha project",
            folders=[str(self.folder_a)],
            records=alpha_records,
        )
        sidechain = (
            self.alpha["workspace"] / ".claude" / "projects" / "fixture" / "subagents"
        )
        sidechain.mkdir(parents=True)
        (sidechain / "sidechain.jsonl").write_text(
            json.dumps(
                self.record(
                    "assistant",
                    "sidechain-answer",
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "Sidechain evidence."}],
                    },
                )
            )
            + "\n",
            encoding="utf-8",
        )
        self.create_session(
            suffix="beta",
            title="Beta project",
            folders=[str(self.folder_b)],
            records=[
                self.record(
                    "user", "beta-user", {"role": "user", "content": "Beta only."}
                )
            ],
        )
        self.create_session(
            suffix="composite",
            title="Composite project",
            folders=[str(self.folder_b), str(self.folder_a)],
            records=[
                self.record(
                    "user",
                    "composite-user",
                    {"role": "user", "content": "Composite only."},
                )
            ],
        )
        self.create_session(
            suffix="unassigned",
            title="Unassigned project",
            folders=[],
            records=[
                self.record(
                    "user",
                    "unassigned-user",
                    {"role": "user", "content": "Unassigned only."},
                )
            ],
        )
        self.create_session(
            suffix="unassigned-two",
            title="Another unassigned project",
            folders=[],
            records=[
                self.record(
                    "user",
                    "unassigned-two-user",
                    {"role": "user", "content": "Another unassigned context."},
                )
            ],
        )

        memory = self.session_root / "spaces" / "space-id" / "memory"
        memory.mkdir(parents=True)
        (memory / "MEMORY.md").write_text(
            "# Global memory\n\nShared historical note.\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    @staticmethod
    def record(
        record_type: str, uuid: str, message: dict[str, object]
    ) -> dict[str, object]:
        return {
            "type": record_type,
            "uuid": uuid,
            "timestamp": "2025-06-15T15:06:40Z",
            "message": message,
        }

    def create_session(
        self,
        *,
        suffix: str,
        title: str,
        folders: list[str],
        records: list[dict[str, object]],
    ) -> dict[str, object]:
        session_id = f"local_{suffix}-1234-1234-1234-123456789abc"
        cli_session_id = f"cli-{suffix}-bbbb-cccc-dddd-eeeeeeeeeeee"
        workspace = self.session_root / session_id
        transcript = (
            workspace / ".claude" / "projects" / "fixture" / f"{cli_session_id}.jsonl"
        )
        transcript.parent.mkdir(parents=True)
        transcript.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n",
            encoding="utf-8",
        )
        metadata = {
            "sessionId": session_id,
            "cliSessionId": cli_session_id,
            "title": title,
            "createdAt": 1_750_000_000_000,
            "lastActivityAt": 1_750_000_100_000,
            "isArchived": False,
            "userSelectedFolders": folders,
            "systemPrompt": "Vendor runtime prompt that must not be exported",
            "systemPromptRendererAppends": [
                """<user_preferences>
- Be candid and honest.
</user_preferences>"""
            ],
        }
        self.session_root.mkdir(parents=True, exist_ok=True)
        metadata_path = self.session_root / f"{session_id}.json"
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        return {
            "session_id": session_id,
            "workspace": workspace,
            "transcript": transcript,
            "metadata": metadata_path,
        }

    def test_discovers_canonical_isolated_workspaces_and_memory(self) -> None:
        sessions, warnings = discover_sessions(self.source)
        workspaces = group_sessions(sessions)

        self.assertEqual(warnings, [])
        self.assertEqual(len(sessions), 5)
        self.assertEqual(len(workspaces), 5)
        self.assertEqual(
            len([workspace for workspace in workspaces if not workspace.folders]), 2
        )
        self.assertTrue(
            all(
                len(workspace.sessions) == 1
                for workspace in workspaces
                if not workspace.folders
            )
        )
        alpha = next(item for item in workspaces if item.name == "Alpha")
        composite = next(item for item in workspaces if item.name == "Alpha + Beta")
        self.assertEqual(
            composite.folders,
            tuple(sorted((str(self.folder_a), str(self.folder_b)))),
        )
        self.assertEqual(len(discover_workspace_memory_files(alpha)), 3)
        self.assertEqual(len(discover_workspace_memory_files(composite)), 4)
        self.assertEqual(len(discover_memory_files(self.source)), 1)
        self.assertEqual(sessions[0].user_preferences, ("- Be candid and honest.",))

    def test_standard_export_is_ready_to_open_and_never_mixes_workspaces(self) -> None:
        output = self.root / "standard-export"
        report = export_package(ExportOptions(source=self.source, output=output))
        workspace_ids = {
            workspace.name: workspace.workspace_id
            for workspace in group_sessions(discover_sessions(self.source)[0])
        }
        alpha_path = output / workspace_ids["Alpha"]
        beta_path = output / workspace_ids["Beta"]
        composite_path = output / workspace_ids["Alpha + Beta"]
        alpha_text = self.read_markdown(alpha_path)
        beta_text = self.read_markdown(beta_path)
        composite_text = self.read_markdown(composite_path)

        self.assertEqual(len(report.workspaces), 5)
        self.assertTrue(all(workspace.path.is_dir() for workspace in report.workspaces))
        self.assertTrue(
            all(
                workspace.path.parent == output.resolve()
                for workspace in report.workspaces
            )
        )
        self.assertEqual(
            {path.name for path in alpha_path.glob("*.md")},
            {"AGENTS.md", "MEMORY.md", "HISTORY_INDEX.md", "HISTORY.md"},
        )
        self.assertIn("Alpha only", alpha_text)
        self.assertIn("Alpha memory only", alpha_text)
        self.assertNotIn("Beta only", alpha_text)
        self.assertNotIn("Beta memory only", alpha_text)
        self.assertNotIn("Composite only", alpha_text)
        self.assertIn("Beta only", beta_text)
        self.assertNotIn("Alpha only", beta_text)
        self.assertIn("Alpha memory only", composite_text)
        self.assertIn("Beta memory only", composite_text)
        self.assertIn("Be candid and honest", alpha_text)
        self.assertIn("historical evidence", alpha_text)
        self.assertIn("[REDACTED TOKEN]", alpha_text)
        self.assertIn("[REDACTED]", alpha_text)
        self.assertNotIn("Global memory", alpha_text)
        self.assertIn(
            "Global memory",
            (output / "_shared-memory" / "MEMORY.md").read_text(encoding="utf-8"),
        )
        self.assertNotIn("supersecret123", self.read_all_text(output))

    def test_standard_coverage_is_honest_about_omissions(self) -> None:
        session = next(
            session
            for session in discover_sessions(self.source)[0]
            if session.session_id == self.alpha["session_id"]
        )
        turns, coverage = parse_session(
            session, mode="standard", include_sidechains=False, redactor=Redactor()
        )

        self.assertEqual([turn.role for turn in turns], ["user", "assistant"])
        self.assertEqual(coverage.omitted_thinking_blocks, 1)
        self.assertEqual(coverage.omitted_tool_calls, 1)
        self.assertEqual(coverage.omitted_tool_results, 1)
        self.assertEqual(coverage.sidechain_files, 1)
        self.assertEqual(coverage.source_records_sidechain, 1)
        self.assertEqual(coverage.system_prompts_omitted, 1)

    def test_evidence_mode_includes_redacted_evidence_and_sidechains(self) -> None:
        output = self.root / "evidence-export"
        alpha_workspace = next(
            item
            for item in group_sessions(discover_sessions(self.source)[0])
            if item.name == "Alpha"
        )
        report = export_package(
            ExportOptions(
                source=self.source,
                output=output,
                include_evidence=True,
                workspace_ids=(alpha_workspace.workspace_id,),
            )
        )
        text = self.read_markdown(output / alpha_workspace.workspace_id)

        self.assertEqual(len(report.workspaces), 1)
        self.assertIn("Tool: Read", text)
        self.assertIn("File evidence", text)
        self.assertIn("Sidechain evidence", text)
        self.assertNotIn("private reasoning", text)
        self.assertGreater(report.coverage.exported_tool_calls, 0)
        self.assertGreater(report.coverage.exported_tool_results, 0)

    def test_can_omit_shared_memory(self) -> None:
        output = self.root / "no-shared-memory"
        report = export_package(
            ExportOptions(
                source=self.source, output=output, include_shared_memory=False
            )
        )

        self.assertFalse((output / "_shared-memory").exists())
        self.assertEqual(report.shared_memory_sources, 0)

    def test_install_writes_original_folders_without_mixing_or_overwriting(
        self,
    ) -> None:
        report = install_workspaces(InstallOptions(source=self.source))
        alpha_agents = (self.folder_a / "AGENTS.md").read_text(encoding="utf-8")
        alpha_memory = (self.folder_a / "MEMORY.md").read_text(encoding="utf-8")
        alpha_history = (self.folder_a / "HISTORY.md").read_text(encoding="utf-8")
        beta_history = (self.folder_b / "HISTORY.md").read_text(encoding="utf-8")

        self.assertEqual(report.sessions_installed, 2)
        self.assertEqual(len(report.workspaces), 2)
        self.assertEqual(len(report.skipped), 3)
        self.assertIn("Keep this content", alpha_agents)
        self.assertIn("cowork2chatgpt:instructions:start", alpha_agents)
        self.assertIn("Keep this memory", alpha_memory)
        self.assertIn("Alpha memory only", alpha_memory)
        self.assertNotIn("Beta memory only", alpha_memory)
        self.assertIn("Alpha only", alpha_history)
        self.assertNotIn("Beta only", alpha_history)
        self.assertNotIn("Composite only", alpha_history)
        self.assertIn("Beta only", beta_history)
        self.assertNotIn("Composite only", beta_history)

        install_workspaces(InstallOptions(source=self.source))
        alpha_agents = (self.folder_a / "AGENTS.md").read_text(encoding="utf-8")
        alpha_memory = (self.folder_a / "MEMORY.md").read_text(encoding="utf-8")
        alpha_history = (self.folder_a / "HISTORY.md").read_text(encoding="utf-8")
        self.assertEqual(alpha_agents.count("cowork2chatgpt:instructions:start"), 1)
        self.assertEqual(alpha_memory.count("cowork2chatgpt:memory:start"), 1)
        self.assertEqual(alpha_memory.count("Keep this memory"), 1)
        self.assertEqual(alpha_memory.count("Alpha instructions"), 1)
        self.assertEqual(alpha_history.count(self.alpha["session_id"]), 1)

        portable = self.root / "post-install-export"
        alpha_workspace = next(
            workspace
            for workspace in group_sessions(discover_sessions(self.source)[0])
            if workspace.name == "Alpha"
        )
        export_package(
            ExportOptions(
                source=self.source,
                output=portable,
                workspace_ids=(alpha_workspace.workspace_id,),
            )
        )
        portable_memory = (
            portable / alpha_workspace.workspace_id / "MEMORY.md"
        ).read_text(encoding="utf-8")
        self.assertEqual(portable_memory.count("Keep this memory"), 1)
        self.assertEqual(portable_memory.count("Alpha instructions"), 1)

    def test_install_refuses_to_replace_unrelated_history(self) -> None:
        unrelated = self.folder_b / "HISTORY.md"
        unrelated.write_text("# My hand-written history\n", encoding="utf-8")

        with self.assertRaises(CoworkExportError):
            install_workspaces(InstallOptions(source=self.source))

        self.assertEqual(
            unrelated.read_text(encoding="utf-8"), "# My hand-written history\n"
        )
        self.assertNotIn(
            "cowork2chatgpt:instructions:start",
            (self.folder_a / "AGENTS.md").read_text(encoding="utf-8"),
        )

    def test_refuses_unknown_workspace_and_existing_output(self) -> None:
        with self.assertRaises(CoworkExportError):
            export_package(
                ExportOptions(
                    source=self.source,
                    output=self.root / "unknown",
                    workspace_ids=("does-not-exist",),
                )
            )

        output = self.root / "existing"
        output.mkdir()
        with self.assertRaises(CoworkExportError):
            export_package(ExportOptions(source=self.source, output=output))

    def test_packing_respects_workspace_file_budget(self) -> None:
        documents = [f"# Session {index}\n\n" + ("x" * 8_000) for index in range(6)]
        chunks = pack_documents(documents, target_chars=10_000, max_chunks=2)

        self.assertLessEqual(len(chunks), 2)
        self.assertTrue(all("Imported Cowork history" in chunk for chunk in chunks))

    @staticmethod
    def read_markdown(output: Path) -> str:
        return "\n".join(
            path.read_text(encoding="utf-8") for path in sorted(output.glob("*.md"))
        )

    @staticmethod
    def read_all_text(output: Path) -> str:
        return "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in output.rglob("*")
            if path.is_file()
        )


if __name__ == "__main__":
    unittest.main()
