"""Multi-source PDF downloader & DOI resolver for Crawly (requests + BeautifulSoup4, configured via config.json)."""

from __future__ import annotations

import csv
import difflib
import re
import urllib.parse
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import requests
from bs4 import BeautifulSoup

from .models import DEFAULT_API_ENDPOINTS, AppConfig, Paper, save_papers_to_csv
from .sources import get_browser_headers, get_polite_headers, normalize_doi, reconstruct_openalex_abstract


def _title_similarity(a: str, b: str) -> float:
    def _clean(s: str) -> str:
        s = re.sub(r"\[(BOOK|HTML|B|PDF|CITATION|DOC)\]", "", str(s), flags=re.IGNORECASE)
        s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
        return re.sub(r"\s+", " ", s).strip()

    ca, cb = _clean(a), _clean(b)
    if not ca or not cb:
        return 0.0
    if ca == cb or (len(ca) > 20 and (ca in cb or cb in ca)):
        return 1.0
    return difflib.SequenceMatcher(None, ca, cb).ratio()


def extract_doi_from_text_or_url(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    decoded = urllib.parse.unquote(text)
    m = re.search(r"(10\.\d{4,9}/[-._;()/:A-Za-z0-9]+)", decoded)
    if not m:
        return ""
    doi = m.group(1).rstrip(".,;)/")
    for suffix in (".pdf", ".short", ".full", "/meta", "/full", "/pdf", "/abstract"):
        if doi.lower().endswith(suffix):
            doi = doi[: -len(suffix)]
    return normalize_doi(doi)


def resolve_paper_metadata(paper: Paper, timeout: int = 10, config: Optional[AppConfig] = None) -> Paper:
    cfg = config or AppConfig.load()
    if not paper.doi:
        paper.doi = extract_doi_from_text_or_url(paper.url) or extract_doi_from_text_or_url(paper.title)

    clean_t = paper.clean_title()
    oa_base = cfg.api_endpoints.get("openalex_works", DEFAULT_API_ENDPOINTS["openalex_works"]).rstrip("/")
    cr_base = cfg.api_endpoints.get("crossref_works", DEFAULT_API_ENDPOINTS["crossref_works"]).rstrip("/")
    polite_hdrs = get_polite_headers(cfg)

    try:
        if paper.doi:
            oa_api = f"{oa_base}/https://doi.org/{urllib.parse.quote(paper.doi, safe='/')}"
            r = requests.get(oa_api, headers=polite_hdrs, timeout=timeout)
            if r.status_code == 200:
                item = r.json()
                best_oa = item.get("best_oa_location") or {}
                prim = item.get("primary_location") or {}
                oa_info = item.get("open_access") or {}
                candidate_pdf = best_oa.get("pdf_url") or prim.get("pdf_url") or oa_info.get("oa_url") or ""
                if candidate_pdf and not paper.pdf_url:
                    paper.pdf_url = candidate_pdf
                if not paper.abstract:
                    paper.abstract = reconstruct_openalex_abstract(item.get("abstract_inverted_index"))
                if not paper.citations and item.get("cited_by_count"):
                    paper.citations = int(item["cited_by_count"])
        if not paper.doi and clean_t:
            r = requests.get(
                oa_base,
                params={"search": clean_t, "per-page": 3},
                headers=polite_hdrs,
                timeout=timeout,
            )
            if r.status_code == 200:
                for item in r.json().get("results") or []:
                    cand_title = item.get("title") or item.get("display_name") or ""
                    if _title_similarity(clean_t, cand_title) >= 0.70:
                        found_doi = normalize_doi(item.get("doi"))
                        if found_doi:
                            paper.doi = found_doi
                        best_oa = item.get("best_oa_location") or {}
                        prim = item.get("primary_location") or {}
                        oa_info = item.get("open_access") or {}
                        candidate_pdf = best_oa.get("pdf_url") or prim.get("pdf_url") or oa_info.get("oa_url") or ""
                        if candidate_pdf and not paper.pdf_url:
                            paper.pdf_url = candidate_pdf
                        if not paper.abstract:
                            paper.abstract = reconstruct_openalex_abstract(item.get("abstract_inverted_index"))
                        if not paper.citations and item.get("cited_by_count"):
                            paper.citations = int(item["cited_by_count"])
                        break
    except Exception:
        pass

    if not paper.doi and clean_t:
        try:
            r = requests.get(
                cr_base,
                params={"query.bibliographic": clean_t, "rows": 3},
                headers=polite_hdrs,
                timeout=timeout,
            )
            if r.status_code == 200:
                items = (r.json().get("message") or {}).get("items") or []
                for item in items:
                    titles = item.get("title") or []
                    cand_title = titles[0] if titles else ""
                    if _title_similarity(clean_t, cand_title) >= 0.72:
                        paper.doi = normalize_doi(item.get("DOI"))
                        for link in item.get("link") or []:
                            if "pdf" in (link.get("content-type") or "").lower() and not paper.pdf_url:
                                paper.pdf_url = link.get("URL") or ""
                        break
        except Exception:
            pass

    return paper


def _extract_pdf_url_from_html(html: str, base_url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for selector in [
        ("embed", {"id": "pdf"}),
        ("iframe", {"id": "pdf"}),
        ("embed", {"type": "application/pdf"}),
        ("iframe", {}),
        ("embed", {}),
    ]:
        tag = soup.find(selector[0], selector[1])
        if tag and tag.get("src"):
            src = tag["src"].strip().split("#")[0].strip()
            if src:
                return urllib.parse.urljoin(base_url, src)

    for btn in soup.find_all(["button", "a"]):
        onclick = btn.get("onclick") or ""
        m = re.search(r"location\.href\s*=\s*['\"]([^'\"]+)['\"]", onclick)
        if m:
            raw = m.group(1).replace("\\/", "/").split("#")[0].strip()
            if raw:
                return urllib.parse.urljoin(base_url, raw)

    meta_pdf = soup.find("meta", attrs={"name": re.compile(r"citation_pdf_url", re.I)})
    if meta_pdf and meta_pdf.get("content"):
        return urllib.parse.urljoin(base_url, meta_pdf["content"].strip())

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if ".pdf" in href.lower() and not href.lower().startswith("javascript:"):
            return urllib.parse.urljoin(base_url, href.split("#")[0])

    return ""


def _fetch_and_verify_pdf(
    url: str,
    target_path: Path,
    timeout: int = 20,
    config: Optional[AppConfig] = None,
) -> bool:
    if not url or not url.startswith(("http://", "https://")):
        return False
    cfg = config or AppConfig.load()
    headers = {
        "User-Agent": get_browser_headers(cfg)["User-Agent"],
        "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, stream=True)
        if resp.status_code != 200:
            return False

        chunks = []
        total_bytes = 0
        first_chunk = b""
        for chunk in resp.iter_content(chunk_size=16384):
            if not chunk:
                continue
            if not first_chunk:
                first_chunk = chunk
            chunks.append(chunk)
            total_bytes += len(chunk)
            if b"%PDF-" not in first_chunk[:1024] and total_bytes > 262144:
                break

        content = b"".join(chunks)
        pdf_idx = content.find(b"%PDF-")
        if 0 <= pdf_idx <= 1024 and len(content) > 1024:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_bytes(content[pdf_idx:])
            return True

        ctype = (resp.headers.get("Content-Type") or "").lower()
        if "html" in ctype or content.lstrip().startswith((b"<!DOCTYPE", b"<html", b"<HTML")):
            html_text = content.decode("utf-8", errors="ignore")
            nested_pdf_url = _extract_pdf_url_from_html(html_text, resp.url)
            if nested_pdf_url and nested_pdf_url != url:
                resp2 = requests.get(
                    nested_pdf_url,
                    headers={**headers, "Referer": resp.url},
                    timeout=timeout,
                    allow_redirects=True,
                )
                if resp2.status_code == 200:
                    idx2 = resp2.content.find(b"%PDF-")
                    if 0 <= idx2 <= 1024 and len(resp2.content) > 1024:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        target_path.write_bytes(resp2.content[idx2:])
                        return True
    except Exception:
        return False
    return False


def _candidate_publisher_oa_urls(paper: Paper) -> List[Tuple[str, str]]:
    candidates: List[Tuple[str, str]] = []
    if paper.pdf_url:
        candidates.append(("Direct/OA Link", paper.pdf_url))
    u = (paper.url or "").strip()
    if "arxiv.org/abs/" in u:
        candidates.append(("arXiv Direct", u.replace("/abs/", "/pdf/") + ".pdf"))
    if "mdpi.com/" in u and not u.endswith("/pdf"):
        candidates.append(("MDPI Open Access", u.rstrip("/") + "/pdf"))
    return candidates


def _candidate_unpaywall_urls(
    doi: str,
    email: str,
    timeout: int = 10,
    config: Optional[AppConfig] = None,
) -> List[Tuple[str, str]]:
    if not doi:
        return []
    cfg = config or AppConfig.load()
    out: List[Tuple[str, str]] = []
    base = cfg.api_endpoints.get("unpaywall_base", DEFAULT_API_ENDPOINTS["unpaywall_base"]).rstrip("/")
    url = f"{base}/{urllib.parse.quote(doi, safe='/')}"
    try:
        r = requests.get(url, params={"email": email}, headers=get_polite_headers(cfg), timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            best = data.get("best_oa_location") or {}
            if best.get("url_for_pdf"):
                out.append(("Unpaywall OA", best["url_for_pdf"]))
            for loc in data.get("oa_locations") or []:
                u = loc.get("url_for_pdf")
                if u and all(u != existing[1] for existing in out):
                    out.append(("Unpaywall OA", u))
    except Exception:
        pass
    return out


def _candidate_semantic_scholar_urls(
    paper: Paper,
    api_key: str = "",
    timeout: int = 10,
    config: Optional[AppConfig] = None,
) -> List[Tuple[str, str]]:
    cfg = config or AppConfig.load()
    out: List[Tuple[str, str]] = []
    headers = get_polite_headers(cfg)
    if api_key:
        headers["x-api-key"] = api_key
    s2_base = cfg.api_endpoints.get("semantic_scholar_paper", DEFAULT_API_ENDPOINTS["semantic_scholar_paper"]).rstrip("/")
    try:
        if paper.doi:
            r = requests.get(
                f"{s2_base}/DOI:{urllib.parse.quote(paper.doi, safe='/')}",
                params={"fields": "openAccessPdf,externalIds"},
                headers=headers,
                timeout=timeout,
            )
            if r.status_code == 200:
                item = r.json()
                oa = (item.get("openAccessPdf") or {}).get("url")
                if oa:
                    out.append(("Semantic Scholar OA", oa))
                arxiv_id = (item.get("externalIds") or {}).get("ArXiv")
                if arxiv_id:
                    out.append(("arXiv Preprint", f"https://arxiv.org/pdf/{arxiv_id}.pdf"))
    except Exception:
        pass
    return out


def _candidate_europe_pmc_urls(
    paper: Paper,
    timeout: int = 10,
    config: Optional[AppConfig] = None,
) -> List[Tuple[str, str]]:
    cfg = config or AppConfig.load()
    out: List[Tuple[str, str]] = []
    q = f'DOI:"{paper.doi}"' if paper.doi else f'TITLE:"{paper.clean_title()}"'
    epmc_search = cfg.api_endpoints.get("europe_pmc_search", DEFAULT_API_ENDPOINTS["europe_pmc_search"])
    epmc_pdf = cfg.api_endpoints.get("europe_pmc_pdf", DEFAULT_API_ENDPOINTS["europe_pmc_pdf"])
    try:
        r = requests.get(
            epmc_search,
            params={"query": q, "format": "json", "pageSize": 1},
            headers=get_polite_headers(cfg),
            timeout=timeout,
        )
        if r.status_code == 200:
            results = ((r.json().get("resultList") or {}).get("result")) or []
            if results:
                pmcid = results[0].get("pmcid")
                if pmcid:
                    out.append(
                        (
                            "Europe PMC",
                            f"{epmc_pdf}?accid={pmcid}&blobtype=pdf",
                        )
                    )
    except Exception:
        pass
    return out


def _try_scihub_download(
    paper: Paper,
    target_path: Path,
    mirrors: Sequence[str],
    timeout: int = 15,
    config: Optional[AppConfig] = None,
) -> Optional[str]:
    cfg = config or AppConfig.load()
    doi = normalize_doi(paper.doi)
    if doi and cfg.scihub_cdn_url:
        cdn_url = cfg.scihub_cdn_url.replace("{doi}", doi)
        if _fetch_and_verify_pdf(cdn_url, target_path, timeout=timeout, config=cfg):
            cdn_host = urllib.parse.urlparse(cdn_url).netloc or "CDN"
            return f"Sci-Hub CDN ({cdn_host})"

    queries = []
    if doi:
        queries.append(doi)
    if paper.url and paper.url != "NA":
        queries.append(paper.url)

    for mirror in mirrors:
        m_base = mirror.strip().rstrip("/")
        if not m_base:
            continue
        if not m_base.startswith(("http://", "https://")):
            m_base = "https://" + m_base
        for q in queries:
            lookup_url = f"{m_base}/{q}"
            if _fetch_and_verify_pdf(lookup_url, target_path, timeout=timeout, config=cfg):
                return f"Sci-Hub ({urllib.parse.urlparse(m_base).netloc})"

    return None


def download_paper_pdf(
    paper: Paper,
    output_dir: Path,
    config: Optional[AppConfig] = None,
    custom_scihub_url: Optional[str] = None,
) -> Tuple[bool, str, Optional[Path]]:
    cfg = config or AppConfig.load()
    output_dir.mkdir(parents=True, exist_ok=True)
    target_path = output_dir / paper.safe_filename()

    if target_path.exists() and target_path.stat().st_size > 1024:
        try:
            with target_path.open("rb") as fh:
                head = fh.read(1024)
            if b"%PDF-" in head:
                paper.local_pdf = str(target_path)
                paper.download_source = paper.download_source or "Local Cache"
                return True, paper.download_source, target_path
        except Exception:
            pass

    resolve_paper_metadata(paper, timeout=cfg.request_timeout, config=cfg)

    candidates: List[Tuple[str, str]] = []
    candidates.extend(_candidate_publisher_oa_urls(paper))
    if paper.doi:
        candidates.extend(_candidate_unpaywall_urls(paper.doi, cfg.unpaywall_email, timeout=cfg.request_timeout, config=cfg))
        candidates.extend(
            _candidate_semantic_scholar_urls(
                paper, api_key=cfg.semantic_scholar_api_key, timeout=cfg.request_timeout, config=cfg
            )
        )
    candidates.extend(_candidate_europe_pmc_urls(paper, timeout=cfg.request_timeout, config=cfg))

    tried_urls = set()
    for source_label, cand_url in candidates:
        if not cand_url or cand_url in tried_urls:
            continue
        tried_urls.add(cand_url)
        if _fetch_and_verify_pdf(cand_url, target_path, timeout=cfg.request_timeout + 8, config=cfg):
            paper.local_pdf = str(target_path)
            paper.download_source = source_label
            return True, source_label, target_path

    if cfg.use_scihub_fallback or custom_scihub_url:
        mirrors = list(cfg.scihub_mirrors)
        if custom_scihub_url:
            clean_m = custom_scihub_url.strip().rstrip("/")
            if clean_m and clean_m not in mirrors:
                mirrors.insert(0, clean_m)
        sh_source = _try_scihub_download(
            paper,
            target_path,
            mirrors=mirrors,
            timeout=cfg.request_timeout + 8,
            config=cfg,
        )
        if sh_source:
            paper.local_pdf = str(target_path)
            paper.download_source = sh_source
            return True, sh_source, target_path

    return False, "Not Found", None


def download_batch_pdfs(
    papers: Sequence[Paper],
    output_dir: str | Path,
    csv_path: Optional[str | Path] = None,
    config: Optional[AppConfig] = None,
    custom_scihub_url: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, Paper, bool, str], None]] = None,
) -> Dict[str, int]:
    cfg = config or AppConfig.load()
    out_path = Path(str(output_dir).strip())
    out_path.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    not_found_rows: List[Dict[str, str]] = []
    by_source: Dict[str, int] = {}

    total = len(papers)
    for idx, paper in enumerate(papers, start=1):
        ok, src, _ = download_paper_pdf(
            paper,
            output_dir=out_path,
            config=cfg,
            custom_scihub_url=custom_scihub_url,
        )
        if ok:
            downloaded += 1
            by_source[src] = by_source.get(src, 0) + 1
        else:
            not_found_rows.append(
                {
                    "Paper Title": paper.clean_title(),
                    "Paper URL": paper.url,
                    "DOI": paper.doi,
                }
            )
        if progress_callback:
            progress_callback(idx, total, paper, ok, src)

    nf_path = out_path / "papers_not_found.csv"
    with nf_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["Paper Title", "Paper URL", "DOI"])
        writer.writeheader()
        writer.writerows(not_found_rows)

    if csv_path:
        try:
            save_papers_to_csv(list(papers), csv_path)
        except Exception:
            pass

    return {
        "total": total,
        "downloaded": downloaded,
        "missing": total - downloaded,
        **by_source,
    }
