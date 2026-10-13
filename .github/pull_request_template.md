## Summary of Changes

<!-- Briefly describe what this Pull Request adds, fixes, or improves in crawly: the literature assistant -->

## Mandatory Contributor Quality Gate Checklist

> **Note:** Pull Requests will **not** be reviewed or merged by the maintainer unless the automated CI workflow passes all unit tests with **100% code coverage**. If any test fails or coverage is `< 100%`, please fix the issue before requesting a merge.

- [ ] I have run `python -m coverage run -m unittest discover -s tests -v` locally and verified that **all unit tests pass**.
- [ ] I have run `python -m coverage report -m --fail-under=100` locally and verified **100% code coverage** across all modules (`crawly.py`, `downloader.py`, `crawly_core/*`).
- [ ] Any new configuration parameters are documented in `config.json` and `README.md`.
- [ ] Legal Open-Access defaults and mandatory user risk-acceptance prompts for third-party opt-in modules remain intact.

