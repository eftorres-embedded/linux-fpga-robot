#!/usr/bin/env python3
"""
fix_arty_z7_sdt_dts.py

Post-generation DTS cleanup for the Arty Z7-20 SDT flow.

Purpose:
  Convert SDTGen's raw system DTS into a Linux/U-Boot-safe DTS.

Fixes:
  1. Ensure root compatible includes "xlnx,zynq-7000".
  2. Rename QSPI linear flash node:
       memory@fc000000 -> flash@fc000000
     and remove device_type = "memory" from that node.
  3. Rename PS RAM / OCM nodes:
       memory@0        -> sram@0
       memory@ffff0000 -> sram@ffff0000
     and remove device_type = "memory" from those nodes.
  4. Leave DDR as the only system memory node:
       memory@00100000 with device_type = "memory".

This script intentionally does not modify vendor files under /opt/Xilinx.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


ROOT_COMPAT_OLD_RE = re.compile(
    r'compatible\s*=\s*"xlnx,arty-z7-20"\s*;',
)

ROOT_COMPAT_NEW = (
    'compatible = "xlnx,arty-z7-20", "xlnx,zynq-7000";'
)


def replace_root_compatible(text: str) -> tuple[str, bool]:
    """Ensure root compatible has both board and Zynq family strings."""
    if '"xlnx,zynq-7000"' in text:
        return text, False

    new_text, count = ROOT_COMPAT_OLD_RE.subn(ROOT_COMPAT_NEW, text, count=1)
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
    """
    pattern = re.compile(
        rf'({re.escape(label)}\s*:\s*){re.escape(old_unit_name)}(\s*\{{)'
    )

    match = pattern.search(text)
    if not match:
        # Already patched?
        already = re.search(
            rf'{re.escape(label)}\s*:\s*{re.escape(new_unit_name)}\s*\{{',
            text,
        )
        if already:
            return text, False

        raise RuntimeError(
            f"Could not find node '{label}: {old_unit_name}'"
        )

    open_brace_idx = text.find("{", match.start())
    close_brace_idx = find_matching_brace(text, open_brace_idx)

    before = text[: match.start()]
    node = text[match.start() : close_brace_idx + 1]
    after = text[close_brace_idx + 1 :]

    node = pattern.sub(rf"\1{new_unit_name}\2", node, count=1)

    if remove_memory_device_type:
        node, removed = re.subn(
            r'\n[ \t]*device_type\s*=\s*"memory"\s*;',
            "",
            node,
            count=1,
        )
        if removed != 1:
            raise RuntimeError(
                f'Node "{label}" did not contain device_type = "memory";'
            )

    return before + node + after, True


def validate_text(text: str) -> None:
    """Basic text-level validation before writing."""
    required = [
        '"xlnx,zynq-7000"',
        "ps7_qspi_linear_0_memory: flash@fc000000",
        "ps7_ram_0_memory: sram@0",
        "ps7_ram_1_memory: sram@ffff0000",
        "ps7_ddr_0_memory: memory@00100000",
    ]

    for token in required:
        if token not in text:
            raise RuntimeError(f"Validation failed: missing {token}")

    # Ensure the known bad labels are no longer memory@ nodes.
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
