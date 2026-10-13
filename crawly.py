#!/usr/bin/env python
# coding: utf-8
"""crawly: the literature assistant — Unified Academic Paper Discovery, Multi-Source PDF Downloader & AI Literature Review.

Repository: https://github.com/lokeshsk/crawly

Usage:
  Interactive Terminal UI (TUI):
      python crawly.py

  Direct CLI Subcommands:
      python crawly.py search "synthetic aperture radar" -o sar_papers.csv --limit 10
      python crawly.py download sar_papers.csv
      python crawly.py ai sar_papers.csv --mode 1
      python crawly.py ai sar_papers.csv --mode 2
      python crawly.py ai sar_papers.csv --mode 3 -q "What are the main compressed sensing methods for SAR?"
      python crawly.py pipeline "deep learning SAR despeckling" -o sar_dl --limit 8 --mode all
      python crawly.py config --provider ollama --model llama3.2
"""

import sys
from crawly_core.cli import main

if __name__ == "__main__":
    sys.exit(main())
