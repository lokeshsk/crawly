"""Tests for crawly_core.downloader (100% coverage)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from crawly_core.downloader import (
    _candidate_europe_pmc_urls,
    _candidate_publisher_oa_urls,
    _candidate_semantic_scholar_urls,
    _candidate_unpaywall_urls,
    _extract_pdf_url_from_html,
    _fetch_and_verify_pdf,
    _title_similarity,
    _try_scihub_download,
    download_batch_pdfs,
    download_paper_pdf,
    extract_doi_from_text_or_url,
    resolve_paper_metadata,
)
from crawly_core.models import AppConfig, Paper


class TestDownloader(unittest.TestCase):
    def test_similarity_and_doi_extraction(self) -> None:
        self.assertEqual(_title_similarity("", "abc"), 0.0)
        self.assertEqual(_title_similarity("A sufficiently long title for substring match", "A sufficiently long title for substring match extra"), 1.0)
        self.assertGreater(_title_similarity("Short title one", "Short title two"), 0.5)

        self.assertEqual(extract_doi_from_text_or_url(""), "")
        self.assertEqual(extract_doi_from_text_or_url("no doi here"), "")
        self.assertEqual(
            extract_doi_from_text_or_url("https://link.springer.com/article/10.1007/s11042-020-09876-5.pdf"),
            "10.1007/s11042-020-09876-5",
        )

    @patch("crawly_core.downloader.requests.get")
    def test_resolve_paper_metadata(self, mock_get: MagicMock) -> None:
        cfg = AppConfig()
        # Case 1: Paper already has DOI in URL -> resolves via OpenAlex DOI endpoint
        p1 = Paper(title="SAR Imaging Paper", url="https://doi.org/10.1109/sar.2023")
        m_resp = MagicMock()
        m_resp.status_code = 200
        m_resp.json.return_value = {
            "best_oa_location": {"pdf_url": "https://oa.org/sar.pdf"},
            "abstract_inverted_index": {"SAR": [0], "abstract": [1]},
            "cited_by_count": 33,
        }
        mock_get.return_value = m_resp
        resolve_paper_metadata(p1, config=cfg)
        self.assertEqual(p1.doi, "10.1109/sar.2023")
        self.assertEqual(p1.pdf_url, "https://oa.org/sar.pdf")
        self.assertEqual(p1.citations, 33)

        # Case 2: No DOI -> resolves via OpenAlex title search
        p2 = Paper(title="Unique SAR Title For OpenAlex Search")
        m_resp2 = MagicMock()
        m_resp2.status_code = 200
        m_resp2.json.return_value = {
            "results": [
                {
                    "title": "Unique SAR Title For OpenAlex Search",
                    "doi": "https://doi.org/10.1000/found_oa",
                    "best_oa_location": {"pdf_url": "https://oa.org/found.pdf"},
                    "abstract_inverted_index": {"Found": [0]},
                    "cited_by_count": 10,
                }
            ]
        }
        mock_get.return_value = m_resp2
        resolve_paper_metadata(p2, config=cfg)
        self.assertEqual(p2.doi, "10.1000/found_oa")

        # Case 3: OpenAlex returns nothing -> resolves via Crossref title search
        p3 = Paper(title="Unique Title For Crossref Resolution")
        m_empty = MagicMock(status_code=200)
        m_empty.json.return_value = {"results": []}
        m_cr = MagicMock(status_code=200)
        m_cr.json.return_value = {
            "message": {
                "items": [
                    {
                        "title": ["Unique Title For Crossref Resolution"],
                        "DOI": "10.1000/found_cr",
                        "link": [{"content-type": "application/pdf", "URL": "https://cr.org/found.pdf"}],
                    }
                ]
            }
        }
        mock_get.side_effect = [m_empty, m_cr]
        resolve_paper_metadata(p3, config=cfg)
        self.assertEqual(p3.doi, "10.1000/found_cr")
        self.assertEqual(p3.pdf_url, "https://cr.org/found.pdf")

    def test_extract_pdf_url_from_html(self) -> None:
        base = "https://mirror.example.org/paper"
        self.assertEqual(
            _extract_pdf_url_from_html('<html><embed id="pdf" src="/dl/file1.pdf#page=1"/></html>', base),
            "https://mirror.example.org/dl/file1.pdf",
        )
        self.assertEqual(
            _extract_pdf_url_from_html("<html><button onclick=\"location.href='/dl/file2.pdf'\">Save</button></html>", base),
            "https://mirror.example.org/dl/file2.pdf",
        )
        self.assertEqual(
            _extract_pdf_url_from_html('<html><meta name="citation_pdf_url" content="/dl/file3.pdf"/></html>', base),
            "https://mirror.example.org/dl/file3.pdf",
        )
        self.assertEqual(
            _extract_pdf_url_from_html('<html><a href="/dl/file4.pdf">PDF</a></html>', base),
            "https://mirror.example.org/dl/file4.pdf",
        )
        self.assertEqual(_extract_pdf_url_from_html("<html><body>No PDF here</body></html>", base), "")

    @patch("crawly_core.downloader.requests.get")
    def test_fetch_and_verify_pdf_and_candidates(self, mock_get: MagicMock) -> None:
        cfg = AppConfig()
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "test.pdf"
            self.assertFalse(_fetch_and_verify_pdf("", tpath, config=cfg))

            # Non-200
            mock_get.return_value = MagicMock(status_code=404)
            self.assertFalse(_fetch_and_verify_pdf("https://example.org/404.pdf", tpath, config=cfg))

            # Direct valid PDF stream
            pdf_bytes = b"%PDF-1.5\n" + (b"0" * 2048)
            r_pdf = MagicMock(status_code=200)
            r_pdf.iter_content.return_value = [b"", pdf_bytes]
            mock_get.return_value = r_pdf
            self.assertTrue(_fetch_and_verify_pdf("https://example.org/direct.pdf", tpath, config=cfg))
            self.assertTrue(tpath.exists())

            # HTML landing page with nested PDF link + large non-PDF stream break test
            r_html = MagicMock(status_code=200, url="https://example.org/landing", headers={"Content-Type": "text/html"})
            html_bytes = b'<!DOCTYPE html><html><embed id="pdf" src="https://example.org/nested.pdf"/></html>' + (b" " * 270000)
            r_html.iter_content.return_value = [html_bytes[:150000], html_bytes[150000:]]
            r_nested = MagicMock(status_code=200, content=pdf_bytes)
            mock_get.side_effect = [r_html, r_nested]
            tpath2 = Path(tmp) / "nested.pdf"
            self.assertTrue(_fetch_and_verify_pdf("https://example.org/landing", tpath2, config=cfg))
            mock_get.side_effect = None

            # Non-PDF, non-HTML 200 response -> returns False at line 218
            r_plain = MagicMock(status_code=200, headers={"Content-Type": "text/plain"})
            r_plain.iter_content.return_value = [b"plain text without pdf header"]
            mock_get.return_value = r_plain
            self.assertFalse(_fetch_and_verify_pdf("https://example.org/plain.txt", tpath, config=cfg))

            # Candidate generators
            p_pub = Paper(title="P", url="https://arxiv.org/abs/2301.00001", pdf_url="https://direct.org/1.pdf")
            cands_pub = _candidate_publisher_oa_urls(p_pub)
            self.assertEqual(len(cands_pub), 2)
            p_mdpi = Paper(title="M", url="https://www.mdpi.com/2072-4292/15/1/1")
            self.assertEqual(len(_candidate_publisher_oa_urls(p_mdpi)), 1)

            # Unpaywall
            self.assertEqual(_candidate_unpaywall_urls("", "a@b.com", config=cfg), [])
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {
                    "best_oa_location": {"url_for_pdf": "https://upw.org/1.pdf"},
                    "oa_locations": [{"url_for_pdf": "https://upw.org/2.pdf"}],
                },
            )
            self.assertEqual(len(_candidate_unpaywall_urls("10.1000/1", "a@b.com", config=cfg)), 2)

            # Semantic Scholar OA candidate
            p_s2 = Paper(title="S2", doi="10.1000/1")
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"openAccessPdf": {"url": "https://s2.org/1.pdf"}, "externalIds": {"ArXiv": "2301.1"}},
            )
            self.assertEqual(len(_candidate_semantic_scholar_urls(p_s2, api_key="k", config=cfg)), 2)

            # Europe PMC candidate
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"resultList": {"result": [{"pmcid": "PMC999"}]}},
            )
            self.assertEqual(len(_candidate_europe_pmc_urls(p_s2, config=cfg)), 1)

    @patch("crawly_core.downloader._fetch_and_verify_pdf")
    @patch("crawly_core.downloader.resolve_paper_metadata")
    def test_scihub_and_batch_download(self, mock_resolve: MagicMock, mock_fetch: MagicMock) -> None:
        cfg = AppConfig(use_scihub_fallback=True, scihub_mirrors=["", "sci-hub.se"])
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp)
            p = Paper(title="Test Paper", doi="10.1000/test", url="https://example.org/p")
            tpath = out_dir / p.safe_filename()

            # 1. Sci-Hub CDN success
            mock_fetch.return_value = True
            self.assertIn("Sci-Hub CDN", _try_scihub_download(p, tpath, mirrors=cfg.scihub_mirrors, config=cfg) or "")

            # 2. Sci-Hub mirror success (CDN fails, mirror succeeds)
            mock_fetch.side_effect = [False, True]
            self.assertIn("Sci-Hub (sci-hub.se)", _try_scihub_download(p, tpath, mirrors=cfg.scihub_mirrors, config=cfg) or "")

            # 3. Sci-Hub all fail
            mock_fetch.side_effect = None
            mock_fetch.return_value = False
            self.assertIsNone(_try_scihub_download(p, tpath, mirrors=cfg.scihub_mirrors, config=cfg))

            # 4. download_paper_pdf from Local Cache
            tpath.write_bytes(b"%PDF-1.5\n" + (b"x" * 2000))
            ok, src, path_out = download_paper_pdf(p, out_dir, config=cfg)
            self.assertTrue(ok)
            self.assertEqual(src, "Local Cache")
            tpath.unlink()

            # 5. download_paper_pdf via Legal OA candidate
            p_oa = Paper(title="OA Paper", pdf_url="https://oa.org/paper.pdf")
            mock_fetch.return_value = True
            ok2, src2, _ = download_paper_pdf(p_oa, out_dir, config=cfg)
            self.assertTrue(ok2)
            self.assertEqual(src2, "Direct/OA Link")

            # 6. download_paper_pdf via Sci-Hub fallback with custom_scihub_url + duplicate candidate URL + Not Found
            p_sh = Paper(title="SH Paper", doi="10.1000/sh", pdf_url="https://dup.org/1.pdf")
            with (
                patch("crawly_core.downloader._candidate_unpaywall_urls", return_value=[("Dup", "https://dup.org/1.pdf")]),
                patch("crawly_core.downloader._candidate_semantic_scholar_urls", return_value=[]),
                patch("crawly_core.downloader._candidate_europe_pmc_urls", return_value=[]),
                patch("crawly_core.downloader._try_scihub_download", side_effect=["Sci-Hub (custom.sh)", None]),
            ):
                mock_fetch.return_value = False
                ok3, src3, _ = download_paper_pdf(p_sh, out_dir, config=cfg, custom_scihub_url="https://custom.sh")
                self.assertTrue(ok3)
                self.assertEqual(src3, "Sci-Hub (custom.sh)")

                # When Sci-Hub also returns None -> hits line 424 ("Not Found")
                ok4, src4, _ = download_paper_pdf(Paper(title="None Found", doi="10.1000/nf"), out_dir, config=cfg)
                self.assertFalse(ok4)
                self.assertEqual(src4, "Not Found")

            # 7. download_batch_pdfs (1 success, 1 missing)
            p_miss = Paper(title="Missing Paper", doi="10.1000/miss")
            csv_file = out_dir / "batch.csv"
            with patch(
                "crawly_core.downloader.download_paper_pdf",
                side_effect=[(True, "Unpaywall OA", tpath), (False, "Not Found", None)],
            ):
                cb_calls = []
                stats = download_batch_pdfs(
                    [p_oa, p_miss],
                    output_dir=out_dir,
                    csv_path=csv_file,
                    config=cfg,
                    progress_callback=lambda i, t, pp, ok_flag, s: cb_calls.append((i, ok_flag, s)),
                )
                self.assertEqual(stats["total"], 2)
                self.assertEqual(stats["downloaded"], 1)
                self.assertEqual(stats["missing"], 1)
                self.assertEqual(len(cb_calls), 2)
                self.assertTrue((out_dir / "papers_not_found.csv").exists())
                self.assertTrue(csv_file.exists())

            # Test sync_dataset_to_zotero
            from crawly_core.downloader import sync_dataset_to_zotero

            local_pdf = out_dir / p_oa.safe_filename()
            local_pdf.write_bytes(b"%PDF-1.5 test")
            p_oa.local_pdf = str(local_pdf)

            # 1. Zotero connector online (200)
            mock_zot_resp = MagicMock()
            mock_zot_resp.status_code = 200
            with patch("crawly_core.downloader.requests.get", return_value=mock_zot_resp):
                is_live, msg, bib_p = sync_dataset_to_zotero([p_oa], collection_name="Test Collection", output_dir=out_dir)
                self.assertTrue(is_live)
                self.assertIn("ONLINE", msg)
                self.assertTrue(bib_p.exists())
                content = bib_p.read_text(encoding="utf-8")
                self.assertIn("file =", content)
                self.assertIn("application/pdf", content)

            # 2. Zotero non-200 status code
            mock_zot_err = MagicMock()
            mock_zot_err.status_code = 502
            with patch("crawly_core.downloader.requests.get", return_value=mock_zot_err):
                is_live2, msg2, _ = sync_dataset_to_zotero([p_oa], collection_name="Err Col", output_dir=out_dir)
                self.assertFalse(is_live2)
                self.assertIn("502", msg2)

            # 3. Zotero connector offline (exception)
            with patch("crawly_core.downloader.requests.get", side_effect=OSError("Connection refused")):
                is_live3, msg3, bib_p3 = sync_dataset_to_zotero([p_oa], collection_name="", output_dir=out_dir)
                self.assertFalse(is_live3)
                self.assertIn("not running locally", msg3)
                self.assertTrue(bib_p3.exists())

