"""Data models, CSV/BibTeX serialization, and config.json management for Crawly."""

from __future__ import annotations

import csv
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def resolve_config_path() -> Path:
    """Locate config.json in current working directory first, then project root."""
    cwd_cfg = Path.cwd() / "config.json"
    if cwd_cfg.exists():
        return cwd_cfg
    root_cfg = Path(__file__).resolve().parent.parent / "config.json"
    if root_cfg.exists():
        return root_cfg
    return cwd_cfg


CONFIG_PATH = resolve_config_path()

CONFIG_DOCUMENTATION = {
    "description": (
        "crawly: the literature assistant — Master Configuration File. Edit any value below to customize "
        "AI models, search defaults, API keys, timeouts, and download behavior."
    ),
    "repository": "https://github.com/lokeshsk/crawly",
    "ai_provider_options": [
        "ollama            -> Local self-hosted Ollama server (default base_url: http://localhost:11434)",
        "lmstudio          -> Local self-hosted LM Studio server (default base_url: http://localhost:1234/v1)",
        "openai_compatible -> Any OpenAI-compatible API (OpenAI, OpenRouter, Groq, DeepSeek, Together, vLLM, llama.cpp)",
        "gemini            -> Google Gemini API (requires ai_api_key)",
        "anthropic         -> Anthropic Claude API (requires ai_api_key)",
        "extractive        -> Built-in offline NLP & BM25 extractive engine (requires no local server or API key)",
    ],
    "default_sort_options": [
        "relevance -> Best match across databases",
        "desc      -> Newest publication year first",
        "asc       -> Oldest publication year first",
        "citations -> Highest citation count first",
    ],
    "available_sources": [
        "openalex",
        "semantic_scholar",
        "arxiv",
        "europe_pmc",
        "crossref",
        "doaj",
        "hal",
        "openaire",
        "google_scholar",
    ],
}

DEFAULT_OPEN_SOURCES = [
    "openalex",
    "semantic_scholar",
    "arxiv",
    "europe_pmc",
    "crossref",
    "doaj",
    "hal",
    "openaire",
]

DEFAULT_SCIHUB_MIRRORS = [
    "https://sci-hub.ee",
    "https://sci-hub.ren",
    "https://sci-hub.al",
    "https://sci-hub.ru",
    "https://sci-hub.st",
    "https://sci-hub.wf",
    "https://sci-hub.se",
]

DEFAULT_API_ENDPOINTS = {
    "openalex_works": "https://api.openalex.org/works",
    "semantic_scholar_search": "https://api.semanticscholar.org/graph/v1/paper/search",
    "semantic_scholar_paper": "https://api.semanticscholar.org/graph/v1/paper",
    "arxiv_query": "http://export.arxiv.org/api/query",
    "europe_pmc_search": "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
    "europe_pmc_pdf": "https://europepmc.org/backend/ptpmcrender.fcgi",
    "crossref_works": "https://api.crossref.org/works",
    "doaj_search": "https://doaj.org/api/search/articles",
    "hal_search": "https://api.archives-ouvertes.fr/search/",
    "openaire_search": "https://api.openaire.eu/search/publications",
    "unpaywall_base": "https://api.unpaywall.org/v2",
    "google_scholar": "https://scholar.google.com/scholar",
    "gemini_base": "https://generativelanguage.googleapis.com/v1beta/models",
    "anthropic_messages": "https://api.anthropic.com/v1/messages",
}

CSV_FIELDNAMES = [
    "Paper Title",
    "Year",
    "Author",
    "Publication",
    "Url of paper",
    "DOI",
    "PDF URL",
    "Citations",
    "Source",
    "Abstract",
    "Local PDF",
    "Download Source",
]


@dataclass
class Paper:
    """Unified representation of an academic paper across search, download, and AI stages."""

    title: str
    year: int = 0
    authors: str = "Unknown"
    publication: str = "Unknown"
    url: str = "NA"
    doi: str = ""
    pdf_url: str = ""
    abstract: str = ""
    citations: int = 0
    source: str = "unknown"
    local_pdf: str = ""
    download_source: str = ""
    summary: str = ""

    def clean_title(self) -> str:
        t = re.sub(r"\[(BOOK|HTML|B|PDF|CITATION|DOC)\]", "", str(self.title), flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", t).strip()

    def safe_filename(self, max_len: int = 120) -> str:
        base = self.clean_title() or (self.doi.replace("/", "_") if self.doi else "paper")
        cleaned = re.sub(r'[\\/*?:"<>|\r\n\t]+', " ", base)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ._-")
        if len(cleaned) > max_len:
            cleaned = cleaned[:max_len].rstrip(" ._-")
        if not cleaned.lower().endswith(".pdf"):
            cleaned += ".pdf"
        return cleaned

    def has_pdf(self) -> bool:
        """Check if paper has a downloaded local PDF or an online PDF URL."""
        return bool((self.local_pdf and str(self.local_pdf).strip()) or (self.pdf_url and str(self.pdf_url).strip()))

    def bibtex_key(self) -> str:
        """Generate a clean BibTeX citation key (e.g. vaswani2017attention)."""
        author_part = re.sub(r"[^a-zA-Z0-9]+", "", (self.authors or "paper").split(",")[0].split()[-1] if (self.authors and " " in self.authors) else (self.authors.split(",")[0] if self.authors else "paper")).lower() or "paper"
        yr_digits = re.sub(r"[^0-9]", "", str(self.year or ""))
        yr = yr_digits if yr_digits else "nd"
        title_word = re.sub(r"[^a-zA-Z0-9]+", "", self.clean_title().split()[0]).lower() if self.clean_title() else "work"
        return f"{author_part}{yr}{title_word}"

    def to_bibtex(self) -> str:
        """Generate a formatted BibTeX entry string for this paper."""
        ckey = self.bibtex_key()
        bib_authors = " and ".join([a.strip() for a in (self.authors or "Unknown").split(",") if a.strip()])
        lines = [
            f"@article{{{ckey},",
            f"  title = {{{self.clean_title()}}},",
            f"  author = {{{bib_authors}}},",
        ]
        yr_digits = re.sub(r"[^0-9]", "", str(self.year or ""))
        if yr_digits and int(yr_digits) > 0:
            lines.append(f"  year = {{{yr_digits}}},")
        if self.publication and self.publication != "Unknown":
            lines.append(f"  journal = {{{self.publication}}},")
        if self.doi:
            lines.append(f"  doi = {{{self.doi}}},")
        if self.url and self.url != "NA":
            lines.append(f"  url = {{{self.url}}},")
        if self.abstract:
            safe_abs = self.abstract.replace("{", "").replace("}", "")[:1000]
            lines.append(f"  abstract = {{{safe_abs}}},")
        lines.append("}")
        return "\n".join(lines)

    @property
    def ai_summary(self) -> str:
        """Alias for summary."""
        return self.summary

    @ai_summary.setter
    def ai_summary(self, val: str) -> None:
        self.summary = val

    def to_csv_row(self) -> Dict[str, Any]:
        return {
            "Paper Title": self.clean_title(),
            "Year": int(self.year) if str(self.year).isdigit() else 0,
            "Author": self.authors or "Unknown",
            "Publication": self.publication or "Unknown",
            "Url of paper": self.url or "NA",
            "DOI": self.doi or "",
            "PDF URL": self.pdf_url or "",
            "Citations": int(self.citations) if str(self.citations).isdigit() else 0,
            "Source": self.source or "",
            "Abstract": self.abstract or "",
            "Local PDF": self.local_pdf or "",
            "Download Source": self.download_source or "",
        }

    @classmethod
    def from_csv_row(cls, row: Dict[str, Any]) -> "Paper":
        def _str(val: Any, default: str = "") -> str:
            if val is None:
                return default
            s = str(val).strip()
            return default if s.lower() in ("nan", "none", "") else s

        def _int(val: Any, default: int = 0) -> int:
            try:
                if val is None or str(val).strip().lower() in ("nan", "none", ""):
                    return default
                return int(float(str(val).strip()))
            except (ValueError, TypeError):
                return default

        title = _str(row.get("Paper Title") or row.get("title") or row.get("Title"), "Untitled")
        title = re.sub(r"\[(BOOK|HTML|B|PDF)\]", "", title, flags=re.IGNORECASE).strip()
        return cls(
            title=title,
            year=_int(row.get("Year") or row.get("year"), 0),
            authors=_str(row.get("Author") or row.get("Authors") or row.get("authors"), "Unknown"),
            publication=_str(row.get("Publication") or row.get("Venue") or row.get("publication"), "Unknown"),
            url=_str(row.get("Url of paper") or row.get("Paper URL") or row.get("url"), "NA"),
            doi=_str(row.get("DOI") or row.get("doi"), ""),
            pdf_url=_str(row.get("PDF URL") or row.get("pdf_url"), ""),
            abstract=_str(row.get("Abstract") or row.get("abstract"), ""),
            citations=_int(row.get("Citations") or row.get("citations"), 0),
            source=_str(row.get("Source") or row.get("source"), "csv"),
            local_pdf=_str(row.get("Local PDF") or row.get("local_pdf"), ""),
            download_source=_str(row.get("Download Source") or row.get("download_source"), ""),
            summary=_str(row.get("Summary") or row.get("AI Summary") or row.get("summary"), ""),
        )


def load_papers_from_csv(csv_path: str | Path) -> List[Paper]:
    path = Path(str(csv_path).strip())
    if path.suffix.lower() != ".csv" and not path.exists():
        path = Path(f"{path}.csv")
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")
    papers: List[Paper] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if not row:
                continue
            papers.append(Paper.from_csv_row(row))
    return papers


def save_papers_to_csv(
    papers: Sequence[Paper],
    csv_path: str | Path,
    extra_fields: Optional[Sequence[str]] = None,
) -> Path:
    path = Path(str(csv_path).strip())
    if path.suffix.lower() != ".csv":
        path = Path(f"{path}.csv")
    fieldnames = list(CSV_FIELDNAMES)
    if extra_fields:
        for ef in extra_fields:
            if ef not in fieldnames:
                fieldnames.append(ef)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for p in papers:
            row = p.to_csv_row()
            if "AI Summary" in fieldnames:
                row["AI Summary"] = p.summary or ""
            writer.writerow(row)
    return path


def export_papers_to_bibtex(papers: Sequence[Paper], bib_path: str | Path) -> Path:
    """Export papers to a standard BibTeX (.bib) file for Zotero, Mendeley, EndNote, or LaTeX/Overleaf."""
    path = Path(str(bib_path).strip())
    if path.suffix.lower() != ".bib":
        path = Path(f"{path}.bib")

    entries: List[str] = []
    used_keys: set[str] = set()
    for idx, p in enumerate(papers, start=1):
        first_author = re.sub(r"[^a-zA-Z]", "", (p.authors or "Author").split(",")[0].split()[-1]).lower() or "paper"
        yr = str(p.year) if p.year and p.year > 0 else "nd"
        first_word = re.sub(r"[^a-zA-Z0-9]", "", p.clean_title().split()[0]).lower() if p.clean_title() else "work"
        cite_key = f"{first_author}{yr}{first_word}"
        if cite_key in used_keys:
            cite_key = f"{cite_key}_{idx}"
        used_keys.add(cite_key)

        bib_authors = " and ".join([a.strip() for a in (p.authors or "Unknown").split(",") if a.strip()])
        lines = [
            f"@article{{{cite_key},",
            f"  title = {{{p.clean_title()}}},",
            f"  author = {{{bib_authors}}},",
        ]
        if p.year and p.year > 0:
            lines.append(f"  year = {{{p.year}}},")
        if p.publication and p.publication != "Unknown":
            lines.append(f"  journal = {{{p.publication}}},")
        if p.doi:
            lines.append(f"  doi = {{{p.doi}}},")
        if p.url and p.url != "NA":
            lines.append(f"  url = {{{p.url}}},")
        if p.abstract:
            safe_abs = p.abstract.replace("{", "").replace("}", "")[:1000]
            lines.append(f"  abstract = {{{safe_abs}}},")
        lines.append("}")
        entries.append("\n".join(lines))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n\n".join(entries) + "\n", encoding="utf-8")
    return path


@dataclass
class AppConfig:
    """Master configuration backed by user-editable `config.json`."""

    ai_provider: str = "ollama"
    ai_model: str = "llama3.2"
    ai_base_url: str = "http://localhost:11434"
    ai_api_key: str = ""
    temperature: float = 0.2
    max_pdf_pages: int = 25
    max_text_chars: int = 14000

    default_sources: List[str] = field(default_factory=lambda: list(DEFAULT_OPEN_SOURCES))
    default_limit_per_source: int = 10
    default_sort: str = "relevance"
    request_timeout: int = 12

    unpaywall_email: str = "crawly.theliteratureassistant@gmail.com"
    semantic_scholar_api_key: str = ""
    core_api_key: str = ""
    polite_user_agent: str = (
        "crawly/2.0 (crawly: the literature assistant; https://github.com/lokeshsk/crawly; mailto:crawly.theliteratureassistant@gmail.com)"
    )
    browser_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )

    use_scihub_fallback: bool = False
    use_selenium_fallback: bool = False
    scihub_cdn_url: str = "https://sci.bban.top/pdf/{doi}.pdf"
    scihub_mirrors: List[str] = field(default_factory=lambda: list(DEFAULT_SCIHUB_MIRRORS))
    api_endpoints: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_API_ENDPOINTS))

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "AppConfig":
        target = path or resolve_config_path()
        cfg = cls()
        if target.exists():
            try:
                data = json.loads(target.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if k.startswith("_"):
                        continue
                    if k == "api_endpoints" and isinstance(v, dict):
                        merged_ep = dict(DEFAULT_API_ENDPOINTS)
                        merged_ep.update({str(ek).lower(): str(ev) for ek, ev in v.items()})
                        cfg.api_endpoints = merged_ep
                    elif hasattr(cfg, k):
                        setattr(cfg, k, v)
            except Exception:
                pass
        else:
            try:
                cfg.save(target)
            except Exception:
                pass

        # Environment variable overrides
        if os.environ.get("CRAWLY_AI_PROVIDER"):
            cfg.ai_provider = os.environ["CRAWLY_AI_PROVIDER"]
        if os.environ.get("CRAWLY_AI_MODEL"):
            cfg.ai_model = os.environ["CRAWLY_AI_MODEL"]
        if os.environ.get("CRAWLY_AI_BASE_URL"):
            cfg.ai_base_url = os.environ["CRAWLY_AI_BASE_URL"]
        if os.environ.get("CRAWLY_AI_API_KEY"):
            cfg.ai_api_key = os.environ["CRAWLY_AI_API_KEY"]
        elif os.environ.get("OPENAI_API_KEY") and cfg.ai_provider == "openai_compatible" and not cfg.ai_api_key:
            cfg.ai_api_key = os.environ["OPENAI_API_KEY"]
        elif os.environ.get("GEMINI_API_KEY") and cfg.ai_provider == "gemini" and not cfg.ai_api_key:
            cfg.ai_api_key = os.environ["GEMINI_API_KEY"]
        elif os.environ.get("ANTHROPIC_API_KEY") and cfg.ai_provider == "anthropic" and not cfg.ai_api_key:
            cfg.ai_api_key = os.environ["ANTHROPIC_API_KEY"]
        return cfg

    def save(self, path: Optional[Path] = None) -> Path:
        target = path or resolve_config_path()
        payload: Dict[str, Any] = {"_documentation": CONFIG_DOCUMENTATION}
        payload.update(asdict(self))
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return target
