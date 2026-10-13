"""Tests for crawly_core.ai_engine (100% coverage)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from crawly_core.ai_engine import (
    LLMClient,
    PaperRAGIndex,
    _extractive_structured_summary,
    discover_local_models,
    extract_paper_fulltext,
    extract_pdf_pages,
    run_mode_1_per_paper_summaries,
    run_mode_2_literature_review_synthesis,
)
from crawly_core.models import AppConfig, Paper


class TestAIEngine(unittest.TestCase):
    def test_extract_pdf_pages_and_fulltext(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tdir = Path(tmp)
            missing_pdf = tdir / "missing.pdf"
            self.assertEqual(extract_pdf_pages(missing_pdf), [])

            fake_pdf = tdir / "Sample Paper.pdf"
            fake_pdf.write_bytes(b"%PDF-1.5\n" + (b"a" * 2048))

            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Hyphen-\nated text on page one."
            mock_reader = MagicMock()
            mock_reader.pages = [mock_page]

            with patch("crawly_core.ai_engine.PdfReader", return_value=mock_reader):
                pages = extract_pdf_pages(fake_pdf, max_pages=5)
                self.assertEqual(len(pages), 1)
                self.assertIn("Hyphenated", pages[0][1])

                p_with_pdf = Paper(title="Sample Paper", local_pdf=str(fake_pdf))
                txt, basis = extract_paper_fulltext(p_with_pdf, output_dir=tdir)
                self.assertIn("Full PDF", basis)
                self.assertIn("[Page 1]", txt)

            # Fallback to abstract and metadata only
            p_abs = Paper(title="No PDF Paper", abstract="Abstract content only")
            txt_a, basis_a = extract_paper_fulltext(p_abs, output_dir=tdir)
            self.assertEqual(basis_a, "Abstract")
            self.assertEqual(txt_a, "Abstract content only")

            p_meta = Paper(title="Meta Paper", year=2024, authors="K. Author", publication="IEEE")
            txt_m, basis_m = extract_paper_fulltext(p_meta, output_dir=tdir)
            self.assertEqual(basis_m, "Metadata Only")
            self.assertIn("Meta Paper", txt_m)

    @patch("crawly_core.ai_engine.requests.get")
    @patch("crawly_core.ai_engine.requests.post")
    def test_discover_models_and_llm_client(self, mock_post: MagicMock, mock_get: MagicMock) -> None:
        # discover_local_models for ollama and lmstudio
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": [{"name": "llama3.2"}]})
        self.assertEqual(discover_local_models("ollama", "http://localhost:11434"), ["llama3.2"])

        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": [{"id": "qwen2.5-7b"}]})
        self.assertEqual(discover_local_models("lmstudio", "http://localhost:1234/v1"), ["qwen2.5-7b"])

        # LLMClient.check_connection across all providers
        self.assertTrue(LLMClient(AppConfig(ai_provider="extractive")).check_connection()[0])

        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": [{"name": "mistral"}]})
        c_ollama = LLMClient(AppConfig(ai_provider="ollama", ai_model="other"))
        self.assertTrue(c_ollama.check_connection()[0])
        self.assertEqual(c_ollama.config.ai_model, "mistral")

        mock_get.return_value = MagicMock(status_code=500)
        self.assertFalse(LLMClient(AppConfig(ai_provider="ollama")).check_connection()[0])

        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": [{"id": "lm-model"}]})
        c_lms = LLMClient(AppConfig(ai_provider="lmstudio", ai_model="other"))
        self.assertTrue(c_lms.check_connection()[0])
        mock_get.return_value = MagicMock(status_code=500)
        self.assertFalse(LLMClient(AppConfig(ai_provider="lmstudio")).check_connection()[0])

        self.assertFalse(LLMClient(AppConfig(ai_provider="openai_compatible", ai_base_url="")).check_connection()[0])
        self.assertTrue(LLMClient(AppConfig(ai_provider="openai_compatible", ai_base_url="http://localhost:8000/v1")).check_connection()[0])

        self.assertFalse(LLMClient(AppConfig(ai_provider="gemini", ai_api_key="")).check_connection()[0])
        self.assertTrue(LLMClient(AppConfig(ai_provider="gemini", ai_api_key="k")).check_connection()[0])

        self.assertFalse(LLMClient(AppConfig(ai_provider="anthropic", ai_api_key="")).check_connection()[0])
        self.assertTrue(LLMClient(AppConfig(ai_provider="anthropic", ai_api_key="k")).check_connection()[0])

        self.assertFalse(LLMClient(AppConfig(ai_provider="unknown_xyz")).check_connection()[0])

        # LLMClient.generate across all providers
        self.assertIsNone(LLMClient(AppConfig(ai_provider="extractive")).generate("sys", "usr"))

        # Ollama generate
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"models": [{"name": "llama3.2"}]})
        mock_post.return_value = MagicMock(status_code=200, json=lambda: {"message": {"content": "Ollama answer"}})
        self.assertEqual(LLMClient(AppConfig(ai_provider="ollama", ai_model="other")).generate("s", "u"), "Ollama answer")

        # LM Studio / OpenAI-compatible generate
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"data": [{"id": "local-m"}]})
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"choices": [{"message": {"content": "OpenAI answer"}}]},
        )
        self.assertEqual(
            LLMClient(AppConfig(ai_provider="lmstudio", ai_model="other", ai_api_key="sk-1")).generate("s", "u"),
            "OpenAI answer",
        )

        # Gemini generate
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"candidates": [{"content": {"parts": [{"text": "Gemini answer"}]}}]},
        )
        self.assertEqual(
            LLMClient(AppConfig(ai_provider="gemini", ai_model="other", ai_api_key="gk")).generate("s", "u"),
            "Gemini answer",
        )

        # Anthropic generate
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"content": [{"type": "text", "text": "Claude answer"}]},
        )
        self.assertEqual(
            LLMClient(AppConfig(ai_provider="anthropic", ai_model="other", ai_api_key="ak")).generate("s", "u"),
            "Claude answer",
        )

        # Non-200 returns None
        mock_post.return_value = MagicMock(status_code=500)
        self.assertIsNone(LLMClient(AppConfig(ai_provider="anthropic", ai_api_key="ak")).generate("s", "u"))

    def test_modes_1_2_3_and_extractive(self) -> None:
        p1 = Paper(
            title="Compressed Sensing SAR Imaging",
            year=2023,
            authors="Alice, Bob",
            publication="IEEE TGRS",
            doi="10.1109/sar.1",
            abstract=(
                "In this paper we propose a novel compressed sensing framework for synthetic aperture radar imaging. "
                "The proposed algorithm uses an L1-norm regularization model and matched filtering formulation. "
                "Experimental simulation results demonstrate a 4 dB improvement in signal-to-noise ratio and high accuracy. "
                "However, computational complexity remains a challenge for future real-time onboard work."
            ),
        )
        p_short = Paper(title="Short Paper", year=2022, authors="C. Author", publication="Venue")
        self.assertIn("Objective:", _extractive_structured_summary(p_short, "tiny", "Metadata"))
        self.assertIn("Methodology:", _extractive_structured_summary(p1, p1.abstract, "Abstract"))

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            cfg_ext = AppConfig(ai_provider="extractive")

            # Mode 1 (extractive fallback)
            m1_cbs = []
            rep1 = run_mode_1_per_paper_summaries(
                [p1, p_short],
                output_dir=out_dir,
                dataset_name="test_ds",
                config=cfg_ext,
                progress_callback=lambda i, t, p, b: m1_cbs.append((i, b)),
            )
            self.assertTrue(rep1.exists())
            self.assertEqual(len(m1_cbs), 2)

            # Mode 2 (extractive fallback + LLM success branch)
            m2_cbs = []
            syn_ext, rev_path = run_mode_2_literature_review_synthesis(
                [p1],
                output_dir=out_dir,
                dataset_name="test_ds",
                config=cfg_ext,
                progress_callback=lambda i, t, msg: m2_cbs.append(msg),
            )
            self.assertTrue(rev_path.exists())
            self.assertIn("Comparative Literature Matrix", syn_ext)
            self.assertGreaterEqual(len(m2_cbs), 2)

            with patch.object(LLMClient, "generate", return_value="## LLM Synthesis Section"):
                syn_llm, _ = run_mode_2_literature_review_synthesis([p1], output_dir=out_dir, dataset_name="test_ds", config=cfg_ext)
                self.assertIn("## LLM Synthesis Section", syn_llm)

            # Extractive summary fallback when no keywords match any sentence
            no_kw_summary = _extractive_structured_summary(
                p1,
                "First generic sentence with sufficient length to be retained by splitter. Second generic sentence also with sufficient characters for testing.",
                "Abstract",
            )
            self.assertIn("First generic sentence", no_kw_summary)

            # Mode 3 (PaperRAGIndex with explicit local_pdf, output_dir PDF, and abstract fallback)
            pdf_file = out_dir / p1.safe_filename()
            pdf_file.write_bytes(b"%PDF-1.5\n" + (b"x" * 2048))
            p_local = Paper(title="Direct Local PDF Paper", authors="Lee", year="2024", local_pdf=str(pdf_file))
            long_page_text = " ".join([f"word{i}" for i in range(200)]) + " compressed sensing radar reconstruction algorithm."
            with patch("crawly_core.ai_engine.extract_pdf_pages", return_value=[(1, "short"), (2, long_page_text)]):
                idx_cbs = []
                rag = PaperRAGIndex(
                    [p1, p_short, p_local],
                    output_dir=out_dir,
                    config=cfg_ext,
                    progress_callback=lambda i, t, pp: idx_cbs.append(i),
                )
                self.assertEqual(len(idx_cbs), 3)
                self.assertGreaterEqual(len(rag.chunks), 2)

                # Retrieve with query and empty query
                self.assertTrue(rag.retrieve(""))
                hits = rag.retrieve("compressed sensing radar")
                self.assertTrue(hits)

                # Answer question in extractive mode and LLM mode
                ans_ext = rag.answer_question("What compressed sensing algorithm is used?", config=cfg_ext)
                self.assertIn("Retrieved Evidence", ans_ext)

                with patch.object(LLMClient, "generate", return_value="Cited answer [Paper #1, Page 2]"):
                    ans_llm = rag.answer_question("What compressed sensing algorithm is used?", config=cfg_ext)
                    self.assertIn("[Paper #1, Page 2]", ans_llm)

                # Empty chunks edge case
                rag.chunks = []
                self.assertIn("No indexed text passages", rag.answer_question("anything", config=cfg_ext))

            # Test run_mode_gaps_synthesis (extractive fallback and LLM mode)
            from crawly_core.ai_engine import generate_interactive_html_report, run_mode_gaps_synthesis

            gaps_cbs = []
            gaps_ext, gaps_p = run_mode_gaps_synthesis(
                [p1, p_short],
                output_dir=out_dir,
                dataset_name="test_gaps",
                config=cfg_ext,
                progress_callback=lambda s, t, msg: gaps_cbs.append(msg),
            )
            self.assertTrue(gaps_p.exists())
            self.assertIn("AI Research Gaps", gaps_ext)
            self.assertGreaterEqual(len(gaps_cbs), 2)

            with patch.object(LLMClient, "generate", return_value="## LLM Open Challenges Synthesis"):
                gaps_llm, _ = run_mode_gaps_synthesis([p1], output_dir=out_dir, dataset_name="test_gaps", config=cfg_ext)
                self.assertIn("## LLM Open Challenges Synthesis", gaps_llm)

            # Test generate_interactive_html_report
            html_rep = generate_interactive_html_report(
                [p1, p_short, p_local],
                dataset_name="test_ds",
                output_dir=out_dir,
                summaries={p1.clean_title(): "Summary for p1"},
                synthesis_md="## Synthesis content",
                gaps_md="## Gaps content",
                config=cfg_ext,
            )
            self.assertTrue(html_rep.exists())
            html_txt = html_rep.read_text(encoding="utf-8")
            self.assertIn("Literature Review Dashboard", html_txt)
            self.assertIn("Compressed Sensing SAR Imaging", html_txt)
            self.assertIn("Summary for p1", html_txt)
            self.assertIn("Synthesis content", html_txt)

