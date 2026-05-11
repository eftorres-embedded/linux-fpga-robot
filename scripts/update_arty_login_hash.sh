#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR="${1:-$HOME/yocto/rel-v2025.2/edf/build}"
LOCAL_CONF="$BUILD_DIR/conf/local.conf"
ARTY_USER_DEFAULT="eder"

if [[ ! -f "$LOCAL_CONF" ]]; then
    echo "ERROR: local.conf not found:"
    echo "  $LOCAL_CONF"
    echo
    echo "Usage:"
    echo "  $0 [yocto-build-dir]"
    exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
    echo "ERROR: openssl is required."
    echo "Install it with:"
    echo "  sudo apt install openssl"
    exit 1
fi

read -rp "Linux username [${ARTY_USER_DEFAULT}]: " ARTY_USER
ARTY_USER="${ARTY_USER:-$ARTY_USER_DEFAULT}"

if [[ ! "$ARTY_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
    echo "ERROR: Invalid username: $ARTY_USER"
    echo "Use lowercase letters, numbers, underscore, or dash."
    echo "First character must be a lowercase letter or underscore."
    exit 1
fi

read -srp "New temp password for ${ARTY_USER}: " PW1
echo
read -srp "Confirm password: " PW2
echo

if [[ "$PW1" != "$PW2" ]]; then
    echo "ERROR: Passwords do not match."
    exit 1
fi

if [[ -z "$PW1" ]]; then
    echo "ERROR: Password cannot be empty."
    exit 1
fi

HASH="$(printf '%s' "$PW1" | openssl passwd -6 -stdin)"
unset PW1 PW2

BACKUP="$LOCAL_CONF.bak.login-hash.$(date +%Y%m%d_%H%M%S)"
cp "$LOCAL_CONF" "$BACKUP"

python3 - "$LOCAL_CONF" "$ARTY_USER" "$HASH" <<'PY'
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
user = sys.argv[2]
hash_value = sys.argv[3]

text = path.read_text()

user_line = f'ARTY_USER = "{user}"'
hash_line = f'ARTY_PASS_HASH = "{hash_value}"'

if re.search(r'^ARTY_USER\s*=', text, flags=re.MULTILINE):
    text = re.sub(r'^ARTY_USER\s*=.*$', user_line, text, flags=re.MULTILINE)
else:
    text += "\n# Lab-only login setup for Arty Z7 bring-up.\n"
    text += "# Do not commit real passwords to a public repo.\n"
    text += user_line + "\n"

if re.search(r'^ARTY_PASS_HASH\s*=', text, flags=re.MULTILINE):
    text = re.sub(r'^ARTY_PASS_HASH\s*=.*$', hash_line, text, flags=re.MULTILINE)
else:
    text += hash_line + "\n"

path.write_text(text)
PY

echo
echo "Updated:"
echo "  $LOCAL_CONF"
echo
echo "Backup:"
echo "  $BACKUP"
echo
echo "Configured:"
echo "  ARTY_USER = $ARTY_USER"
echo "  ARTY_PASS_HASH = <new SHA-512 hash>"
echo
echo "Check what BitBake sees:"
echo "  cd $BUILD_DIR"
echo "  MACHINE=arty-z7-20-sdt bitbake -e core-image-minimal | grep -E '^ARTY_USER=|^ARTY_PASS_HASH='"
echo
echo "Then rebuild rootfs/image:"
echo "  MACHINE=arty-z7-20-sdt bitbake -c rootfs -f core-image-minimal"
echo "  MACHINE=arty-z7-20-sdt bitbake core-image-minimal"