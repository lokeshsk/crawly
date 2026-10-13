"""Tests for crawly_core.models (100% coverage)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crawly_core.models import (
    AppConfig,
    Paper,
    export_papers_to_bibtex,
    load_papers_from_csv,
    resolve_config_path,
    save_papers_to_csv,
)


class TestModels(unittest.TestCase):
    def test_paper_methods_and_csv_roundtrip(self) -> None:
        p1 = Paper(
            title="[PDF] A Very Long Paper Title With Special / * ? : < > | Chars " + ("x" * 130),
            year=2024,
            authors="Alice Smith, Bob Jones",
            publication="IEEE Transactions",
            url="https://doi.org/10.1109/test.1",
            doi="10.1109/test.1",
            pdf_url="https://example.org/p1.pdf",
            abstract="This is {an} abstract.",
            citations=42,
            source="OpenAlex",
            local_pdf="/tmp/p1.pdf",
            download_source="OpenAlex",
            summary="Structured summary text",
        )
        self.assertFalse(p1.clean_title().startswith("[PDF]"))
        fname = p1.safe_filename(max_len=40)
        self.assertTrue(fname.endswith(".pdf"))
        self.assertLessEqual(len(fname), 44)

        p_empty = Paper(title="", doi="10.1000/xyz.pdf")
        self.assertEqual(p_empty.safe_filename(), "10.1000_xyz.pdf")

        row = p1.to_csv_row()
        p1_reloaded = Paper.from_csv_row({**row, "AI Summary": "Summary!"})
        self.assertEqual(p1_reloaded.year, 2024)
        self.assertEqual(p1_reloaded.citations, 42)
        self.assertEqual(p1_reloaded.summary, "Summary!")

        # Test edge cases in from_csv_row (_str None/nan, _int invalid/nan)
        p_edge = Paper.from_csv_row(
            {
                "Paper Title": None,
                "Year": "invalid_int",
                "Author": "nan",
                "Citations": None,
            }
        )
        self.assertEqual(p_edge.title, "Untitled")
        self.assertEqual(p_edge.year, 0)
        self.assertEqual(p_edge.authors, "Unknown")
        self.assertEqual(p_edge.citations, 0)

        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            csv_file = save_papers_to_csv([p1, p1], tdir / "sample_dataset", extra_fields=["AI Summary", "Paper Title"])
            self.assertTrue(csv_file.exists())
            self.assertEqual(csv_file.suffix, ".csv")

            # Load with and without .csv suffix
            loaded1 = load_papers_from_csv(csv_file)
            loaded2 = load_papers_from_csv(tdir / "sample_dataset")
            self.assertEqual(len(loaded1), 2)
            self.assertEqual(len(loaded2), 2)

            with self.assertRaises(FileNotFoundError):
                load_papers_from_csv(tdir / "non_existent_file.csv")

            # BibTeX export (with and without .bib extension, duplicate cite_keys)
            bib_file = export_papers_to_bibtex([p1, p1, p_edge], tdir / "refs")
            self.assertTrue(bib_file.exists())
            self.assertEqual(bib_file.suffix, ".bib")
            bib_text = bib_file.read_text(encoding="utf-8")
            self.assertIn("@article{", bib_text)
            self.assertIn("_2,", bib_text)

    def test_resolve_config_path_and_appconfig(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            cfg_file = tdir / "config.json"

            # Save & Load when file doesn't exist yet (auto-creates)
            cfg = AppConfig.load(path=cfg_file)
            self.assertTrue(cfg_file.exists())
            self.assertEqual(cfg.ai_provider, "ollama")

            # Custom JSON with _documentation and api_endpoints
            cfg_file.write_text(
                json.dumps(
                    {
                        "_documentation": {"note": "ignored"},
                        "ai_provider": "lmstudio",
                        "ai_model": "qwen2.5",
                        "temperature": 0.5,
                        "api_endpoints": {"openalex_works": "https://custom.openalex.org/works"},
                        "unknown_field": "ignored",
                    }
                ),
                encoding="utf-8",
            )
            cfg2 = AppConfig.load(path=cfg_file)
            self.assertEqual(cfg2.ai_provider, "lmstudio")
            self.assertEqual(cfg2.ai_model, "qwen2.5")
            self.assertEqual(cfg2.temperature, 0.5)
            self.assertEqual(cfg2.api_endpoints["openalex_works"], "https://custom.openalex.org/works")

            # Test environment variable overrides
            with patch.dict(
                os.environ,
                {
                    "CRAWLY_AI_PROVIDER": "openai_compatible",
                    "CRAWLY_AI_MODEL": "gpt-4o-mini",
                    "CRAWLY_AI_BASE_URL": "https://api.openai.com/v1",
                    "CRAWLY_AI_API_KEY": "sk-test",
                },
                clear=False,
            ):
                cfg_env = AppConfig.load(path=cfg_file)
                self.assertEqual(cfg_env.ai_provider, "openai_compatible")
                self.assertEqual(cfg_env.ai_model, "gpt-4o-mini")
                self.assertEqual(cfg_env.ai_base_url, "https://api.openai.com/v1")
                self.assertEqual(cfg_env.ai_api_key, "sk-test")

            # Test provider-specific API key env vars
            cfg_file.write_text(json.dumps({"ai_provider": "openai_compatible", "ai_api_key": ""}), encoding="utf-8")
            with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-oa"}, clear=True):
                self.assertEqual(AppConfig.load(path=cfg_file).ai_api_key, "sk-oa")

            cfg_file.write_text(json.dumps({"ai_provider": "gemini", "ai_api_key": ""}), encoding="utf-8")
            with patch.dict(os.environ, {"GEMINI_API_KEY": "gem-key"}, clear=True):
                self.assertEqual(AppConfig.load(path=cfg_file).ai_api_key, "gem-key")

            cfg_file.write_text(json.dumps({"ai_provider": "anthropic", "ai_api_key": ""}), encoding="utf-8")
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "ant-key"}, clear=True):
                self.assertEqual(AppConfig.load(path=cfg_file).ai_api_key, "ant-key")

            # Test empty row in CSV (line 208)
            csv_file = tdir / "empty_row.csv"
            csv_file.write_text("Title,Authors\n\n", encoding="utf-8")
            p1 = Paper(title="Sample Row")
            with patch("crawly_core.models.csv.DictReader", return_value=[{}, p1.to_csv_row()]):
                self.assertEqual(len(load_papers_from_csv(csv_file)), 1)

            # Test resolve_config_path branches (including when neither cwd nor root exists -> line 22)
            old_cwd = Path.cwd()
            try:
                os.chdir(tdir)
                self.assertEqual(resolve_config_path(), cfg_file)
                cfg_file.unlink()
                resolved = resolve_config_path()
                self.assertEqual(resolved.name, "config.json")
                with patch.object(Path, "exists", return_value=False):
                    self.assertEqual(resolve_config_path().name, "config.json")
            finally:
                os.chdir(old_cwd)
