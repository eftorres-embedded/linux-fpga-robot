#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR="${1:-$HOME/yocto/rel-v2025.2/edf/build}"
IMG="$BUILD_DIR/tmp/deploy/images/arty-z7-20-sdt/core-image-minimal-arty-z7-20-sdt.rootfs.wic.qemu-sd"

BOOTCMD="$(mktemp)"
BOOTSCRIPT="$(mktemp)"
MNT="$(mktemp -d)"
LOOP=""

cleanup() {
    set +e
    if mountpoint -q "$MNT"; then
        sudo umount "$MNT"
    fi
    if [[ -n "$LOOP" ]]; then
        sudo losetup -d "$LOOP"
    fi
    rm -f "$BOOTCMD" "$BOOTSCRIPT"
    rmdir "$MNT" 2>/dev/null || true
}
trap cleanup EXIT

if [[ ! -f "$IMG" ]]; then
    echo "ERROR: WIC image not found:"
    echo "  $IMG"
    exit 1
fi

if ! command -v mkimage >/dev/null 2>&1; then
    echo "ERROR: mkimage not found."
    echo "Install u-boot-tools:"
    echo "  sudo apt install u-boot-tools"
    exit 1
fi

cat > "$BOOTCMD" <<'EOF'
echo "Booting Arty Z7 from FAT boot partition..."

mmc dev 0

setenv kernel_addr_r 0x02080000
setenv fdt_addr_r    0x02A00000

setenv bootargs console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait earlycon

echo "Loading zImage from mmc 0:1..."
fatload mmc 0:1 ${kernel_addr_r} zImage

echo "Loading system.dtb from mmc 0:1..."
fatload mmc 0:1 ${fdt_addr_r} system.dtb

echo "Starting Linux..."
bootz ${kernel_addr_r} - ${fdt_addr_r}
EOF

mkimage \
  -A arm \
  -T script \
  -C none \
  -n "Arty Z7 SD boot script" \
  -d "$BOOTCMD" \
  "$BOOTSCRIPT"

LOOP=$(sudo losetup -Pf --show "$IMG")

sudo mount "${LOOP}p1" "$MNT"
sudo cp "$BOOTSCRIPT" "$MNT/boot.scr"
sync

echo "Patched boot.scr inside:"
echo "  $IMG"
echo
echo "Boot script now loads:"
echo "  zImage     from mmc 0:1"
echo "  system.dtb from mmc 0:1"
echo "  rootfs     from /dev/mmcblk0p2"
