"""Tests for crawly_core.sources (100% coverage)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from crawly_core.models import AppConfig, Paper
from crawly_core.sources import (
    deduplicate_and_merge_papers,
    get_browser_headers,
    get_polite_headers,
    normalize_doi,
    reconstruct_openalex_abstract,
    search_arxiv,
    search_crossref,
    search_doaj,
    search_europe_pmc,
    search_google_scholar,
    search_hal,
    search_multi_source,
    search_openaire,
    search_openalex,
    search_semantic_scholar,
    strip_jats_xml,
)


def _mock_resp(status: int = 200, json_data: dict | None = None, text: str = "") -> MagicMock:
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_data or {}
    m.text = text
    return m


class TestSources(unittest.TestCase):
    def test_helpers(self) -> None:
        cfg = AppConfig()
        self.assertIn("User-Agent", get_polite_headers(cfg))
        self.assertIn("User-Agent", get_browser_headers(cfg))
        self.assertEqual(normalize_doi(None), "")
        self.assertEqual(normalize_doi("https://doi.org/10.1109/ABC.123"), "10.1109/abc.123")
        self.assertEqual(reconstruct_openalex_abstract(None), "")
        self.assertEqual(reconstruct_openalex_abstract({"empty": []}), "")
        self.assertEqual(reconstruct_openalex_abstract({"hello": [0], "world": [1]}), "hello world")
        self.assertEqual(strip_jats_xml(""), "")
        self.assertEqual(strip_jats_xml("<jats:p>Deep   <b>SAR</b></jats:p>"), "Deep SAR")

    @patch("crawly_core.sources.requests.get")
    def test_all_individual_search_connectors(self, mock_get: MagicMock) -> None:
        cfg = AppConfig(semantic_scholar_api_key="s2-key")

        # 1. OpenAlex (non-200 + 200)
        mock_get.return_value = _mock_resp(500)
        self.assertEqual(search_openalex("radar", config=cfg), [])
        mock_get.return_value = _mock_resp(
            200,
            {
                "results": [
                    {"title": ""},
                    {
                        "title": "OpenAlex Paper",
                        "publication_year": 2023,
                        "authorships": [{"author": {"display_name": "A. Author"}}],
                        "primary_location": {"source": {"display_name": "IEEE"}, "landing_page_url": "https://oa.org/1"},
                        "doi": "https://doi.org/10.1000/oa1",
                        "best_oa_location": {"pdf_url": "https://oa.org/1.pdf"},
                        "abstract_inverted_index": {"Radar": [0], "imaging": [1]},
                        "cited_by_count": 15,
                    },
                ]
            },
        )
        oa_res = search_openalex("radar", config=cfg)
        self.assertEqual(len(oa_res), 1)
        self.assertEqual(oa_res[0].doi, "10.1000/oa1")

        # 2. Semantic Scholar (non-200 + 200 with ArXiv fallback)
        mock_get.return_value = _mock_resp(429)
        self.assertEqual(search_semantic_scholar("radar", config=cfg), [])
        mock_get.return_value = _mock_resp(
            200,
            {
                "data": [
                    {"title": ""},
                    {
                        "title": "S2 Paper",
                        "year": 2022,
                        "authors": [{"name": "B. Researcher"}],
                        "venue": "NeurIPS",
                        "externalIds": {"DOI": "10.1000/s2", "ArXiv": "2301.00001"},
                        "openAccessPdf": None,
                        "abstract": "S2 abstract",
                        "citationCount": 9,
                    },
                ]
            },
        )
        s2_res = search_semantic_scholar("radar", config=cfg)
        self.assertEqual(len(s2_res), 1)
        self.assertIn("arxiv.org/pdf/2301.00001.pdf", s2_res[0].pdf_url)

        # 3. arXiv (non-200 + 200 XML)
        mock_get.return_value = _mock_resp(500)
        self.assertEqual(search_arxiv("radar", config=cfg), [])
        arxiv_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
          <entry><title>   </title></entry>
          <entry>
            <id>http://arxiv.org/abs/2401.12345v1</id>
            <published>2024-01-15T00:00:00Z</published>
            <title>arXiv SAR Paper</title>
            <summary>arXiv summary text</summary>
            <author><name>C. Scientist</name></author>
            <link title="pdf" href="http://arxiv.org/pdf/2401.12345v1" type="application/pdf"/>
            <arxiv:doi>10.48550/arXiv.2401.12345</arxiv:doi>
          </entry>
          <entry>
            <id>http://arxiv.org/abs/2401.99999v1</id>
            <published>2024-01-15T00:00:00Z</published>
            <title>arXiv No Link Paper</title>
            <summary>Summary 2</summary>
          </entry>
        </feed>"""
        mock_get.return_value = _mock_resp(200, text=arxiv_xml)
        ax_res = search_arxiv("radar", config=cfg)
        self.assertEqual(len(ax_res), 2)
        self.assertTrue(ax_res[0].pdf_url.endswith(".pdf"))
        self.assertTrue(ax_res[1].pdf_url.endswith(".pdf"))

        # 4. Europe PMC (non-200 + 200)
        mock_get.return_value = _mock_resp(500)
        self.assertEqual(search_europe_pmc("radar", config=cfg), [])
        mock_get.return_value = _mock_resp(
            200,
            {
                "resultList": {
                    "result": [
                        {"title": ""},
                        {
                            "title": "Europe PMC Paper.",
                            "pubYear": "2021",
                            "authorString": "D. Medic",
                            "journalTitle": "BioMed",
                            "doi": "10.1000/epmc1",
                            "pmcid": "PMC12345",
                            "pmid": "9999",
                            "isOpenAccess": "Y",
                            "abstractText": "<p>Bio abstract</p>",
                            "citedByCount": 5,
                            "fullTextUrlList": {
                                "fullTextUrl": [
                                    {"documentStyle": "pdf", "url": "https://epmc.org/1.pdf"},
                                    {"documentStyle": "html", "url": "https://epmc.org/1"},
                                ]
                            },
                        },
                        {
                            "title": "Europe PMC Paper 2",
                            "pubYear": "2020",
                            "pmid": "8888",
                            "fullTextUrlList": {"fullTextUrl": [{"documentStyle": "pdf", "url": "https://epmc.org/2.pdf"}]},
                        },
                    ]
                }
            },
        )
        ep_res = search_europe_pmc("radar", config=cfg)
        self.assertEqual(len(ep_res), 2)

        # 5. Crossref (non-200 + 200)
        mock_get.return_value = _mock_resp(500)
        self.assertEqual(search_crossref("radar", config=cfg), [])
        mock_get.return_value = _mock_resp(
            200,
            {
                "message": {
                    "items": [
                        {"title": []},
                        {
                            "title": ["Crossref Paper"],
                            "DOI": "10.1000/cr1",
                            "published-print": {"date-parts": [[2019, 5]]},
                            "author": [{"given": "E.", "family": "Author"}],
                            "container-title": ["Nature"],
                            "link": [{"content-type": "application/pdf", "URL": "https://cr.org/1.pdf"}],
                            "abstract": "<jats:p>CR abstract</jats:p>",
                            "is-referenced-by-count": 12,
                            "URL": "https://doi.org/10.1000/cr1",
                        },
                    ]
                }
            },
        )
        cr_res = search_crossref("radar", config=cfg)
        self.assertEqual(len(cr_res), 1)
        self.assertEqual(cr_res[0].year, 2019)

        # 6. DOAJ (non-200 + 200)
        mock_get.return_value = _mock_resp(500)
        self.assertEqual(search_doaj("radar", config=cfg), [])
        mock_get.return_value = _mock_resp(
            200,
            {
                "results": [
                    {"bibjson": {"title": ""}},
                    {
                        "bibjson": {
                            "title": "DOAJ Paper",
                            "year": "2023",
                            "author": [{"name": "F. Open"}],
                            "journal": {"title": "Remote Sensing"},
                            "identifier": [{"type": "doi", "id": "10.3390/rs1"}],
                            "link": [
                                {"url": "https://mdpi.com/1.pdf", "content_type": "application/pdf"},
                                {"url": "https://mdpi.com/1", "content_type": "text/html"},
                            ],
                            "abstract": "DOAJ abstract",
                        }
                    },
                    {
                        "bibjson": {
                            "title": "DOAJ No Landing",
                            "year": "2022",
                            "link": [{"url": "https://mdpi.com/2.pdf", "content_type": "application/pdf"}],
                        }
                    },
                ]
            },
        )
        doaj_res = search_doaj("radar", config=cfg)
        self.assertEqual(len(doaj_res), 2)

        # 7. HAL (non-200 + 200)
        mock_get.return_value = _mock_resp(500)
        self.assertEqual(search_hal("radar", config=cfg), [])
        mock_get.return_value = _mock_resp(
            200,
            {
                "response": {
                    "docs": [
                        {"title_s": []},
                        {
                            "title_s": ["HAL Paper"],
                            "producedDateY_i": 2021,
                            "authFullName_s": ["G. Savant"],
                            "journalTitle_s": "HAL Journal",
                            "doiId_s": "10.1000/hal1",
                            "fileMain_s": "https://hal.science/1.pdf",
                            "uri_s": "https://hal.science/1",
                            "abstract_s": ["HAL abstract"],
                        },
                    ]
                }
            },
        )
        hal_res = search_hal("radar", config=cfg)
        self.assertEqual(len(hal_res), 1)

        # 8. OpenAIRE (non-200 + 200 dict/list variants)
        mock_get.return_value = _mock_resp(500)
        self.assertEqual(search_openaire("radar", config=cfg), [])
        mock_get.return_value = _mock_resp(
            200,
            {
                "response": {
                    "results": {
                        "result": [
                            {"metadata": {}},
                            {"metadata": {"oaf:entity": {"oaf:result": {"title": ""}}}},
                            {
                                "metadata": {
                                    "oaf:entity": {
                                        "oaf:result": {
                                            "title": [{"$": "OpenAIRE Paper 1"}],
                                            "dateofacceptance": {"$": "2020-01-01"},
                                            "creator": {"$" : "H. Euro"},
                                            "description": [{"$": "OAire desc"}],
                                            "pid": {"@classid": "doi", "$": "10.1000/oaire1"},
                                            "children": {
                                                "instance": {
                                                    "accessright": {"@classid": "OPEN"},
                                                    "webresource": {"url": {"$": "https://oaire.eu/1.pdf"}},
                                                }
                                            },
                                        }
                                    }
                                }
                            },
                            {
                                "metadata": {
                                    "oaf:entity": {
                                        "oaf:result": {
                                            "title": {"$": "OpenAIRE Paper 2"},
                                            "description": {"$": "Desc 2"},
                                            "children": {"instance": ["invalid", {"webresource": {"url": {"$": ""}}}]},
                                        }
                                    }
                                }
                            },
                        ]
                    }
                }
            },
        )
        oaire_res = search_openaire("radar", config=cfg)
        self.assertEqual(len(oaire_res), 2)

        # Single dict result in OpenAIRE
        mock_get.return_value = _mock_resp(
            200,
            {
                "response": {
                    "results": {
                        "result": {
                            "metadata": {
                                "oaf:entity": {
                                    "oaf:result": {
                                        "title": "Plain String Title",
                                    }
                                }
                            }
                        }
                    }
                }
            },
        )
        self.assertEqual(len(search_openaire("radar", config=cfg)), 1)

        # 9. Google Scholar (non-200 + 200 HTML)
        mock_get.return_value = _mock_resp(403)
        self.assertEqual(search_google_scholar("radar", config=cfg), [])
        scholar_html = """
        <html><body>
          <div class="gs_r gs_or gs_scl"></div>
          <div class="gs_r gs_or gs_scl">
            <div class="gs_or_ggsm"><a href="https://scholar.example/1.pdf">[PDF]</a></div>
            <h3 class="gs_rt"><a href="https://scholar.example/1">[PDF] Scholar Paper 1</a></h3>
            <div class="gs_a">I. Author - Journal of Radar, 2018 - Publisher</div>
            <div class="gs_rs">Scholar snippet text</div>
            <div class="gs_fl"><a href="#">Cited by 77</a></div>
          </div>
          <div class="gs_r gs_or gs_scl">
            <h3 class="gs_rt">Scholar Paper 2</h3>
            <div class="gs_a">J. Author - 2019</div>
          </div>
        </body></html>
        """
        mock_get.return_value = _mock_resp(200, text=scholar_html)
        with patch("crawly_core.sources.time.sleep") as mock_sleep:
            gs_res = search_google_scholar("radar", page_start=1, page_end=2, delay_seconds=0.01, config=cfg)
            mock_sleep.assert_called_once()
        self.assertEqual(len(gs_res), 4)
        self.assertEqual(gs_res[0].citations, 77)

    def test_deduplicate_and_multi_source(self) -> None:
        p_empty = Paper(title="   ")
        p_with_doi_first = Paper(title="First With DOI", doi="10.1000/first")
        p1 = Paper(title="Deep SAR Imaging", doi="", year=0, authors="Unknown", publication="OpenAlex", url="NA", source="OpenAlex")
        p2 = Paper(
            title="Deep SAR Imaging!",
            doi="10.1000/sar",
            year=2023,
            authors="Alice",
            publication="IEEE TGRS",
            url="https://ieee.org/1",
            pdf_url="https://ieee.org/1.pdf",
            abstract="Longer abstract text",
            citations=25,
            source="Crossref",
        )
        p3 = Paper(title="Different Title Same DOI", doi="10.1000/sar", source="arXiv")
        merged = deduplicate_and_merge_papers([p_empty, p_with_doi_first, p1, p2, p3])
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[1].doi, "10.1000/sar")
        self.assertEqual(merged[1].year, 2023)
        self.assertEqual(merged[1].citations, 25)
        self.assertIn("Crossref", merged[1].source)

        # Test search_multi_source across all sources + unknown source + sort modes
        with (
            patch("crawly_core.sources.search_openalex", return_value=[Paper(title="P1", year=2022, citations=5)]),
            patch("crawly_core.sources.search_semantic_scholar", return_value=[Paper(title="P2", year=2020, citations=20)]),
            patch("crawly_core.sources.search_arxiv", return_value=[]),
            patch("crawly_core.sources.search_europe_pmc", return_value=[]),
            patch("crawly_core.sources.search_crossref", return_value=[]),
            patch("crawly_core.sources.search_doaj", return_value=[]),
            patch("crawly_core.sources.search_hal", return_value=[]),
            patch("crawly_core.sources.search_openaire", return_value=[]),
            patch("crawly_core.sources.search_google_scholar", return_value=[]),
        ):
            callbacks = []
            all_srcs = [
                "openalex",
                "semantic_scholar",
                "arxiv",
                "europe_pmc",
                "crossref",
                "doaj",
                "hal",
                "openaire",
                "google_scholar",
                "unknown_db",
            ]
            res_asc = search_multi_source(
                "radar",
                sources=all_srcs,
                sort_by="asc",
                progress_callback=lambda lbl, cnt: callbacks.append((lbl, cnt)),
            )
            self.assertEqual([p.year for p in res_asc], [2020, 2022])
            self.assertEqual(len(callbacks), len(all_srcs))

            res_desc = search_multi_source("radar", sources=["openalex", "semantic_scholar"], sort_by="desc")
            self.assertEqual([p.year for p in res_desc], [2022, 2020])

            res_cit = search_multi_source("radar", sources=["openalex", "semantic_scholar"], sort_by="citations")
            self.assertEqual([p.citations for p in res_cit], [20, 5])
