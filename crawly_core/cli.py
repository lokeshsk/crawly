"""Unified Rich CLI & Modern Terminal UI (TUI) for Crawly Literature Review Suite."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from rich import box
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .ai_engine import (
    LLMClient,
    PaperRAGIndex,
    discover_local_models,
    generate_interactive_html_report,
    run_mode_1_per_paper_summaries,
    run_mode_2_literature_review_synthesis,
    run_mode_gaps_synthesis,
)
from .downloader import download_batch_pdfs, sync_dataset_to_zotero
from .models import (
    DEFAULT_API_ENDPOINTS,
    AppConfig,
    Paper,
    export_papers_to_bibtex,
    load_papers_from_csv,
    resolve_config_path,
    save_papers_to_csv,
)
from .sources import ALL_OPEN_SOURCES, SOURCE_LABELS, fetch_citation_snowball, search_multi_source

console = Console()


def create_modern_progress() -> Progress:
    """Create a sleek, multi-column Rich progress bar with spinner, bar, %, count, elapsed, and ETA."""
    return Progress(
        SpinnerColumn("dots", style="bold cyan"),
        TextColumn("[bold cyan]{task.description}[/bold cyan]"),
        BarColumn(bar_width=32, style="dim", complete_style="cyan", finished_style="bold green"),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )


LEGAL_DISCLAIMER_BANNER = (
    "[bold red]⚠ LEGAL WARNING & NON-LIABILITY DISCLAIMER[/bold red]\n\n"
    "1. [bold yellow]Not Recommended by Developers:[/bold yellow] The developers and contributors of crawly (crawly: the literature assistant) "
    "[bold]do NOT recommend, endorse, or encourage[/bold] the use of Sci-Hub, shadow libraries, or automated "
    "scraping of websites that prohibit automated access or bypass copyright/paywall protections.\n"
    "2. [bold green]Legal Open-Access Default:[/bold green] crawly is designed to operate within a legal framework "
    "using official Open Access APIs (OpenAlex, Unpaywall, Semantic Scholar, arXiv, Europe PMC, Crossref, DOAJ, HAL, OpenAIRE).\n"
    "3. [bold red]Assumption of Risk & Zero Developer Liability:[/bold red] Accessing third-party mirrors (such as Sci-Hub) "
    "or scraping restricted websites may violate copyright laws, publisher agreements, or Terms of Service in your country/jurisdiction. "
    "If you choose to proceed, [bold]you do so strictly at your own sole risk and responsibility[/bold]. "
    "The developers, authors, and maintainers of this software [bold]shall NOT be held liable or responsible[/bold] "
    "for any legal actions, copyright infringement claims, ISP blocks, data loss, or any other harm or damages "
    "caused by or arising from your use of these optional features."
)


def prompt_third_party_risk_acceptance(
    feature_label: str,
    auto_accept_flag: bool = False,
) -> bool:
    """Display legal warning banner and require explicit user risk acceptance before proceeding."""
    console.print()
    console.print(
        Panel(
            f"{LEGAL_DISCLAIMER_BANNER}\n\n"
            f"[bold white]Requested Action Beyond Standard Open-Access Framework:[/bold white] [yellow]{feature_label}[/yellow]",
            title="[bold red]⚠ USER RISK ACCEPTANCE REQUIRED[/bold red]",
            border_style="red",
            box=box.DOUBLE,
        )
    )
    if auto_accept_flag:
        console.print(
            "[bold yellow]⚠ Proceeding because '--accept-risk' flag was explicitly provided by the user. "
            "User assumes all legal responsibility.[/bold yellow]\n"
        )
        return True

    if not sys.stdin.isatty():
        console.print(
            "[bold red]✗ Non-interactive session detected without '--accept-risk'. "
            "Staying strictly within Legal Open Access sources.[/bold red]\n"
        )
        return False

    accepted = Confirm.ask(
        "[bold yellow]Do you confirm that you understand these legal risks, absolve the developers of all liability, "
        "and wish to continue at your own sole risk?[/bold yellow]",
        default=False,
    )
    if not accepted:
        console.print(
            "[bold green]✓ Declined third-party risk. Continuing strictly within the Legal Open Access framework.[/bold green]\n"
        )
    return accepted


def list_workspace_csvs(cwd: Path = Path(".")) -> List[Path]:
    csvs = []
    for p in sorted(cwd.glob("*.csv")):
        if p.name != "papers_not_found.csv" and not p.name.endswith("_summaries.csv"):
            csvs.append(p)
    return csvs


def render_header(config: AppConfig) -> None:
    client = LLMClient(config)
    ok, status_msg = client.check_connection()
    status_color = "green" if ok else "yellow"
    compliance_badge = (
        "[bold green]● Strict Legal Open-Access Mode (Default)[/bold green]"
        if not config.use_scihub_fallback
        else "[bold yellow]● Third-Party Fallback Enabled (User Accepted Risk)[/bold yellow]"
    )
    cfg_path = resolve_config_path()
    sub = (
        "[bold cyan]crawly: the literature assistant[/bold cyan] — [bold white]Multi-Source Academic Search, "
        "Open-Access PDF Downloader & AI Literature Review[/bold white]\n"
        f"[dim]Open Databases:[/dim]  OpenAlex · Unpaywall · Semantic Scholar · arXiv · Europe PMC · Crossref · DOAJ · HAL · OpenAIRE\n"
        f"[dim]Compliance Mode:[/dim] {compliance_badge}\n"
        f"[dim]AI Engine:[/dim]       [{status_color}]{status_msg}[/{status_color}] "
        f"[dim](temp={config.temperature}, max_pages={config.max_pdf_pages})[/dim]\n"
        f"[dim]Config File:[/dim]     [cyan]{cfg_path.name}[/cyan] [dim]({cfg_path})[/dim]"
    )
    console.print(Panel(sub, box=box.ROUNDED, border_style="cyan", padding=(0, 2)))


def render_papers_table(papers: Sequence[Paper], title: str = "Discovered Papers", max_rows: int = 25) -> None:
    table = Table(title=title, box=box.ROUNDED, header_style="bold cyan", show_lines=False)
    table.add_column("#", style="dim", width=4)
    table.add_column("Title", style="bold white", ratio=3)
    table.add_column("Year", style="cyan", width=6)
    table.add_column("Authors", style="green", ratio=2)
    table.add_column("Venue / Source", style="magenta", ratio=2)
    table.add_column("Cited", justify="right", width=6)
    table.add_column("DOI / OA", style="yellow", width=12)

    for idx, p in enumerate(papers[:max_rows], start=1):
        oa_badge = "[bold green]✓ PDF[/bold green]" if (p.pdf_url or p.local_pdf) else ("[cyan]DOI[/cyan]" if p.doi else "-")
        table.add_row(
            str(idx),
            p.clean_title()[:85],
            str(p.year or "-"),
            (p.authors or "Unknown")[:32],
            f"{(p.publication or '')[:22]} ({p.source})",
            str(p.citations or 0),
            oa_badge,
        )
    console.print(table)
    if len(papers) > max_rows:
        console.print(f"[dim]... and {len(papers) - max_rows} more papers saved to CSV.[/dim]")


def prompt_select_csv(default_hint: str = "test_1-2") -> Path:
    csvs = list_workspace_csvs()
    if csvs:
        console.print("\n[bold cyan]Available Paper Datasets (.csv):[/bold cyan]")
        for i, c in enumerate(csvs, start=1):
            console.print(f"  [bold cyan]{i}.[/bold cyan] {c.name}")
        default_val = csvs[0].stem
    else:
        default_val = default_hint

    raw = Prompt.ask(
        "\nEnter CSV number or file name (with or without .csv)",
        default=default_val,
    ).strip()
    if raw.isdigit() and csvs and 1 <= int(raw) <= len(csvs):
        return csvs[int(raw) - 1]
    if not raw.lower().endswith(".csv"):
        raw += ".csv"
    return Path(raw)


def interactive_search_flow(config: AppConfig) -> Optional[Path]:
    console.print("\n[bold cyan]━━━ 1. Search & Discover Research Papers ━━━[/bold cyan]")
    query = Prompt.ask("Enter research keywords / topic").strip()
    if not query:
        console.print("[red]Search query cannot be empty.[/red]")
        return None

    console.print("\n[bold]Select Search Databases:[/bold]")
    console.print(
        "  [bold cyan]1.[/bold cyan] Configured Default Open APIs [green](Recommended)[/green] "
        f"({', '.join(config.default_sources or ALL_OPEN_SOURCES)})"
    )
    console.print("  [bold cyan]2.[/bold cyan] Fast Core STEM & CS Open APIs (OpenAlex, Semantic Scholar, arXiv, Crossref)")
    console.print("  [bold cyan]3.[/bold cyan] Biomedical & Life Sciences Open APIs (Europe PMC, OpenAlex, Semantic Scholar, Crossref)")
    console.print("  [bold cyan]4.[/bold cyan] All Open APIs + Google Scholar Scraper [yellow](⚠ Web scraping — requires risk acceptance)[/yellow]")
    console.print("  [bold cyan]5.[/bold cyan] Google Scholar Scraper Only [yellow](⚠ Legacy web scraping — requires risk acceptance)[/yellow]")

    src_choice = Prompt.ask("Choose source preset", choices=["1", "2", "3", "4", "5"], default="1")
    scholar_pages = (1, 1)
    if src_choice == "1":
        sources = list(config.default_sources or ALL_OPEN_SOURCES)
    elif src_choice == "2":
        sources = ["openalex", "semantic_scholar", "arxiv", "crossref"]
    elif src_choice == "3":
        sources = ["europe_pmc", "openalex", "semantic_scholar", "crossref"]
    elif src_choice in ("4", "5"):
        accepted = prompt_third_party_risk_acceptance(
            "Automated HTML scraping of Google Scholar (may violate Google Terms of Service or trigger IP rate limits)"
        )
        if not accepted:
            sources = list(config.default_sources or ALL_OPEN_SOURCES)
        else:
            page_str = Prompt.ask("Enter Google Scholar page range (e.g. 1-2)", default="1-2").strip()
            if "-" in page_str:
                pparts = page_str.split("-", 1)
                scholar_pages = (max(int(pparts[0]), 1), max(int(pparts[1]), 1))
            sources = (list(ALL_OPEN_SOURCES) + ["google_scholar"]) if src_choice == "4" else ["google_scholar"]
    else:
        sources = list(config.default_sources or ALL_OPEN_SOURCES)

    limit_per_source = int(
        Prompt.ask("Max papers to fetch per source", default=str(config.default_limit_per_source))
    )
    sort_by = Prompt.ask(
        "Sort results by",
        choices=["relevance", "desc", "asc", "citations"],
        default=config.default_sort or "relevance",
    )
    default_slug = "_".join(query.lower().split()[:3]) or "papers"
    out_name = Prompt.ask("Output CSV file name (without .csv)", default=default_slug).strip()
    if out_name.lower().endswith(".csv"):
        out_name = out_name[:-4]

    with create_modern_progress() as progress:
        task = progress.add_task(f"Searching {len(sources)} academic databases", total=len(sources))

        def _on_src(label: str, count: int) -> None:
            progress.console.print(f"  [green]✓[/green] {label}: found [bold]{count}[/bold] papers")
            progress.advance(task)

        papers = search_multi_source(
            query=query,
            sources=sources,
            limit_per_source=limit_per_source,
            scholar_pages=scholar_pages,
            sort_by=sort_by,
            config=config,
            progress_callback=_on_src,
        )

    if not papers:
        console.print("[yellow]No papers found for that query. Try broader keywords.[/yellow]")
        return None

    csv_path = save_papers_to_csv(papers, f"{out_name}.csv")
    bib_path = export_papers_to_bibtex(papers, f"{out_name}.bib")
    render_papers_table(papers, title=f"Search Results ({len(papers)} unique deduplicated papers)")
    console.print(f"\n[bold green]✓ Saved {len(papers)} papers to CSV:[/bold green] [underline]{csv_path}[/underline]")
    console.print(f"[bold green]✓ Saved BibTeX citations to:[/bold green] [underline]{bib_path}[/underline]")

    if Confirm.ask("\nWould you like to download full-text PDFs for these papers now?", default=True):
        interactive_download_flow(config, preset_csv=csv_path)
    return csv_path


def interactive_download_flow(
    config: AppConfig,
    preset_csv: Optional[Path] = None,
    custom_scihub_url: Optional[str] = None,
    force_ask_scihub: bool = False,
) -> Optional[Path]:
    console.print("\n[bold cyan]━━━ 2. Multi-Source Full-Text PDF Downloader ━━━[/bold cyan]")
    csv_path = preset_csv or prompt_select_csv()
    try:
        papers = load_papers_from_csv(csv_path)
    except Exception as exc:
        console.print(f"[red]Error loading CSV: {exc}[/red]")
        return None

    out_dir = Path(csv_path.stem)
    console.print(
        f"Loaded [bold]{len(papers)}[/bold] papers from [cyan]{csv_path.name}[/cyan]. "
        f"Output folder: [cyan]{out_dir}/[/cyan]"
    )

    console.print("\n[bold]Select PDF Download Compliance Mode:[/bold]")
    console.print(
        "  [bold cyan]1.[/bold cyan] [green]Legal Open Access Only (Recommended & Default)[/green]\n"
        "     [dim]Uses OpenAlex OA, Unpaywall, Semantic Scholar, arXiv preprints, Europe PMC, DOAJ, HAL, and Publisher OA.[/dim]"
    )
    console.print(
        "  [bold cyan]2.[/bold cyan] [yellow]Legal Open Access + Third-Party Mirror Fallback (Sci-Hub)[/yellow]\n"
        "     [dim]⚠ Not recommended by developers. Requires explicit legal risk acceptance; use strictly at your own risk.[/dim]"
    )

    default_dl_mode = "2" if (force_ask_scihub or custom_scihub_url or config.use_scihub_fallback) else "1"
    dl_mode = Prompt.ask("Choose download mode", choices=["1", "2"], default=default_dl_mode)

    session_cfg = AppConfig(**config.__dict__)
    if dl_mode == "2":
        accepted = prompt_third_party_risk_acceptance(
            "Third-Party Shadow Library / Sci-Hub Fallback for Paywalled Articles"
        )
        session_cfg.use_scihub_fallback = accepted
        if not accepted:
            custom_scihub_url = None
    else:
        session_cfg.use_scihub_fallback = False
        custom_scihub_url = None

    if session_cfg.use_scihub_fallback:
        console.print(
            "[dim]Waterfall order: Direct OA -> OpenAlex -> Unpaywall -> Semantic Scholar / arXiv -> Europe PMC -> Sci-Hub Fallback (User Accepted Risk)[/dim]\n"
        )
    else:
        console.print(
            "[dim]Waterfall order (Strict Legal OA): Direct OA -> OpenAlex -> Unpaywall -> Semantic Scholar / arXiv -> Europe PMC[/dim]\n"
        )

    with create_modern_progress() as progress:
        task = progress.add_task("Downloading & verifying PDFs", total=len(papers))

        def _on_paper(idx: int, total: int, paper: Paper, ok: bool, src: str) -> None:
            short_t = paper.clean_title()[:55]
            if ok:
                progress.console.print(
                    f"  [green]✓ [{idx}/{total}][/green] {short_t} [dim]({paper.doi or 'no-doi'})[/dim] -> [bold green]{src}[/bold green]"
                )
            else:
                progress.console.print(
                    f"  [red]✗ [{idx}/{total}][/red] {short_t} [dim]({paper.doi or 'no-doi'})[/dim] -> [yellow]Not Found in enabled sources[/yellow]"
                )
            progress.advance(task)

        stats = download_batch_pdfs(
            papers=papers,
            output_dir=out_dir,
            csv_path=csv_path,
            config=session_cfg,
            custom_scihub_url=custom_scihub_url,
            progress_callback=_on_paper,
        )

    summary_tbl = Table(title="PDF Download Summary", box=box.ROUNDED, header_style="bold cyan")
    summary_tbl.add_column("Metric / Source", style="cyan")
    summary_tbl.add_column("Count", justify="right", style="bold white")
    summary_tbl.add_row("Total Papers", str(stats["total"]))
    summary_tbl.add_row("Successfully Downloaded PDFs", f"[green]{stats['downloaded']}[/green]")
    summary_tbl.add_row("Missing (saved to papers_not_found.csv)", f"[yellow]{stats['missing']}[/yellow]")
    for k, v in stats.items():
        if k not in ("total", "downloaded", "missing"):
            summary_tbl.add_row(f"  ↳ via {k}", str(v))
    console.print("\n", summary_tbl)
    console.print(f"[bold green]✓ PDFs saved in:[/bold green] [underline]{out_dir.resolve()}[/underline]")
    return csv_path


def interactive_ai_flow(config: AppConfig, preset_csv: Optional[Path] = None, preset_mode: Optional[str] = None) -> None:
    console.print("\n[bold cyan]━━━ 3. AI Literature Review & Research Assistant ━━━[/bold cyan]")
    csv_path = preset_csv or prompt_select_csv()
    try:
        papers = load_papers_from_csv(csv_path)
    except Exception as exc:
        console.print(f"[red]Error loading CSV: {exc}[/red]")
        return

    dataset_name = csv_path.stem
    out_dir = Path(dataset_name)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not preset_mode:
        console.print("\n[bold]Select AI Literature Review Mode:[/bold]")
        console.print("  [bold cyan]1.[/bold cyan] [cyan]Mode 1: Structured Per-Paper Summaries[/cyan] (Objective, Methodology, Key Findings, Limitations for each paper)")
        console.print("  [bold cyan]2.[/bold cyan] [cyan]Mode 2: Synthesized Literature Review & Comparison Matrix[/cyan] (Cross-paper synthesis, themes & Markdown comparison table)")
        console.print("  [bold cyan]3.[/bold cyan] [cyan]Mode 3: Interactive Chat / Q&A with Papers[/cyan] (Ask questions across downloaded PDFs with page citations)")
        console.print("  [bold cyan]4.[/bold cyan] [green]Run Mode 1 + Mode 2 Together[/green]")
        mode = Prompt.ask("Choose mode", choices=["1", "2", "3", "4"], default="1")
    else:
        mode = preset_mode

    if mode in ("1", "4"):
        with create_modern_progress() as progress:
            task = progress.add_task("Mode 1: Summarizing papers", total=len(papers))

            def _on_sum(idx: int, total: int, paper: Paper, basis: str) -> None:
                progress.console.print(
                    f"  [green]✓ [{idx}/{total}][/green] Summarized [bold]{paper.clean_title()[:52]}[/bold] [dim]({basis})[/dim]"
                )
                progress.advance(task)

            report_path = run_mode_1_per_paper_summaries(
                papers=papers,
                output_dir=out_dir,
                dataset_name=dataset_name,
                config=config,
                progress_callback=_on_sum,
            )

        console.print(f"\n[bold green]✓ Per-paper summaries saved to:[/bold green] [underline]{report_path}[/underline]")
        console.print(f"[bold green]✓ Enriched CSV saved to:[/bold green] [underline]{out_dir / (dataset_name + '_summaries.csv')}[/underline]\n")
        for p in papers[:3]:
            console.print(
                Panel(
                    Markdown(p.summary or "No summary generated."),
                    title=f"[bold]{p.clean_title()} ({p.year})[/bold]",
                    border_style="green",
                )
            )

    if mode in ("2", "4"):
        total_m2 = min(len(papers), 30) + 1
        with create_modern_progress() as progress:
            task_m2 = progress.add_task("Mode 2: Synthesizing literature review", total=total_m2)

            def _on_m2(step_idx: int, total_steps: int, msg: str) -> None:
                progress.advance(task_m2)

            synthesis_md, rev_path = run_mode_2_literature_review_synthesis(
                papers=papers,
                output_dir=out_dir,
                dataset_name=dataset_name,
                config=config,
                progress_callback=_on_m2,
            )
        console.print(Panel(Markdown(synthesis_md), title="Synthesized Literature Review", border_style="cyan"))
        console.print(f"\n[bold green]✓ Literature Review saved to:[/bold green] [underline]{rev_path}[/underline]")

    if mode == "3":
        with create_modern_progress() as progress:
            task_idx = progress.add_task("Mode 3: Indexing local PDFs & abstracts", total=len(papers))

            def _on_idx(idx: int, total: int, paper: Paper) -> None:
                progress.advance(task_idx)

            rag = PaperRAGIndex(papers=papers, output_dir=out_dir, config=config, progress_callback=_on_idx)
        console.print(
            f"[green]✓ Indexed [bold]{len(rag.chunks)}[/bold] passages across [bold]{len(papers)}[/bold] papers.[/green]"
        )
        console.print("[dim]Type your research question below (or type 'exit' / 'q' to return to menu).[/dim]\n")
        while True:
            q = Prompt.ask("[bold yellow]Ask your papers[/bold yellow]").strip()
            if not q or q.lower() in ("exit", "quit", "q"):
                break
            with console.status("[cyan]Retrieving passages & generating cited answer...[/cyan]"):
                ans = rag.answer_question(q, config=config)
            console.print(Panel(Markdown(ans), title=f"Answer: {q}", border_style="yellow"))


def interactive_config_flow(config: AppConfig) -> AppConfig:
    cfg_path = resolve_config_path()
    console.print(f"\n[bold cyan]━━━ 5. Configure AI Provider & Settings ({cfg_path.name}) ━━━[/bold cyan]")
    console.print(f"[dim]All settings are persisted to [bold]{cfg_path}[/bold] (you can also edit config.json directly in any text editor).[/dim]\n")
    console.print("  [bold cyan]1.[/bold cyan] [cyan]Ollama (Local Self-Hosted)[/cyan] — e.g. http://localhost:11434")
    console.print("  [bold cyan]2.[/bold cyan] [cyan]LM Studio (Local Self-Hosted Server)[/cyan] — e.g. http://localhost:1234/v1")
    console.print("  [bold cyan]3.[/bold cyan] [cyan]Any OpenAI-Compatible Endpoint[/cyan] (Custom Base URL + API Key: vLLM, llama.cpp, OpenRouter, Groq, DeepSeek, OpenAI)")
    console.print("  [bold cyan]4.[/bold cyan] [cyan]Google Gemini API[/cyan]")
    console.print("  [bold cyan]5.[/bold cyan] [cyan]Anthropic Claude API[/cyan]")
    console.print("  [bold cyan]6.[/bold cyan] [cyan]Offline Extractive NLP Engine[/cyan] (Zero-dependency local extractive summaries & BM25 Q&A)")

    choice = Prompt.ask("Select AI backend", choices=["1", "2", "3", "4", "5", "6"], default="1")
    if choice == "1":
        config.ai_provider = "ollama"
        config.ai_base_url = Prompt.ask("Ollama Base URL", default=config.ai_base_url or "http://localhost:11434").strip()
        models = discover_local_models("ollama", config.ai_base_url)
        if models:
            console.print(f"[green]Detected local Ollama models:[/green] {', '.join(models)}")
            config.ai_model = Prompt.ask("Model name", default=models[0]).strip()
        else:
            config.ai_model = Prompt.ask("Ollama model name", default=config.ai_model or "llama3.2").strip()
    elif choice == "2":
        config.ai_provider = "lmstudio"
        config.ai_base_url = Prompt.ask("LM Studio Base URL", default="http://localhost:1234/v1").strip()
        models = discover_local_models("lmstudio", config.ai_base_url)
        if models:
            console.print(f"[green]Detected LM Studio models:[/green] {', '.join(models)}")
            config.ai_model = Prompt.ask("Model ID", default=models[0]).strip()
        else:
            config.ai_model = Prompt.ask("LM Studio Model ID", default="local-model").strip()
    elif choice == "3":
        config.ai_provider = "openai_compatible"
        config.ai_base_url = Prompt.ask(
            "OpenAI-Compatible Base URL (e.g. https://api.openai.com/v1, https://openrouter.ai/api/v1, http://localhost:8000/v1)",
            default=config.ai_base_url if "http" in config.ai_base_url else "https://api.openai.com/v1",
        ).strip()
        config.ai_api_key = Prompt.ask("API Key (leave blank if local server)", default=config.ai_api_key, password=True).strip()
        config.ai_model = Prompt.ask(
            "Model name (e.g. gpt-4o-mini, deepseek-chat, meta-llama/llama-3.1-8b-instruct)",
            default=config.ai_model or "gpt-4o-mini",
        ).strip()
    elif choice == "4":
        config.ai_provider = "gemini"
        config.ai_api_key = Prompt.ask("Google Gemini API Key", default=config.ai_api_key, password=True).strip()
        config.ai_model = Prompt.ask("Gemini Model", default="gemini-2.5-flash").strip()
    elif choice == "5":
        config.ai_provider = "anthropic"
        config.ai_api_key = Prompt.ask("Anthropic API Key", default=config.ai_api_key, password=True).strip()
        config.ai_model = Prompt.ask("Claude Model", default="claude-3-5-sonnet-latest").strip()
    else:
        config.ai_provider = "extractive"
        config.ai_model = "extractive-bm25"

    config.temperature = float(Prompt.ask("LLM sampling temperature (0.0 - 1.0)", default=str(config.temperature)))
    config.max_pdf_pages = int(Prompt.ask("Max PDF pages to extract per paper", default=str(config.max_pdf_pages)))
    config.default_limit_per_source = int(
        Prompt.ask("Default max results per search database", default=str(config.default_limit_per_source))
    )
    config.unpaywall_email = Prompt.ask("Email for Unpaywall Legal Open-Access API", default=config.unpaywall_email).strip()
    saved_to = config.save()
    console.print(f"[bold green]✓ Configuration saved to:[/bold green] [underline]{saved_to}[/underline]")
    return config


def run_doctor_diagnostics(config: AppConfig) -> None:
    import requests

    console.print("\n[bold cyan]━━━ crawly: System & API Health Doctor ━━━[/bold cyan]")
    tbl = Table(title="Connectivity & Service Diagnostics", box=box.ROUNDED, header_style="bold cyan")
    tbl.add_column("Component / API", style="bold white")
    tbl.add_column("Status", width=14)
    tbl.add_column("Endpoint / Details", style="dim")

    ep_map = config.api_endpoints or DEFAULT_API_ENDPOINTS
    endpoints = [
        ("OpenAlex API", f"{ep_map.get('openalex_works', DEFAULT_API_ENDPOINTS['openalex_works'])}?per-page=1"),
        ("Semantic Scholar API", f"{ep_map.get('semantic_scholar_search', DEFAULT_API_ENDPOINTS['semantic_scholar_search'])}?query=radar&limit=1"),
        ("arXiv API", f"{ep_map.get('arxiv_query', DEFAULT_API_ENDPOINTS['arxiv_query'])}?search_query=all:radar&max_results=1"),
        ("Europe PMC API", f"{ep_map.get('europe_pmc_search', DEFAULT_API_ENDPOINTS['europe_pmc_search'])}?query=radar&format=json&pageSize=1"),
        ("Crossref API", f"{ep_map.get('crossref_works', DEFAULT_API_ENDPOINTS['crossref_works'])}?rows=1"),
        ("DOAJ API", f"{ep_map.get('doaj_search', DEFAULT_API_ENDPOINTS['doaj_search']).rstrip('/')}/radar?pageSize=1"),
        ("HAL Open Archive API", f"{ep_map.get('hal_search', DEFAULT_API_ENDPOINTS['hal_search'])}?q=radar&rows=1&wt=json"),
        ("OpenAIRE API", f"{ep_map.get('openaire_search', DEFAULT_API_ENDPOINTS['openaire_search'])}?keywords=radar&size=1&format=json"),
    ]

    with create_modern_progress() as progress:
        task = progress.add_task("Probing academic APIs & AI backend", total=len(endpoints) + 1)
        for name, url in endpoints:
            try:
                r = requests.get(url, headers={"User-Agent": config.polite_user_agent}, timeout=6)
                ok = r.status_code == 200
                tbl.add_row(name, "[green]✓ ONLINE[/green]" if ok else f"[yellow]HTTP {r.status_code}[/yellow]", url[:62])
            except Exception as e:
                tbl.add_row(name, "[red]✗ OFFLINE[/red]", str(e)[:62])
            progress.advance(task)

        client = LLMClient(config)
        ai_ok, ai_msg = client.check_connection()
        tbl.add_row(
            f"AI Provider ({config.ai_provider})",
            "[green]✓ READY[/green]" if ai_ok else "[yellow]FALLBACK[/yellow]",
            ai_msg,
        )
        progress.advance(task)

    console.print(tbl)


def run_snowball_flow(doi_or_query: str, config: Optional[AppConfig] = None, output: str = "", limit: int = 10) -> Path:
    cfg = config or AppConfig.load()
    console.print(f"\n[bold cyan]━━━ Citation Snowballing: Tracing Network for '{doi_or_query}' ━━━[/bold cyan]")
    with create_modern_progress() as progress:
        task = progress.add_task("Tracing Citation Graph (OpenAlex & Semantic Scholar)", total=3)
        seed, back, fwd = fetch_citation_snowball(
            doi_or_query,
            max_backward=limit,
            max_forward=limit,
            config=cfg,
            progress_callback=lambda stage, count: progress.advance(task),
        )

    if not seed and not back and not fwd:
        console.print(f"[bold red]✗ Could not locate citation network for '{doi_or_query}'.[/bold red]")
        return Path(".")

    if seed:
        console.print(
            Panel(
                f"[bold cyan]{seed.clean_title()}[/bold cyan]\n"
                f"Authors: {seed.authors} ({seed.year}) · Venue: {seed.publication}\n"
                f"DOI: {seed.doi or 'N/A'} · Citations: {seed.citations}",
                title="Anchor Seed Paper",
                border_style="cyan",
            )
        )

    tbl = Table(title="Connected Literature Tree", box=box.ROUNDED, header_style="bold cyan")
    tbl.add_column("Type", width=16)
    tbl.add_column("Title", style="bold white", ratio=3)
    tbl.add_column("Year", width=6)
    tbl.add_column("Authors", style="green", ratio=2)
    tbl.add_column("DOI", style="dim", width=14)

    for p in back:
        tbl.add_row("[yellow]Backward (Ref)[/yellow]", p.clean_title()[:65], str(p.year or ""), p.authors[:25], p.doi or "")
    for p in fwd:
        tbl.add_row("[green]Forward (Cites)[/green]", p.clean_title()[:65], str(p.year or ""), p.authors[:25], p.doi or "")
    console.print(tbl)

    all_snow = ([seed] if seed else []) + back + fwd
    clean_q = re.sub(r"[^a-zA-Z0-9]+", "_", doi_or_query).strip("_")
    slug = output or ("_".join(clean_q.split()[:3]) + "_snowball.csv")
    out_csv = Path(slug if slug.endswith(".csv") else f"{slug}.csv")
    save_papers_to_csv(all_snow, out_csv)
    export_papers_to_bibtex(all_snow, f"{out_csv.stem}.bib")
    console.print(f"[bold green]✓ Saved {len(all_snow)} connected papers to:[/bold green] [underline]{out_csv}[/underline]")
    return out_csv


def run_report_flow(csv_path: Path, output: str = "", config: Optional[AppConfig] = None) -> Path:
    cfg = config or AppConfig.load()
    papers = load_papers_from_csv(csv_path)
    if not papers:
        console.print(f"[bold red]✗ No papers found in {csv_path}.[/bold red]")
        return Path(".")

    out_dir = csv_path.parent
    ds_name = csv_path.stem
    with create_modern_progress() as progress:
        task = progress.add_task(f"Generating Interactive HTML Dashboard for '{ds_name}'", total=1)
        html_p = generate_interactive_html_report(
            papers=papers,
            dataset_name=ds_name,
            output_dir=out_dir,
            config=cfg,
        )
        progress.advance(task)

    console.print(f"[bold green]✓ Interactive HTML Review Dashboard generated:[/bold green] [underline]{html_p}[/underline]")
    return html_p


def run_zotero_flow(csv_path: Path, collection_name: str = "", config: Optional[AppConfig] = None) -> Path:
    cfg = config or AppConfig.load()
    papers = load_papers_from_csv(csv_path)
    if not papers:
        console.print(f"[bold red]✗ No papers found in {csv_path}.[/bold red]")
        return Path(".")

    col_name = collection_name or csv_path.stem
    is_live, status_msg, bib_p = sync_dataset_to_zotero(papers, collection_name=col_name, output_dir=csv_path.parent, config=cfg)
    if is_live:
        console.print(f"[bold green]✓ {status_msg}[/bold green]")
    else:
        console.print(f"[bold yellow]ℹ {status_msg}[/bold yellow]")
    return bib_p


def run_watchdog_flow(
    query: str,
    days: int = 7,
    limit: int = 10,
    download_pdfs: bool = True,
    summarize: bool = True,
    config: Optional[AppConfig] = None,
) -> Path:
    import datetime
    cfg = config or AppConfig.load()
    console.print(f"\n[bold cyan]━━━ Literature Watchdog: Scanning recent works for '{query}' (past {days} days) ━━━[/bold cyan]")
    cutoff_date = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()

    with create_modern_progress() as progress:
        task = progress.add_task(f"Searching OpenAlex & arXiv for recent preprints/papers since {cutoff_date}", total=2)
        papers = search_multi_source(
            query=f"{query}",
            sources=["openalex", "arxiv", "europe_pmc"],
            limit_per_source=limit,
            sort_mode="desc",
            config=cfg,
            progress_callback=lambda s, c: progress.advance(task),
        )

    if not papers:
        console.print(f"[yellow]No new papers discovered in the past {days} days for '{query}'.[/yellow]")
        return Path(".")

    clean_slug = re.sub(r"[^a-zA-Z0-9]+", "_", query).strip("_")
    slug = f"Watchdog_{clean_slug}_{datetime.date.today().isoformat()}"
    out_dir = Path.cwd() / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_p = out_dir / f"{slug}.csv"
    save_papers_to_csv(papers, csv_p)
    export_papers_to_bibtex(papers, out_dir / f"{slug}.bib")

    if download_pdfs:
        with create_modern_progress() as progress:
            dl_task = progress.add_task("Downloading new Open-Access PDFs", total=len(papers))
            download_batch_pdfs(
                papers,
                output_dir=out_dir,
                config=cfg,
                progress_callback=lambda i, t, p, ok, s: progress.advance(dl_task),
            )

    digest_lines = [
        f"# 🐕 Literature Watchdog Digest — `{query}`",
        f"*Period: {cutoff_date} to {datetime.date.today().isoformat()} · {len(papers)} works discovered*",
        "",
        "## Newly Discovered Works",
    ]
    for idx, p in enumerate(papers, start=1):
        digest_lines.append(
            f"### {idx}. {p.clean_title()} ({p.year})\n"
            f"- **Authors:** {p.authors}\n"
            f"- **Venue:** {p.publication or 'Preprint'}\n"
            f"- **DOI:** `{p.doi or 'N/A'}` | [Link]({p.url})\n"
            f"- **Abstract Snippet:** {p.abstract[:280]}...\n"
        )
    digest_p = out_dir / f"{slug}_Digest.md"
    digest_p.write_text("\n".join(digest_lines), encoding="utf-8")
    generate_interactive_html_report(papers, dataset_name=slug, output_dir=out_dir, config=cfg)

    console.print(f"[bold green]✓ Watchdog digest saved to:[/bold green] [underline]{digest_p}[/underline]")
    return digest_p


def run_interactive_tui() -> None:
    config = AppConfig.load()
    while True:
        console.print()
        render_header(config)
        console.print("[bold]Main Menu:[/bold]")
        console.print("  [bold cyan]1.[/bold cyan] Search & Discover Papers [dim](OpenAlex, Semantic Scholar, arXiv, Europe PMC, Crossref, DOAJ, HAL, OpenAIRE)[/dim]")
        console.print("  [bold cyan]2.[/bold cyan] Download Full-Text PDFs [dim](Legal Open Access Default + Optional Risk-Gated Third-Party Fallback)[/dim]")
        console.print("  [bold cyan]3.[/bold cyan] AI Literature Review & Q&A [dim](Mode 1: Summaries · Mode 2: Matrix · Mode 3: RAG Q&A · Mode gaps: Open Gaps)[/dim]")
        console.print("  [bold cyan]4.[/bold cyan] Run End-to-End Automated Pipeline [dim](Search ➔ Download PDFs ➔ AI Literature Review)[/dim]")
        console.print("  [bold cyan]5.[/bold cyan] Configure AI Models & Settings [dim](Updates config.json: Ollama, LM Studio, OpenAI API, Gemini, Claude)[/dim]")
        console.print("  [bold cyan]6.[/bold cyan] Export Dataset to BibTeX (.bib) [dim](For Zotero, Mendeley, EndNote & Overleaf/LaTeX)[/dim]")
        console.print("  [bold cyan]7.[/bold cyan] Run System & API Health Doctor")
        console.print("  [bold cyan]8.[/bold cyan] Citation Graph Snowballing [dim](Trace forward & backward citations around an anchor paper)[/dim]")
        console.print("  [bold cyan]9.[/bold cyan] Export Interactive HTML Review Dashboard [dim](Single-file dashboard with search & cards)[/dim]")
        console.print("  [bold cyan]10.[/bold cyan] Sync Dataset to Local Zotero [dim](Direct local HTTP connector or importable bundle with PDFs)[/dim]")
        console.print("  [bold cyan]11.[/bold cyan] Literature Watchdog [dim](Scan recent preprints & papers for alerts/digest)[/dim]")
        console.print("  [bold cyan]0.[/bold cyan] Exit")

        choice = Prompt.ask("\nSelect an option", choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "0", "q"], default="1")
        if choice in ("0", "q"):
            console.print("[bold cyan]Goodbye! Happy researching![/bold cyan]")
            break
        elif choice == "1":
            interactive_search_flow(config)
        elif choice == "2":
            interactive_download_flow(config)
        elif choice == "3":
            interactive_ai_flow(config)
        elif choice == "4":
            csv_p = interactive_search_flow(config)
            if csv_p:
                interactive_ai_flow(config, preset_csv=csv_p)
        elif choice == "5":
            config = interactive_config_flow(config)
        elif choice == "6":
            csv_p = prompt_select_csv()
            papers = load_papers_from_csv(csv_p)
            bib_p = export_papers_to_bibtex(papers, f"{csv_p.stem}.bib")
            console.print(f"[bold green]✓ Exported {len(papers)} BibTeX citations to:[/bold green] [underline]{bib_p}[/underline]")
        elif choice == "7":
            run_doctor_diagnostics(config)
        elif choice == "8":
            target = Prompt.ask("Enter seed DOI or paper title to trace").strip()
            if target:
                run_snowball_flow(target, config=config)
        elif choice == "9":
            csv_p = prompt_select_csv()
            run_report_flow(csv_p, config=config)
        elif choice == "10":
            csv_p = prompt_select_csv()
            run_zotero_flow(csv_p, config=config)
        elif choice == "11":
            query = Prompt.ask("Enter research topic / keywords for Watchdog scan").strip()
            if query:
                run_watchdog_flow(query, days=7, config=config)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="crawly",
        description="crawly: the literature assistant — Unified Multi-Source Academic Search, Legal Open-Access PDF Downloader & AI Literature Review CLI",
    )
    sub = parser.add_subparsers(dest="command")

    # search subcommand
    p_search = sub.add_parser("search", help="Search across open academic databases and save CSV + BibTeX")
    p_search.add_argument("query", help="Search keywords / research topic")
    p_search.add_argument("-o", "--output", default="", help="Output CSV filename")
    p_search.add_argument("-l", "--limit", type=int, default=0, help="Max results per source (defaults to config.json)")
    p_search.add_argument(
        "-s",
        "--sources",
        default="default",
        help="Comma-separated sources (openalex,semantic_scholar,arxiv,europe_pmc,crossref,doaj,hal,openaire,google_scholar) or 'all'",
    )
    p_search.add_argument("--sort", default="", choices=["", "relevance", "asc", "desc", "citations"])
    p_search.add_argument("--min-year", type=int, default=0, help="Filter papers published on or after this year")
    p_search.add_argument("--max-year", type=int, default=0, help="Filter papers published on or before this year")
    p_search.add_argument(
        "--accept-risk",
        action="store_true",
        help="Explicitly accept sole legal responsibility if using non-API web scraping (e.g. google_scholar)",
    )

    # download subcommand
    p_dl = sub.add_parser("download", help="Download PDFs for papers in a CSV file (Legal Open Access by default)")
    p_dl.add_argument("csv", help="Path to CSV file (e.g. test_1-2.csv)")
    p_dl.add_argument("-o", "--output-dir", default="", help="Output directory for PDFs (defaults to CSV stem)")
    p_dl.add_argument(
        "--enable-scihub",
        action="store_true",
        help="Enable optional third-party Sci-Hub fallback (NOT recommended by developers; requires risk acceptance)",
    )
    p_dl.add_argument("--scihub-url", default="", help="Optional custom Sci-Hub mirror URL (implies --enable-scihub)")
    p_dl.add_argument(
        "--accept-risk",
        action="store_true",
        help="Confirm you accept all legal risks and absolve developers of liability when enabling third-party mirrors",
    )

    # ai subcommand
    p_ai = sub.add_parser("ai", help="Run AI Literature Review (Mode 1, Mode 2, Mode 3, or gaps) on a dataset")
    p_ai.add_argument("csv", help="Path to CSV file (e.g. test_1-2.csv)")
    p_ai.add_argument(
        "-m",
        "--mode",
        choices=["1", "2", "3", "gaps", "all"],
        default="1",
        help="1 = Per-Paper Summaries, 2 = Synthesis Matrix, 3 = Q&A over PDFs, gaps = Open Challenges Matrix, all = 1+2+gaps",
    )
    p_ai.add_argument("-q", "--question", default="", help="Question for Mode 3 (non-interactive one-shot Q&A)")
    p_ai.add_argument("--provider", default="", help="Override AI provider (ollama, lmstudio, openai_compatible, gemini, anthropic, extractive)")
    p_ai.add_argument("--model", default="", help="Override AI model name")
    p_ai.add_argument("--base-url", default="", help="Override AI base URL")
    p_ai.add_argument("--api-key", default="", help="Override AI API key")

    # pipeline subcommand
    p_pipe = sub.add_parser("pipeline", help="End-to-end Search -> Download PDFs (Legal OA by default) -> AI Literature Review")
    p_pipe.add_argument("query", help="Search keywords / research topic")
    p_pipe.add_argument("-o", "--output", default="", help="Dataset name / CSV stem")
    p_pipe.add_argument("-l", "--limit", type=int, default=0, help="Max results per source (defaults to config.json)")
    p_pipe.add_argument("-m", "--mode", choices=["1", "2", "gaps", "all"], default="all", help="AI review mode to run")
    p_pipe.add_argument(
        "--enable-scihub",
        action="store_true",
        help="Enable third-party Sci-Hub fallback (requires risk acceptance)",
    )
    p_pipe.add_argument(
        "--accept-risk",
        action="store_true",
        help="Confirm you accept all legal risks and absolve developers of liability",
    )

    # snowball subcommand
    p_snow = sub.add_parser("snowball", help="Trace forward and backward citation network around an anchor paper")
    p_snow.add_argument("target", help="DOI or paper title string to trace")
    p_snow.add_argument("-o", "--output", default="", help="Output CSV filename")
    p_snow.add_argument("-l", "--limit", type=int, default=10, help="Max citations to fetch per direction (default 10)")

    # report subcommand
    p_rep = sub.add_parser("report", help="Generate an interactive single-file HTML review dashboard for a CSV dataset")
    p_rep.add_argument("csv", help="Path to CSV dataset")
    p_rep.add_argument("-o", "--output", default="", help="Output HTML filename")

    # zotero subcommand
    p_zot = sub.add_parser("zotero", help="Sync dataset papers and local PDFs to Zotero desktop")
    p_zot.add_argument("csv", help="Path to CSV dataset")
    p_zot.add_argument("-c", "--collection-name", default="", help="Zotero collection name")

    # watch subcommand
    p_wat = sub.add_parser("watch", help="Literature Watchdog: scan recent preprints/papers and generate alerts digest")
    p_wat.add_argument("query", help="Keywords / research topic")
    p_wat.add_argument("-d", "--days", type=int, default=7, help="Number of past days to scan (default 7)")
    p_wat.add_argument("-l", "--limit", type=int, default=10, help="Max papers to fetch")
    p_wat.add_argument("--no-download", action="store_true", help="Skip downloading PDFs")

    # export-bibtex subcommand
    p_bib = sub.add_parser("export-bibtex", help="Export a CSV paper dataset to BibTeX (.bib) for Zotero/Mendeley/LaTeX")
    p_bib.add_argument("csv", help="Path to CSV file (e.g. test_1-2.csv)")
    p_bib.add_argument("-o", "--output", default="", help="Output .bib filename")

    # doctor subcommand
    sub.add_parser("doctor", help="Check connectivity to all Open Access APIs and configured AI providers")

    # config subcommand
    p_cfg = sub.add_parser("config", help="View or update settings in config.json via CLI flags")
    p_cfg.add_argument("--provider", choices=["ollama", "lmstudio", "openai_compatible", "gemini", "anthropic", "extractive"])
    p_cfg.add_argument("--model", help="Model identifier (e.g. llama3.2, gpt-4o-mini, gemini-2.5-flash)")
    p_cfg.add_argument("--base-url", help="Base URL for Ollama, LM Studio, or OpenAI-compatible server")
    p_cfg.add_argument("--api-key", help="API key for commercial or custom endpoints")
    p_cfg.add_argument("--temperature", type=float, help="LLM sampling temperature (e.g. 0.2)")
    p_cfg.add_argument("--max-pdf-pages", type=int, help="Max PDF pages to extract per paper (e.g. 25)")
    p_cfg.add_argument("--limit", type=int, help="Default max papers per search source (e.g. 10)")
    p_cfg.add_argument("--show", action="store_true", help="Display current config.json values")

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    config = AppConfig.load()

    if not args.command:
        run_interactive_tui()
        return 0

    if args.command == "doctor":
        render_header(config)
        run_doctor_diagnostics(config)
        return 0

    if args.command == "export-bibtex":
        csv_p = Path(args.csv if args.csv.endswith(".csv") else f"{args.csv}.csv")
        papers = load_papers_from_csv(csv_p)
        out_bib = args.output or f"{csv_p.stem}.bib"
        bib_p = export_papers_to_bibtex(papers, out_bib)
        console.print(f"[bold green]✓ Exported {len(papers)} BibTeX entries to:[/bold green] {bib_p}")
        return 0

    if args.command == "config":
        changed = False
        if args.provider:
            config.ai_provider = args.provider
            changed = True
        if args.model:
            config.ai_model = args.model
            changed = True
        if args.base_url:
            config.ai_base_url = args.base_url
            changed = True
        if args.api_key is not None:
            config.ai_api_key = args.api_key
            changed = True
        if args.temperature is not None:
            config.temperature = args.temperature
            changed = True
        if args.max_pdf_pages is not None:
            config.max_pdf_pages = args.max_pdf_pages
            changed = True
        if args.limit is not None:
            config.default_limit_per_source = args.limit
            changed = True

        saved_path = config.save()
        if changed:
            console.print(
                f"[bold green]✓ Updated {saved_path}:[/bold green] "
                f"provider=[cyan]{config.ai_provider}[/cyan], model=[cyan]{config.ai_model}[/cyan], "
                f"base_url=[cyan]{config.ai_base_url}[/cyan], temperature=[cyan]{config.temperature}[/cyan]"
            )
        else:
            render_header(config)
            console.print(f"[bold cyan]Active configuration file:[/bold cyan] [underline]{saved_path}[/underline]")
        return 0

    if args.command == "snowball":
        render_header(config)
        run_snowball_flow(args.target, config=config, output=args.output, limit=args.limit)
        return 0

    if args.command == "report":
        csv_p = Path(args.csv if args.csv.endswith(".csv") else f"{args.csv}.csv")
        run_report_flow(csv_p, output=args.output, config=config)
        return 0

    if args.command == "zotero":
        csv_p = Path(args.csv if args.csv.endswith(".csv") else f"{args.csv}.csv")
        run_zotero_flow(csv_p, collection_name=args.collection_name, config=config)
        return 0

    if args.command == "watch":
        render_header(config)
        run_watchdog_flow(
            args.query,
            days=args.days,
            limit=args.limit,
            download_pdfs=not args.no_download,
            config=config,
        )
        return 0

    if args.command == "search":
        if args.sources in ("all", "default"):
            srcs = list(ALL_OPEN_SOURCES) if args.sources == "all" else list(config.default_sources or ALL_OPEN_SOURCES)
        else:
            srcs = [s.strip() for s in args.sources.split(",") if s.strip()]

        if "google_scholar" in [s.lower() for s in srcs]:
            if not prompt_third_party_risk_acceptance(
                "Automated HTML scraping of Google Scholar",
                auto_accept_flag=args.accept_risk,
            ):
                srcs = [s for s in srcs if s.lower() != "google_scholar"]
                if not srcs:
                    srcs = list(config.default_sources or ALL_OPEN_SOURCES)
        out_csv = args.output or ("_".join(args.query.lower().split()[:3]) + ".csv")
        if not out_csv.lower().endswith(".csv"):
            out_csv += ".csv"
        render_header(config)

        limit_val = args.limit if args.limit > 0 else config.default_limit_per_source
        sort_val = args.sort if args.sort else config.default_sort

        with create_modern_progress() as progress:
            task = progress.add_task(f"Searching {len(srcs)} academic databases", total=len(srcs))

            def _on_search_src(lbl: str, cnt: int) -> None:
                progress.console.print(f"  [green]✓[/green] {lbl}: [bold]{cnt}[/bold] papers")
                progress.advance(task)

            papers = search_multi_source(
                query=args.query,
                sources=srcs,
                limit_per_source=limit_val,
                sort_by=sort_val,
                config=config,
                progress_callback=_on_search_src,
            )

        if args.min_year:
            papers = [p for p in papers if p.year >= args.min_year]
        if args.max_year:
            papers = [p for p in papers if 0 < p.year <= args.max_year]
        save_papers_to_csv(papers, out_csv)
        bib_p = export_papers_to_bibtex(papers, Path(out_csv).with_suffix(".bib"))
        render_papers_table(papers, title=f"Search Results for '{args.query}' ({len(papers)} unique papers)")
        console.print(f"[bold green]✓ Saved CSV to {out_csv} and BibTeX to {bib_p}[/bold green]")
        return 0

    if args.command == "download":
        session_cfg = AppConfig(**config.__dict__)
        wants_scihub = bool(args.enable_scihub or args.scihub_url or config.use_scihub_fallback)
        if wants_scihub:
            accepted = prompt_third_party_risk_acceptance(
                "Third-Party Shadow Library / Sci-Hub Fallback for Paywalled Articles",
                auto_accept_flag=args.accept_risk,
            )
            session_cfg.use_scihub_fallback = accepted
        else:
            session_cfg.use_scihub_fallback = False

        render_header(session_cfg)
        csv_p = Path(args.csv if args.csv.endswith(".csv") else f"{args.csv}.csv")
        papers = load_papers_from_csv(csv_p)
        out_dir = Path(args.output_dir) if args.output_dir else Path(csv_p.stem)

        with create_modern_progress() as progress:
            task = progress.add_task(f"Downloading PDFs for {csv_p.name}", total=len(papers))

            def _on_dl(i: int, t: int, p: Paper, ok: bool, s: str) -> None:
                progress.console.print(
                    f"  [{'green' if ok else 'red'}]{'✓' if ok else '✗'} [{i}/{t}][/{'green' if ok else 'red'}] "
                    f"{p.clean_title()[:58]} -> [bold]{s}[/bold]"
                )
                progress.advance(task)

            stats = download_batch_pdfs(
                papers=papers,
                output_dir=out_dir,
                csv_path=csv_p,
                config=session_cfg,
                custom_scihub_url=args.scihub_url if session_cfg.use_scihub_fallback else None,
                progress_callback=_on_dl,
            )

        bib_p = export_papers_to_bibtex(papers, out_dir / f"{csv_p.stem}.bib")
        console.print(
            f"\n[bold green]✓ Downloaded {stats['downloaded']}/{stats['total']} PDFs to {out_dir}/ (BibTeX: {bib_p})[/bold green]"
        )
        return 0

    if args.command == "ai":
        if args.provider:
            config.ai_provider = args.provider
        if args.model:
            config.ai_model = args.model
        if args.base_url:
            config.ai_base_url = args.base_url
        if args.api_key:
            config.ai_api_key = args.api_key

        render_header(config)
        csv_p = Path(args.csv if args.csv.endswith(".csv") else f"{args.csv}.csv")
        papers = load_papers_from_csv(csv_p)
        dataset_name = csv_p.stem
        out_dir = Path(dataset_name)

        if args.mode in ("1", "all"):
            with create_modern_progress() as progress:
                task = progress.add_task("Mode 1: Generating per-paper summaries", total=len(papers))

                def _on_ai1(i: int, t: int, p: Paper, b: str) -> None:
                    progress.console.print(
                        f"  [green]✓ [{i}/{t}][/green] Summarized: {p.clean_title()[:56]} [dim]({b})[/dim]"
                    )
                    progress.advance(task)

                rep = run_mode_1_per_paper_summaries(
                    papers=papers,
                    output_dir=out_dir,
                    dataset_name=dataset_name,
                    config=config,
                    progress_callback=_on_ai1,
                )
            console.print(f"[bold green]✓ Mode 1 Per-Paper Summaries saved to:[/bold green] {rep}")

        if args.mode in ("2", "all"):
            total_m2 = min(len(papers), 30) + 1
            with create_modern_progress() as progress:
                task_m2 = progress.add_task("Mode 2: Synthesizing literature review", total=total_m2)

                def _on_ai2(step_idx: int, total_steps: int, msg: str) -> None:
                    progress.advance(task_m2)

                syn, rev = run_mode_2_literature_review_synthesis(
                    papers=papers,
                    output_dir=out_dir,
                    dataset_name=dataset_name,
                    config=config,
                    progress_callback=_on_ai2,
                )
            console.print(Panel(Markdown(syn), title="Mode 2: Literature Review & Comparison Matrix", border_style="cyan"))
            console.print(f"[bold green]✓ Mode 2 Literature Review saved to:[/bold green] {rev}")

        if args.mode in ("gaps", "all"):
            total_gaps = min(len(papers), 30) + 1
            with create_modern_progress() as progress:
                task_gaps = progress.add_task("Mode gaps: Synthesizing research gaps & open challenges", total=total_gaps)
                gaps_txt, gaps_path = run_mode_gaps_synthesis(
                    papers=papers,
                    output_dir=out_dir,
                    dataset_name=dataset_name,
                    config=config,
                    progress_callback=lambda s, tot, m: progress.advance(task_gaps),
                )
            console.print(Panel(Markdown(gaps_txt), title="Identified Research Gaps & Future Directions", border_style="magenta"))
            console.print(f"[bold green]✓ Research Gaps Report saved to:[/bold green] {gaps_path}")

        if args.mode in ("1", "2", "gaps", "all"):
            html_rep = generate_interactive_html_report(papers=papers, dataset_name=dataset_name, output_dir=out_dir, config=config)
            console.print(f"[bold green]✓ Interactive HTML Review Dashboard generated:[/bold green] [underline]{html_rep}[/underline]")

        if args.mode == "3":
            if args.question:
                with create_modern_progress() as progress:
                    task_idx = progress.add_task("Mode 3: Indexing local PDFs & abstracts", total=len(papers))
                    rag = PaperRAGIndex(
                        papers=papers,
                        output_dir=out_dir,
                        config=config,
                        progress_callback=lambda i, t, p: progress.advance(task_idx),
                    )
                ans = rag.answer_question(args.question, config=config)
                console.print(Panel(Markdown(ans), title=f"Q: {args.question}", border_style="yellow"))
            else:
                interactive_ai_flow(config, preset_csv=csv_p, preset_mode="3")
        return 0

    if args.command == "pipeline":
        session_cfg = AppConfig(**config.__dict__)
        if args.enable_scihub or config.use_scihub_fallback:
            session_cfg.use_scihub_fallback = prompt_third_party_risk_acceptance(
                "Third-Party Shadow Library / Sci-Hub Fallback",
                auto_accept_flag=args.accept_risk,
            )
        else:
            session_cfg.use_scihub_fallback = False

        render_header(session_cfg)
        slug = args.output or "_".join(args.query.lower().split()[:3])
        if slug.endswith(".csv"):
            slug = slug[:-4]
        csv_p = Path(f"{slug}.csv")
        srcs = list(session_cfg.default_sources or ALL_OPEN_SOURCES)
        limit_val = args.limit if args.limit > 0 else session_cfg.default_limit_per_source

        console.print(f"[bold cyan]━━━ Step 1/3: Searching {len(srcs)} Open Databases for '{args.query}' ━━━[/bold cyan]")
        with create_modern_progress() as progress:
            t1 = progress.add_task("Step 1/3: Querying academic databases", total=len(srcs))

            def _on_p1(lbl: str, cnt: int) -> None:
                progress.console.print(f"  [green]✓[/green] {lbl}: [bold]{cnt}[/bold] papers")
                progress.advance(t1)

            papers = search_multi_source(
                query=args.query,
                sources=srcs,
                limit_per_source=limit_val,
                config=session_cfg,
                progress_callback=_on_p1,
            )

        save_papers_to_csv(papers, csv_p)
        out_dir = Path(slug)
        out_dir.mkdir(parents=True, exist_ok=True)
        export_papers_to_bibtex(papers, out_dir / f"{slug}.bib")

        console.print(f"\n[bold cyan]━━━ Step 2/3: Downloading Full-Text PDFs ({len(papers)} papers) ━━━[/bold cyan]")
        with create_modern_progress() as progress:
            t2 = progress.add_task("Step 2/3: Downloading & verifying PDFs", total=len(papers))

            def _on_p2(i: int, tot: int, p: Paper, ok: bool, s: str) -> None:
                progress.console.print(
                    f"  [{'green' if ok else 'red'}]{'✓' if ok else '✗'} [{i}/{tot}][/{'green' if ok else 'red'}] "
                    f"{p.clean_title()[:55]} -> [bold]{s}[/bold]"
                )
                progress.advance(t2)

            download_batch_pdfs(
                papers=papers,
                output_dir=out_dir,
                csv_path=csv_p,
                config=session_cfg,
                progress_callback=_on_p2,
            )

        console.print(f"\n[bold cyan]━━━ Step 3/3: Running AI Literature Review (mode={args.mode}) ━━━[/bold cyan]")
        if args.mode in ("1", "all"):
            with create_modern_progress() as progress:
                t3 = progress.add_task("Step 3a: Generating per-paper summaries", total=len(papers))
                rep = run_mode_1_per_paper_summaries(
                    papers,
                    out_dir,
                    slug,
                    config=session_cfg,
                    progress_callback=lambda i, tot, p, b: progress.advance(t3),
                )
            console.print(f"[bold green]✓ Summaries report:[/bold green] {rep}")
        if args.mode in ("2", "all"):
            total_m2 = min(len(papers), 30) + 1
            with create_modern_progress() as progress:
                t4 = progress.add_task("Step 3b: Synthesizing Literature Review Matrix", total=total_m2)
                _, rev = run_mode_2_literature_review_synthesis(
                    papers,
                    out_dir,
                    slug,
                    config=session_cfg,
                    progress_callback=lambda s_idx, tot, msg: progress.advance(t4),
                )
            console.print(f"[bold green]✓ Literature Review report:[/bold green] {rev}")
        if args.mode in ("gaps", "all"):
            total_gaps = min(len(papers), 30) + 1
            with create_modern_progress() as progress:
                t5 = progress.add_task("Step 3c: Synthesizing Research Gaps & Open Challenges", total=total_gaps)
                _, gaps_rep = run_mode_gaps_synthesis(
                    papers,
                    out_dir,
                    slug,
                    config=session_cfg,
                    progress_callback=lambda s_idx, tot, msg: progress.advance(t5),
                )
            console.print(f"[bold green]✓ Research Gaps report:[/bold green] {gaps_rep}")

        html_p = generate_interactive_html_report(papers, dataset_name=slug, output_dir=out_dir, config=session_cfg)
        console.print(f"[bold green]✓ Interactive HTML Review Dashboard:[/bold green] [underline]{html_p}[/underline]")
        return 0

    return 0
