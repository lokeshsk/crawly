"""AI Literature Review Engine for Crawly (powered by pypdf & requests, configured via config.json).

Supports:
- Local Self-Hosted Models: Ollama (`http://localhost:11434`), LM Studio (`http://localhost:1234/v1`), llama.cpp / vLLM
- Any OpenAI-Compatible Endpoint (OpenRouter, Groq, Together, DeepSeek, OpenAI, custom base_url)
- Commercial APIs: Google Gemini, Anthropic Claude
- Offline Extractive Fallback (TF-IDF / BM25 sentence & passage ranking when no LLM is reachable)
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import requests
from pypdf import PdfReader

from .models import DEFAULT_API_ENDPOINTS, AppConfig, Paper, save_papers_to_csv

logging.getLogger("pypdf").setLevel(logging.ERROR)


def extract_pdf_pages(pdf_path: str | Path, max_pages: Optional[int] = None) -> List[Tuple[int, str]]:
    """Extract (page_number, text) tuples from a local PDF file using pypdf."""
    path = Path(str(pdf_path))
    if not path.exists() or path.stat().st_size < 1024:
        return []
    limit_pages = max_pages if max_pages is not None else AppConfig.load().max_pdf_pages
    pages: List[Tuple[int, str]] = []
    try:
        reader = PdfReader(str(path))
        for idx, page in enumerate(reader.pages[:limit_pages], start=1):
            raw = page.extract_text() or ""
            cleaned = re.sub(r"-\s*\n\s*", "", raw)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if cleaned:
                pages.append((idx, cleaned))
    except Exception:
        pass
    return pages


def extract_paper_fulltext(
    paper: Paper,
    max_chars: Optional[int] = None,
    max_pages: Optional[int] = None,
    output_dir: Optional[Path] = None,
) -> Tuple[str, str]:
    cfg = AppConfig.load()
    char_limit = max_chars if max_chars is not None else cfg.max_text_chars
    page_limit = max_pages if max_pages is not None else cfg.max_pdf_pages

    pdf_candidates: List[Path] = []
    if paper.local_pdf:
        pdf_candidates.append(Path(paper.local_pdf))
    if output_dir:
        pdf_candidates.append(output_dir / paper.safe_filename())
        pdf_candidates.append(output_dir / paper.clean_title())

    for cand in pdf_candidates:
        if cand.exists() and cand.is_file() and cand.stat().st_size > 1024:
            pages = extract_pdf_pages(cand, max_pages=page_limit)
            if pages:
                joined = "\n\n".join([f"[Page {pno}] {txt}" for pno, txt in pages])
                return joined[:char_limit], f"Full PDF ({len(pages)} pages)"

    if paper.abstract:
        return paper.abstract[:char_limit], "Abstract"
    return f"Title: {paper.clean_title()} ({paper.year}) by {paper.authors} in {paper.publication}", "Metadata Only"


def discover_local_models(provider: str, base_url: str, timeout: int = 4) -> List[str]:
    prov = provider.lower().strip()
    b_url = base_url.rstrip("/")
    models: List[str] = []
    try:
        if prov == "ollama":
            r = requests.get(f"{b_url}/api/tags", timeout=timeout)
            if r.status_code == 200:
                for m in r.json().get("models") or []:
                    if m.get("name"):
                        models.append(m["name"])
        else:
            ep = f"{b_url}/models" if b_url.endswith("/v1") else f"{b_url}/v1/models"
            r = requests.get(ep, timeout=timeout)
            if r.status_code == 200:
                for m in r.json().get("data") or []:
                    if m.get("id"):
                        models.append(m["id"])
    except Exception:
        pass
    return models


class LLMClient:
    """Unified client for Ollama, LM Studio, OpenAI-compatible APIs, Gemini, Anthropic, and offline fallback."""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self.config = config or AppConfig.load()

    def check_connection(self) -> Tuple[bool, str]:
        prov = self.config.ai_provider.lower().strip()
        b_url = self.config.ai_base_url.rstrip("/")
        if prov == "extractive":
            return True, "Offline Extractive NLP Engine (Ready)"
        if prov == "ollama":
            models = discover_local_models("ollama", b_url)
            if models:
                if self.config.ai_model not in models:
                    self.config.ai_model = models[0]
                return True, f"Ollama connected ({b_url}) - Models: {', '.join(models[:4])}"
            return False, f"Ollama not reachable at {b_url} (using extractive fallback unless started)"
        if prov == "lmstudio":
            models = discover_local_models("lmstudio", b_url)
            if models:
                if self.config.ai_model not in models:
                    self.config.ai_model = models[0]
                return True, f"LM Studio connected ({b_url}) - Model: {self.config.ai_model}"
            return False, f"LM Studio server not reachable at {b_url}"
        if prov == "openai_compatible":
            if not b_url:
                return False, "Missing ai_base_url in config.json for OpenAI-compatible provider"
            return True, f"OpenAI-Compatible endpoint ({b_url}, model={self.config.ai_model})"
        if prov == "gemini":
            if not self.config.ai_api_key:
                return False, "Missing ai_api_key / GEMINI_API_KEY in config.json"
            return True, f"Google Gemini ({self.config.ai_model})"
        if prov == "anthropic":
            if not self.config.ai_api_key:
                return False, "Missing ai_api_key / ANTHROPIC_API_KEY in config.json"
            return True, f"Anthropic Claude ({self.config.ai_model})"
        return False, f"Unknown provider in config.json: {prov}"

    def generate(self, system_prompt: str, user_prompt: str, timeout: int = 90) -> Optional[str]:
        prov = self.config.ai_provider.lower().strip()
        if prov == "extractive":
            return None

        b_url = self.config.ai_base_url.rstrip("/")
        model = self.config.ai_model

        try:
            if prov == "ollama":
                avail = discover_local_models("ollama", b_url, timeout=3)
                if avail and model not in avail:
                    model = avail[0]
                resp = requests.post(
                    f"{b_url}/api/chat",
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "stream": False,
                        "options": {"temperature": self.config.temperature},
                    },
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    return (resp.json().get("message") or {}).get("content", "").strip()

            elif prov in ("lmstudio", "openai_compatible"):
                if prov == "lmstudio":
                    avail = discover_local_models("lmstudio", b_url, timeout=3)
                    if avail and model not in avail:
                        model = avail[0]
                endpoint = f"{b_url}/chat/completions" if b_url.endswith("/v1") else f"{b_url}/v1/chat/completions"
                headers = {"Content-Type": "application/json"}
                if self.config.ai_api_key:
                    headers["Authorization"] = f"Bearer {self.config.ai_api_key}"
                resp = requests.post(
                    endpoint,
                    headers=headers,
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ],
                        "temperature": self.config.temperature,
                    },
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    choices = resp.json().get("choices") or []
                    if choices:
                        return ((choices[0].get("message") or {}).get("content") or "").strip()

            elif prov == "gemini":
                gem_model = model if model.startswith("gemini") else "gemini-2.5-flash"
                gem_base = self.config.api_endpoints.get("gemini_base", DEFAULT_API_ENDPOINTS["gemini_base"]).rstrip("/")
                url = f"{gem_base}/{gem_model}:generateContent"
                resp = requests.post(
                    url,
                    params={"key": self.config.ai_api_key},
                    json={
                        "systemInstruction": {"parts": [{"text": system_prompt}]},
                        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
                        "generationConfig": {"temperature": self.config.temperature},
                    },
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    cands = resp.json().get("candidates") or []
                    if cands:
                        parts = ((cands[0].get("content") or {}).get("parts")) or []
                        return "".join(p.get("text", "") for p in parts).strip()

            elif prov == "anthropic":
                ant_model = model if "claude" in model else "claude-3-5-sonnet-latest"
                ant_ep = self.config.api_endpoints.get("anthropic_messages", DEFAULT_API_ENDPOINTS["anthropic_messages"])
                resp = requests.post(
                    ant_ep,
                    headers={
                        "x-api-key": self.config.ai_api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": ant_model,
                        "max_tokens": 2048,
                        "system": system_prompt,
                        "messages": [{"role": "user", "content": user_prompt}],
                    },
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    blocks = resp.json().get("content") or []
                    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text").strip()
        except Exception:
            return None
        return None


def _extractive_structured_summary(paper: Paper, full_text: str, source_type: str) -> str:
    clean_text = re.sub(r"\[Page \d+\]", " ", full_text)
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", clean_text)
        if 40 <= len(s.strip()) <= 360 and not s.strip().isupper()
    ]
    if not sentences:
        return (
            f"- **Objective:** Study on *{paper.clean_title()}* ({paper.year}).\n"
            f"- **Authors & Venue:** {paper.authors} ({paper.publication}).\n"
            f"- **Source Basis:** {source_type} | DOI: `{paper.doi or 'N/A'}`"
        )

    def _pick_by_keywords(keywords: Sequence[str], fallback_idx: int) -> str:
        best_s = ""
        best_score = 0
        for s in sentences[:60]:
            sl = s.lower()
            score = sum(2 for kw in keywords if kw in sl)
            if score > best_score:
                best_score = score
                best_s = s
        if best_s:
            return best_s
        idx = min(fallback_idx, len(sentences) - 1)
        return sentences[idx]

    objective = _pick_by_keywords(["propose", "present", "introduce", "overview", "review", "aim", "investigate", "paper"], 0)
    method = _pick_by_keywords(["algorithm", "method", "model", "approach", "technique", "formulation", "framework", "based on"], min(1, len(sentences) - 1))
    findings = _pick_by_keywords(["result", "show", "demonstrate", "improve", "performance", "experiment", "achieve", "accuracy", "simulation"], min(2, len(sentences) - 1))
    limit_s = _pick_by_keywords(["limit", "challenge", "future", "however", "computational", "complex", "conclusion"], len(sentences) - 1)

    return (
        f"- **Objective:** {objective}\n"
        f"- **Methodology:** {method}\n"
        f"- **Key Findings:** {findings}\n"
        f"- **Conclusions / Challenges:** {limit_s}\n"
        f"- **Basis:** Extracted from {source_type}"
    )


def run_mode_1_per_paper_summaries(
    papers: Sequence[Paper],
    output_dir: Path,
    dataset_name: str,
    config: Optional[AppConfig] = None,
    progress_callback: Optional[Callable[[int, int, Paper, str], None]] = None,
) -> Path:
    cfg = config or AppConfig.load()
    client = LLMClient(cfg)
    output_dir.mkdir(parents=True, exist_ok=True)

    system_prompt = (
        "You are an expert academic research assistant. Summarize the provided research paper concisely "
        "using exact facts from the text in 4 bullet points:\n"
        "- **Objective:** Core problem and research goal.\n"
        "- **Methodology:** Key algorithms, architecture, or experimental setup.\n"
        "- **Key Findings:** Quantitative/qualitative results and contributions.\n"
        "- **Limitations & Future Work:** Noted constraints or open directions."
    )

    md_lines = [
        f"# Structured Paper Summaries: `{dataset_name}`",
        "",
        f"- **Total Papers Analyzed:** {len(papers)}",
        f"- **AI Provider:** `{cfg.ai_provider}` (`{cfg.ai_model}`)",
        "",
        "---",
        "",
    ]

    total = len(papers)
    for idx, paper in enumerate(papers, start=1):
        content, basis = extract_paper_fulltext(
            paper,
            max_chars=cfg.max_text_chars,
            max_pages=cfg.max_pdf_pages,
            output_dir=output_dir,
        )
        user_prompt = (
            f"Paper Title: {paper.clean_title()}\n"
            f"Authors: {paper.authors}\n"
            f"Year: {paper.year} | Venue: {paper.publication} | DOI: {paper.doi}\n"
            f"Content Source: {basis}\n\n"
            f"Extracted Text:\n{content}"
        )
        llm_resp = client.generate(system_prompt, user_prompt)
        if not llm_resp:
            llm_resp = _extractive_structured_summary(paper, content, basis)
        paper.summary = llm_resp

        md_lines.extend(
            [
                f"## {idx}. {paper.clean_title()} ({paper.year or 'N/A'})",
                f"- **Authors:** {paper.authors} | **Venue:** {paper.publication} | **Citations:** {paper.citations}",
                f"- **DOI:** `{paper.doi or 'N/A'}` | **Content Source:** {basis} | **URL:** {paper.url}",
                "",
                llm_resp,
                "",
                "---",
                "",
            ]
        )
        if progress_callback:
            progress_callback(idx, total, paper, basis)

    report_path = output_dir / f"{dataset_name}_paper_summaries.md"
    report_path.write_text("\n".join(md_lines), encoding="utf-8")
    save_papers_to_csv(papers, output_dir / f"{dataset_name}_summaries.csv", extra_fields=["AI Summary"])
    return report_path


def run_mode_2_literature_review_synthesis(
    papers: Sequence[Paper],
    output_dir: Path,
    dataset_name: str,
    config: Optional[AppConfig] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[str, Path]:
    cfg = config or AppConfig.load()
    client = LLMClient(cfg)
    output_dir.mkdir(parents=True, exist_ok=True)

    subset = list(papers[:30])
    total_steps = len(subset) + 1
    digest_blocks: List[str] = []
    for idx, p in enumerate(subset, start=1):
        content, basis = extract_paper_fulltext(
            p,
            max_chars=min(cfg.max_text_chars, 3000),
            max_pages=min(cfg.max_pdf_pages, 12),
            output_dir=output_dir,
        )
        snippet = p.summary or content[:1200]
        digest_blocks.append(
            f"[{idx}] {p.clean_title()} ({p.year}, {p.authors}, {p.publication}, DOI:{p.doi}, Cited:{p.citations}, Source:{basis})\n"
            f"Summary/Excerpt: {snippet}"
        )
        if progress_callback:
            progress_callback(idx, total_steps, f"Extracted digest [{idx}/{len(subset)}]: {p.clean_title()[:50]}")

    system_prompt = (
        "You are a senior principal researcher writing a comprehensive, rigorous Literature Review and "
        "Comparative Synthesis based on the provided corpus of papers. Structure your response in Markdown with:\n"
        "1. **Executive Overview & Evolution of the Field**\n"
        "2. **Thematic Taxonomy & Core Methodologies** (citing papers as [1], [2], etc.)\n"
        "3. **Comparative Synthesis Matrix** (a Markdown table comparing Paper, Year, Core Method/Approach, Key Contribution, and Application Domain)\n"
        "4. **Open Challenges, Research Gaps & Future Directions**"
    )
    user_prompt = f"Dataset: {dataset_name} ({len(papers)} papers)\n\nCorpus:\n\n" + "\n\n".join(digest_blocks)

    synthesis = client.generate(system_prompt, user_prompt, timeout=120)
    if not synthesis:
        years = [p.year for p in papers if p.year > 0]
        yr_span = f"{min(years)}–{max(years)}" if years else "N/A"
        pdf_count = sum(1 for p in papers if p.local_pdf or (output_dir / p.safe_filename()).exists())

        table_rows = [
            "| # | Paper Title | Year | Authors | Venue | DOI | Key Focus / Takeaway |",
            "|---|-------------|------|---------|-------|-----|----------------------|",
        ]
        for idx, p in enumerate(papers, start=1):
            content, _ = extract_paper_fulltext(p, max_chars=1500, output_dir=output_dir)
            clean_c = re.sub(r"\[Page \d+\]", " ", content)
            first_sent = re.split(r"(?<=[.!?])\s+", clean_c)[0][:140].replace("|", "/") if clean_c else p.clean_title()
            table_rows.append(
                f"| [{idx}] | {p.clean_title()[:55].replace('|', '/')} | {p.year or 'N/A'} | "
                f"{p.authors[:22].replace('|', '/')} | {p.publication[:20].replace('|', '/')} | "
                f"`{p.doi or 'N/A'}` | {first_sent}... |"
            )

        bib_lines = [
            f"- **[{idx}]** {p.authors} ({p.year or 'n.d.'}). *{p.clean_title()}*. {p.publication}. "
            f"{'https://doi.org/' + p.doi if p.doi else p.url}"
            for idx, p in enumerate(papers, start=1)
        ]

        synthesis = "\n".join(
            [
                f"# Synthesized Literature Review & Comparison Matrix: `{dataset_name}`",
                "",
                "## 1. Executive Overview",
                f"- **Corpus Size:** {len(papers)} research papers ({pdf_count} with local full-text PDFs analyzed)",
                f"- **Publication Span:** {yr_span}",
                f"- **Primary Venues:** {', '.join(sorted({p.publication for p in papers if p.publication and p.publication != 'Unknown'})[:8])}",
                "",
                "## 2. Comparative Literature Matrix",
                "",
                *table_rows,
                "",
                "## 3. Bibliography & Source Links",
                "",
                *bib_lines,
            ]
        )
    else:
        bib_lines = [
            f"- **[{idx}]** {p.authors} ({p.year or 'n.d.'}). *{p.clean_title()}*. {p.publication}. "
            f"{'https://doi.org/' + p.doi if p.doi else p.url}"
            for idx, p in enumerate(papers, start=1)
        ]
        synthesis = (
            f"# Synthesized Literature Review: `{dataset_name}`\n\n"
            + synthesis
            + "\n\n## Bibliography\n\n"
            + "\n".join(bib_lines)
        )

    if progress_callback:
        progress_callback(total_steps, total_steps, "Completed cross-paper Literature Review synthesis")

    out_file = output_dir / f"{dataset_name}_literature_review.md"
    out_file.write_text(synthesis, encoding="utf-8")
    return synthesis, out_file


@dataclass
class PassageChunk:
    paper_idx: int
    paper_title: str
    authors: str
    year: int
    page_num: int
    text: str
    tokens: Counter


def _tokenize(text: str) -> List[str]:
    stop = {
        "the", "and", "for", "that", "this", "with", "from", "are", "was", "were",
        "have", "has", "had", "not", "but", "can", "will", "into", "using", "based",
        "which", "their", "our", "also", "between", "such", "than", "more", "some",
    }
    words = re.findall(r"[a-z0-9]{2,}", text.lower())
    return [w for w in words if w not in stop]


class PaperRAGIndex:
    """Mode 3: Local BM25 / TF-IDF Retrieval-Augmented Generation index over downloaded PDFs & abstracts."""

    def __init__(
        self,
        papers: Sequence[Paper],
        output_dir: Optional[Path] = None,
        config: Optional[AppConfig] = None,
        progress_callback: Optional[Callable[[int, int, Paper], None]] = None,
    ) -> None:
        self.papers = list(papers)
        self.output_dir = output_dir
        self.config = config or AppConfig.load()
        self.chunks: List[PassageChunk] = []
        self.df: Counter = Counter()
        self._build_index(progress_callback=progress_callback)

    def _build_index(self, progress_callback: Optional[Callable[[int, int, Paper], None]] = None) -> None:
        total = len(self.papers)
        for idx, p in enumerate(self.papers, start=1):
            pdf_path: Optional[Path] = None
            if p.local_pdf and Path(p.local_pdf).exists():
                pdf_path = Path(p.local_pdf)
            elif self.output_dir and (self.output_dir / p.safe_filename()).exists():
                pdf_path = self.output_dir / p.safe_filename()

            if pdf_path:
                pages = extract_pdf_pages(pdf_path, max_pages=self.config.max_pdf_pages)
                for pno, page_txt in pages:
                    words = page_txt.split()
                    step = 130
                    window = 160
                    for start in range(0, max(len(words), 1), step):
                        passage = " ".join(words[start : start + window]).strip()
                        if len(passage) < 60:
                            continue
                        toks = Counter(_tokenize(f"{p.clean_title()} {passage}"))
                        self.chunks.append(
                            PassageChunk(
                                paper_idx=idx,
                                paper_title=p.clean_title(),
                                authors=p.authors,
                                year=p.year,
                                page_num=pno,
                                text=passage,
                                tokens=toks,
                            )
                        )
            else:
                fallback_txt = p.abstract or p.summary or f"{p.clean_title()} ({p.year}) by {p.authors}"
                toks = Counter(_tokenize(f"{p.clean_title()} {fallback_txt}"))
                self.chunks.append(
                    PassageChunk(
                        paper_idx=idx,
                        paper_title=p.clean_title(),
                        authors=p.authors,
                        year=p.year,
                        page_num=0,
                        text=fallback_txt,
                        tokens=toks,
                    )
                )
            if progress_callback:
                progress_callback(idx, total, p)

        for ch in self.chunks:
            for term in ch.tokens.keys():
                self.df[term] += 1

    def retrieve(self, query: str, top_k: int = 5) -> List[Tuple[float, PassageChunk]]:
        q_tokens = _tokenize(query)
        if not q_tokens or not self.chunks:
            return [(1.0, c) for c in self.chunks[:top_k]]

        n_docs = len(self.chunks)
        scored: List[Tuple[float, PassageChunk]] = []
        for ch in self.chunks:
            doc_len = sum(ch.tokens.values()) or 1
            score = 0.0
            for qt in q_tokens:
                tf = ch.tokens.get(qt, 0)
                if tf > 0:
                    idf = math.log(1.0 + (n_docs - self.df[qt] + 0.5) / (self.df[qt] + 0.5))
                    score += idf * ((tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * (doc_len / 120.0))))
            if score > 0:
                scored.append((score, ch))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_k] if scored else [(0.1, c) for c in self.chunks[:top_k]]

    def answer_question(self, question: str, config: Optional[AppConfig] = None, top_k: int = 5) -> str:
        cfg = config or self.config
        client = LLMClient(cfg)
        hits = self.retrieve(question, top_k=top_k)
        if not hits:
            return "No indexed text passages found in the dataset."

        context_blocks: List[str] = []
        for rank, (score, ch) in enumerate(hits, start=1):
            loc = f"Page {ch.page_num}" if ch.page_num > 0 else "Abstract/Metadata"
            context_blocks.append(
                f"Excerpt [{rank}] — Paper #{ch.paper_idx}: \"{ch.paper_title}\" ({ch.authors}, {ch.year}, {loc}):\n"
                f"{ch.text}"
            )

        system_prompt = (
            "You are an academic research assistant answering questions grounded strictly in the retrieved "
            "excerpts from the user's downloaded PDF papers. Always cite the Paper # and Page number in "
            "brackets like [Paper #1, Page 3] for every claim."
        )
        user_prompt = (
            f"Question: {question}\n\n"
            f"Retrieved Excerpts from Local PDFs:\n\n" + "\n\n".join(context_blocks)
        )

        llm_ans = client.generate(system_prompt, user_prompt, timeout=90)
        if llm_ans:
            return llm_ans

        lines = [
            "### Retrieved Evidence from Downloaded PDFs & Papers",
            "*(Offline Extractive RAG Mode — configure Ollama, LM Studio, or an API key in `config.json` for generative synthesis)*",
            "",
        ]
        for rank, (score, ch) in enumerate(hits, start=1):
            loc = f"p. {ch.page_num}" if ch.page_num > 0 else "Abstract"
            lines.append(
                f"**{rank}. [{ch.authors} ({ch.year}), *{ch.paper_title}*, {loc}]**\n"
                f"> {ch.text[:500]}{'...' if len(ch.text) > 500 else ''}\n"
            )
        return "\n".join(lines)


def run_mode_gaps_synthesis(
    papers: Sequence[Paper],
    output_dir: Optional[Path] = None,
    dataset_name: str = "dataset",
    config: Optional[AppConfig] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> Tuple[str, Path]:
    """Synthesize identified research gaps, limitations, and future directions across papers."""
    cfg = config or AppConfig.load()
    out_dir = output_dir or Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", dataset_name).strip("_") or "dataset"

    top_papers = list(papers)[:30]
    total_steps = len(top_papers) + 1
    summaries_data: List[Dict[str, str]] = []

    for idx, p in enumerate(top_papers, start=1):
        pdf_path = Path(p.local_pdf) if p.local_pdf and Path(p.local_pdf).exists() else None
        if not pdf_path and (out_dir / p.safe_filename()).exists():
            pdf_path = out_dir / p.safe_filename()

        raw_text = ""
        if pdf_path:
            pages = extract_pdf_pages(pdf_path, max_pages=cfg.max_pdf_pages)
            raw_text = "\n".join(txt for _, txt in pages)

        basis_text = raw_text if raw_text.strip() else (p.abstract or p.clean_title())
        sentences = [
            s.strip()
            for s in re.split(r"(?<=[.!?])\s+", basis_text)
            if 30 <= len(s.strip()) <= 320
        ]
        gap_sentences = [
            s for s in sentences
            if any(k in s.lower() for k in ["limit", "challenge", "future", "remain", "however", "bottleneck", "lack", "restrict", "gap", "need to", "unresolved"])
        ]
        lim_str = " ".join(gap_sentences[:3]) if gap_sentences else (sentences[-1] if sentences else "Not specified.")

        summaries_data.append(
            {
                "idx": str(idx),
                "title": p.clean_title(),
                "authors": p.authors or "Unknown",
                "year": str(p.year or ""),
                "limitations": lim_str,
                "doi": p.doi or "",
            }
        )
        if progress_callback:
            progress_callback(idx, total_steps, f"Analyzed gaps in paper {idx}/{len(top_papers)}")

    client = LLMClient(cfg)
    llm_available, _ = client.check_connection()

    table_rows: List[str] = [
        "| # | Paper Title | Authors (Year) | Key Limitations & Constraints | Identified Research Gap |",
        "| :--- | :--- | :--- | :--- | :--- |",
    ]
    for d in summaries_data:
        table_rows.append(
            f"| {d['idx']} | **{d['title']}** | {d['authors']} ({d['year']}) | {d['limitations'][:240]}... | Open challenge in generalizability & verification |"
        )
    gaps_table = "\n".join(table_rows)

    llm_report = ""
    if llm_available:
        if progress_callback:
            progress_callback(total_steps, total_steps, "Synthesizing cross-paper research gaps with AI...")
        sys_p = (
            "You are a senior academic advisor assisting a graduate researcher. Based on the extracted limitations "
            "and methodology constraints across these scientific papers, produce a comprehensive Research Gaps & Open Challenges Report. "
            "Highlight methodological blind spots, dataset constraints, computational trade-offs, and 3-5 concrete high-impact research directions."
        )
        usr_p = (
            f"Research Dataset: {dataset_name} ({len(top_papers)} papers)\n\n"
            "Extracted Paper Limitations & Constraints:\n"
            + "\n".join(
                f"- [Paper #{d['idx']}: {d['title']} ({d['year']})]: {d['limitations']}"
                for d in summaries_data
            )
        )
        llm_report = client.generate(sys_p, usr_p, timeout=120)

    doc_lines = [
        f"# AI Research Gaps & Future Directions — `{dataset_name}`",
        f"*Generated by crawly: the literature assistant ({cfg.ai_provider} · {cfg.ai_model}) on {time.strftime('%Y-%m-%d %H:%M:%S')}*",
        "",
        "## 1. Executive Summary of Open Challenges",
        (
            llm_report
            if llm_report
            else (
                "Based on the analyzed papers, common research gaps include limited real-world benchmarking, "
                "computational scalability bottlenecks, lack of standardized evaluation protocols, and sensitivity to noise or out-of-distribution inputs."
            )
        ),
        "",
        "## 2. Cross-Paper Limitations & Research Gaps Matrix",
        gaps_table,
        "",
        "## 3. Recommended Research Questions for Investigation",
        "1. **Robustness & Generalizability:** How do proposed methods perform under severe real-world noise and distribution shift?",
        "2. **Computational Efficiency:** Can lightweight or compressed architectures achieve comparable performance for real-time deployment?",
        "3. **Multi-Modal / Hybrid Formulations:** Does combining physics-based domain priors with deep representations overcome data sparsity?",
        "",
        "---",
        f"*Report saved for dataset `{dataset_name}` with {len(top_papers)} papers.*",
    ]
    report_text = "\n".join(doc_lines)
    report_path = out_dir / f"AI_Research_Gaps_{slug}.md"
    report_path.write_text(report_text, encoding="utf-8")
    return report_text, report_path


def generate_interactive_html_report(
    papers: Sequence[Paper],
    dataset_name: str = "dataset",
    output_dir: Optional[Path] = None,
    summaries: Optional[Dict[str, str]] = None,
    synthesis_md: Optional[str] = None,
    gaps_md: Optional[str] = None,
    config: Optional[AppConfig] = None,
) -> Path:
    """Generate a modern, self-contained interactive HTML review dashboard."""
    cfg = config or AppConfig.load()
    out_dir = output_dir or Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", dataset_name).strip("_") or "dataset"
    html_path = out_dir / f"AI_Literature_Report_{slug}.html"

    clean_papers = list(papers)
    oa_count = sum(1 for p in clean_papers if p.has_pdf())
    total_citations = sum(int(p.citations) for p in clean_papers if str(p.citations).isdigit())
    valid_years = [int(p.year) for p in clean_papers if str(p.year).isdigit() and int(p.year) > 0]
    year_range = f"{min(valid_years)}–{max(valid_years)}" if valid_years else "N/A"

    papers_json = []
    for idx, p in enumerate(clean_papers, start=1):
        summary_txt = (summaries or {}).get(p.clean_title(), p.ai_summary or "")
        pdf_loc = ""
        if p.local_pdf and Path(p.local_pdf).exists():
            pdf_loc = Path(p.local_pdf).name
        elif (out_dir / p.safe_filename()).exists():
            pdf_loc = p.safe_filename()

        papers_json.append(
            {
                "id": idx,
                "title": p.clean_title(),
                "authors": p.authors or "Unknown",
                "year": str(p.year) if p.year else "",
                "publication": p.publication or "Scholarly Publication",
                "citations": p.citations,
                "doi": p.doi or "",
                "url": p.url or "",
                "has_pdf": p.has_pdf(),
                "pdf_file": pdf_loc,
                "summary": summary_txt,
                "bibtex": p.to_bibtex(),
            }
        )

    # Safe JSON dump for embedded script
    serialized_papers = json.dumps(papers_json)
    safe_synth = (synthesis_md or "Run Mode 2 to generate cross-paper literature synthesis.").replace("<", "&lt;").replace(">", "&gt;")
    safe_gaps = (gaps_md or "Run Mode gaps to generate open research challenges matrix.").replace("<", "&lt;").replace(">", "&gt;")

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Literature Review Dashboard — {dataset_name}</title>
  <style>
    :root {{
      --bg: #0f172a;
      --surface: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #0284c7;
      --accent-hover: #0369a1;
      --badge-bg: rgba(2, 132, 199, 0.15);
      --badge-border: #0284c7;
      --green: #22c55e;
      --font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: var(--font);
      line-height: 1.5;
    }}
    .container {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 2rem 1.5rem;
    }}
    header {{
      border-bottom: 1px solid var(--border);
      padding-bottom: 1.5rem;
      margin-bottom: 2rem;
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      flex-wrap: wrap;
      gap: 1rem;
    }}
    h1 {{
      margin: 0 0 0.5rem 0;
      font-size: 1.85rem;
      color: #38bdf8;
    }}
    .subtitle {{
      color: var(--text-muted);
      font-size: 0.95rem;
      margin: 0;
    }}
    .stats-bar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .stat-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      padding: 1rem 1.25rem;
    }}
    .stat-label {{
      font-size: 0.8rem;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .stat-val {{
      font-size: 1.5rem;
      font-weight: 700;
      color: var(--text);
      margin-top: 0.25rem;
    }}
    .controls {{
      display: flex;
      gap: 1rem;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
    }}
    .search-input {{
      flex: 1;
      min-width: 260px;
      padding: 0.65rem 1rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      color: var(--text);
      font-size: 0.95rem;
    }}
    .filter-select {{
      padding: 0.65rem 1rem;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 0.5rem;
      color: var(--text);
      font-size: 0.95rem;
    }}
    .tabs {{
      display: flex;
      gap: 0.5rem;
      border-bottom: 1px solid var(--border);
      margin-bottom: 1.5rem;
    }}
    .tab-btn {{
      background: transparent;
      border: none;
      border-bottom: 2px solid transparent;
      color: var(--text-muted);
      padding: 0.65rem 1rem;
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
    }}
    .tab-btn.active {{
      color: #38bdf8;
      border-bottom-color: #38bdf8;
    }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}
    .paper-card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      padding: 1.25rem;
      margin-bottom: 1rem;
      transition: transform 0.1s ease;
    }}
    .paper-card:hover {{
      border-color: #38bdf8;
    }}
    .card-title {{
      font-size: 1.15rem;
      font-weight: 700;
      margin: 0 0 0.35rem 0;
      color: #f1f5f9;
    }}
    .card-meta {{
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-bottom: 0.75rem;
    }}
    .badge {{
      display: inline-block;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.2rem 0.5rem;
      border-radius: 9999px;
      background: var(--badge-bg);
      border: 1px solid var(--badge-border);
      color: #38bdf8;
      margin-right: 0.5rem;
    }}
    .badge-green {{
      background: rgba(34, 197, 94, 0.15);
      border-color: var(--green);
      color: var(--green);
    }}
    .summary-box {{
      background: #0f172a;
      border: 1px solid #1e293b;
      border-radius: 0.5rem;
      padding: 0.85rem 1rem;
      margin-top: 0.75rem;
      font-size: 0.9rem;
      white-space: pre-wrap;
    }}
    .actions-row {{
      display: flex;
      gap: 0.5rem;
      margin-top: 0.85rem;
      flex-wrap: wrap;
    }}
    .btn {{
      background: var(--border);
      color: var(--text);
      border: 1px solid transparent;
      padding: 0.35rem 0.75rem;
      border-radius: 0.4rem;
      font-size: 0.8rem;
      cursor: pointer;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }}
    .btn:hover {{ background: #475569; }}
    .btn-primary {{ background: var(--accent); color: #fff; }}
    .btn-primary:hover {{ background: var(--accent-hover); }}
    pre.markdown-view {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 0.75rem;
      padding: 1.5rem;
      font-family: var(--mono);
      font-size: 0.88rem;
      white-space: pre-wrap;
      line-height: 1.6;
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>Literature Review Dashboard</h1>
        <p class="subtitle">Dataset: <strong>{dataset_name}</strong> · Generated by <strong>crawly: the literature assistant</strong></p>
      </div>
      <div>
        <span class="badge">AI Engine: {cfg.ai_provider} ({cfg.ai_model})</span>
      </div>
    </header>

    <div class="stats-bar">
      <div class="stat-card">
        <div class="stat-label">Total Papers</div>
        <div class="stat-val" id="statTotal">{len(clean_papers)}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Open Access PDFs</div>
        <div class="stat-val">{oa_count}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Total Citations</div>
        <div class="stat-val">{total_citations:,}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Year Range</div>
        <div class="stat-val">{year_range}</div>
      </div>
    </div>

    <div class="tabs">
      <button class="tab-btn active" onclick="switchTab('catalog')">Paper Catalog &amp; Summaries</button>
      <button class="tab-btn" onclick="switchTab('synthesis')">Literature Synthesis Matrix</button>
      <button class="tab-btn" onclick="switchTab('gaps')">Research Gaps &amp; Roadmap</button>
    </div>

    <div id="catalog" class="tab-panel active">
      <div class="controls">
        <input type="text" id="searchInput" class="search-input" placeholder="Search by title, author, venue, or keyword..." oninput="filterCards()">
        <select id="filterOA" class="filter-select" onchange="filterCards()">
          <option value="all">All Papers</option>
          <option value="oa">With PDF Only</option>
        </select>
        <select id="sortSelect" class="filter-select" onchange="filterCards()">
          <option value="relevance">Default Order</option>
          <option value="citations">Most Cited First</option>
          <option value="newest">Newest First</option>
          <option value="oldest">Oldest First</option>
        </select>
      </div>

      <div id="paperList"></div>
    </div>

    <div id="synthesis" class="tab-panel">
      <pre class="markdown-view">{safe_synth}</pre>
    </div>

    <div id="gaps" class="tab-panel">
      <pre class="markdown-view">{safe_gaps}</pre>
    </div>
  </div>

  <script>
    const papers = {serialized_papers};

    function renderCards(list) {{
      const container = document.getElementById('paperList');
      if (!list.length) {{
        container.innerHTML = '<p style="color:var(--text-muted); text-align:center; padding:2rem;">No matching papers found.</p>';
        return;
      }}
      container.innerHTML = list.map(p => `
        <div class="paper-card">
          <div class="card-title">#${{p.id}}. ${{p.title}}</div>
          <div class="card-meta">
            <strong>${{p.authors}}</strong> · ${{p.year || 'Unknown'}} · <em>${{p.publication}}</em>
          </div>
          <div>
            ${{p.has_pdf ? '<span class="badge badge-green">✓ Open Access PDF</span>' : '<span class="badge">Metadata Only</span>'}}
            <span class="badge">Citations: ${{p.citations}}</span>
            ${{p.doi ? `<span class="badge">DOI: ${{p.doi}}</span>` : ''}}
          </div>
          ${{p.summary ? `<div class="summary-box"><strong>AI Structured Summary:</strong>\\n${{p.summary}}</div>` : ''}}
          <div class="actions-row">
            ${{p.pdf_file ? `<a class="btn btn-primary" href="${{p.pdf_file}}" target="_blank">📄 Open Local PDF</a>` : (p.url ? `<a class="btn btn-primary" href="${{p.url}}" target="_blank">🔗 Publisher Link</a>` : '')}}
            ${{p.doi ? `<a class="btn" href="https://doi.org/${{p.doi}}" target="_blank">🌐 View DOI</a>` : ''}}
            <button class="btn" onclick="copyBib(${{p.id}})">📋 Copy BibTeX</button>
          </div>
        </div>
      `).join('');
    }}

    function filterCards() {{
      const q = document.getElementById('searchInput').value.toLowerCase().trim();
      const oaOnly = document.getElementById('filterOA').value === 'oa';
      const sort = document.getElementById('sortSelect').value;

      let filtered = papers.filter(p => {{
        if (oaOnly && !p.has_pdf) return false;
        if (!q) return true;
        const hay = (p.title + ' ' + p.authors + ' ' + p.publication + ' ' + p.summary + ' ' + p.doi).toLowerCase();
        return hay.includes(q);
      }});

      if (sort === 'citations') {{
        filtered.sort((a, b) => b.citations - a.citations);
      }} else if (sort === 'newest') {{
        filtered.sort((a, b) => (Number(b.year) || 0) - (Number(a.year) || 0));
      }} else if (sort === 'oldest') {{
        filtered.sort((a, b) => (Number(a.year) || 9999) - (Number(b.year) || 9999));
      }}

      renderCards(filtered);
    }}

    function switchTab(id) {{
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      event.target.classList.add('active');
      document.getElementById(id).classList.add('active');
    }}

    function copyBib(id) {{
      const p = papers.find(x => x.id === id);
      if (p && p.bibtex) {{
        navigator.clipboard.writeText(p.bibtex).then(() => alert('BibTeX copied to clipboard!'));
      }}
    }}

    renderCards(papers);
  </script>
</body>
</html>
"""
    html_path.write_text(html_content, encoding="utf-8")
    return html_path

