# Planned Updates & Product Roadmap for `crawly`

This document details the planned features, user experience enhancements, and technical roadmap for upcoming releases of **crawly: the literature assistant**.

---

## 🗺️ Roadmap Overview

```
                      ┌──────────────────────────────────────┐
                      │    crawly v2.1.0 (Current Stable)    │
                      │  8 APIs · OA Waterfall · Snowball   │
                      │  Zotero · Watchdog · Gaps · HTML Rep │
                      └──────────────────┬───────────────────┘
                                         │
         ┌───────────────────────────────┼───────────────────────────────┐
         ▼                               ▼                               ▼
┌──────────────────┐           ┌──────────────────┐           ┌──────────────────┐
│   Milestone 1    │           │   Milestone 2    │           │   Milestone 3    │
│  Visual & UX     │           │ Systematic Review│           │ Writing & LaTeX  │
│  • Local Web UI  │           │  • PRISMA 2020   │           │ • Related Work   │
│  • 2D Graph Map  │           │  • Contradictions│           │ • Code Finder    │
│  • Mac Binaries  │           │  • Page-Level RAG│           │ • Ref Reconciler │
└──────────────────┘           └──────────────────┘           └──────────────────┘
```

---

## 🎨 Milestone 1: Visual & User-Friendly UX (The "Showstoppers")

### 1. Zero-Dependency Local Web GUI (`crawly ui` / `crawly serve`)
* **Problem Solved:** Many researchers (medical students, social scientists, humanities academics) find terminal CLIs intimidating and prefer a graphical browser experience.
* **Proposed Implementation:**
  * Single command `crawly ui` launches a modern, responsive web dashboard in the default browser (`http://localhost:8080`).
  * Built strictly using Python's standard library (`http.server` + JSON REST handlers) and embedded vanilla HTML/Tailwind CSS/JS—**zero npm/node/flask dependencies**.
  * Visual search bar with multi-database toggles, instant faceted filters, split-screen PDF preview, and chat sidebar.

### 2. Interactive 2D Citation Network Graph (`crawly graph` / Report View)
* **Problem Solved:** Tabular citation lists do not convey how research lineages, foundational paradigms, and recent offshoots evolve over time.
* **Proposed Implementation:**
  * Embedded D3.js / Vis.js force-directed network graph in the HTML dashboard (`crawly report`).
  * **Nodes:** Sized by citation count, colored by publication year or thematic cluster.
  * **Edges:** Directed arrows indicating citing and cited relationships.
  * Interactive physics simulation with node click-to-focus and cluster identification (seminal vs. recent frontier).

### 3. Native macOS Apple Silicon Executables (`crawly-macos-arm64`)
* **Problem Solved:** Provide zero-Python standalone binary downloads for Mac users alongside existing Linux and Windows releases.
* **Proposed Implementation:**
  * Add `macos-latest` runner to `.github/workflows/release-binaries.yml`.
  * Compile native Mach-O single-file executables for Apple Silicon ARM64 and Intel x86_64.

---

## 🔬 Milestone 2: Academic Research & Systematic Review Superpowers

### 4. PRISMA 2020 Flowchart Generator for Systematic Reviews (`crawly prisma`)
* **Problem Solved:** Systematic reviews and meta-analyses in medicine, public health, and engineering strictly mandate an official PRISMA flow diagram documenting screening numbers.
* **Proposed Implementation:**
  * Automated generation of official **PRISMA 2020 SVG / PNG / PDF diagrams**:
    `Records identified ➔ Duplicates removed ➔ Screened ➔ Excluded (with rationale) ➔ Included`.
  * Export structured screening log (`screening_log.csv`) tracking exact inclusion/exclusion rationale per paper.

### 5. Cross-Paper Consensus & Contradiction Radar
* **Problem Solved:** Synthesizing where literature agrees versus diverges currently takes days of manual note-taking.
* **Proposed Implementation:**
  * Multi-document comparative analysis identifying points of empirical consensus and methodological contradictions across downloaded papers.
  * Generates structured consensus matrices (e.g., 7/10 papers confirm hypothesis X under benchmark Y, while 3/10 report regression under condition Z).

### 6. Local Semantic Vector RAG with Page-Level Source Citations (`crawly ask`)
* **Problem Solved:** LLM summaries without exact quotes risk subtle hallucinations; researchers need verifiable source page citations.
* **Proposed Implementation:**
  * Lightweight in-memory semantic indexing (TF-IDF/BM25 + optional Ollama embeddings) over full-text PDFs.
  * Query answers provide exact verifiable page and paragraph anchors: `[Dosovitskiy et al., 2020, Page 6, ¶ 2]`.

---

## ✍️ Milestone 3: Academic Authoring & LaTeX Integrations

### 7. Automated "Related Work" LaTeX Section Generator (`crawly write`)
* **Problem Solved:** Drafting "Section 2: Related Work" or "Literature Review" is one of the most tedious stages of paper writing.
* **Proposed Implementation:**
  * Synthesizes the dataset into a publication-ready `related_work.tex` draft.
  * Organizes papers into thematic subsections (e.g., `\subsection{Foundational Methods}`, `\subsection{Efficiency Optimizations}`).
  * Formats citations using matching BibTeX keys (`\cite{vaswani2017attention}`) with cohesive narrative transitions.

### 8. Preprint-to-Peer-Reviewed Reconciler (`crawly upgrade-refs`)
* **Problem Solved:** Citing early arXiv preprints in camera-ready submissions when papers have since been published in top venues (NeurIPS, Nature, ICML) appears unvetted.
* **Proposed Implementation:**
  * Cross-checks DOIs and titles against Crossref and Semantic Scholar to discover formal journal/conference publications.
  * Automatically updates metadata, venue, volume/pages, and BibTeX entries to the authoritative peer-reviewed citation.

### 9. BibTeX Cleaner & Overleaf Reference Validator (`crawly bibtex --clean`)
* **Problem Solved:** Raw `.bib` files often have duplicates, irregular author names, and missing fields.
* **Proposed Implementation:**
  * Deduplicates `.bib` records by title and DOI.
  * Normalizes author name formats and venue abbreviations (ISO-4).
  * Automatically backfills missing volume/issue/page numbers from Crossref.

---

## 📦 Milestone 4: Code, Benchmark, and Knowledge Management

### 10. Automated Code & Dataset Extractor (`crawly code`)
* **Problem Solved:** Finding the actual code repository, dataset link, or model weights for a paper requires manual searches.
* **Proposed Implementation:**
  * Scans full-text PDFs for GitHub, Hugging Face, Zenodo, and Papers With Code links.
  * Adds direct repo links, star counts, and license badges to CSV datasets and HTML review dashboards.

### 11. Automated Benchmark Leaderboard Extractor (`crawly benchmarks`)
* **Problem Solved:** Compiling benchmark tables across 20+ papers into a unified comparison table is labor-intensive.
* **Proposed Implementation:**
  * Extracts benchmark metric tables (Dataset, Metric, Value, Baseline) directly from PDF text.
  * Compiles a sortable SOTA leaderboard matrix comparing all surveyed architectures on identical datasets.

### 12. Obsidian & Notion Academic Vault Exporter (`crawly export --to obsidian`)
* **Problem Solved:** Thousands of researchers manage literature notes in PKM tools like Obsidian and Notion.
* **Proposed Implementation:**
  * Generates an interlinked Markdown vault: each paper gets its own note with YAML frontmatter (authors, year, DOI, tags).
  * Auto-generates wikilinks between cited works (`[[Attention Is All You Need]]`), instantly populating Obsidian's interactive graph view.

### 13. Anki Flashcards Exporter for Qualifying Exams (`crawly export --to anki`)
* **Problem Solved:** PhD students and researchers need to memorize key papers, architectures, and benchmarks for qualifying exams.
* **Proposed Implementation:**
  * Exports `.apkg` or `.tsv` decks:
    * **Front:** Paper title + core research question.
    * **Back:** Primary contribution, methodology, datasets used, benchmark metrics, and main limitation.

---

## 🏛️ Milestone 5: Institutional Access & Lab Collaboration

### 14. University Library EZProxy / OpenAthens Integration (Legal Non-OA Access)
* **Problem Solved:** Researchers at universities often have legitimate institutional access to paywalled publishers (IEEE, Springer, Elsevier) that open-access APIs cannot download.
* **Proposed Implementation:**
  * Configure university proxy prefix in `config.json` (e.g., `https://doi-org.ezproxy.university.edu/...`).
  * Routes requests through the researcher's authenticated institutional session to download subscribed papers legally.

### 15. "Reviewer #2" Pre-Submission Paper Critique (`crawly critique my_draft.pdf`)
* **Problem Solved:** Authors get rejected when missing standard baselines or making unsubstantiated comparative claims.
* **Proposed Implementation:**
  * Analyzes a user's draft manuscript against the wider literature graph.
  * Flags missing baselines: *"You compared against ResNet and ViT, but missed ConvNeXt (2022) which is standard in this domain."*
  * Alerts on potential overclaims or contradicted benchmark assertions.

### 16. Lab Collaboration Webhooks (Slack, Discord, Telegram)
* **Problem Solved:** Research labs and reading groups need automated discovery digests delivered to shared chat channels.
* **Proposed Implementation:**
  * Extends `crawly watch` with webhook triggers.
  * Posts scheduled digests with paper titles, 2-line AI summaries, and PDF download links directly to Slack, Discord, or Telegram.

---

## 📊 Feature Value Matrix

| Priority | Feature | Effort | Target Audience |
| :--- | :--- | :--- | :--- |
| **P1** | Zero-Dependency Local Web UI (`crawly ui`) | Medium | All researchers, medical/humanities scholars |
| **P1** | Interactive 2D Citation Network Graph | Medium | Visual researchers, survey authors |
| **P1** | Native macOS Apple Silicon Binary | Low | Mac users |
| **P2** | PRISMA 2020 Systematic Review Generator | Low–Medium | Medical, public health & empirical reviewers |
| **P2** | Related Work LaTeX Generator (`crawly write`) | Medium | Paper & thesis writers |
| **P2** | Code & Dataset Extractor (`crawly code`) | Low | ML/AI researchers & engineers |
| **P3** | Obsidian & Notion Vault Exporter | Low | PKM power users, graduate students |
| **P3** | Cross-Paper Consensus/Contradiction Radar | Medium | Systematic literature reviewers |
| **P3** | University EZProxy Integration | Medium | University students & faculty |
| **P3** | Preprint-to-Peer-Reviewed Reconciler | Low | Camera-ready authors |
