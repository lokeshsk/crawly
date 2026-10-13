#!/usr/bin/env python
# coding: utf-8
"""Multi-Source Open Access PDF Downloader for crawly: the literature assistant (downloader.py).

Repository: https://github.com/lokeshsk/crawly

By default, downloads research papers strictly within the Legal Open Access framework:
- OpenAlex Open Access
- Unpaywall Legal OA API
- Semantic Scholar OpenAccessPdf & arXiv Preprints
- Europe PMC / PubMed Central Full-Text PDFs
- DOAJ, HAL Open Archive & Direct Publisher Open Access (MDPI, PIER, etc.)

Any optional third-party mirror fallback is disabled by default, carries an explicit
non-recommendation & non-liability legal warning, and requires the user to accept
sole legal responsibility before proceeding.
"""

import sys
import urllib.request

from rich.console import Console
from rich.prompt import Confirm

from crawly_core.cli import (
    interactive_ai_flow,
    interactive_download_flow,
    prompt_select_csv,
    render_header,
)
from crawly_core.models import AppConfig

console = Console()


def connect(host: str = "https://www.google.com/") -> bool:
    try:
        urllib.request.urlopen(host, timeout=5)
        return True
    except Exception:
        return False


def main() -> int:
    print("Checking whether internet is working or not...")
    if connect():
        print("internet connected")
    else:
        print("No internet! check your internet connection")
        return 1

    config = AppConfig.load()
    render_header(config)

    csv_path = prompt_select_csv(default_hint="papers")

    res_path = interactive_download_flow(
        config=config,
        preset_csv=csv_path,
    )
    if res_path and Confirm.ask(
        "\nWould you like to run AI Literature Review / Summarization on these papers now?",
        default=False,
    ):
        interactive_ai_flow(config, preset_csv=res_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
