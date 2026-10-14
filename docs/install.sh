#!/usr/bin/env bash
# ==============================================================================
# crawly: the literature assistant — One-Line Installer for Linux / macOS / WSL
# https://github.com/lokeshsk/crawly
# Usage: curl -fsSL https://lokeshsk.github.io/crawly/install.sh | bash
# ==============================================================================
set -e

REPO="lokeshsk/crawly"
INSTALL_DIR="${HOME}/.local/bin"
SHARE_DIR="${HOME}/.local/share/crawly"
ZIP_URL="https://github.com/${REPO}/releases/latest/download/crawly-universal-windows-linux.zip"
FALLBACK_ZIP_URL="https://github.com/${REPO}/raw/main/dist/crawly-universal-windows-linux.zip"

echo "🕷️  Installing crawly: the literature assistant..."

mkdir -p "${INSTALL_DIR}"
mkdir -p "${SHARE_DIR}"

TMP_DIR=$(mktemp -d)
trap 'rm -rf "${TMP_DIR}"' EXIT

ZIP_PATH="${TMP_DIR}/crawly.zip"

# Download release bundle
if curl -fsSL "${ZIP_URL}" -o "${ZIP_PATH}" 2>/dev/null; then
    echo "✓ Downloaded latest release bundle"
elif curl -fsSL "${FALLBACK_ZIP_URL}" -o "${ZIP_PATH}" 2>/dev/null; then
    echo "✓ Downloaded bundle from main branch"
else
    echo "✗ Failed to download crawly bundle. Please check your internet connection."
    exit 1
fi

unzip -q -o "${ZIP_PATH}" -d "${SHARE_DIR}"
chmod +x "${SHARE_DIR}/crawly" "${SHARE_DIR}/crawly.pyz" 2>/dev/null || true

# Symlink crawly.pyz into ~/.local/bin
ln -sf "${SHARE_DIR}/crawly.pyz" "${INSTALL_DIR}/crawly.pyz" 2>/dev/null || true

# Install robust launcher into ~/.local/bin that resolves symlinks and checks fallback paths
cat << 'EOF' > "${INSTALL_DIR}/crawly"
#!/usr/bin/env sh
# Crawly Self-Contained Launcher for Linux / WSL / macOS
PRG="$0"
while [ -h "$PRG" ]; do
  link=$(readlink "$PRG" 2>/dev/null) || true
  [ -z "$link" ] && break
  case "$link" in
    /*) PRG="$link" ;;
    *)  PRG="$(dirname "$PRG")/$link" ;;
  esac
done
DIR="$(CDPATH= cd -- "$(dirname -- "$PRG")" && pwd)"
if [ -f "$DIR/crawly.pyz" ]; then
  exec python3 "$DIR/crawly.pyz" "$@"
elif [ -f "${HOME}/.local/share/crawly/crawly.pyz" ]; then
  exec python3 "${HOME}/.local/share/crawly/crawly.pyz" "$@"
else
  echo "Error: crawly.pyz not found. Please re-run install.sh or verify ~/.local/share/crawly" >&2
  exit 1
fi
EOF
chmod +x "${INSTALL_DIR}/crawly"
cp -f "${INSTALL_DIR}/crawly" "${SHARE_DIR}/crawly" 2>/dev/null || true
ln -sf "${INSTALL_DIR}/crawly" "${INSTALL_DIR}/crawly-cli" 2>/dev/null || true

echo "✓ Installed crawly to ${INSTALL_DIR}/crawly"

# Ensure ~/.local/bin is in PATH
if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    SHELL_PROFILE=""
    if [[ -f "${HOME}/.bashrc" ]]; then
        SHELL_PROFILE="${HOME}/.bashrc"
    elif [[ -f "${HOME}/.zshrc" ]]; then
        SHELL_PROFILE="${HOME}/.zshrc"
    elif [[ -f "${HOME}/.profile" ]]; then
        SHELL_PROFILE="${HOME}/.profile"
    fi

    if [[ -n "${SHELL_PROFILE}" ]]; then
        echo 'export PATH="${HOME}/.local/bin:$PATH"' >> "${SHELL_PROFILE}"
        echo "✓ Added ${INSTALL_DIR} to PATH in ${SHELL_PROFILE}"
    fi
    export PATH="${INSTALL_DIR}:$PATH"
fi

echo ""
echo "🎉 Installation successful! You can now run:"
echo "   crawly                     # Interactive Literature Dashboard"
echo "   crawly search \"radar\"      # Search across 8+ open scholarly databases"
echo "   crawly snowball \"<DOI>\"    # Trace citation network forward & backward"
echo "   crawly doctor              # Health check for APIs & AI models"
echo ""

