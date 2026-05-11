# Arty Z7 EDF / Yocto Rebuild Guide

## Purpose

This guide documents the reproducible flow I used to bring up AMD EDF / Yocto Linux on a Zynq-7000 board, starting from Vivado and ending with an SD-card boot.

The exact board used here is the **Digilent Arty Z7-20**, but the same method can be adapted to an Arty Z7-10, PYNQ-Z1, or another Zynq-7000 board. The board name, XSA name, DDR range, Ethernet PHY details, and generated DTS labels must be checked for the actual board.

```text
Vivado hardware design
    -> XSA
    -> XSCT / SDTGen
    -> SDT artifact tarball
    -> Yocto custom machine
    -> FSBL + U-Boot + Linux + rootfs
    -> SD-card boot
```

## Paths used in this guide

```text
Project repo:        ~/fpga_projects/linux-fpga-robot
EDF workspace:       ~/yocto/rel-v2025.2/edf
EDF build dir:       ~/yocto/rel-v2025.2/edf/build
Custom layer:        ~/fpga_projects/linux-fpga-robot/yocto/meta-linux-fpga-robot
XSA:                 ~/fpga_projects/linux-fpga-robot/hw/xsa/arty_z7_20_base.xsa
Generated SDT:       ~/fpga_projects/linux-fpga-robot/hw/sdt/arty-z7-20-sdt
Yocto machine:       arty-z7-20-sdt
Reference machine:   zynq-zc702-sdt-full
```

---

# Quick repeatable rebuild loop

For normal rebuilds, I do not manually patch files one by one. The repeatable loop is:

```bash
# 1. If I need to change the lab login password:
cd ~/fpga_projects/linux-fpga-robot
./scripts/update_arty_login_hash.sh

# 2. Build or rebuild the image:
cd ~/yocto/rel-v2025.2/edf/build
MACHINE=arty-z7-20-sdt bitbake core-image-minimal

# 3. Verify the deployed DTB before imaging:
fdtget -t s tmp/deploy/images/arty-z7-20-sdt/system.dtb / compatible
fdtget -t x tmp/deploy/images/arty-z7-20-sdt/system.dtb /memory reg
fdtget -t s tmp/deploy/images/arty-z7-20-sdt/system.dtb /memory device_type

# 4. Patch boot.scr inside the WIC image before writing the SD card:
cd ~/fpga_projects/linux-fpga-robot
./scripts/patch_arty_z7_wic_bootscr.sh

# 5. Write the SD card.
```

Required DTB validation before writing the SD card:

```text
xlnx,arty-z7-20
xlnx,zynq-7000
100000 1ff00000
memory
```

If the DTS was regenerated from the XSA/SDT flow, I also rerun:

```bash
cd ~/fpga_projects/linux-fpga-robot
./scripts/fix_arty_z7_sdt_dts.py \
  yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts
```

---

# 1. Vivado hardware design

## 1.1 Create the project

In Vivado:

```text
Create Project
Select board: Digilent Arty Z7-20
Create Block Design
Add ZYNQ7 Processing System
Run Block Automation / Apply Board Preset
```

For a different board, the first thing to change is the Vivado board preset. I do not reuse the Arty Z7 preset for PYNQ or another board.

## 1.2 Zynq-7000 block settings to verify

For the first bootable Linux platform, I keep the PL simple and focus on the PS.

Required:

```text
DDR enabled
UART0 enabled for serial console
SD0 enabled for microSD boot/rootfs
```

Recommended for Arty Z7 bring-up:

```text
ENET0 enabled
MDIO enabled
Ethernet PHY mode set by the board preset, normally RGMII-ID for Arty Z7
USB0 enabled if USB host is wanted
QSPI enabled if the board preset enables it
```

Recommended for later FPGA fabric work:

```text
M_AXI_GP0 enabled
FCLK_CLK0 enabled, usually 100 MHz
FCLK_RESET0_N enabled if needed by PL reset logic
```

For my base design, I used the Digilent board preset and enabled MDIO for Ethernet 0. The generated SDT later showed `serial0`, `ethernet0`, `sdhci0`, `uart0`, `usb0`, and `gem0` as expected.

## 1.3 Generate and export hardware

In Vivado:

```text
Generate Output Products
Create HDL Wrapper
Let Vivado manage wrapper and auto-update
Generate Bitstream
File -> Export -> Export Hardware
Include bitstream: Yes
Output: ~/fpga_projects/linux-fpga-robot/hw/xsa/arty_z7_20_base.xsa
```

Verify the XSA:

```bash
cd ~/fpga_projects/linux-fpga-robot

ls -lh hw/xsa/
file hw/xsa/arty_z7_20_base.xsa
unzip -l hw/xsa/arty_z7_20_base.xsa | head -n 80
```

Expected files inside the XSA:

```text
system.hwh
ps7_init.tcl
ps7_init.c
ps7_init.h
ps7_init_gpl.c
ps7_init_gpl.h
xsa.xml
sysdef.xml
*.bit
```

Optional checkpoint:

```bash
git add hw/xsa/arty_z7_20_base.xsa
git commit -m "Add Arty Z7-20 base Vivado XSA"
```

---

# 2. Install AMD EDF / Yocto

## 2.1 Install packages

```bash
sudo apt update

sudo apt install -y \
  gawk wget git diffstat unzip texinfo gcc build-essential chrpath socat cpio \
  python3 python3-pip python3-pexpect xz-utils debianutils iputils-ping \
  python3-git python3-jinja2 libegl1-mesa libsdl1.2-dev pylint xterm \
  python3-subunit mesa-common-dev zstd liblz4-tool file locales curl \
  device-tree-compiler u-boot-tools
```

## 2.2 Locale

```bash
sudo locale-gen en_US.UTF-8
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8
```

## 2.3 Make `/bin/sh` point to bash behavior

```bash
ls -l /bin/sh
sudo dpkg-reconfigure dash
```

When asked whether to use `dash` as `/bin/sh`, select:

```text
No
```

## 2.4 Git and repo tool

```bash
git config --global user.email "you@example.com"
git config --global user.name "Your Name"

mkdir -p ~/bin
curl https://storage.googleapis.com/git-repo-downloads/repo > ~/bin/repo
chmod a+x ~/bin/repo
echo 'export PATH="$HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
which repo
```

## 2.5 Create EDF workspace

```bash
mkdir -p ~/yocto/rel-v2025.2/edf
cd ~/yocto/rel-v2025.2/edf

repo init \
  -u https://github.com/Xilinx/yocto-manifests.git \
  -b rel-v2025.2 \
  -m default-edf.xml

repo sync -j8
```

If the parallel sync fails, retry with:

```bash
repo sync
```

## 2.6 Enter the EDF build environment

```bash
cd ~/yocto/rel-v2025.2/edf
unset TEMPLATECONF
source edf-init-build-env
```

This should place me in:

```text
~/yocto/rel-v2025.2/edf/build
```

Verify:

```bash
which bitbake
echo $BUILDDIR
bitbake --version
```

After restarting the computer or opening a new terminal, re-enter with:

```bash
cd ~/yocto/rel-v2025.2/edf
source edf-init-build-env
```

---

# 3. Phase 1: build a known-good reference board

Before customizing Arty Z7, I first prove that the EDF workspace works.

## 3.1 Find available Zynq machines

```bash
cd ~/yocto/rel-v2025.2/edf/build
find ../sources -path "*/conf/machine/*.conf" | grep -i zynq
```

I used:

```text
zynq-zc702-sdt-full
```

## 3.2 Build ZC702 reference image

```bash
MACHINE=zynq-zc702-sdt-full bitbake core-image-minimal
```

This validates the Yocto setup before any custom board work.

## 3.3 Boot ZC702 reference image in QEMU

```bash
cd ~/yocto/rel-v2025.2/edf/build/tmp/deploy/images/zynq-zc702-sdt-full
runqemu core-image-minimal-zynq-zc702-sdt-full.rootfs.qemuboot.conf nographic
```

Exit QEMU:

```text
Ctrl-a
x
```

This proves:

```text
EDF sources are good
BitBake can build
The reference machine works
QEMU boot flow works
```

---

# 4. Phase 2: create custom Yocto layer and machine

## 4.1 Create layer skeleton

```bash
cd ~/fpga_projects/linux-fpga-robot

mkdir -p yocto/meta-linux-fpga-robot/conf/machine
mkdir -p yocto/meta-linux-fpga-robot/recipes-bsp
mkdir -p yocto/meta-linux-fpga-robot/recipes-core/images
mkdir -p yocto/meta-linux-fpga-robot/recipes-kernel
```

Expected layout:

```text
linux-fpga-robot/
└── yocto/
    └── meta-linux-fpga-robot/
        ├── conf/
        │   ├── layer.conf
        │   └── machine/
        │       └── arty-z7-20-sdt.conf
        ├── recipes-bsp/
        ├── recipes-core/
        │   └── images/
        └── recipes-kernel/
```

## 4.2 Create `layer.conf`

```bash
cat > yocto/meta-linux-fpga-robot/conf/layer.conf <<'EOF'
# meta-linux-fpga-robot layer

BBPATH .= ":${LAYERDIR}"

BBFILES += "${LAYERDIR}/recipes-*/*/*.bb \
            ${LAYERDIR}/recipes-*/*/*.bbappend"

BBFILE_COLLECTIONS += "linux-fpga-robot"
BBFILE_PATTERN_linux-fpga-robot = "^${LAYERDIR}/"
BBFILE_PRIORITY_linux-fpga-robot = "6"

LAYERSERIES_COMPAT_linux-fpga-robot = "scarthgap"
EOF
```

## 4.3 Create initial machine file

```bash
cat > yocto/meta-linux-fpga-robot/conf/machine/arty-z7-20-sdt.conf <<'EOF'
#@TYPE: Machine
#@NAME: arty-z7-20-sdt
#@DESCRIPTION: Machine configuration for Digilent Arty Z7-20 using AMD EDF SDT flow.

require conf/machine/zynq-zc702-sdt-full.conf

MACHINEOVERRIDES =. "arty-z7-20-sdt:"
EOF
```

This starts by inheriting ZC702 only as a bootstrap. It is not the final board support.

## 4.4 Add layer to EDF

```bash
cd ~/yocto/rel-v2025.2/edf/build
bitbake-layers add-layer ~/fpga_projects/linux-fpga-robot/yocto/meta-linux-fpga-robot
bitbake-layers show-layers
```

Expected: `meta-linux-fpga-robot` appears.

## 4.5 Verify machine name

```bash
MACHINE=arty-z7-20-sdt bitbake -e | grep '^MACHINE='
```

Expected:

```text
MACHINE="arty-z7-20-sdt"
```

## 4.6 Build initial custom machine

```bash
MACHINE=arty-z7-20-sdt bitbake core-image-minimal
```

At this stage, the image can build because it still inherits ZC702 hardware. The goal is only to prove the custom layer and machine name are wired correctly.

---

# 5. Trace inherited hardware files

I do not guess which files are used. I trace them from BitBake.

```bash
cd ~/yocto/rel-v2025.2/edf/build

MACHINE=arty-z7-20-sdt bitbake -e core-image-minimal | grep '^MACHINE='
MACHINE=arty-z7-20-sdt bitbake -e core-image-minimal | grep '^MACHINEOVERRIDES='
MACHINE=arty-z7-20-sdt bitbake -e core-image-minimal | grep -E '^(SOC_FAMILY|DEFAULTTUNE|TUNE_FEATURES|MACHINE_FEATURES)='
```

Find DTS/DTB files:

```bash
find tmp/work -path "*device-tree*" -name "*.dts" | grep -E "arty|zc702|zynq"
find tmp/work -path "*device-tree*" -name "*.dtb" | grep -E "arty|zc702|zynq"
```

Trace SDT variables:

```bash
MACHINE=arty-z7-20-sdt bitbake -e device-tree | grep -iE "system|dtfile|sdt"
MACHINE=arty-z7-20-sdt bitbake -e sdt-artifacts | grep -E '^(FILE=|PN=|S=|WORKDIR=|SRC_URI=|SDT_URI=)'
```

The important discovery was:

```text
sdt-artifacts does not convert XSA -> SDT.
It only installs an existing SDT artifact directory/tarball into /usr/share/sdt/${MACHINE}.
```

So the missing bridge is:

```text
XSA -> SDT directory -> tarball -> SDT_URI
```

---

# 6. Generate Arty SDT from XSA

## 6.1 Locate XSCT

```bash
which xsct || true
find /tools /opt ~/ -path "*/bin/xsct" 2>/dev/null
```

In my setup:

```text
/opt/Xilinx/2025.2/Vitis/bin/xsct
```

## 6.2 Create SDT generation script

```bash
cd ~/fpga_projects/linux-fpga-robot
mkdir -p scripts/sdt

cat > scripts/sdt/gen_arty_z7_20_sdt.tcl <<'EOF'
sdtgen set_dt_param -xsa /home/eder/fpga_projects/linux-fpga-robot/hw/xsa/arty_z7_20_base.xsa
sdtgen set_dt_param -dir /home/eder/fpga_projects/linux-fpga-robot/hw/sdt/arty-z7-20-sdt
sdtgen set_dt_param -trace enable
sdtgen generate_sdt
exit
EOF
```

Run:

```bash
/opt/Xilinx/2025.2/Vitis/bin/xsct scripts/sdt/gen_arty_z7_20_sdt.tcl
```

## 6.3 Inspect generated SDT

```bash
cd ~/fpga_projects/linux-fpga-robot

find hw/sdt/arty-z7-20-sdt -maxdepth 2 -type f | sort

grep -Rni "zc702" hw/sdt/arty-z7-20-sdt || echo "No ZC702 references found"

grep -RniE "model|compatible|board|arty" hw/sdt/arty-z7-20-sdt | head -n 80

grep -RniE "ps7_ddr|memory@|reg = <0x00100000|0x1ff00000|0x3ff00000" \
  hw/sdt/arty-z7-20-sdt
```

For Arty Z7-20, the DDR should be:

```text
reg = <0x00100000 0x1FF00000>
```

Check peripherals:

```bash
grep -RniE "gem0|ethernet|mdio|phy-mode|phy-handle|rgmii|uart0|sdhci0|usb0|qspi|status" \
  hw/sdt/arty-z7-20-sdt/pcw.dtsi \
  hw/sdt/arty-z7-20-sdt/zynq-7000.dtsi
```

---

# 7. Package Arty SDT for Yocto

## 7.1 Create local SDT tarball

```bash
cd ~/fpga_projects/linux-fpga-robot

mkdir -p yocto/meta-linux-fpga-robot/recipes-bsp/sdt-artifacts/files

tar -czf yocto/meta-linux-fpga-robot/recipes-bsp/sdt-artifacts/files/arty-z7-20-sdt.tar.gz \
  -C hw/sdt \
  arty-z7-20-sdt

sha256sum yocto/meta-linux-fpga-robot/recipes-bsp/sdt-artifacts/files/arty-z7-20-sdt.tar.gz
```

## 7.2 Create `sdt-artifacts.bbappend`

```bash
mkdir -p yocto/meta-linux-fpga-robot/recipes-bsp/sdt-artifacts

cat > yocto/meta-linux-fpga-robot/recipes-bsp/sdt-artifacts/sdt-artifacts.bbappend <<'EOF'
FILESEXTRAPATHS:prepend := "${THISDIR}/files:"
EOF
```

## 7.3 Override SDT in machine file

Edit:

```bash
yocto/meta-linux-fpga-robot/conf/machine/arty-z7-20-sdt.conf
```

Add after the `require` line:

```bitbake
# Use locally generated Arty Z7-20 SDT artifacts instead of inherited ZC702 SDT.
SDT_URI = "file://arty-z7-20-sdt.tar.gz"
SDT_URI[sha256sum] = "PASTE_SHA256_HERE"
SDT_URI[S] = "${WORKDIR}/arty-z7-20-sdt"
```

## 7.4 Verify Yocto sees the local SDT

```bash
cd ~/yocto/rel-v2025.2/edf
source edf-init-build-env

MACHINE=arty-z7-20-sdt bitbake -e sdt-artifacts | grep -E '^(SDT_URI=|SRC_URI=|S=)'
MACHINE=arty-z7-20-sdt bitbake-layers show-appends | grep -A3 sdt-artifacts
```

Expected:

```text
SDT_URI="file://arty-z7-20-sdt.tar.gz"
SRC_URI="file://arty-z7-20-sdt.tar.gz"
S=".../sdt-artifacts/1.0/arty-z7-20-sdt"
```

Rebuild SDT artifact:

```bash
MACHINE=arty-z7-20-sdt bitbake -c cleansstate sdt-artifacts
MACHINE=arty-z7-20-sdt bitbake sdt-artifacts
```

Inspect:

```bash
head -n 60 tmp/work/arty_z7_20_sdt-amd-linux-gnueabi/sdt-artifacts/1.0/arty-z7-20-sdt/system-top.dts

grep -Rni "zc702" tmp/work/arty_z7_20_sdt-amd-linux-gnueabi/sdt-artifacts/1.0/arty-z7-20-sdt \
  || echo "No ZC702 references found"
```

---

# 8. Create Arty Linux DTS wrapper

`SDT_URI` fixes the SDT artifact, but inherited ZC702 machine settings can still point the Linux device-tree recipe at ZC702 wrapper files. I override `CONFIG_DTFILE_DIR` and `CONFIG_DTFILE`.

## 8.1 Create DTS directory

```bash
cd ~/fpga_projects/linux-fpga-robot
mkdir -p yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt
```

## 8.2 Flatten the generated SDT top-level DTS

The generated `system-top.dts` includes `zynq-7000.dtsi` and `pcw.dtsi`. I flatten it so the Yocto device-tree recipe does not fail on missing includes.

```bash
cd ~/fpga_projects/linux-fpga-robot

gcc -E -nostdinc -undef -D__DTS__ -x assembler-with-cpp -P \
  -I hw/sdt/arty-z7-20-sdt \
  hw/sdt/arty-z7-20-sdt/system-top.dts \
  -o yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts

grep -n "#include" yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts \
  || echo "No include directives left"
```

## 8.3 Add Arty system config include

```bash
cat > yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/arty-z7-20-sdt-system-conf.dtsi <<'EOF'
/ {
        chosen {
                bootargs = "earlycon";
                stdout-path = "serial0:115200n8";
        };
};
EOF
```

## 8.4 Override `CONFIG_DTFILE` in machine file

Add to `arty-z7-20-sdt.conf`:

```bitbake
# Use Arty Z7-20 Linux device-tree wrapper instead of inherited ZC702 wrapper.
CONFIG_DTFILE_DIR := "${@bb.utils.which(d.getVar('BBPATH'), 'conf/dts/arty-z7-20-sdt')}"
CONFIG_DTFILE = "${CONFIG_DTFILE_DIR}/cortexa9-linux.dts"
```

Verify:

```bash
cd ~/yocto/rel-v2025.2/edf/build

MACHINE=arty-z7-20-sdt bitbake -e device-tree | grep -E '^(SYSTEM_DTFILE=|SYSTEM_DTFILE_DIR=|CONFIG_DTFILE=|CONFIG_DTFILE_DIR=|SYSTEM_DTFILE_DEPENDS=)'
```

Expected:

```text
CONFIG_DTFILE_DIR=".../meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt"
CONFIG_DTFILE=".../meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts"
```

Build device tree:

```bash
MACHINE=arty-z7-20-sdt bitbake -c cleansstate device-tree
MACHINE=arty-z7-20-sdt bitbake device-tree
```

Verify no ZC702 references:

```bash
grep -Rni "zc702" tmp/work/arty_z7_20_sdt-amd-linux-gnueabi/device-tree/1.0 \
  || echo "No ZC702 references found in rebuilt device-tree workdir"
```

---

# 9. DTS fixups required for Linux and U-Boot

Two DTS fixes are required after SDT generation:

```text
1. The root compatible must include both:
   xlnx,arty-z7-20
   xlnx,zynq-7000

2. Only DDR should be a root-level device_type = "memory" node.
```

The generated SDT originally emitted QSPI linear flash and PS RAM/OCM as root-level memory nodes. U-Boot resolved `/memory` to QSPI instead of DDR, causing a hang after:

```text
DRAM: ECC disabled
```

The fix is kept in a repo script so I can rerun it every time the DTS is regenerated.

## 9.1 Create or replace `scripts/fix_arty_z7_sdt_dts.py`

```bash
cd ~/fpga_projects/linux-fpga-robot
mkdir -p scripts

cat > scripts/fix_arty_z7_sdt_dts.py <<'PY'
#!/usr/bin/env python3
"""
fix_arty_z7_sdt_dts.py

Post-generation DTS cleanup for the Arty Z7-20 SDT flow.

Purpose:
  Convert SDTGen's raw system DTS into a Linux/U-Boot-safe DTS.

Fixes:
  1. Ensure the root compatible includes:
       "xlnx,arty-z7-20", "xlnx,zynq-7000"

  2. Rename QSPI linear flash node:
       ps7_qspi_linear_0_memory: memory@fc000000
     to:
       ps7_qspi_linear_0_memory: flash@fc000000
     and remove device_type = "memory" from that node.

  3. Rename PS RAM / OCM nodes:
       ps7_ram_0_memory: memory@0
       ps7_ram_1_memory: memory@ffff0000
     to:
       ps7_ram_0_memory: sram@0
       ps7_ram_1_memory: sram@ffff0000
     and remove device_type = "memory" from those nodes.

  4. Leave DDR as the only system memory node:
       ps7_ddr_0_memory: memory@00100000
       device_type = "memory";

This script intentionally does not modify vendor files under /opt/Xilinx.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


ROOT_COMPAT_OLD_RE = re.compile(
    r'(?m)^([ \t]*)compatible\s*=\s*"xlnx,arty-z7-20"\s*;'
)

ROOT_COMPAT_NEW_RE = re.compile(
    r'(?m)^[ \t]*compatible\s*=\s*"xlnx,arty-z7-20"\s*,\s*"xlnx,zynq-7000"\s*;'
)


def replace_root_compatible(text: str) -> tuple[str, bool]:
    """
    Ensure the root node compatible has both board and Zynq family strings.

    Important:
      Do not simply search the whole file for "xlnx,zynq-7000".
      That string can appear elsewhere while the root compatible is still wrong.
    """
    if ROOT_COMPAT_NEW_RE.search(text):
        return text, False

    new_text, count = ROOT_COMPAT_OLD_RE.subn(
        r'\1compatible = "xlnx,arty-z7-20", "xlnx,zynq-7000";',
        text,
        count=1,
    )

    if count != 1:
        raise RuntimeError(
            'Could not find root compatible = "xlnx,arty-z7-20";'
        )

    return new_text, True


def find_matching_brace(text: str, open_brace_idx: int) -> int:
    """Find matching closing brace for a node block."""
    depth = 0

    for i in range(open_brace_idx, len(text)):
        char = text[i]

        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1

            if depth == 0:
                return i

    raise RuntimeError("Could not find matching closing brace")


def find_labeled_node(text: str, label: str) -> tuple[re.Match[str], int, int]:
    """
    Find a labeled DTS node and return:
      match, open_brace_idx, close_brace_idx
    """
    pattern = re.compile(
        rf'(?m)^([ \t]*{re.escape(label)}\s*:\s*)([A-Za-z0-9_,+.\-]+@[A-Fa-f0-9]+)(\s*\{{)'
    )

    match = pattern.search(text)
    if not match:
        raise RuntimeError(f'Could not find labeled node "{label}"')

    open_brace_idx = text.find("{", match.start())
    close_brace_idx = find_matching_brace(text, open_brace_idx)

    return match, open_brace_idx, close_brace_idx


def patch_node(
    text: str,
    label: str,
    old_unit_name: str,
    new_unit_name: str,
    remove_memory_device_type: bool = True,
) -> tuple[str, bool]:
    """
    Rename a labeled node and optionally remove device_type = "memory"
    from only that node block.

    This is intentionally idempotent:
      - If the node was already renamed, it keeps the new name.
      - If device_type = "memory" was already removed, it does not fail.
    """
    match, _open_brace_idx, close_brace_idx = find_labeled_node(text, label)

    before = text[: match.start()]
    node = text[match.start() : close_brace_idx + 1]
    after = text[close_brace_idx + 1 :]

    changed = False
    current_unit_name = match.group(2)

    if current_unit_name == old_unit_name:
        node = re.sub(
            rf'({re.escape(label)}\s*:\s*){re.escape(old_unit_name)}(\s*\{{)',
            rf'\1{new_unit_name}\2',
            node,
            count=1,
        )
        changed = True
    elif current_unit_name == new_unit_name:
        pass
    else:
        raise RuntimeError(
            f'Node "{label}" has unexpected unit name "{current_unit_name}". '
            f'Expected "{old_unit_name}" or "{new_unit_name}".'
        )

    if remove_memory_device_type:
        node, removed = re.subn(
            r'\n[ \t]*device_type\s*=\s*"memory"\s*;',
            "",
            node,
            count=1,
        )

        if removed:
            changed = True

    return before + node + after, changed


def validate_text(text: str) -> None:
    """Basic text-level validation before writing."""
    if not ROOT_COMPAT_NEW_RE.search(text):
        raise RuntimeError(
            'Validation failed: root compatible must be '
            '"xlnx,arty-z7-20", "xlnx,zynq-7000";'
        )

    required = [
        "ps7_qspi_linear_0_memory: flash@fc000000",
        "ps7_ram_0_memory: sram@0",
        "ps7_ram_1_memory: sram@ffff0000",
        "ps7_ddr_0_memory: memory@00100000",
    ]

    for token in required:
        if token not in text:
            raise RuntimeError(f"Validation failed: missing {token}")

    forbidden = [
        "ps7_qspi_linear_0_memory: memory@fc000000",
        "ps7_ram_0_memory: memory@0",
        "ps7_ram_1_memory: memory@ffff0000",
    ]

    for token in forbidden:
        if token in text:
            raise RuntimeError(f"Validation failed: still contains {token}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "dts",
        type=Path,
        help="Path to cortexa9-linux.dts",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not create a .bak file",
    )
    args = parser.parse_args()

    dts_path = args.dts

    if not dts_path.exists():
        print(f"ERROR: DTS file not found: {dts_path}", file=sys.stderr)
        return 1

    original = dts_path.read_text()
    text = original

    text, changed_root = replace_root_compatible(text)

    text, changed_qspi = patch_node(
        text,
        label="ps7_qspi_linear_0_memory",
        old_unit_name="memory@fc000000",
        new_unit_name="flash@fc000000",
    )

    text, changed_ram0 = patch_node(
        text,
        label="ps7_ram_0_memory",
        old_unit_name="memory@0",
        new_unit_name="sram@0",
    )

    text, changed_ram1 = patch_node(
        text,
        label="ps7_ram_1_memory",
        old_unit_name="memory@ffff0000",
        new_unit_name="sram@ffff0000",
    )

    validate_text(text)

    if text == original:
        print("No changes needed; DTS already appears fixed.")
        return 0

    if not args.no_backup:
        backup_path = dts_path.with_suffix(dts_path.suffix + ".bak")
        shutil.copy2(dts_path, backup_path)
        print(f"Backup written: {backup_path}")

    dts_path.write_text(text)

    print("Applied Arty Z7 DTS fixups:")
    print(f"  root compatible updated: {changed_root}")
    print(f"  QSPI flash node fixed:   {changed_qspi}")
    print(f"  PS RAM node 0 fixed:     {changed_ram0}")
    print(f"  PS RAM node 1 fixed:     {changed_ram1}")
    print(f"Updated DTS: {dts_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
PY

chmod +x scripts/fix_arty_z7_sdt_dts.py
```

Run it:

```bash
./scripts/fix_arty_z7_sdt_dts.py \
  yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts
```

## 9.2 Validate DTS before building

```bash
cd ~/fpga_projects/linux-fpga-robot

dtc -I dts -O dtb \
  -o /tmp/arty-test.dtb \
  yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts

fdtget -t s /tmp/arty-test.dtb / compatible
fdtget -t x /tmp/arty-test.dtb /memory reg
fdtget -t s /tmp/arty-test.dtb /memory device_type
```

Required:

```text
xlnx,arty-z7-20
xlnx,zynq-7000
100000 1ff00000
memory
```

# 10. FSBL / libxil cleanup

The inherited ZC702 machine also brings a ZC702 FSBL multiconfig. This can still build, but the standalone/libxil config needed cleanup.

## 10.1 Build FSBL

```bash
cd ~/yocto/rel-v2025.2/edf/build
MACHINE=arty-z7-20-sdt bitbake mc:zynq-zc702-sdt-full-cortexa9-fsbl:fsbl-firmware
```

If it fails, inspect logs:

```bash
find tmp-zynq-zc702-sdt-full-cortexa9-fsbl/work \
  -path "*/fsbl-firmware/*/temp/log.do_*" -type f

grep -nE "ERROR|Error|error:|fatal|No such file|undefined|failed" <log-path>
```

## 10.2 Remove TTCPS from inherited libxil config if needed

The observed issue was that `ttcps` was selected but `XPAR_XTTCPS_NUM_INSTANCES` was not generated.

```bash
cd ~/fpga_projects/linux-fpga-robot
mkdir -p yocto/meta-linux-fpga-robot/conf/machine/include/arty-z7-20-sdt

sed '/PACKAGECONFIG\[ttcps\]/d' \
  ~/yocto/rel-v2025.2/edf/sources/meta-amd-adaptive-socs/meta-amd-adaptive-socs-bsp/conf/machine/include/zynq-zc702-sdt-full/zynq-zc702-sdt-full-cortexa9-fsbl-libxil.conf \
  > yocto/meta-linux-fpga-robot/conf/machine/include/arty-z7-20-sdt/arty-z7-20-sdt-cortexa9-fsbl-libxil.conf

cat >> yocto/meta-linux-fpga-robot/conf/machine/include/arty-z7-20-sdt/arty-z7-20-sdt-cortexa9-fsbl-libxil.conf <<'EOF'

# Arty Z7-20 SDT does not currently generate XPAR_XTTCPS_NUM_INSTANCES.
# Do not pull the TTCPS standalone driver into the FSBL BSP.
PACKAGECONFIG:remove = "ttcps"
EOF
```

Add to `arty-z7-20-sdt.conf`:

```bitbake
# Use Arty-specific standalone/libxil config instead of inherited ZC702 config.
LIBXIL_CONFIG = "conf/machine/include/arty-z7-20-sdt/arty-z7-20-sdt-cortexa9-fsbl-libxil.conf"
```

Verify:

```bash
cd ~/yocto/rel-v2025.2/edf/build

MACHINE=arty-z7-20-sdt bitbake -e mc:zynq-zc702-sdt-full-cortexa9-fsbl:fsbl-firmware | \
  grep -E '^(LIBXIL_CONFIG=|CONFIG_DTFILE=|SYSTEM_DTFILE=|MACHINE=|BB_CURRENT_MC=)'
```

Build again:

```bash
MACHINE=arty-z7-20-sdt bitbake mc:zynq-zc702-sdt-full-cortexa9-fsbl:fsbl-firmware
```

Find FSBL outputs:

```bash
find tmp-zynq-zc702-sdt-full-cortexa9-fsbl \
  -type f \( -name "*fsbl*arty*.elf" -o -name "zynq_fsbl.elf" \) | sort
```

---

# 11. Lab login user and password

I use a lab-only login user for bring-up. Real/final project credentials should not be committed.

The project uses two parts:

```text
1. core-image-minimal.bbappend
   Repo-controlled rootfs postprocess hook.
   Safe to commit because it does not contain the password hash.

2. build/conf/local.conf
   Private username/password-hash values.
   Do not commit.
```

## 11.1 Add image postprocess hook

Create:

```bash
cd ~/fpga_projects/linux-fpga-robot
mkdir -p yocto/meta-linux-fpga-robot/recipes-core/images
cat > yocto/meta-linux-fpga-robot/recipes-core/images/core-image-minimal.bbappend <<'EOF'
# Lab-only login setup for Arty Z7 bring-up.
# ARTY_USER and ARTY_PASS_HASH are expected to be defined in build/conf/local.conf.
# Do not commit real password hashes to a public repo.

ROOTFS_POSTPROCESS_COMMAND:append = " arty_set_known_login; "

arty_set_known_login() {
    if [ -z "${ARTY_USER}" ] || [ -z "${ARTY_PASS_HASH}" ]; then
        bbfatal "ARTY_USER and ARTY_PASS_HASH must be set in local.conf"
    fi

    sed -i 's#^root:[^:]*:#root:${ARTY_PASS_HASH}:#' ${IMAGE_ROOTFS}${sysconfdir}/shadow

    if ! grep -q '^${ARTY_USER}:' ${IMAGE_ROOTFS}${sysconfdir}/group; then
        echo '${ARTY_USER}:x:1000:' >> ${IMAGE_ROOTFS}${sysconfdir}/group
    fi

    if ! grep -q '^${ARTY_USER}:' ${IMAGE_ROOTFS}${sysconfdir}/passwd; then
        echo '${ARTY_USER}:x:1000:1000:Arty User:/home/${ARTY_USER}:/bin/sh' >> ${IMAGE_ROOTFS}${sysconfdir}/passwd
    fi

    if grep -q '^${ARTY_USER}:' ${IMAGE_ROOTFS}${sysconfdir}/shadow; then
        sed -i 's#^${ARTY_USER}:[^:]*:#${ARTY_USER}:${ARTY_PASS_HASH}:#' ${IMAGE_ROOTFS}${sysconfdir}/shadow
    else
        echo '${ARTY_USER}:${ARTY_PASS_HASH}:19000:0:99999:7:::' >> ${IMAGE_ROOTFS}${sysconfdir}/shadow
    fi

    if [ -f ${IMAGE_ROOTFS}${sysconfdir}/gshadow ]; then
        if ! grep -q '^${ARTY_USER}:' ${IMAGE_ROOTFS}${sysconfdir}/gshadow; then
            echo '${ARTY_USER}:!::' >> ${IMAGE_ROOTFS}${sysconfdir}/gshadow
        fi
    fi

    install -d -m 0755 -o 1000 -g 1000 ${IMAGE_ROOTFS}/home/${ARTY_USER}
}
EOF
```

## 11.2 Add local private variables manually, if needed

In:

```text
~/yocto/rel-v2025.2/edf/build/conf/local.conf
```

Add:

```bitbake
# Lab-only login setup for Arty Z7 bring-up.
# Do not commit this file.

ARTY_USER = "eder"
ARTY_PASS_HASH = "PASTE_SHA512_HASH_HERE"
```

The preferred method is to use the script in the next step so I do not make copy/paste mistakes.

## 11.3 Script to update the hash without copy/paste mistakes

```bash
cd ~/fpga_projects/linux-fpga-robot
mkdir -p scripts
cat > scripts/update_arty_login_hash.sh <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

BUILD_DIR="${1:-$HOME/yocto/rel-v2025.2/edf/build}"
LOCAL_CONF="$BUILD_DIR/conf/local.conf"
ARTY_USER_DEFAULT="eder"

if [[ ! -f "$LOCAL_CONF" ]]; then
    echo "ERROR: local.conf not found: $LOCAL_CONF"
    exit 1
fi

if ! command -v openssl >/dev/null 2>&1; then
    echo "ERROR: openssl is required."
    exit 1
fi

read -rp "Linux username [${ARTY_USER_DEFAULT}]: " ARTY_USER
ARTY_USER="${ARTY_USER:-$ARTY_USER_DEFAULT}"

if [[ ! "$ARTY_USER" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
    echo "ERROR: Invalid username: $ARTY_USER"
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
    text += "\n# Lab-only login setup for Arty Z7 bring-up.\n# Do not commit this file.\n" + user_line + "\n"

if re.search(r'^ARTY_PASS_HASH\s*=', text, flags=re.MULTILINE):
    text = re.sub(r'^ARTY_PASS_HASH\s*=.*$', hash_line, text, flags=re.MULTILINE)
else:
    text += hash_line + "\n"

path.write_text(text)
PY

echo "Updated $LOCAL_CONF"
echo "Backup: $BACKUP"
echo "Now rebuild rootfs/image:"
echo "  cd $BUILD_DIR"
echo "  MACHINE=arty-z7-20-sdt bitbake -c rootfs -f core-image-minimal"
echo "  MACHINE=arty-z7-20-sdt bitbake core-image-minimal"
EOF

chmod +x scripts/update_arty_login_hash.sh
```

Run it whenever I need a new temporary password:

```bash
cd ~/fpga_projects/linux-fpga-robot
./scripts/update_arty_login_hash.sh
```

Force rootfs rebuild after changing the password:

```bash
cd ~/yocto/rel-v2025.2/edf/build
MACHINE=arty-z7-20-sdt bitbake -c rootfs -f core-image-minimal
MACHINE=arty-z7-20-sdt bitbake core-image-minimal
```

Verify BitBake sees the new values:

```bash
MACHINE=arty-z7-20-sdt bitbake -e core-image-minimal | grep -E '^ARTY_USER=|^ARTY_PASS_HASH='
```

Verify the generated rootfs has the user and password hash:

```bash
grep '^eder:' tmp/work/arty_z7_20_sdt-amd-linux-gnueabi/core-image-minimal/*/rootfs/etc/passwd
grep '^eder:' tmp/work/arty_z7_20_sdt-amd-linux-gnueabi/core-image-minimal/*/rootfs/etc/shadow
grep '^root:' tmp/work/arty_z7_20_sdt-amd-linux-gnueabi/core-image-minimal/*/rootfs/etc/shadow
```

# 12. Build full image

```bash
cd ~/yocto/rel-v2025.2/edf/build
MACHINE=arty-z7-20-sdt bitbake core-image-minimal
```

Check deploy output:

```bash
ls -lh tmp/deploy/images/arty-z7-20-sdt | grep -E "BOOT|boot.bin|wic|system.dtb|zImage|uImage|rootfs|boot.scr"
find tmp/deploy/images/arty-z7-20-sdt -maxdepth 1 -type f | sort
```

---

# 13. Inspect WIC image before writing SD card

```bash
cd ~/yocto/rel-v2025.2/edf/build

LOOPDEV=$(sudo losetup -Pf --show tmp/deploy/images/arty-z7-20-sdt/core-image-minimal-arty-z7-20-sdt.rootfs.wic.qemu-sd)
echo "$LOOPDEV"
lsblk "$LOOPDEV"

mkdir -p /tmp/arty_boot /tmp/arty_root
sudo mount ${LOOPDEV}p1 /tmp/arty_boot
sudo mount ${LOOPDEV}p2 /tmp/arty_root

ls -lh /tmp/arty_boot
ls -lh /tmp/arty_root | head

sudo umount /tmp/arty_boot
sudo umount /tmp/arty_root
sudo losetup -d "$LOOPDEV"
```

Expected:

```text
partition 1 = FAT boot partition
partition 2 = ext4 rootfs partition
```

---

# 14. Write SD card

Warning: this is destructive.

```bash
lsblk
# insert SD card
lsblk
```

Set the correct card device:

```bash
SDCARD=/dev/sda
lsblk "$SDCARD"
```

Write image:

```bash
cd ~/yocto/rel-v2025.2/edf/build

sudo umount ${SDCARD}1 || true
sudo umount ${SDCARD}2 || true

sudo dd if=tmp/deploy/images/arty-z7-20-sdt/core-image-minimal-arty-z7-20-sdt.rootfs.wic.qemu-sd \
  of=$SDCARD \
  bs=4M \
  status=progress \
  conv=fsync

sync
lsblk "$SDCARD"
sudo fdisk -l "$SDCARD"
sudo eject "$SDCARD"
```

---

# 15. Boot from serial console

```bash
picocom -b 115200 /dev/ttyUSB1
```

Expected:

```text
FSBL starts
U-Boot starts
DRAM: ECC disabled 511 MiB
Linux starts
rootfs mounts
login prompt appears
```

---

# 16. Manual U-Boot boot if `boot.scr` fails

At the `Zynq>` prompt:

```text
mmc dev 0
mmc part
fatls mmc 0:1 /
fatls mmc 0:1 /devicetree
ext4ls mmc 0:2 /
ext4ls mmc 0:2 /boot
```

Expected:

```text
mmc 0:1 = FAT boot partition with BOOT.bin, boot.scr, zImage, uImage, system.dtb
mmc 0:2 = ext4 rootfs partition with /bin, /etc, /usr, /home, ...
```

Manual `zImage` boot:

```text
fatload mmc 0:1 0x02080000 zImage
fatload mmc 0:1 0x02A00000 system.dtb
setenv bootargs console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait earlycon
bootz 0x02080000 - 0x02A00000
```

Manual `uImage` boot if needed:

```text
fatload mmc 0:1 0x02000000 uImage
fatload mmc 0:1 0x02A00000 system.dtb
setenv bootargs console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait earlycon
bootm 0x02000000 - 0x02A00000
```

Do not run `saveenv` during bring-up.

---

# 17. Boot script / filesystem partition fix

The observed failure was:

```text
Found U-Boot script /boot.scr
Checking for kernel:zImage
kernel image zImage not found on mmc 0:2
```

But the actual layout was:

```text
mmc 0:1 = FAT boot partition with BOOT.bin, boot.scr, zImage, uImage, system.dtb
mmc 0:2 = ext4 root filesystem
```

The practical fix is to replace `boot.scr` **inside the generated WIC image before writing the SD card**. This makes the SD card boot automatically without manually typing U-Boot commands.

## 17.1 Create `scripts/patch_arty_z7_wic_bootscr.sh`

```bash
cd ~/fpga_projects/linux-fpga-robot
mkdir -p scripts
cat > scripts/patch_arty_z7_wic_bootscr.sh <<'EOF'
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
    echo "ERROR: mkimage not found. Install u-boot-tools:"
    echo "  sudo apt install u-boot-tools"
    exit 1
fi

cat > "$BOOTCMD" <<'BOOTCMD_EOF'
echo "Booting Arty Z7 from FAT boot partition..."

mmc dev 0
setenv kernel_addr_r 0x02080000
setenv fdt_addr_r    0x02A00000
setenv bootargs console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait earlycon

if fatload mmc 0:1 ${kernel_addr_r} zImage; then
    echo "Loaded zImage from mmc 0:1"
else
    echo "ERROR: could not load zImage from mmc 0:1"
    exit
fi

if fatload mmc 0:1 ${fdt_addr_r} system.dtb; then
    echo "Loaded system.dtb from mmc 0:1"
elif fatload mmc 0:1 ${fdt_addr_r} devicetree/cortexa9-linux.dtb; then
    echo "Loaded devicetree/cortexa9-linux.dtb from mmc 0:1"
else
    echo "ERROR: could not load DTB from mmc 0:1"
    exit
fi

bootz ${kernel_addr_r} - ${fdt_addr_r}
BOOTCMD_EOF

mkimage -A arm -T script -C none -n "Arty Z7 SD boot script" -d "$BOOTCMD" "$BOOTSCRIPT" >/dev/null

LOOP=$(sudo losetup -Pf --show "$IMG")
sudo mount "${LOOP}p1" "$MNT"
sudo cp "$MNT/boot.scr" "$MNT/boot.scr.before-arty-fix" 2>/dev/null || true
sudo cp "$BOOTSCRIPT" "$MNT/boot.scr"
sync

echo "Patched boot.scr inside: $IMG"
EOF

chmod +x scripts/patch_arty_z7_wic_bootscr.sh
```

## 17.2 Use the WIC boot-script patch before imaging

After each successful `bitbake core-image-minimal`, run:

```bash
cd ~/fpga_projects/linux-fpga-robot
./scripts/patch_arty_z7_wic_bootscr.sh
```

This patches the `.wic.qemu-sd` image directly. After that, the SD-card `dd` step writes an image that already has the corrected `boot.scr`.

## 17.3 Manual U-Boot boot remains the fallback

```text
fatload mmc 0:1 0x02080000 zImage
fatload mmc 0:1 0x02A00000 system.dtb
setenv bootargs console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait earlycon
bootz 0x02080000 - 0x02A00000
```

# 18. Validate Linux after boot

After Linux boots, run:

```bash
uname -a
cat /proc/cmdline
mount | grep -E " / |/boot"
cat /proc/device-tree/model; echo
tr '\0' '\n' < /proc/device-tree/compatible
ip link
dmesg | grep -Ei "slcr|clkc|mmcblk|macb|ttyPS0|fpga|error|fail|panic"
```

Expected key results:

```text
model: Digilent Arty Z7-20
compatible includes: xlnx,arty-z7-20 and xlnx,zynq-7000
/dev/mmcblk0p2 mounted on /
/dev/mmcblk0p1 mounted on /boot
```

If `/proc/cmdline` contains `rootwit`, that is a typo. It must be:

```text
rootwait
```

---

# 19. Regeneration and rebuild checklist

Whenever the XSA changes, I repeat the full hardware-to-image sequence.

## 19.1 Regenerate SDT and DTS

```bash
cd ~/fpga_projects/linux-fpga-robot

/opt/Xilinx/2025.2/Vitis/bin/xsct scripts/sdt/gen_arty_z7_20_sdt.tcl

gcc -E -nostdinc -undef -D__DTS__ -x assembler-with-cpp -P \
  -I hw/sdt/arty-z7-20-sdt \
  hw/sdt/arty-z7-20-sdt/system-top.dts \
  -o yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts

./scripts/fix_arty_z7_sdt_dts.py \
  yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts

dtc -I dts -O dtb \
  -o /tmp/arty-test.dtb \
  yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts

fdtget -t s /tmp/arty-test.dtb / compatible
fdtget -t x /tmp/arty-test.dtb /memory reg
fdtget -t s /tmp/arty-test.dtb /memory device_type
```

Required validation:

```text
xlnx,arty-z7-20
xlnx,zynq-7000
100000 1ff00000
memory
```

## 19.2 Repack SDT tarball and update SHA

```bash
cd ~/fpga_projects/linux-fpga-robot

rm -f yocto/meta-linux-fpga-robot/recipes-bsp/sdt-artifacts/files/arty-z7-20-sdt.tar.gz

tar -czf yocto/meta-linux-fpga-robot/recipes-bsp/sdt-artifacts/files/arty-z7-20-sdt.tar.gz \
  -C hw/sdt \
  arty-z7-20-sdt

sha256sum yocto/meta-linux-fpga-robot/recipes-bsp/sdt-artifacts/files/arty-z7-20-sdt.tar.gz
```

Update `SDT_URI[sha256sum]` in:

```text
yocto/meta-linux-fpga-robot/conf/machine/arty-z7-20-sdt.conf
```

## 19.3 Change lab login password, if needed

```bash
cd ~/fpga_projects/linux-fpga-robot
./scripts/update_arty_login_hash.sh

cd ~/yocto/rel-v2025.2/edf/build
MACHINE=arty-z7-20-sdt bitbake -c rootfs -f core-image-minimal
```

## 19.4 Rebuild Yocto artifacts

```bash
cd ~/yocto/rel-v2025.2/edf/build

MACHINE=arty-z7-20-sdt bitbake -c cleansstate sdt-artifacts device-tree u-boot-xlnx
MACHINE=arty-z7-20-sdt bitbake core-image-minimal
```

## 19.5 Verify deployed DTBs before writing SD card

```bash
fdtget -t s tmp/deploy/images/arty-z7-20-sdt/system.dtb / compatible
fdtget -t x tmp/deploy/images/arty-z7-20-sdt/system.dtb /memory reg
fdtget -t s tmp/deploy/images/arty-z7-20-sdt/system.dtb /memory device_type
```

Required:

```text
xlnx,arty-z7-20
xlnx,zynq-7000
100000 1ff00000
memory
```

## 19.6 Patch `boot.scr` inside the WIC image before imaging

```bash
cd ~/fpga_projects/linux-fpga-robot
./scripts/patch_arty_z7_wic_bootscr.sh
```

## 19.7 Write SD card

```bash
cd ~/yocto/rel-v2025.2/edf/build

lsblk
SDCARD=/dev/sda
lsblk "$SDCARD"

sudo umount ${SDCARD}1 2>/dev/null || true
sudo umount ${SDCARD}2 2>/dev/null || true
sudo wipefs -a "$SDCARD"

sudo dd \
  if=tmp/deploy/images/arty-z7-20-sdt/core-image-minimal-arty-z7-20-sdt.rootfs.wic.qemu-sd \
  of="$SDCARD" \
  bs=4M \
  status=progress \
  conv=fsync

sync
sudo eject "$SDCARD"
```

# 20. Current known-good result

The known-good boot result after the DTS fixes was:

```text
U-Boot starts
Model: Digilent Arty Z7-20
DRAM: ECC disabled 511 MiB
Linux starts
rootfs mounts from /dev/mmcblk0p2
/boot mounts from /dev/mmcblk0p1
/proc/device-tree/compatible contains xlnx,arty-z7-20 and xlnx,zynq-7000
lab user eder login works
```

The remaining cleanup is to make the `boot.scr` partition fix fully Yocto-native instead of patching the SD card after imaging.

---

# 21. Notes for Arty Z7-10 or PYNQ-Z1

The method is the same, but these must be regenerated and rechecked:

```text
Vivado board preset
XSA filename
SDT output directory
machine name
root compatible string
DDR range
Ethernet PHY details
SDT tarball name
SDT_URI sha256sum
DTS fixup labels
```

I should not assume that another board emits the same DTS node labels. The safe rule is:

```text
Generate first.
Inspect generated DTS.
Patch only what is proven wrong.
Validate with dtc and fdtget before rebuilding.
```
