#!/usr/bin/env python3
"""Build script for Crawly standalone releases (for Contributors / Release Maintainers).

Produces in `dist/`:
1. `dist/crawly.pyz` — Self-contained Cross-Platform Executable Archive bundling `crawly_core`
   AND all third-party libraries (`pypdf`, `rich`, `requests`, `bs4`, `urllib3`, `certifi`, etc.)
   into a single ~2.5 MB file that works on BOTH Windows and Linux/WSL without `pip install`!
2. `dist/crawly.bat` (Windows launcher) & `dist/crawly` (Linux / WSL / macOS executable launcher).
3. `dist/crawly-universal-windows-linux.zip` — Ready-to-distribute zip for Windows & Linux users.
4. Optional native OS binary (`dist/crawly-linux-x86_64` or `dist/crawly-windows-x86_64.exe`) if PyInstaller is installed.
"""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
import zipapp
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

# Configure UTF-8 encoding on Windows to prevent UnicodeEncodeError in CI
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BUNDLED_PACKAGES = [
    "requests",
    "urllib3",
    "idna",
    "certifi",
    "charset_normalizer",
    "bs4",
    "soupsieve",
    "pypdf",
    "rich",
    "pygments",
    "markdown_it",
    "mdurl",
]


def _copy_package_into(pkg_name: str, target_dir: Path) -> None:
    spec = importlib.util.find_spec(pkg_name)
    if not spec or not spec.origin:
        print(f"  [!] Warning: package '{pkg_name}' not found in current build env")
        return
    origin = Path(spec.origin)
    if origin.name == "__init__.py":
        src_dir = origin.parent
        dst_dir = target_dir / pkg_name
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        shutil.copytree(
            src_dir,
            dst_dir,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", "*.so", "*.pyd"),
        )
    else:
        shutil.copy2(origin, target_dir / origin.name)


def build_universal_pyz() -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / "bundle"
        stage.mkdir(parents=True, exist_ok=True)

        # Copy crawly_core
        shutil.copytree(
            ROOT / "crawly_core",
            stage / "crawly_core",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )

        # Bundle all required third-party pure-Python libraries inside the archive
        print("Bundling dependencies (pypdf, rich, requests, bs4, etc.) into single portable archive...")
        for pkg in BUNDLED_PACKAGES:
            _copy_package_into(pkg, stage)

        # Write __main__.py entry point
        main_py = stage / "__main__.py"
        main_py.write_text(
            "import sys\nfrom crawly_core.cli import main\nif __name__ == '__main__':\n    sys.exit(main())\n",
            encoding="utf-8",
        )

        pyz_path = DIST / "crawly.pyz"
        zipapp.create_archive(
            stage,
            target=pyz_path,
            interpreter="/usr/bin/env python3",
            compressed=True,
        )
        pyz_path.chmod(pyz_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"✓ Built self-contained cross-platform bundle: {pyz_path} ({pyz_path.stat().st_size / (1024*1024):.2f} MB)")

    # Create Linux / WSL / macOS launcher script
    sh_launcher = DIST / "crawly"
    sh_launcher.write_text(
        '#!/usr/bin/env sh\n'
        '# Crawly Self-Contained Launcher for Linux / WSL / macOS (No pip install required)\n'
        'DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
        'exec python3 "$DIR/crawly.pyz" "$@"\n',
        encoding="utf-8",
    )
    sh_launcher.chmod(sh_launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Create Windows .bat launcher script (works with python or py launcher on Windows)
    bat_launcher = DIST / "crawly.bat"
    bat_launcher.write_text(
        "@echo off\r\n"
        "REM Crawly Self-Contained Launcher for Windows (No pip install required)\r\n"
        "where python >nul 2>nul\r\n"
        "if %ERRORLEVEL% EQU 0 (\r\n"
        '    python "%~dp0crawly.pyz" %*\r\n'
        ") else (\r\n"
        '    py "%~dp0crawly.pyz" %*\r\n'
        ")\r\n",
        encoding="utf-8",
    )

    # Copy config.json into dist/ so standalone users can directly edit it
    if (ROOT / "config.json").exists():
        shutil.copy2(ROOT / "config.json", DIST / "config.json")

    # Package universal zip for Windows + Linux/WSL users
    zip_path = DIST / "crawly-universal-windows-linux.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(pyz_path, arcname="crawly.pyz")
        zf.write(sh_launcher, arcname="crawly")
        zf.write(bat_launcher, arcname="crawly.bat")
        if (ROOT / "config.json").exists():
            zf.write(ROOT / "config.json", arcname="config.json")
        if (ROOT / "README.md").exists():
            zf.write(ROOT / "README.md", arcname="README.md")
    print(f"✓ Built universal Windows + Linux/WSL release archive: {zip_path}")
    return pyz_path


def build_native_pyinstaller_binary() -> None:
    if importlib.util.find_spec("PyInstaller") is None:
        print("ℹ PyInstaller not installed; skipping native OS binary compilation (universal crawly.pyz is ready).")
        return
    sys_name = "windows" if os.name == "nt" or "windows" in platform.system().lower() else platform.system().lower()
    raw_arch = platform.machine().lower()
    arch = "x86_64" if raw_arch in ("amd64", "x86_64", "x64") else raw_arch
    bin_name = f"crawly-{sys_name}-{arch}"
    print(f"Compiling native standalone binary '{bin_name}' with PyInstaller...")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--clean",
        "--name",
        bin_name,
        "--distpath",
        str(DIST),
        str(ROOT / "crawly.py"),
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT))
    if proc.returncode != 0:
        print(f"[!] PyInstaller compilation exited with code {proc.returncode}")
        sys.exit(proc.returncode)

    # Clean temporary PyInstaller build artifacts
    shutil.rmtree(ROOT / "build", ignore_errors=True)
    spec_file = ROOT / f"{bin_name}.spec"
    if spec_file.exists():
        spec_file.unlink()
    out_bin = DIST / (f"{bin_name}.exe" if sys_name == "windows" else bin_name)
    if out_bin.exists():
        print(f"✓ Built native standalone executable: {out_bin} ({out_bin.stat().st_size / (1024*1024):.2f} MB)")


if __name__ == "__main__":
    build_universal_pyz()
    if "--native" in sys.argv:
        build_native_pyinstaller_binary()

