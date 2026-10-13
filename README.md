# crawly: the literature assistant

[![GitHub Repository](https://img.shields.io/badge/GitHub-lokeshsk%2Fcrawly-blue?logo=github)](https://github.com/lokeshsk/crawly)
[![CI & 100% Coverage Gate](https://github.com/lokeshsk/crawly/actions/workflows/ci-tests-coverage.yml/badge.svg)](https://github.com/lokeshsk/crawly/actions/workflows/ci-tests-coverage.yml)
[![Coverage](https://img.shields.io/badge/Code%20Coverage-100%25-brightgreen)](tests/)
[![Website](https://img.shields.io/badge/Website-lokeshsk.github.io%2Fcrawly-0284c7)](https://lokeshsk.github.io/crawly/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

**crawly** (**crawly: the literature assistant**) is an end-to-end academic research assistant for discovering scientific papers across 8+ official Open Access databases, downloading full-text PDFs within a **strict Legal Open-Access framework by default**, exporting BibTeX citations, and generating AI-powered literature reviews using either **local self-hosted LLMs** (Ollama, LM Studio, vLLM, llama.cpp) or **commercial/OpenAI-compatible APIs** (OpenAI, Gemini, Anthropic, OpenRouter, Groq, DeepSeek).

- **Repository:** [https://github.com/lokeshsk/crawly](https://github.com/lokeshsk/crawly)
- **Documentation & Command Builder Website:** [https://lokeshsk.github.io/crawly/](https://lokeshsk.github.io/crawly/)
- **Maintainer:** Lokesh Kumar (`crawly.theliteratureassistant@gmail.com`)

> [!CAUTION]
> ### Legal Warning & Non-Liability Disclaimer
> 1. **Not Recommended by Developers:** The developers, authors, and contributors of **crawly** (`crawly: the literature assistant`) **do NOT recommend, endorse, or encourage** the use of Sci-Hub, shadow libraries, or automated scraping of websites that prohibit automated access or bypass copyright/paywall protections.
> 2. **Strict Legal Open-Access Default:** By default, **crawly** operates strictly within a legal framework using official Open Access APIs and repositories (**OpenAlex**, **Unpaywall**, **Semantic Scholar**, **arXiv**, **Europe PMC / PubMed Central**, **Crossref**, **DOAJ**, **HAL Open Archive**, and **OpenAIRE**).
> 3. **Use at Your Own Sole Risk & Zero Developer Liability:** Any feature that goes beyond official Open Access APIs (such as third-party mirror fallbacks or HTML scraping) is disabled by default (`"use_scihub_fallback": false` in [`config.json`](config.json)) and guarded by an explicit risk-acceptance prompt. If a user chooses to enable or continue with such external websites or tools, **they do so strictly at their own sole risk and legal responsibility**. The developers and contributors **shall NOT be held liable or responsible** for any copyright claims, Terms of Service violations, ISP blocks, legal consequences, or any other harm or damages arising from the user's actions.

---

## 1. Quick Start for Users (No `pip install` or Dependencies Required!)

Normal users do **not** need to install [`requirements.txt`](requirements.txt). Pre-bundled & compiled executables are available directly in the [`dist/`](dist/) folder with `pypdf`, `rich`, `requests`, `beautifulsoup4`, and [`config.json`](config.json) already bundled inside:

```bash
git clone https://github.com/lokeshsk/crawly.git
cd crawly
```

### Option A: Universal Cross-Platform Bundle (Works on BOTH Windows & Linux / WSL)
Unzip [`dist/crawly-universal-windows-linux.zip`](dist/crawly-universal-windows-linux.zip) (or run directly from [`dist/`](dist/)):
- **On Windows (Command Prompt / PowerShell / Double-Click):**
  ```cmd
  dist\crawly.bat
  ```
- **On Linux / WSL / macOS:**
  ```bash
  ./dist/crawly
  ```
- **Direct Single-File Archive (`crawly.pyz`):**
  ```bash
  python dist/crawly.pyz
  ```

### Option B: Native Standalone Binary (Zero Python Setup Needed)
- **Linux / WSL:**
  ```bash
  ./dist/crawly-linux-x86_64
  ```
- **Windows:**
  ```powershell
  .\dist\crawly-windows-x86_64.exe
  ```

---

## 2. Setting Up & Customizing [`config.json`](config.json)

All configuration values—including AI providers, model names, base URLs, API keys, temperature, PDF parsing limits, default search databases, timeouts, user-agents, and API endpoints—are stored in [**`config.json`**](config.json) in the project root (or current working directory).

Nothing is hardcoded: if `config.json` is deleted, **crawly** automatically regenerates it with clean default values and built-in `_documentation` labels.

### Three Ways to Change Settings in `config.json`

1. **Edit [`config.json`](config.json) directly** in any text editor (VS Code, Notepad, nano, vim).
2. **Interactive Terminal UI:** Launch `./dist/crawly` and choose **Option `5` (Configure AI Models & Settings)**.
3. **CLI Command:**
   ```bash
   # View current config.json status
   ./dist/crawly config --show

   # Update values in config.json via CLI flags
   ./dist/crawly config --provider ollama --model llama3.2 --temperature 0.2
   ./dist/crawly config --provider lmstudio --base-url http://localhost:1234/v1 --model local-model
   ./dist/crawly config --provider openai_compatible --base-url https://api.openai.com/v1 --api-key sk-... --model gpt-4o-mini
   ./dist/crawly config --provider gemini --api-key YOUR_GEMINI_KEY --model gemini-2.5-flash
   ./dist/crawly config --provider anthropic --api-key YOUR_ANTHROPIC_KEY --model claude-3-5-sonnet-latest
   ```

---

### Complete `config.json` Field Reference

| Variable Name | Default Value | What to Put / Allowed Values |
| :--- | :--- | :--- |
| **`ai_provider`** | `"ollama"` | Which AI engine to use:<br>• `"ollama"` — Local self-hosted Ollama server<br>• `"lmstudio"` — Local self-hosted LM Studio server<br>• `"openai_compatible"` — Any OpenAI-compatible server (OpenAI, OpenRouter, Groq, DeepSeek, Together, vLLM, llama.cpp)<br>• `"gemini"` — Google Gemini API<br>• `"anthropic"` — Anthropic Claude API<br>• `"extractive"` — Offline NLP & BM25 extractive engine (no LLM server or API key needed) |
| **`ai_model`** | `"llama3.2"` | Model identifier for your chosen provider:<br>• Ollama: `"llama3.2"`, `"qwen2.5:7b"`, `"mistral"`, `"deepseek-r1:8b"`<br>• LM Studio: `"local-model"` or the loaded GGUF model ID<br>• OpenAI / OpenRouter: `"gpt-4o-mini"`, `"deepseek-chat"`, `"meta-llama/llama-3.1-8b-instruct"`<br>• Gemini: `"gemini-2.5-flash"`, `"gemini-2.5-pro"`<br>• Anthropic: `"claude-3-5-sonnet-latest"` |
| **`ai_base_url`** | `"http://localhost:11434"` | Server base URL for local or OpenAI-compatible providers:<br>• Ollama: `"http://localhost:11434"`<br>• LM Studio: `"http://localhost:1234/v1"`<br>• vLLM / llama.cpp: `"http://localhost:8000/v1"`<br>• OpenAI: `"https://api.openai.com/v1"`<br>• OpenRouter: `"https://openrouter.ai/api/v1"`<br>• Groq: `"https://api.groq.com/openai/v1"` |
| **`ai_api_key`** | `""` | API key for commercial/cloud providers (`openai_compatible`, `gemini`, `anthropic`). Leave `""` for local Ollama or LM Studio. Can also be set via env vars (`CRAWLY_AI_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`). |
| **`temperature`** | `0.2` | Float between `0.0` and `1.0`. Lower values (`0.1`–`0.3`) produce more factual, deterministic literature summaries. |
| **`max_pdf_pages`** | `25` | Maximum number of PDF pages to extract per paper with `pypdf` for AI summarization and RAG indexing. |
| **`max_text_chars`** | `14000` | Maximum characters of extracted full-text PDF content passed to the LLM per paper. |
| **`default_sources`** | `["openalex", "semantic_scholar", "arxiv", "europe_pmc", "crossref", "doaj", "hal", "openaire"]` | List of open academic databases searched by default when `--sources` is not specified. |
| **`default_limit_per_source`** | `10` | Default maximum number of papers to fetch from each database per search query. |
| **`default_sort`** | `"relevance"` | Default sorting order for search results: `"relevance"`, `"desc"` (newest year first), `"asc"` (oldest year first), or `"citations"` (most cited first). |
| **`request_timeout`** | `12` | HTTP timeout in seconds for database queries and metadata resolution. |
| **`unpaywall_email`** | `"crawly.theliteratureassistant@gmail.com"` | Polite contact email sent to the Unpaywall Legal Open-Access API when resolving OA PDF links by DOI. |
| **`semantic_scholar_api_key`** | `""` | Optional Semantic Scholar API key for higher rate limits (leave `""` for public tier). |
| **`polite_user_agent`** | `"crawly/2.0 (crawly: the literature assistant; https://github.com/lokeshsk/crawly; mailto:crawly.theliteratureassistant@gmail.com)"` | User-Agent header used for polite academic API requests (OpenAlex, Crossref, Unpaywall, Europe PMC). |
| **`browser_user_agent`** | `"Mozilla/5.0 ..."` | Browser User-Agent header used when downloading PDFs from publisher repositories. |
| **`use_scihub_fallback`** | `false` | Keep `false` for strict Legal Open-Access compliance. Even if set to `true`, **crawly** displays the Legal Warning & Non-Liability Disclaimer requiring explicit risk acceptance. |
| **`scihub_cdn_url`** | `"https://sci.bban.top/pdf/{doi}.pdf"` | Template URL (`{doi}` placeholder) used only if the user explicitly accepts legal risk for third-party fallback. |
| **`scihub_mirrors`** | `["https://sci-hub.ee", ...]` | List of mirror URLs tried only if the user explicitly accepts legal risk for third-party fallback. |
| **`api_endpoints`** | `{...}` | Dictionary of base URLs for OpenAlex, Semantic Scholar, arXiv, Europe PMC, Crossref, DOAJ, HAL, OpenAIRE, Unpaywall, Gemini, and Anthropic. |

---

### Example `config.json` Setups for Popular AI Providers

#### A. Local Ollama (Default — Free & Private)
1. Install Ollama (`https://ollama.com`) and pull a model: `ollama pull llama3.2`
2. Set in `config.json`:
```json
{
  "ai_provider": "ollama",
  "ai_model": "llama3.2",
  "ai_base_url": "http://localhost:11434",
  "ai_api_key": "",
  "temperature": 0.2
}
```

#### B. Local LM Studio (Free & Private GUI Server)
1. Open LM Studio, load any GGUF model, and start the Local Server on port `1234`.
2. Set in `config.json`:
```json
{
  "ai_provider": "lmstudio",
  "ai_model": "local-model",
  "ai_base_url": "http://localhost:1234/v1",
  "ai_api_key": "",
  "temperature": 0.2
}
```

#### C. OpenAI / OpenRouter / Groq / DeepSeek (`openai_compatible`)
```json
{
  "ai_provider": "openai_compatible",
  "ai_model": "gpt-4o-mini",
  "ai_base_url": "https://api.openai.com/v1",
  "ai_api_key": "sk-proj-YOUR_API_KEY",
  "temperature": 0.2
}
```

#### D. Google Gemini API (`gemini`)
```json
{
  "ai_provider": "gemini",
  "ai_model": "gemini-2.5-flash",
  "ai_api_key": "AIzaSyYOUR_GEMINI_API_KEY",
  "temperature": 0.2
}
```

#### E. Offline Extractive Engine (`extractive` — No LLM or Internet Needed)
```json
{
  "ai_provider": "extractive",
  "ai_model": "extractive-bm25"
}
```

---

## 3. CLI Subcommands & Usage

All commands display modern multi-column progress bars (spinner, progress bar, percentage, `M/N` counter, elapsed time, and ETA) and work identically whether you invoke `./dist/crawly`, `dist\crawly.bat`, `./dist/crawly-linux-x86_64`, or `python crawly.py`:

```bash
# 1. Launch Interactive Terminal UI Dashboard
./dist/crawly

# 2. Search across all legal open databases (saves CSV + BibTeX)
./dist/crawly search "synthetic aperture radar" -o sar_papers.csv --limit 10

# 3. Download PDFs using strictly Legal Open Access repositories (Default)
./dist/crawly download sar_papers.csv

# 4. Run AI Literature Review Modes
#    Mode 1: Per-Paper Structured Summaries (Objective, Methodology, Key Findings, Limitations)
./dist/crawly ai sar_papers.csv --mode 1
#    Mode 2: Synthesized Cross-Paper Literature Review & Markdown Comparison Matrix
./dist/crawly ai sar_papers.csv --mode 2
#    Mode 3: Citation-Grounded RAG Q&A over Downloaded PDFs
./dist/crawly ai sar_papers.csv --mode 3 -q "What are the main compressed sensing methods for SAR?"

# 5. Run the complete end-to-end pipeline (Search -> Download Legal OA PDFs -> AI Review)
./dist/crawly pipeline "deep learning SAR despeckling" -o sar_dl --limit 8 --mode all

# 6. Export any CSV dataset to BibTeX (.bib) for Zotero / Mendeley / Overleaf
./dist/crawly export-bibtex sar_papers.csv

# 7. Run System & API Health Doctor
./dist/crawly doctor
```

---

## 4. For Contributors & Developers (100% Test & Coverage Quality Gate)

Every Pull Request submitted to **crawly: the literature assistant** is verified by the automated GitHub Actions quality gate ([`.github/workflows/ci-tests-coverage.yml`](.github/workflows/ci-tests-coverage.yml)).

> [!IMPORTANT]
> **Mandatory Pull Request Policy:** All unit tests in [`tests/`](tests/) must pass and total code coverage across `crawly.py`, `downloader.py`, and `crawly_core/*` must be **100%** (`fail_under = 100` in [`.coveragerc`](.coveragerc)). If any test case fails or code coverage drops below 100%, the CI workflow will block the PR and automatically comment on the PR asking the contributor to fix the failing tests or add missing test coverage before it comes to the maintainer for review and merging.

```bash
# 1. Install developer, test, and build dependencies
pip install -r requirements.txt coverage pytest pytest-cov pyinstaller

# 2. Run the full test suite and enforce 100% code coverage
python -m coverage run -m unittest discover -s tests -v
python -m coverage report -m --fail-under=100

# 3. Run from source
python crawly.py
python downloader.py

# 4. Rebuild dist/crawly.pyz, launchers, universal zip, and native binary
python build_release.py --native
```

### Contact & Credits
- **Author & Maintainer:** Lokesh Kumar (`crawly.theliteratureassistant@gmail.com`)
- **Credits:** Original v1 Google Scholar script inspired by `https://jovian.ai/saini-9`.

### Support / Donation
If you like **crawly: the literature assistant**, you can buy me a cup of tea :)

[![paypal](https://www.paypalobjects.com/en_US/i/btn/btn_donateCC_LG.gif)](https://paypal.me/lokeshsk755)
