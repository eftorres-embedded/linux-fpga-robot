# Arty Z7 EDF / Yocto Current Change Log

## Purpose

This note captures the current working state of the Arty Z7 EDF / Yocto bring-up and the project-side changes that were added to make the image boot correctly.

Current board:

```text
Digilent Arty Z7-20
Zynq-7000 / XC7Z020
Machine: arty-z7-20-sdt
EDF / Yocto: rel-v2025.2
Host: Ubuntu 22.04
```

Main repo:

```text
~/fpga_projects/linux-fpga-robot
```

EDF build directory:

```text
~/yocto/rel-v2025.2/edf/build
```

Custom Yocto layer:

```text
~/fpga_projects/linux-fpga-robot/yocto/meta-linux-fpga-robot
```

---

# 1. Current confirmed working result

The Arty Z7-20 now boots from SD card into Linux.

Confirmed working:

```text
SD card image boots
FSBL starts
U-Boot starts
U-Boot detects DDR correctly: 511 MiB
Linux starts
Root filesystem mounts from /dev/mmcblk0p2
Lab user/password login works
Ethernet link comes up
DHCP assigns an IP address
Internet ping works
DNS works
```

Validated Ethernet result:

```text
end0: UP, LOWER_UP
DHCP address: 192.168.50.7/24
Default gateway: 192.168.50.1
Gateway ping: OK
8.8.8.8 ping: OK
google.com ping: OK
```

The important Linux validation commands used were:

```bash
uname -a
cat /proc/cmdline
mount | grep -E " / |/boot"
cat /proc/device-tree/model; echo
tr '\0' '\n' < /proc/device-tree/compatible
ip link
ip addr show end0
ip route
ping -c 4 192.168.50.1
ping -c 4 8.8.8.8
ping -c 4 google.com
```

Expected key results:

```text
/proc/device-tree/model:
  Digilent Arty Z7-20

/proc/device-tree/compatible:
  xlnx,arty-z7-20
  xlnx,zynq-7000

rootfs:
  /dev/mmcblk0p2 mounted on /

boot partition:
  /dev/mmcblk0p1 mounted on /boot
```

---

# 2. Custom Yocto layer and machine

The project uses a custom layer:

```text
yocto/meta-linux-fpga-robot
```

Expected layer structure:

```text
yocto/meta-linux-fpga-robot/
├── conf/
│   ├── layer.conf
│   ├── machine/
│   │   └── arty-z7-20-sdt.conf
│   └── dts/
│       └── arty-z7-20-sdt/
│           ├── cortexa9-linux.dts
│           └── arty-z7-20-sdt-system-conf.dtsi
├── recipes-bsp/
│   └── sdt-artifacts/
│       ├── sdt-artifacts.bbappend
│       └── files/
│           └── arty-z7-20-sdt.tar.gz
└── recipes-core/
    └── images/
        └── core-image-minimal.bbappend
```

The custom machine is:

```text
yocto/meta-linux-fpga-robot/conf/machine/arty-z7-20-sdt.conf
```

It started by inheriting the ZC702 SDT machine as a bootstrap, then overrides the parts needed for Arty Z7 hardware.

The machine file should contain the local SDT artifact override:

```bitbake
# Use locally generated Arty Z7-20 SDT artifacts instead of inherited ZC702 SDT.
SDT_URI = "file://arty-z7-20-sdt.tar.gz"
SDT_URI[sha256sum] = "PASTE_SHA256_HERE"
SDT_URI[S] = "${WORKDIR}/arty-z7-20-sdt"
```

It should also force the Arty DTS wrapper:

```bitbake
# Use Arty Z7-20 Linux device-tree wrapper instead of inherited ZC702 wrapper.
CONFIG_DTFILE_DIR := "${@bb.utils.which(d.getVar('BBPATH'), 'conf/dts/arty-z7-20-sdt')}"
CONFIG_DTFILE = "${CONFIG_DTFILE_DIR}/cortexa9-linux.dts"
```

And it uses the Arty-specific standalone/libxil config if the FSBL BSP pulls in invalid inherited drivers:

```bitbake
# Use Arty-specific standalone/libxil config instead of inherited ZC702 config.
LIBXIL_CONFIG = "conf/machine/include/arty-z7-20-sdt/arty-z7-20-sdt-cortexa9-fsbl-libxil.conf"
```

---

# 3. SDT / DTS flow currently used

The XSA is generated from Vivado and saved under the project repo:

```text
~/fpga_projects/linux-fpga-robot/hw/xsa/arty_z7_20_base.xsa
```

The SDT output is generated from the XSA:

```text
~/fpga_projects/linux-fpga-robot/hw/sdt/arty-z7-20-sdt
```

The SDT artifact is packaged into the custom Yocto layer:

```text
yocto/meta-linux-fpga-robot/recipes-bsp/sdt-artifacts/files/arty-z7-20-sdt.tar.gz
```

The flattened Linux DTS is stored here:

```text
yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts
```

Flatten command:

```bash
cd ~/fpga_projects/linux-fpga-robot

gcc -E -nostdinc -undef -D__DTS__ -x assembler-with-cpp -P \
  -I hw/sdt/arty-z7-20-sdt \
  hw/sdt/arty-z7-20-sdt/system-top.dts \
  -o yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts
```

After flattening, run the DTS fixup script:

```bash
./scripts/fix_arty_z7_sdt_dts.py \
  yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts
```

---

# 4. DTS fixups currently required

Three DTS fixes are required after SDT generation.

## 4.1 Root compatible fix

The generated root compatible was missing the Zynq family compatible.

Bad:

```dts
compatible = "xlnx,arty-z7-20";
```

Good:

```dts
compatible = "xlnx,arty-z7-20", "xlnx,zynq-7000";
```

Without this, Linux crashed during Zynq clock initialization:

```text
Zynq clock init
Unable to handle kernel NULL pointer dereference
PC is at clk_register_zynq_pll
```

## 4.2 Memory node fix

The SDT-generated DTS emitted several non-DDR regions as root-level memory nodes:

```text
QSPI linear flash: memory@fc000000
PS RAM / OCM:      memory@0
PS RAM / OCM:      memory@ffff0000
DDR:               memory@00100000
```

U-Boot selected the wrong `/memory` node when QSPI appeared as `device_type = "memory"`.

Bad U-Boot result:

```text
/memory reg -> fc000000 1000000
```

Good U-Boot/Linux result:

```text
/memory reg -> 100000 1ff00000
/memory device_type -> memory
```

The fix is:

```text
ps7_qspi_linear_0_memory: memory@fc000000 -> flash@fc000000
ps7_ram_0_memory:         memory@0        -> sram@0
ps7_ram_1_memory:         memory@ffff0000 -> sram@ffff0000
```

Remove `device_type = "memory";` from those non-DDR nodes.

Leave DDR as the only root-level memory node with:

```dts
device_type = "memory";
```

## 4.3 GEM0 Ethernet PHY fix

Linux originally paused about 38 seconds after:

```text
CAN device driver interface
```

Before the fix:

```text
[    0.604050] CAN device driver interface
[   38.688289] macb e000b000.ethernet eth0: Cadence GEM rev ...
```

The live device tree showed GEM0 had:

```text
compatible = "xlnx,zynq-gem", "cdns,gem"
status = "okay"
phy-mode = "rgmii-id"
xlnx,has-mdio = <1>
```

but it did not have:

```text
phy-handle
mdio child node
ethernet-phy@0 child node
```

The fix added an explicit PHY node under GEM0:

```dts
phy-handle = <&ethernet_phy0>;

mdio {
        #address-cells = <0x01>;
        #size-cells = <0x00>;

        ethernet_phy0: ethernet-phy@0 {
                reg = <0x00>;
        };
};
```

After the fix:

```text
[    0.603927] CAN device driver interface
[    0.739873] macb e000b000.ethernet eth0: Cadence GEM rev ...
```

Ethernet was then confirmed working:

```text
Link is Up - 1Gbps/Full
DHCP assigned 192.168.50.7/24
Internet and DNS pings passed
```

---

# 5. Current `fix_arty_z7_sdt_dts.py` purpose

The script is stored at:

```text
scripts/fix_arty_z7_sdt_dts.py
```

It should be committed and reused every time `cortexa9-linux.dts` is regenerated.

It currently performs these fixes:

```text
1. Adds root compatible "xlnx,zynq-7000".
2. Converts QSPI linear flash from memory@fc000000 to flash@fc000000.
3. Converts PS RAM / OCM memory@0 and memory@ffff0000 to sram nodes.
4. Removes device_type = "memory" from non-DDR memory-like nodes.
5. Adds explicit GEM0 MDIO/PHY node for PHY address 0.
6. Validates that DDR remains the only real /memory node.
```

Run it with:

```bash
cd ~/fpga_projects/linux-fpga-robot

./scripts/fix_arty_z7_sdt_dts.py \
  yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts
```

Validate with:

```bash
dtc -I dts -O dtb \
  -o /tmp/arty-fixed-test.dtb \
  yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts

fdtget -t s /tmp/arty-fixed-test.dtb / compatible
fdtget -t x /tmp/arty-fixed-test.dtb /memory reg
fdtget -t s /tmp/arty-fixed-test.dtb /memory device_type
fdtget -t s /tmp/arty-fixed-test.dtb /axi/ethernet@e000b000 phy-mode
fdtget -t x /tmp/arty-fixed-test.dtb /axi/ethernet@e000b000/mdio/ethernet-phy@0 reg
```

Required:

```text
xlnx,arty-z7-20
xlnx,zynq-7000
100000 1ff00000
memory
rgmii-id
0
```

---

# 6. Lab login user and password changes

A lab-only login user was added through a `core-image-minimal.bbappend` rootfs postprocess hook.

File:

```text
yocto/meta-linux-fpga-robot/recipes-core/images/core-image-minimal.bbappend
```

The `.bbappend` expects these private variables in the EDF build `local.conf`:

```text
~/yocto/rel-v2025.2/edf/build/conf/local.conf
```

Expected local variables:

```bitbake
# Lab-only login setup for Arty Z7 bring-up.
# Do not commit this file.

ARTY_USER = "eder"
ARTY_PASS_HASH = "SHA512_CRYPT_HASH_HERE"
```

A helper script was created to update the hash without copy/paste mistakes:

```text
scripts/update_arty_login_hash.sh
```

Run it with:

```bash
cd ~/fpga_projects/linux-fpga-robot
./scripts/update_arty_login_hash.sh
```

Then rebuild the rootfs/image:

```bash
cd ~/yocto/rel-v2025.2/edf/build

MACHINE=arty-z7-20-sdt bitbake -c rootfs -f core-image-minimal
MACHINE=arty-z7-20-sdt bitbake core-image-minimal
```

Verify root and user hashes exist in the generated rootfs:

```bash
grep '^eder:' tmp/work/arty_z7_20_sdt-amd-linux-gnueabi/core-image-minimal/*/rootfs/etc/passwd
grep '^eder:' tmp/work/arty_z7_20_sdt-amd-linux-gnueabi/core-image-minimal/*/rootfs/etc/shadow
grep '^root:' tmp/work/arty_z7_20_sdt-amd-linux-gnueabi/core-image-minimal/*/rootfs/etc/shadow
```

Important notes:

```text
The password does not change unless update_arty_login_hash.sh is run or ARTY_PASS_HASH is edited.
A normal bitbake rebuild does not generate a new password.
local.conf must not be committed.
The password/hash is lab-only.
```

---

# 7. Boot script / partition fix

The generated boot script originally failed because it searched for the kernel on the rootfs partition:

```text
Found U-Boot script /boot.scr
Checking for kernel:zImage
kernel image zImage not found on mmc 0:2
```

Actual partition layout:

```text
mmc 0:1 = FAT boot partition with BOOT.bin, boot.scr, zImage, uImage, system.dtb
mmc 0:2 = ext4 root filesystem
```

Manual boot command that proved the correct layout:

```text
fatload mmc 0:1 0x02080000 zImage
fatload mmc 0:1 0x02A00000 system.dtb
setenv bootargs console=ttyPS0,115200 root=/dev/mmcblk0p2 rw rootwait earlycon
bootz 0x02080000 - 0x02A00000
```

A helper script now patches the generated WIC image before writing the SD card:

```text
scripts/patch_arty_z7_wic_bootscr.sh
```

Run after each full image build:

```bash
cd ~/fpga_projects/linux-fpga-robot
./scripts/patch_arty_z7_wic_bootscr.sh
```

This script installs a corrected `boot.scr` into partition 1 of:

```text
~/yocto/rel-v2025.2/edf/build/tmp/deploy/images/arty-z7-20-sdt/core-image-minimal-arty-z7-20-sdt.rootfs.wic.qemu-sd
```

The corrected `boot.scr` loads:

```text
zImage     from mmc 0:1
system.dtb from mmc 0:1
rootfs     from /dev/mmcblk0p2
```

---

# 8. Current rebuild sequence after DTS or login changes

From the repo:

```bash
cd ~/fpga_projects/linux-fpga-robot

./scripts/fix_arty_z7_sdt_dts.py \
  yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts
```

Validate DTS:

```bash
dtc -I dts -O dtb \
  -o /tmp/arty-fixed-test.dtb \
  yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts

fdtget -t s /tmp/arty-fixed-test.dtb / compatible
fdtget -t x /tmp/arty-fixed-test.dtb /memory reg
fdtget -t s /tmp/arty-fixed-test.dtb /memory device_type
fdtget -t s /tmp/arty-fixed-test.dtb /axi/ethernet@e000b000 phy-mode
fdtget -t x /tmp/arty-fixed-test.dtb /axi/ethernet@e000b000/mdio/ethernet-phy@0 reg
```

Rebuild affected Yocto pieces:

```bash
cd ~/yocto/rel-v2025.2/edf/build

MACHINE=arty-z7-20-sdt bitbake -c cleansstate device-tree u-boot-xlnx
MACHINE=arty-z7-20-sdt bitbake core-image-minimal
```

Verify deployed DTB:

```bash
fdtget -t s tmp/deploy/images/arty-z7-20-sdt/system.dtb / compatible
fdtget -t x tmp/deploy/images/arty-z7-20-sdt/system.dtb /memory reg
fdtget -t s tmp/deploy/images/arty-z7-20-sdt/system.dtb /memory device_type
fdtget -t s tmp/deploy/images/arty-z7-20-sdt/system.dtb /axi/ethernet@e000b000 phy-mode
fdtget -t x tmp/deploy/images/arty-z7-20-sdt/system.dtb /axi/ethernet@e000b000/mdio/ethernet-phy@0 reg
```

Patch the WIC boot script:

```bash
cd ~/fpga_projects/linux-fpga-robot
./scripts/patch_arty_z7_wic_bootscr.sh
```

Then write the SD card.

---

# 9. SD card imaging command

Warning: this is destructive. Confirm the SD card device with `lsblk` first.

```bash
cd ~/yocto/rel-v2025.2/edf/build

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

---

# 10. Serial console command

Use:

```bash
sudo picocom -b 115200 /dev/ttyUSB1
```

If needed, check ports:

```bash
ls /dev/ttyUSB*
```

Exit picocom:

```text
Ctrl-A
Ctrl-X
```

---

# 11. Git commits to make

After confirming the current boot and Ethernet result, commit the project-side changes:

```bash
cd ~/fpga_projects/linux-fpga-robot

git status

git add scripts/fix_arty_z7_sdt_dts.py
git add scripts/patch_arty_z7_wic_bootscr.sh
git add scripts/update_arty_login_hash.sh
git add yocto/meta-linux-fpga-robot/recipes-core/images/core-image-minimal.bbappend
git add yocto/meta-linux-fpga-robot/conf/dts/arty-z7-20-sdt/cortexa9-linux.dts

git commit -m "Fix Arty Z7 SD boot, login, DTS memory, and Ethernet PHY"
```

Do not commit:

```text
~/yocto/rel-v2025.2/edf/build/conf/local.conf
```

because it contains the private lab password hash.

---

# 12. Remaining cleanup items

The system works, but these are still cleanup items:

```text
1. Make boot.scr generation Yocto-native instead of patching the WIC image after build.
2. Add a stable MAC address or proper MAC-source handling instead of random/generated MAC.
3. Consider adding sudo/wheel support only if needed; current lab user is a normal user.
4. Clean up DTS warnings only after the main boot path is stable.
5. Turn the WIC boot script patch into a recipe or bbappend.
6. Re-run full validation whenever the Vivado XSA/SDT is regenerated.
```

---

# 13. Known-good boot milestone summary

Known-good state reached:

```text
U-Boot:
  Model: Digilent Arty Z7-20
  DRAM: ECC disabled 511 MiB

Linux:
  Boots from zImage + system.dtb on FAT partition
  Rootfs mounts from /dev/mmcblk0p2
  Login works for lab user/root password setup

Device tree:
  compatible includes xlnx,arty-z7-20 and xlnx,zynq-7000
  /memory resolves to DDR at 0x00100000 size 0x1ff00000
  GEM0 has rgmii-id and explicit ethernet-phy@0

Ethernet:
  end0 link up at 1 Gbps full duplex
  DHCP IP: 192.168.50.7/24
  Gateway ping OK
  Internet ping OK
  DNS OK
```
