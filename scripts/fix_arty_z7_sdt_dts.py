#!/usr/bin/env python3
"""
fix_arty_z7_sdt_dts.py

Post-generation DTS cleanup for the Arty Z7-20 SDT flow.

Fixes:
  1. Ensure root compatible includes:
       "xlnx,arty-z7-20", "xlnx,zynq-7000"

  2. Rename non-DDR memory nodes:
       QSPI: memory@fc000000 -> flash@fc000000
       OCM:  memory@0        -> sram@0
       OCM:  memory@ffff0000 -> sram@ffff0000

     and remove device_type = "memory" from those non-DDR nodes.

  3. Add explicit GEM0 MDIO/PHY description:
       ethernet@e000b000
         phy-handle = <&ethernet_phy0>;
         mdio/ethernet-phy@0 { reg = <0>; };

  4. Leave DDR as the only system memory node:
       memory@00100000 with device_type = "memory";
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
    depth = 0

    for i in range(open_brace_idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i

    raise RuntimeError("Could not find matching closing brace")


def find_labeled_node(text: str, label: str) -> tuple[re.Match[str], int, int]:
    pattern = re.compile(
        rf'(?m)^([ \t]*{re.escape(label)}\s*:\s*)'
        rf'([A-Za-z0-9_,+.\-]+@[A-Fa-f0-9]+)(\s*\{{)'
    )

    match = pattern.search(text)
    if not match:
        raise RuntimeError(f'Could not find labeled node "{label}"')

    open_brace_idx = text.find("{", match.start())
    close_brace_idx = find_matching_brace(text, open_brace_idx)

    return match, open_brace_idx, close_brace_idx


def find_node_by_name(text: str, node_name: str) -> tuple[int, int]:
    """
    Find a DTS node by unit name.

    Supports both:
      ethernet@e000b000 {
      gem0: ethernet@e000b000 {
    """
    pattern = re.compile(
        rf'(?m)^[ \t]*(?:[A-Za-z0-9_]+:\s*)?{re.escape(node_name)}\s*\{{'
    )

    match = pattern.search(text)
    if not match:
        raise RuntimeError(f'Could not find node "{node_name}"')

    open_brace_idx = text.find("{", match.start())
    close_brace_idx = find_matching_brace(text, open_brace_idx)

    return match.start(), close_brace_idx

def patch_node(
    text: str,
    label: str,
    old_unit_name: str,
    new_unit_name: str,
    remove_memory_device_type: bool = True,
) -> tuple[str, bool]:
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


def patch_gem0_phy(text: str) -> tuple[str, bool]:
    """
    Add explicit MDIO/PHY node for Arty Z7 GEM0.

    Live Linux showed GEM0 eventually found:
      RTL8211E at PHY address 0

    The generated DTS had:
      ethernet@e000b000
        xlnx,has-mdio = <1>;
        phy-mode = "rgmii-id";

    but no phy-handle and no mdio/ethernet-phy@0 child.
    """
    node_start, node_end = find_node_by_name(text, "ethernet@e000b000")

    before = text[:node_start]
    node = text[node_start:node_end + 1]
    after = text[node_end + 1:]

    if "phy-handle = <&ethernet_phy0>;" in node and "ethernet_phy0: ethernet-phy@0" in node:
        return text, False

    insert = '''
                        phy-handle = <&ethernet_phy0>;

                        mdio {
                                #address-cells = <0x01>;
                                #size-cells = <0x00>;

                                ethernet_phy0: ethernet-phy@0 {
                                        reg = <0x00>;
                                };
                        };
'''

    patched_node = node[:-1] + insert + node[-1]
    return before + patched_node + after, True


def validate_text(text: str) -> None:
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
        "phy-handle = <&ethernet_phy0>;",
        "ethernet_phy0: ethernet-phy@0",
        "reg = <0x00>;",
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

    text, changed_gem0_phy = patch_gem0_phy(text)

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
    print(f"  GEM0 PHY node fixed:     {changed_gem0_phy}")
    print(f"Updated DTS: {dts_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
