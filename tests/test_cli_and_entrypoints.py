"""Tests for crawly_core.cli, crawly.py, and downloader.py (100% coverage)."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import crawly as crawly_entry
import downloader as downloader_entry
from crawly_core.cli import (
    build_arg_parser,
    create_modern_progress,
    interactive_ai_flow,
    interactive_config_flow,
    interactive_download_flow,
    interactive_search_flow,
    list_workspace_csvs,
    main,
    prompt_select_csv,
    prompt_third_party_risk_acceptance,
    render_header,
    render_papers_table,
    run_doctor_diagnostics,
    run_interactive_tui,
)
from crawly_core.models import AppConfig, Paper, save_papers_to_csv


class TestCLIAndEntrypoints(unittest.TestCase):
    def test_risk_acceptance_and_ui_helpers(self) -> None:
        self.assertIsNotNone(create_modern_progress())

        # Auto-accept flag
        self.assertTrue(prompt_third_party_risk_acceptance("Test feature", auto_accept_flag=True))

        # Non-TTY stdin returns False
        with patch("crawly_core.cli.sys.stdin.isatty", return_value=False):
            self.assertFalse(prompt_third_party_risk_acceptance("Test feature", auto_accept_flag=False))

        # Interactive TTY Confirm.ask True and False
        with (
            patch("crawly_core.cli.sys.stdin.isatty", return_value=True),
            patch("crawly_core.cli.Confirm.ask", side_effect=[True, False]),
        ):
            self.assertTrue(prompt_third_party_risk_acceptance("Test feature"))
            self.assertFalse(prompt_third_party_risk_acceptance("Test feature"))

        cfg = AppConfig(ai_provider="extractive", use_scihub_fallback=False)
        render_header(cfg)
        papers = [Paper(title=f"Paper {i}", year=2020 + (i % 5), doi=f"10.1000/{i}", pdf_url="https://x.org/1.pdf") for i in range(30)]
        render_papers_table(papers, max_rows=5)

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            save_papers_to_csv(papers[:2], tdir / "dataset_a.csv")
            save_papers_to_csv(papers[:1], tdir / "papers_not_found.csv")
            old_cwd = Path.cwd()
            try:
                os.chdir(tdir)
                csvs = list_workspace_csvs(tdir)
                self.assertEqual(len(csvs), 1)
                with patch("crawly_core.cli.Prompt.ask", side_effect=["1", "custom_name"]):
                    self.assertEqual(prompt_select_csv().name, "dataset_a.csv")
                    self.assertEqual(prompt_select_csv().name, "custom_name.csv")
                # When no CSVs exist in directory
                (tdir / "dataset_a.csv").unlink()
                with patch("crawly_core.cli.Prompt.ask", return_value="fallback.csv"):
                    self.assertEqual(prompt_select_csv().name, "fallback.csv")
            finally:
                os.chdir(old_cwd)

    def test_interactive_flows(self) -> None:
        cfg = AppConfig(ai_provider="extractive")
        sample_papers = [Paper(title="Sample SAR Paper", year=2023, doi="10.1000/sar1", abstract="SAR abstract text.")]

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            old_cwd = Path.cwd()
            try:
                os.chdir(tdir)

                # 1. interactive_search_flow: empty query
                with patch("crawly_core.cli.Prompt.ask", return_value=""):
                    self.assertIsNone(interactive_search_flow(cfg))

                # 2. interactive_search_flow: preset 1 (found papers), preset 2 (no papers), preset 3, preset 4 (accepted & declined), preset 5
                with (
                    patch("crawly_core.cli.Prompt.ask", side_effect=["radar", "1", "5", "relevance", "out1.csv"]),
                    patch("crawly_core.cli.Confirm.ask", return_value=False),
                    patch("crawly_core.cli.search_multi_source", side_effect=lambda **kw: (kw["progress_callback"]("OpenAlex", 1), sample_papers)[1]),
                ):
                    res_csv = interactive_search_flow(cfg)
                    self.assertIsNotNone(res_csv)

                # Preset 2 -> empty results
                with (
                    patch("crawly_core.cli.Prompt.ask", side_effect=["radar", "2", "5", "relevance", "out2"]),
                    patch("crawly_core.cli.search_multi_source", return_value=[]),
                ):
                    self.assertIsNone(interactive_search_flow(cfg))

                # Preset 3 + Preset 4 (risk declined & risk accepted) + trigger download
                with (
                    patch("crawly_core.cli.Prompt.ask", side_effect=["radar", "3", "5", "relevance", "out3"]),
                    patch("crawly_core.cli.Confirm.ask", return_value=True),
                    patch("crawly_core.cli.search_multi_source", return_value=sample_papers),
                    patch("crawly_core.cli.interactive_download_flow") as mock_dl_flow,
                ):
                    interactive_search_flow(cfg)
                    mock_dl_flow.assert_called_once()

                with (
                    patch("crawly_core.cli.Prompt.ask", side_effect=["radar", "4", "1-2", "5", "relevance", "out4"]),
                    patch("crawly_core.cli.prompt_third_party_risk_acceptance", return_value=True),
                    patch("crawly_core.cli.Confirm.ask", return_value=False),
                    patch("crawly_core.cli.search_multi_source", return_value=sample_papers),
                ):
                    interactive_search_flow(cfg)

                with (
                    patch("crawly_core.cli.Prompt.ask", side_effect=["radar", "5", "5", "relevance", "out5"]),
                    patch("crawly_core.cli.prompt_third_party_risk_acceptance", return_value=False),
                    patch("crawly_core.cli.Confirm.ask", return_value=False),
                    patch("crawly_core.cli.search_multi_source", return_value=sample_papers),
                ):
                    interactive_search_flow(cfg)

                # 3. interactive_download_flow (missing CSV + Mode 1 Legal OA + Mode 2 Risk Accepted/Declined)
                self.assertIsNone(interactive_download_flow(cfg, preset_csv=tdir / "missing.csv"))

                csv_path = save_papers_to_csv(sample_papers, tdir / "dl_test.csv")

                def _fake_batch_dl(**kwargs):
                    cb = kwargs.get("progress_callback")
                    if cb:
                        cb(1, 2, sample_papers[0], True, "OpenAlex OA")
                        cb(2, 2, sample_papers[0], False, "Not Found")
                    return {"total": 2, "downloaded": 1, "missing": 1, "OpenAlex OA": 1}

                with (
                    patch("crawly_core.cli.Prompt.ask", return_value="1"),
                    patch("crawly_core.cli.download_batch_pdfs", side_effect=_fake_batch_dl),
                ):
                    self.assertEqual(interactive_download_flow(cfg, preset_csv=csv_path), csv_path)

                with (
                    patch("crawly_core.cli.Prompt.ask", return_value="2"),
                    patch("crawly_core.cli.prompt_third_party_risk_acceptance", side_effect=[True, False]),
                    patch("crawly_core.cli.download_batch_pdfs", side_effect=_fake_batch_dl),
                ):
                    interactive_download_flow(cfg, preset_csv=csv_path, custom_scihub_url="https://sci-hub.se")
                    interactive_download_flow(cfg, preset_csv=csv_path, custom_scihub_url="https://sci-hub.se")

                # 4. interactive_ai_flow (missing CSV + Mode 4 [1+2] + Mode 3 Q&A)
                interactive_ai_flow(cfg, preset_csv=tdir / "missing.csv")

                with patch("crawly_core.cli.Prompt.ask", return_value="4"):
                    interactive_ai_flow(cfg, preset_csv=csv_path)

                with patch("crawly_core.cli.Prompt.ask", side_effect=["What is SAR?", "exit"]):
                    interactive_ai_flow(cfg, preset_csv=csv_path, preset_mode="3")

                # 5. interactive_config_flow across choices 1..6
                for choice_idx, extra_prompts in [
                    ("1", ["http://localhost:11434", "llama3.2"]),
                    ("2", ["http://localhost:1234/v1", "local-model"]),
                    ("3", ["https://api.openai.com/v1", "sk-key", "gpt-4o-mini"]),
                    ("4", ["gem-key", "gemini-2.5-flash"]),
                    ("5", ["ant-key", "claude-3-5-sonnet-latest"]),
                    ("6", []),
                ]:
                    tail_prompts = ["0.2", "25", "10", "crawly.theliteratureassistant@gmail.com"]
                    with (
                        patch("crawly_core.cli.discover_local_models", return_value=["detected-model"] if choice_idx in ("1", "2") else []),
                        patch("crawly_core.cli.Prompt.ask", side_effect=[choice_idx, *extra_prompts, *tail_prompts]),
                    ):
                        interactive_config_flow(cfg)

                # Also test choice 1 & 2 when no local models are detected
                for choice_idx, extra_prompts in [
                    ("1", ["http://localhost:11434", "llama3.2"]),
                    ("2", ["http://localhost:1234/v1", "local-model"]),
                ]:
                    tail_prompts = ["0.2", "25", "10", "crawly.theliteratureassistant@gmail.com"]
                    with (
                        patch("crawly_core.cli.discover_local_models", return_value=[]),
                        patch("crawly_core.cli.Prompt.ask", side_effect=[choice_idx, *extra_prompts, *tail_prompts]),
                    ):
                        interactive_config_flow(cfg)

                # 6. run_doctor_diagnostics
                with patch("requests.get", return_value=MagicMock(status_code=200)):
                    run_doctor_diagnostics(cfg)

                # 7. run_interactive_tui menu loop
                with (
                    patch("crawly_core.cli.Prompt.ask", side_effect=["1", "2", "3", "4", "5", "6", "7", "0"]),
                    patch("crawly_core.cli.interactive_search_flow", return_value=csv_path),
                    patch("crawly_core.cli.interactive_download_flow", return_value=csv_path),
                    patch("crawly_core.cli.interactive_ai_flow"),
                    patch("crawly_core.cli.interactive_config_flow", return_value=cfg),
                    patch("crawly_core.cli.prompt_select_csv", return_value=csv_path),
                    patch("crawly_core.cli.run_doctor_diagnostics"),
                ):
                    run_interactive_tui()
            finally:
                os.chdir(old_cwd)

    def test_cli_main_subcommands_and_entrypoints(self) -> None:
        sample_papers = [
            Paper(title="CLI SAR Paper", year=2023, doi="10.1000/cli1", abstract="CLI abstract"),
            Paper(title="CLI Ref Paper", year=2020, doi="10.1000/cli2", abstract="Ref abstract"),
            Paper(title="CLI Citing Paper", year=2024, doi="10.1000/cli3", abstract="Citing abstract"),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            old_cwd = Path.cwd()
            try:
                os.chdir(tdir)
                csv_p = save_papers_to_csv(sample_papers, tdir / "cli_ds.csv")

                # No args -> run_interactive_tui
                with patch("crawly_core.cli.run_interactive_tui") as mock_tui:
                    self.assertEqual(main([]), 0)
                    mock_tui.assert_called_once()

                # doctor
                with patch("crawly_core.cli.run_doctor_diagnostics"):
                    self.assertEqual(main(["doctor"]), 0)

                # export-bibtex
                self.assertEqual(main(["export-bibtex", "cli_ds.csv"]), 0)

                # config (--show and updates)
                self.assertEqual(main(["config", "--show"]), 0)
                self.assertEqual(
                    main(
                        [
                            "config",
                            "--provider",
                            "extractive",
                            "--model",
                            "extractive-bm25",
                            "--base-url",
                            "http://localhost:11434",
                            "--api-key",
                            "k",
                            "--temperature",
                            "0.3",
                            "--max-pdf-pages",
                            "20",
                            "--limit",
                            "12",
                        ]
                    ),
                    0,
                )

                # search (default sources + google_scholar risk declined)
                with (
                    patch("crawly_core.cli.prompt_third_party_risk_acceptance", return_value=False),
                    patch(
                        "crawly_core.cli.search_multi_source",
                        side_effect=lambda **kw: (kw["progress_callback"]("OpenAlex", 1), sample_papers)[1],
                    ),
                ):
                    self.assertEqual(
                        main(["search", "radar", "-s", "google_scholar", "-o", "s_out", "--min-year", "2020", "--max-year", "2025"]),
                        0,
                    )

                # download (Legal OA + --enable-scihub --accept-risk)
                with patch(
                    "crawly_core.cli.download_batch_pdfs",
                    side_effect=lambda **kw: (kw["progress_callback"](1, 1, sample_papers[0], True, "OA"), {"total": 1, "downloaded": 1, "missing": 0})[1],
                ):
                    self.assertEqual(main(["download", "cli_ds.csv"]), 0)
                    self.assertEqual(main(["download", "cli_ds.csv", "--enable-scihub", "--accept-risk"]), 0)

                # ai (mode all + mode 3 with -q and without -q)
                self.assertEqual(
                    main(
                        [
                            "ai",
                            "cli_ds.csv",
                            "--mode",
                            "all",
                            "--provider",
                            "extractive",
                            "--model",
                            "extractive-bm25",
                            "--base-url",
                            "http://localhost:11434",
                            "--api-key",
                            "k",
                        ]
                    ),
                    0,
                )
                self.assertEqual(main(["ai", "cli_ds.csv", "--mode", "3", "-q", "What is SAR?"]), 0)
                with patch("crawly_core.cli.interactive_ai_flow") as mock_ai_flow:
                    self.assertEqual(main(["ai", "cli_ds.csv", "--mode", "3"]), 0)
                    mock_ai_flow.assert_called_once()

                # pipeline (default Legal OA + --enable-scihub --accept-risk)
                with (
                    patch(
                        "crawly_core.cli.search_multi_source",
                        side_effect=lambda **kw: (kw["progress_callback"]("OpenAlex", 1), sample_papers)[1],
                    ),
                    patch(
                        "crawly_core.cli.download_batch_pdfs",
                        side_effect=lambda **kw: (kw["progress_callback"](1, 1, sample_papers[0], True, "OA"), {"total": 1, "downloaded": 1, "missing": 0})[1],
                    ),
                ):
                    self.assertEqual(main(["pipeline", "radar", "-o", "pipe_ds.csv", "--mode", "all"]), 0)
                    self.assertEqual(
                        main(["pipeline", "radar", "-o", "pipe_ds2", "--enable-scihub", "--accept-risk", "--mode", "1"]),
                        0,
                    )

                # Cover remaining edge cases in cli.py:
                # 1. interactive_search_flow with unrecognized source choice ("9")
                with (
                    patch("crawly_core.cli.Prompt.ask", side_effect=["radar", "9", "5", "relevance", "out_9.csv"]),
                    patch("crawly_core.cli.Confirm.ask", return_value=False),
                    patch("crawly_core.cli.search_multi_source", return_value=sample_papers),
                ):
                    interactive_search_flow(AppConfig())

                # 2. run_doctor_diagnostics when requests.get raises a network error
                with (
                    patch("requests.get", side_effect=RuntimeError("DNS failure")),
                    patch("crawly_core.cli.LLMClient.check_connection", return_value=(False, "Offline")),
                ):
                    run_doctor_diagnostics(AppConfig())

                # 3. main(["search", ...]) with --sources all
                with patch("crawly_core.cli.search_multi_source", return_value=sample_papers):
                    self.assertEqual(main(["search", "radar", "--sources", "all", "-o", "all_src.csv"]), 0)

                # 4. New feature subcommands: snowball, report, zotero, watch, and mode gaps
                # snowball
                with patch("crawly_core.cli.fetch_citation_snowball", return_value=(sample_papers[0], [sample_papers[1]], [sample_papers[2]])):
                    self.assertEqual(main(["snowball", "10.1000/anchor", "-l", "5"]), 0)
                with patch("crawly_core.cli.fetch_citation_snowball", return_value=(None, [], [])):
                    self.assertEqual(main(["snowball", "unknown_anchor"]), 0)

                # report
                self.assertEqual(main(["report", "cli_ds.csv"]), 0)
                empty_csv = tdir / "empty.csv"
                empty_csv.write_text("Title,Authors\n", encoding="utf-8")
                self.assertEqual(main(["report", str(empty_csv)]), 0)

                # zotero
                with patch("crawly_core.downloader.requests.get", return_value=MagicMock(status_code=200)):
                    self.assertEqual(main(["zotero", "cli_ds.csv", "-c", "MyCollection"]), 0)
                self.assertEqual(main(["zotero", str(empty_csv)]), 0)

                # watch
                with (
                    patch("crawly_core.cli.search_multi_source", return_value=[sample_papers[0]]),
                    patch("crawly_core.cli.download_batch_pdfs", return_value={"total": 1, "downloaded": 1}),
                ):
                    self.assertEqual(main(["watch", "radar imaging", "-d", "5", "-l", "2"]), 0)
                with patch("crawly_core.cli.search_multi_source", return_value=[]):
                    self.assertEqual(main(["watch", "empty topic", "--no-download"]), 0)

                # ai --mode gaps and pipeline --mode gaps
                self.assertEqual(main(["ai", "cli_ds.csv", "--mode", "gaps"]), 0)
                with (
                    patch("crawly_core.cli.search_multi_source", return_value=[sample_papers[0]]),
                    patch("crawly_core.cli.download_batch_pdfs", return_value={"total": 1, "downloaded": 1}),
                ):
                    self.assertEqual(main(["pipeline", "radar", "--mode", "gaps", "-o", "pipe_gaps"]), 0)

                # Interactive TUI menu choices 8, 9, 10, 11
                with (
                    patch("crawly_core.cli.Prompt.ask", side_effect=["8", "10.1000/anchor", "9", "cli_ds.csv", "10", "cli_ds.csv", "11", "radar", "0"]),
                    patch("crawly_core.cli.fetch_citation_snowball", return_value=(sample_papers[0], [], [])),
                    patch("crawly_core.cli.search_multi_source", return_value=[sample_papers[0]]),
                    patch("crawly_core.downloader.requests.get", side_effect=OSError("offline")),
                ):
                    run_interactive_tui()

                # 5. main() when parser returns an unrecognized command
                with patch("argparse.ArgumentParser.parse_args", return_value=MagicMock(config=None, command="unknown_cmd")):
                    self.assertEqual(main(["unknown_cmd"]), 0)

                # Test crawly.py and downloader.py entrypoints
                self.assertTrue(callable(crawly_entry.main))
                with patch("urllib.request.urlopen", return_value=MagicMock()):
                    self.assertTrue(downloader_entry.connect())
                with patch("urllib.request.urlopen", side_effect=OSError("offline")):
                    self.assertFalse(downloader_entry.connect())

                with patch("downloader.connect", return_value=False):
                    self.assertEqual(downloader_entry.main(), 1)

                with (
                    patch("downloader.connect", return_value=True),
                    patch("downloader.prompt_select_csv", return_value=csv_p),
                    patch("downloader.interactive_download_flow", return_value=csv_p),
                    patch("downloader.Confirm.ask", return_value=True),
                    patch("downloader.interactive_ai_flow") as mock_dl_ai,
                ):
                    self.assertEqual(downloader_entry.main(), 0)
                    mock_dl_ai.assert_called_once()
            finally:
                os.chdir(old_cwd)
