"""Multi-source academic paper search & discovery engine for Crawly.

Uses requests & BeautifulSoup4 with settings loaded from `config.json` to query:
1. OpenAlex (250M+ scholarly works, abstracts, citations, OA PDFs)
2. Semantic Scholar (Academic Graph, abstracts, citations, openAccessPdf)
3. arXiv (Preprints in Physics, CS, Math, Stat, Q-Bio, Q-Fin with direct PDFs)
4. Europe PMC / PubMed Central (Biomedical & life sciences with OA PDFs)
5. Crossref (Authoritative DOI registry & publisher metadata)
6. DOAJ (Directory of Open Access Journals)
7. HAL Open Archive (Global open-access repository with direct PDFs)
8. OpenAIRE (European Open Science Cloud scholarly aggregator)
9. Google Scholar (Optional risk-gated web scraper)
"""

from __future__ import annotations

import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import requests
from bs4 import BeautifulSoup

from .models import DEFAULT_API_ENDPOINTS, DEFAULT_OPEN_SOURCES, AppConfig, Paper

ALL_OPEN_SOURCES = list(DEFAULT_OPEN_SOURCES)

SOURCE_LABELS = {
    "openalex": "OpenAlex",
    "semantic_scholar": "Semantic Scholar",
    "arxiv": "arXiv",
    "europe_pmc": "Europe PMC / PubMed",
    "crossref": "Crossref",
    "doaj": "DOAJ (Open Access Journals)",
    "hal": "HAL Open Archive",
    "openaire": "OpenAIRE Graph",
    "google_scholar": "Google Scholar",
}


def get_polite_headers(config: Optional[AppConfig] = None) -> Dict[str, str]:
    cfg = config or AppConfig.load()
    return {"User-Agent": cfg.polite_user_agent}


def get_browser_headers(config: Optional[AppConfig] = None) -> Dict[str, str]:
    cfg = config or AppConfig.load()
    return {"User-Agent": cfg.browser_user_agent}


def normalize_doi(doi: Optional[str]) -> str:
    if not doi:
        return ""
    s = str(doi).strip()
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^doi:\s*", "", s, flags=re.IGNORECASE)
    return s.strip().lower()


def reconstruct_openalex_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
    if not inverted_index or not isinstance(inverted_index, dict):
        return ""
    pos_map: Dict[int, str] = {}
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for p in positions:
                if isinstance(p, int):
                    pos_map[p] = word
    if not pos_map:
        return ""
    words = [pos_map[idx] for idx in sorted(pos_map.keys())]
    return " ".join(words).strip()


def strip_jats_xml(text: str) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", str(text))
    return re.sub(r"\s+", " ", cleaned).strip()


def _parse_openalex_item(item: dict) -> Paper:
    title = (item.get("title") or item.get("display_name") or "").strip()
    year = item.get("publication_year") or 0
    authorships = item.get("authorships") or []
    author_names = [
        (a.get("author") or {}).get("display_name", "")
        for a in authorships[:5]
        if isinstance(a, dict) and (a.get("author") or {}).get("display_name")
    ]
    authors = ", ".join(author_names) if author_names else "Unknown"
    primary_loc = item.get("primary_location") or {}
    source_info = primary_loc.get("source") or {}
    publication = source_info.get("display_name") or "OpenAlex"
    doi = normalize_doi(item.get("doi"))
    oa_info = item.get("open_access") or {}
    best_oa = item.get("best_oa_location") or {}
    pdf_url = (
        best_oa.get("pdf_url")
        or primary_loc.get("pdf_url")
        or oa_info.get("oa_url")
        or ""
    )
    landing_url = (
        primary_loc.get("landing_page_url")
        or (f"https://doi.org/{doi}" if doi else "")
        or item.get("id")
        or "NA"
    )
    abstract = reconstruct_openalex_abstract(item.get("abstract_inverted_index"))
    citations = item.get("cited_by_count") or 0
    return Paper(
        title=title,
        year=int(year) if year else 0,
        authors=authors,
        publication=publication,
        url=landing_url,
        doi=doi,
        pdf_url=pdf_url or "",
        abstract=abstract,
        citations=int(citations) if citations else 0,
        source="OpenAlex",
    )


def search_openalex(
    query: str,
    limit: int = 20,
    timeout: int = 12,
    config: Optional[AppConfig] = None,
) -> List[Paper]:
    cfg = config or AppConfig.load()
    papers: List[Paper] = []
    per_page = min(max(limit, 1), 100)
    endpoint = cfg.api_endpoints.get("openalex_works", DEFAULT_API_ENDPOINTS["openalex_works"])
    try:
        resp = requests.get(
            endpoint,
            params={"search": query, "per-page": per_page},
            headers=get_polite_headers(cfg),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return papers
        data = resp.json()
        for item in data.get("results", [])[:limit]:
            p = _parse_openalex_item(item)
            if p.title:
                papers.append(p)
    except Exception:
        pass
    return papers


def search_semantic_scholar(
    query: str,
    limit: int = 20,
    timeout: int = 12,
    api_key: str = "",
    config: Optional[AppConfig] = None,
) -> List[Paper]:
    cfg = config or AppConfig.load()
    papers: List[Paper] = []
    headers = get_polite_headers(cfg)
    key = api_key or cfg.semantic_scholar_api_key
    if key:
        headers["x-api-key"] = key
    endpoint = cfg.api_endpoints.get("semantic_scholar_search", DEFAULT_API_ENDPOINTS["semantic_scholar_search"])
    try:
        resp = requests.get(
            endpoint,
            params={
                "query": query,
                "limit": min(max(limit, 1), 100),
                "fields": "title,year,authors,venue,url,abstract,citationCount,externalIds,openAccessPdf",
            },
            headers=headers,
            timeout=timeout,
        )
        if resp.status_code != 200:
            return papers
        data = resp.json()
        for item in data.get("data", [])[:limit]:
            title = (item.get("title") or "").strip()
            if not title:
                continue
            year = item.get("year") or 0
            author_list = [a.get("name", "") for a in (item.get("authors") or [])[:5] if a.get("name")]
            authors = ", ".join(author_list) if author_list else "Unknown"
            venue = item.get("venue") or "Semantic Scholar"
            ext = item.get("externalIds") or {}
            doi = normalize_doi(ext.get("DOI"))
            arxiv_id = ext.get("ArXiv")
            oa_pdf = (item.get("openAccessPdf") or {}).get("url") or ""
            if not oa_pdf and arxiv_id:
                oa_pdf = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            paper_url = (f"https://doi.org/{doi}" if doi else "") or item.get("url") or "NA"
            papers.append(
                Paper(
                    title=title,
                    year=int(year) if year else 0,
                    authors=authors,
                    publication=venue,
                    url=paper_url,
                    doi=doi,
                    pdf_url=oa_pdf,
                    abstract=(item.get("abstract") or "").strip(),
                    citations=int(item.get("citationCount") or 0),
                    source="Semantic Scholar",
                )
            )
    except Exception:
        pass
    return papers


def search_arxiv(
    query: str,
    limit: int = 20,
    timeout: int = 12,
    config: Optional[AppConfig] = None,
) -> List[Paper]:
    cfg = config or AppConfig.load()
    papers: List[Paper] = []
    endpoint = cfg.api_endpoints.get("arxiv_query", DEFAULT_API_ENDPOINTS["arxiv_query"])
    try:
        resp = requests.get(
            endpoint,
            params={"search_query": f"all:{query}", "start": 0, "max_results": min(max(limit, 1), 100)},
            headers=get_polite_headers(cfg),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return papers
        root = ET.fromstring(resp.text)
        ns = {
            "atom": "http://www.w3.org/2005/Atom",
            "arxiv": "http://arxiv.org/schemas/atom",
        }
        for entry in root.findall("atom:entry", ns)[:limit]:
            title_el = entry.find("atom:title", ns)
            title = re.sub(r"\s+", " ", (title_el.text or "")).strip() if title_el is not None else ""
            if not title:
                continue
            summary_el = entry.find("atom:summary", ns)
            abstract = re.sub(r"\s+", " ", (summary_el.text or "")).strip() if summary_el is not None else ""
            pub_el = entry.find("atom:published", ns)
            year = int(pub_el.text[:4]) if (pub_el is not None and pub_el.text and len(pub_el.text) >= 4) else 0
            author_els = entry.findall("atom:author/atom:name", ns)
            authors = ", ".join([a.text.strip() for a in author_els[:5] if a.text]) or "Unknown"
            id_el = entry.find("atom:id", ns)
            abs_url = (id_el.text or "").strip() if id_el is not None else ""
            pdf_url = ""
            for link in entry.findall("atom:link", ns):
                if link.attrib.get("title") == "pdf" or link.attrib.get("type") == "application/pdf":
                    pdf_url = link.attrib.get("href", "")
                    if pdf_url and not pdf_url.endswith(".pdf"):
                        pdf_url += ".pdf"
            if not pdf_url and "/abs/" in abs_url:
                pdf_url = abs_url.replace("/abs/", "/pdf/") + ".pdf"
            doi_el = entry.find("arxiv:doi", ns)
            doi = normalize_doi(doi_el.text if doi_el is not None else "")
            papers.append(
                Paper(
                    title=title,
                    year=year,
                    authors=authors,
                    publication="arXiv",
                    url=abs_url or pdf_url or "NA",
                    doi=doi,
                    pdf_url=pdf_url,
                    abstract=abstract,
                    citations=0,
                    source="arXiv",
                )
            )
    except Exception:
        pass
    return papers


def search_europe_pmc(
    query: str,
    limit: int = 20,
    timeout: int = 12,
    config: Optional[AppConfig] = None,
) -> List[Paper]:
    cfg = config or AppConfig.load()
    papers: List[Paper] = []
    endpoint = cfg.api_endpoints.get("europe_pmc_search", DEFAULT_API_ENDPOINTS["europe_pmc_search"])
    pdf_render_base = cfg.api_endpoints.get("europe_pmc_pdf", DEFAULT_API_ENDPOINTS["europe_pmc_pdf"])
    try:
        resp = requests.get(
            endpoint,
            params={"query": query, "format": "json", "pageSize": min(max(limit, 1), 100), "resultType": "core"},
            headers=get_polite_headers(cfg),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return papers
        data = resp.json()
        results = (data.get("resultList") or {}).get("result") or []
        for item in results[:limit]:
            title = (item.get("title") or "").strip().rstrip(".")
            if not title:
                continue
            year = int(item.get("pubYear")) if str(item.get("pubYear", "")).isdigit() else 0
            authors = item.get("authorString") or "Unknown"
            journal = (item.get("journalInfo") or {}).get("journal", {}).get("title") or item.get("journalTitle") or "Europe PMC"
            doi = normalize_doi(item.get("doi"))
            pmcid = item.get("pmcid") or ""
            pmid = item.get("pmid") or ""
            abstract = strip_jats_xml(item.get("abstractText") or "")
            citations = int(item.get("citedByCount") or 0)
            pdf_url = ""
            if pmcid and (item.get("isOpenAccess") == "Y" or item.get("hasPDF") == "Y"):
                pdf_url = f"{pdf_render_base}?accid={pmcid}&blobtype=pdf"
            full_urls = (item.get("fullTextUrlList") or {}).get("fullTextUrl") or []
            landing_url = ""
            for u in full_urls:
                if u.get("documentStyle") == "pdf" and not pdf_url:
                    pdf_url = u.get("url") or ""
                elif not landing_url and u.get("url"):
                    landing_url = u.get("url")
            if not landing_url:
                landing_url = f"https://doi.org/{doi}" if doi else (f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "NA")
            papers.append(
                Paper(
                    title=title,
                    year=year,
                    authors=authors,
                    publication=journal,
                    url=landing_url,
                    doi=doi,
                    pdf_url=pdf_url,
                    abstract=abstract,
                    citations=citations,
                    source="Europe PMC",
                )
            )
    except Exception:
        pass
    return papers


def search_crossref(
    query: str,
    limit: int = 20,
    timeout: int = 12,
    config: Optional[AppConfig] = None,
) -> List[Paper]:
    cfg = config or AppConfig.load()
    papers: List[Paper] = []
    endpoint = cfg.api_endpoints.get("crossref_works", DEFAULT_API_ENDPOINTS["crossref_works"])
    try:
        resp = requests.get(
            endpoint,
            params={"query": query, "rows": min(max(limit, 1), 50)},
            headers=get_polite_headers(cfg),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return papers
        items = (resp.json().get("message") or {}).get("items") or []
        for item in items[:limit]:
            titles = item.get("title") or []
            title = titles[0].strip() if titles else ""
            if not title:
                continue
            doi = normalize_doi(item.get("DOI"))
            year = 0
            for date_field in ("published-print", "published-online", "created"):
                parts = ((item.get(date_field) or {}).get("date-parts") or [[]])[0]
                if parts and isinstance(parts[0], int):
                    year = parts[0]
                    break
            author_objs = item.get("author") or []
            author_names = [
                f"{a.get('given', '')} {a.get('family', '')}".strip()
                for a in author_objs[:5]
                if a.get("family") or a.get("given")
            ]
            authors = ", ".join(author_names) if author_names else "Unknown"
            containers = item.get("container-title") or []
            publication = containers[0] if containers else (item.get("publisher") or "Crossref")
            pdf_url = ""
            for link in item.get("link") or []:
                if "pdf" in (link.get("content-type") or "").lower():
                    pdf_url = link.get("URL") or ""
                    break
            abstract = strip_jats_xml(item.get("abstract") or "")
            citations = int(item.get("is-referenced-by-count") or 0)
            landing = item.get("URL") or (f"https://doi.org/{doi}" if doi else "NA")
            papers.append(
                Paper(
                    title=title,
                    year=year,
                    authors=authors,
                    publication=publication,
                    url=landing,
                    doi=doi,
                    pdf_url=pdf_url,
                    abstract=abstract,
                    citations=citations,
                    source="Crossref",
                )
            )
    except Exception:
        pass
    return papers


def search_doaj(
    query: str,
    limit: int = 20,
    timeout: int = 12,
    config: Optional[AppConfig] = None,
) -> List[Paper]:
    cfg = config or AppConfig.load()
    papers: List[Paper] = []
    encoded_q = urllib.parse.quote(query)
    base_ep = cfg.api_endpoints.get("doaj_search", DEFAULT_API_ENDPOINTS["doaj_search"]).rstrip("/")
    try:
        resp = requests.get(
            f"{base_ep}/{encoded_q}",
            params={"pageSize": min(max(limit, 1), 50)},
            headers=get_polite_headers(cfg),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return papers
        results = resp.json().get("results") or []
        for item in results[:limit]:
            bib = item.get("bibjson") or {}
            title = (bib.get("title") or "").strip()
            if not title:
                continue
            year_str = str(bib.get("year") or "0")
            year = int(year_str) if year_str.isdigit() else 0
            authors = ", ".join([a.get("name", "") for a in (bib.get("author") or [])[:5] if a.get("name")]) or "Unknown"
            publication = (bib.get("journal") or {}).get("title") or "DOAJ"
            doi = ""
            for ident in bib.get("identifier") or []:
                if (ident.get("type") or "").lower() == "doi":
                    doi = normalize_doi(ident.get("id"))
                    break
            pdf_url = ""
            landing = ""
            for link in bib.get("link") or []:
                lurl = link.get("url") or ""
                ctype = (link.get("content_type") or "").lower()
                if "pdf" in ctype or lurl.lower().endswith(".pdf"):
                    pdf_url = lurl
                elif not landing:
                    landing = lurl
            if not landing:
                landing = f"https://doi.org/{doi}" if doi else (pdf_url or "NA")
            papers.append(
                Paper(
                    title=title,
                    year=year,
                    authors=authors,
                    publication=publication,
                    url=landing,
                    doi=doi,
                    pdf_url=pdf_url,
                    abstract=(bib.get("abstract") or "").strip(),
                    citations=0,
                    source="DOAJ",
                )
            )
    except Exception:
        pass
    return papers


def search_hal(
    query: str,
    limit: int = 20,
    timeout: int = 12,
    config: Optional[AppConfig] = None,
) -> List[Paper]:
    cfg = config or AppConfig.load()
    papers: List[Paper] = []
    endpoint = cfg.api_endpoints.get("hal_search", DEFAULT_API_ENDPOINTS["hal_search"])
    try:
        resp = requests.get(
            endpoint,
            params={
                "q": query,
                "rows": min(max(limit, 1), 50),
                "fl": "title_s,authFullName_s,producedDateY_i,journalTitle_s,doiId_s,uri_s,fileMain_s,abstract_s",
                "wt": "json",
            },
            headers=get_polite_headers(cfg),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return papers
        docs = (resp.json().get("response") or {}).get("docs") or []
        for doc in docs[:limit]:
            titles = doc.get("title_s") or []
            title = titles[0].strip() if isinstance(titles, list) and titles else str(titles or "").strip()
            if not title:
                continue
            year = int(doc.get("producedDateY_i") or 0)
            auths = doc.get("authFullName_s") or []
            authors = ", ".join(auths[:5]) if isinstance(auths, list) and auths else "Unknown"
            publication = doc.get("journalTitle_s") or "HAL Open Archive"
            doi = normalize_doi(doc.get("doiId_s"))
            pdf_url = doc.get("fileMain_s") or ""
            landing = doc.get("uri_s") or (f"https://doi.org/{doi}" if doi else "NA")
            ab_list = doc.get("abstract_s") or []
            abstract = ab_list[0] if isinstance(ab_list, list) and ab_list else ""
            papers.append(
                Paper(
                    title=title,
                    year=year,
                    authors=authors,
                    publication=publication,
                    url=landing,
                    doi=doi,
                    pdf_url=pdf_url,
                    abstract=abstract,
                    citations=0,
                    source="HAL",
                )
            )
    except Exception:
        pass
    return papers


def search_openaire(
    query: str,
    limit: int = 20,
    timeout: int = 12,
    config: Optional[AppConfig] = None,
) -> List[Paper]:
    cfg = config or AppConfig.load()
    papers: List[Paper] = []
    endpoint = cfg.api_endpoints.get("openaire_search", DEFAULT_API_ENDPOINTS["openaire_search"])
    try:
        resp = requests.get(
            endpoint,
            params={"keywords": query, "size": min(max(limit, 1), 50), "format": "json"},
            headers=get_polite_headers(cfg),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return papers
        data = resp.json()
        results = (((data.get("response") or {}).get("results") or {}).get("result")) or []
        if isinstance(results, dict):
            results = [results]
        for item in results[:limit]:
            meta = ((item.get("metadata") or {}).get("oaf:entity") or {}).get("oaf:result") or {}
            if not meta:
                continue
            title_obj = meta.get("title")
            if isinstance(title_obj, list):
                title = (title_obj[0].get("$") if isinstance(title_obj[0], dict) else str(title_obj[0])) if title_obj else ""
            elif isinstance(title_obj, dict):
                title = title_obj.get("$") or ""
            else:
                title = str(title_obj or "")
            title = title.strip()
            if not title:
                continue
            date_str = str((meta.get("dateofacceptance") or {}).get("$") or "")
            year = int(date_str[:4]) if len(date_str) >= 4 and date_str[:4].isdigit() else 0
            creators = meta.get("creator") or []
            if isinstance(creators, dict):
                creators = [creators]
            authors = ", ".join([c.get("$", "") for c in creators[:5] if isinstance(c, dict) and c.get("$")]) or "Unknown"
            desc = meta.get("description")
            if isinstance(desc, list) and desc:
                abstract = desc[0].get("$", "") if isinstance(desc[0], dict) else str(desc[0])
            elif isinstance(desc, dict):
                abstract = desc.get("$", "")
            else:
                abstract = ""
            pids = meta.get("pid") or []
            if isinstance(pids, dict):
                pids = [pids]
            doi = ""
            for p in pids:
                if isinstance(p, dict) and (p.get("@classid") or "").lower() == "doi":
                    doi = normalize_doi(p.get("$"))
                    break
            children = (meta.get("children") or {}).get("instance") or []
            if isinstance(children, dict):
                children = [children]
            pdf_url = ""
            landing = ""
            for inst in children:
                if not isinstance(inst, dict):
                    continue
                access = (inst.get("accessright") or {}).get("@classid", "")
                webres = inst.get("webresource") or []
                if isinstance(webres, dict):
                    webres = [webres]
                for w in webres:
                    u = (w.get("url") or {}).get("$", "") if isinstance(w, dict) else ""
                    if not u:
                        continue
                    if not landing:
                        landing = u
                    if (access == "OPEN" or ".pdf" in u.lower()) and not pdf_url:
                        pdf_url = u
            if not landing:
                landing = f"https://doi.org/{doi}" if doi else "NA"
            papers.append(
                Paper(
                    title=title,
                    year=year,
                    authors=authors,
                    publication="OpenAIRE",
                    url=landing,
                    doi=doi,
                    pdf_url=pdf_url,
                    abstract=strip_jats_xml(abstract),
                    citations=0,
                    source="OpenAIRE",
                )
            )
    except Exception:
        pass
    return papers


def search_google_scholar(
    query: str,
    page_start: int = 1,
    page_end: int = 1,
    delay_seconds: float = 5.0,
    timeout: int = 12,
    config: Optional[AppConfig] = None,
) -> List[Paper]:
    cfg = config or AppConfig.load()
    papers: List[Paper] = []
    q_encoded = urllib.parse.quote_plus(query)
    start_offset = max((page_start - 1) * 10, 0)
    stop_offset = max(page_end * 10, start_offset + 10)
    base_ep = cfg.api_endpoints.get("google_scholar", DEFAULT_API_ENDPOINTS["google_scholar"])

    for idx, offset in enumerate(range(start_offset, stop_offset, 10)):
        if idx > 0 and delay_seconds > 0:
            time.sleep(delay_seconds)
        url = f"{base_ep}?start={offset}&q={q_encoded}&hl=en&as_sdt=0,5"
        try:
            resp = requests.get(url, headers=get_browser_headers(cfg), timeout=timeout)
            if resp.status_code != 200:
                break
            doc = BeautifulSoup(resp.text, "html.parser")
            blocks = doc.select("div.gs_r.gs_or.gs_scl") or doc.select("[data-lid]")
            for block in blocks:
                h3 = block.find("h3", {"class": "gs_rt"}) or block.find("h3")
                if not h3:
                    continue
                raw_title = h3.get_text(" ", strip=True)
                clean_t = re.sub(r"\[(BOOK|HTML|B|PDF|CITATION|DOC)\]", "", raw_title, flags=re.IGNORECASE).strip()
                a_tag = h3.find("a", href=True)
                link = a_tag["href"] if a_tag else "NA"

                side_div = block.find("div", {"class": "gs_or_ggsm"})
                pdf_url = ""
                if side_div:
                    side_a = side_div.find("a", href=True)
                    if side_a:
                        pdf_url = side_a["href"]

                author_div = block.find("div", {"class": "gs_a"})
                year = 0
                authors = "Unknown"
                pub = "Google Scholar"
                if author_div:
                    txt = author_div.get_text(" ", strip=True)
                    ym = re.search(r"\b(19\d\d|20\d\d)\b", txt)
                    if ym:
                        year = int(ym.group(1))
                    parts = [p.strip() for p in txt.split("-")]
                    if parts:
                        authors = parts[0]
                    if len(parts) >= 3:
                        pub = parts[-1]
                    elif len(parts) == 2:
                        pub = parts[1]

                snippet_div = block.find("div", {"class": "gs_rs"})
                abstract = snippet_div.get_text(" ", strip=True) if snippet_div else ""

                citations = 0
                for a in block.select("div.gs_fl a"):
                    m_c = re.search(r"Cited by\s+(\d+)", a.get_text())
                    if m_c:
                        citations = int(m_c.group(1))
                        break

                papers.append(
                    Paper(
                        title=clean_t,
                        year=year,
                        authors=authors,
                        publication=pub,
                        url=link,
                        doi="",
                        pdf_url=pdf_url,
                        abstract=abstract,
                        citations=citations,
                        source="Google Scholar",
                    )
                )
        except Exception:
            break
    return papers


def deduplicate_and_merge_papers(papers: Sequence[Paper]) -> List[Paper]:
    by_key: Dict[str, Paper] = {}
    doi_to_key: Dict[str, str] = {}

    def _norm_title(t: str) -> str:
        s = re.sub(r"\[(BOOK|HTML|B|PDF|CITATION|DOC)\]", "", str(t), flags=re.IGNORECASE)
        return re.sub(r"[^a-z0-9]+", "", s.lower())

    for p in papers:
        nt = _norm_title(p.title)
        if not nt:
            continue
        ndoi = normalize_doi(p.doi)
        if ndoi and ndoi in doi_to_key:
            key = doi_to_key[ndoi]
        elif nt in by_key:
            key = nt
        else:
            key = nt
            by_key[key] = p
            if ndoi:
                doi_to_key[ndoi] = key
            continue

        existing = by_key[key]
        if ndoi and not existing.doi:
            existing.doi = ndoi
            doi_to_key[ndoi] = key
        if p.year and not existing.year:
            existing.year = p.year
        if p.authors and existing.authors in ("", "Unknown"):
            existing.authors = p.authors
        if p.publication and existing.publication in ("", "Unknown", "OpenAlex", "Crossref"):
            existing.publication = p.publication
        if p.url and p.url != "NA" and existing.url in ("", "NA"):
            existing.url = p.url
        if p.pdf_url and not existing.pdf_url:
            existing.pdf_url = p.pdf_url
        if len(p.abstract or "") > len(existing.abstract or ""):
            existing.abstract = p.abstract
        if (p.citations or 0) > (existing.citations or 0):
            existing.citations = p.citations
        if p.source and p.source not in existing.source:
            existing.source = f"{existing.source}, {p.source}"

    return list(by_key.values())


def search_multi_source(
    query: str,
    sources: Optional[Sequence[str]] = None,
    limit_per_source: Optional[int] = None,
    scholar_pages: Tuple[int, int] = (1, 1),
    sort_by: Optional[str] = None,
    config: Optional[AppConfig] = None,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> List[Paper]:
    cfg = config or AppConfig.load()
    selected = list(sources) if sources else list(cfg.default_sources or ALL_OPEN_SOURCES)
    limit = limit_per_source if limit_per_source is not None else cfg.default_limit_per_source
    sort_mode = sort_by if sort_by is not None else cfg.default_sort
    all_found: List[Paper] = []

    def _run_one(src: str) -> Tuple[str, List[Paper]]:
        src_l = src.lower().strip()
        if src_l == "openalex":
            res = search_openalex(query, limit=limit, timeout=cfg.request_timeout, config=cfg)
        elif src_l == "semantic_scholar":
            res = search_semantic_scholar(
                query,
                limit=limit,
                timeout=cfg.request_timeout,
                api_key=cfg.semantic_scholar_api_key,
                config=cfg,
            )
        elif src_l == "arxiv":
            res = search_arxiv(query, limit=limit, timeout=cfg.request_timeout, config=cfg)
        elif src_l == "europe_pmc":
            res = search_europe_pmc(query, limit=limit, timeout=cfg.request_timeout, config=cfg)
        elif src_l == "crossref":
            res = search_crossref(query, limit=limit, timeout=cfg.request_timeout, config=cfg)
        elif src_l == "doaj":
            res = search_doaj(query, limit=limit, timeout=cfg.request_timeout, config=cfg)
        elif src_l == "hal":
            res = search_hal(query, limit=limit, timeout=cfg.request_timeout, config=cfg)
        elif src_l == "openaire":
            res = search_openaire(query, limit=limit, timeout=cfg.request_timeout, config=cfg)
        elif src_l == "google_scholar":
            res = search_google_scholar(
                query,
                page_start=scholar_pages[0],
                page_end=scholar_pages[1],
                delay_seconds=3.0,
                timeout=cfg.request_timeout,
                config=cfg,
            )
        else:
            res = []
        return src_l, res

    with ThreadPoolExecutor(max_workers=min(len(selected), 8)) as pool:
        futures = {pool.submit(_run_one, s): s for s in selected}
        for fut in as_completed(futures):
            src_name, items = fut.result()
            all_found.extend(items)
            if progress_callback:
                progress_callback(SOURCE_LABELS.get(src_name, src_name), len(items))

    merged = deduplicate_and_merge_papers(all_found)

    sort_key = (sort_mode or "relevance").lower().strip()
    if sort_key in ("asc", "year_asc"):
        merged.sort(key=lambda p: (p.year if p.year > 0 else 9999))
    elif sort_key in ("desc", "year_desc"):
        merged.sort(key=lambda p: p.year, reverse=True)
    elif sort_key in ("citations", "citations_desc", "cited"):
        merged.sort(key=lambda p: p.citations, reverse=True)

    return merged


def fetch_citation_snowball(
    doi_or_query: str,
    max_backward: int = 10,
    max_forward: int = 10,
    config: Optional[AppConfig] = None,
    progress_callback: Optional[Callable[[str, int], None]] = None,
) -> Tuple[Optional[Paper], List[Paper], List[Paper]]:
    """Trace citation network forward and backward around an anchor paper.

    Returns:
        (seed_paper, backward_citations, forward_citations)
    """
    cfg = config or AppConfig.load()
    clean_target = (doi_or_query or "").strip()
    if not clean_target:
        return None, [], []

    ep_map = cfg.api_endpoints or {}
    polite_headers = get_polite_headers(cfg)
    is_doi = bool(re.search(r"10\.\d{4,9}/", clean_target) or clean_target.strip().startswith("10."))
    norm_doi = normalize_doi(clean_target) if is_doi else ""

    seed_paper: Optional[Paper] = None
    openalex_work_id: Optional[str] = None
    referenced_ids: List[str] = []

    # 1. Fetch seed paper from OpenAlex
    oa_base = ep_map.get("openalex_works", DEFAULT_API_ENDPOINTS["openalex_works"]).rstrip("/")
    if norm_doi:
        try:
            r = requests.get(f"{oa_base}/https://doi.org/{norm_doi}", headers=polite_headers, timeout=cfg.request_timeout)
            if r.status_code == 200:
                item = r.json()
                parsed = _parse_openalex_item(item)
                if parsed.title:
                    seed_paper = parsed
                    openalex_work_id = str(item.get("id") or "").split("/")[-1]
                    referenced_ids = [str(w).split("/")[-1] for w in item.get("referenced_works", []) if w]
        except Exception:
            seed_paper = None

    if not seed_paper:
        try:
            params = {"search": clean_target, "per-page": 1}
            r = requests.get(oa_base, params=params, headers=polite_headers, timeout=cfg.request_timeout)
            if r.status_code == 200:
                results = r.json().get("results", [])
                if results:
                    item = results[0]
                    seed_paper = _parse_openalex_item(item)
                    openalex_work_id = str(item.get("id") or "").split("/")[-1]
                    referenced_ids = [str(w).split("/")[-1] for w in item.get("referenced_works", []) if w]
        except Exception:
            seed_paper = None

    backward_papers: List[Paper] = []
    forward_papers: List[Paper] = []

    if progress_callback and seed_paper:
        progress_callback("Anchor Seed Paper", 1)

    # 2. Fetch Backward Citations (Foundational Works Cited)
    if referenced_ids and max_backward > 0:
        pick_ids = referenced_ids[:max_backward]
        try:
            filt_str = "|".join(pick_ids)
            r_back = requests.get(
                oa_base,
                params={"filter": f"openalex_id:{filt_str}", "per-page": len(pick_ids)},
                headers=polite_headers,
                timeout=cfg.request_timeout,
            )
            if r_back.status_code == 200:
                for b_item in r_back.json().get("results", []):
                    p = _parse_openalex_item(b_item)
                    if p.title:
                        backward_papers.append(p)
        except Exception:
            pass

    if progress_callback:
        progress_callback("Backward References", len(backward_papers))

    # 3. Fetch Forward Citations (Works Citing the Seed Paper)
    if openalex_work_id and max_forward > 0:
        try:
            r_fwd = requests.get(
                oa_base,
                params={
                    "filter": f"cites:{openalex_work_id}",
                    "sort": "cited_by_count:desc",
                    "per-page": max_forward,
                },
                headers=polite_headers,
                timeout=cfg.request_timeout,
            )
            if r_fwd.status_code == 200:
                for f_item in r_fwd.json().get("results", []):
                    p = _parse_openalex_item(f_item)
                    if p.title:
                        forward_papers.append(p)
        except Exception:
            pass

    if progress_callback:
        progress_callback("Forward Citations", len(forward_papers))

    # Fallback to Semantic Scholar Graph API if OpenAlex yielded zero connections
    if (not backward_papers and not forward_papers) and norm_doi:
        try:
            s2_headers = {"User-Agent": cfg.browser_user_agent}
            if cfg.semantic_scholar_api_key:
                s2_headers["x-api-key"] = cfg.semantic_scholar_api_key
            s2_url = f"https://api.semanticscholar.org/graph/v1/paper/{norm_doi}"
            fields = "title,authors,year,citationCount,references.title,references.authors,references.year,references.externalIds,citations.title,citations.authors,citations.year,citations.externalIds"
            r_s2 = requests.get(s2_url, params={"fields": fields}, headers=s2_headers, timeout=cfg.request_timeout)
            if r_s2.status_code == 200:
                data = r_s2.json()
                if not seed_paper and data.get("title"):
                    s_authors = ", ".join(a.get("name", "") for a in data.get("authors", []) if a.get("name"))
                    seed_paper = Paper(
                        title=data["title"],
                        authors=s_authors,
                        year=str(data.get("year") or ""),
                        doi=norm_doi,
                        citations=int(data.get("citationCount") or 0),
                        source="Semantic Scholar",
                    )
                for ref in data.get("references", [])[:max_backward]:
                    if ref and ref.get("title"):
                        ref_doi = (ref.get("externalIds") or {}).get("DOI", "")
                        ref_auth = ", ".join(a.get("name", "") for a in ref.get("authors", []) if a.get("name"))
                        backward_papers.append(
                            Paper(
                                title=ref["title"],
                                authors=ref_auth,
                                year=str(ref.get("year") or ""),
                                doi=ref_doi,
                                source="Semantic Scholar (Reference)",
                            )
                        )
                for cit in data.get("citations", [])[:max_forward]:
                    if cit and cit.get("title"):
                        cit_doi = (cit.get("externalIds") or {}).get("DOI", "")
                        cit_auth = ", ".join(a.get("name", "") for a in cit.get("authors", []) if a.get("name"))
                        forward_papers.append(
                            Paper(
                                title=cit["title"],
                                authors=cit_auth,
                                year=str(cit.get("year") or ""),
                                doi=cit_doi,
                                source="Semantic Scholar (Citation)",
                            )
                        )
        except Exception:
            pass

    return seed_paper, deduplicate_and_merge_papers(backward_papers), deduplicate_and_merge_papers(forward_papers)

