# SoC FPGA Robot Platform

## Current Status
Early platform bring-up. Initial focus is Linux boot, Ethernet, and first PS-to-PL peripheral integration.

## Overview
This project is a Linux-capable mobile robotics platform built around the **Arty Z7**. The long-term goal is a mecanum-wheel robot that combines embedded Linux, custom FPGA peripherals, and networked operation in a way that is practical to build, test, and extend over time.

The system is split along natural strengths:

- **Processing System (PS / Arm)** handles Linux, networking, application logic, and higher-level control.
- **Programmable Logic (PL / FPGA)** handles custom peripherals, deterministic timing, and hardware acceleration.

The first version of the platform is intentionally focused on a stable bring-up path:

- boot Linux from SD card
- get serial console and Ethernet working
- prove one custom AXI4-Lite peripheral from Linux userspace

Once that base is reliable, the platform will expand toward motor control, sensor integration, and webcam streaming.

## Planned Toolchain
- Vivado 2025.2
- PetaLinux 2025.2
- Ubuntu 22.04.5 LTS
- Target board: Arty Z7-20

---

## Project Goals

### Near-term goals
- Bring up a reproducible Linux image on the Arty Z7
- Create a clean Vivado + PetaLinux workflow on Ubuntu
- Establish PS-to-PL communication through AXI
- Expose at least one custom FPGA peripheral to Linux
- Build a simple userspace test application to read/write FPGA registers

### Mid-term goals
- Integrate PWM-based motor control for mecanum drive
- Add custom SPI and I2C peripherals in PL
- Validate sensor/control paths from Linux to FPGA and back
- Establish a clean software interface for robot services

### Long-term goals
- Add webcam support and network streaming
- Build remote control and telemetry features
- Refine the robot platform into a clean portfolio-grade system

---

## Why this project matters
This project is meant to demonstrate more than just FPGA design or Linux bring-up in isolation. The value of the platform comes from combining:

- custom RTL design
- AXI-based integration
- embedded Linux deployment
- hardware/software partitioning
- structured bring-up and validation

The end result should be a system that is technically solid, easy to explain, and strong enough to serve as a portfolio anchor.

---

## System Architecture

```text
                         +--------------------------------+
                         |         Arty Z7 (Zynq)         |
                         |                                |
                         |  +--------------------------+  |
 Remote Access /         |  |   PS: Dual-core Arm      |  |
 Network / Control  <--> |  |  Linux + app services    |  |
                         |  +-----------+--------------+  |
                         |              | AXI             |
                         |  +-----------v--------------+  |
                         |  |   PL: Custom FPGA logic  |  |
                         |  |                          |  |
                         |  |  - AXI4-Lite slaves      |  |
                         |  |  - PWM / motor control   |  |
                         |  |  - SPI / I2C peripherals |  |
                         |  |  - future encoder logic  |  |
                         |  +--------------------------+  |
                         +--------------------------------+
```

### Planned partitioning

**PS / Linux side**
- boot flow and platform services
- Ethernet / networking
- shell access / SSH
- application logic
- robot coordination and telemetry
- userspace access to custom peripherals

**PL / FPGA side**
- AXI4-Lite peripherals
- PWM generation
- SPI and I2C custom hardware blocks
- future timing-sensitive interfaces
- future motor/encoder support

---

## Bring-Up Strategy

The project will move in layers so each step leaves behind a working checkpoint.

### Phase 1 — Linux platform baseline
- Create Vivado hardware platform for Arty Z7
- Export XSA
- Create and configure PetaLinux project
- Boot Linux from SD card
- Confirm UART console, login, and Ethernet

**Exit condition:** the board boots Linux reliably and is reachable over serial/Ethernet.

### Phase 2 — First custom PL peripheral
- Add one simple AXI4-Lite peripheral in PL
- Rebuild hardware platform and import into PetaLinux
- Update device tree / userspace access path
- Verify register reads and writes from Linux

**Exit condition:** Linux can interact with a custom FPGA register block.

### Phase 3 — Motion control foundation
- Integrate PWM peripheral for motor output
- Define register interface for direction, enable, and duty control
- Validate outputs in hardware before attaching motors

**Exit condition:** Linux can command PWM outputs through the FPGA fabric.

### Phase 4 — Sensor and control expansion
- Add SPI and I2C peripheral blocks
- Validate device communication paths
- Build lightweight control applications

**Exit condition:** Linux can drive sensors/actuators through custom PL peripherals.

### Phase 5 — Robot platform integration
- Add drivetrain hardware
- Add mecanum control logic in software
- Introduce streaming camera support and network services
- Build a presentable demo workflow

**Exit condition:** the robot moves under software control and exposes a clean Linux-based interface.

---

## Early Success Criteria

The project should count as a meaningful success well before the final robot is complete. Good early checkpoints include:

- Vivado project builds cleanly
- PetaLinux image boots from SD
- serial console is stable
- Ethernet link comes up
- custom AXI peripheral is accessible from Linux
- one userspace test utility successfully reads/writes hardware registers

These checkpoints reduce risk and keep the project moving even before the full robot is assembled.

---

## Development Notes

### Design principles
- Prefer small, testable steps over large jumps
- Keep hardware interfaces simple and explicit
- Avoid adding multiple unknowns at the same time
- Preserve working states before major changes
- Treat board bring-up as part of the product, not just setup work

### Initial software approach
For early Linux-to-FPGA interaction, keep the software path simple and transparent. The priority is to prove that Linux can reliably access custom peripherals and that the hardware/software boundary is well understood.

### Initial hardware approach
Start with one small AXI4-Lite peripheral before integrating the full set of custom cores. Once that path is proven, add PWM first, then SPI/I2C, then more advanced interfaces.

---

## Verification Mindset

Each stage should end with something that can be demonstrated, repeated, and checked quickly.

Examples:
- **Boot validation:** Linux consistently reaches login prompt
- **Network validation:** board acquires IP address and responds over Ethernet
- **Peripheral validation:** register transactions behave as expected from Linux
- **PWM validation:** duty/enable changes match expected waveforms
- **Sensor validation:** custom bus transactions return stable device responses

The project should always have at least one known-good checkpoint that can be returned to if a later change breaks the system.

---

## Proposed Repository Layout

```text
soc-fpga-robot/
├── README.md
├── docs/
│   ├── notebook/
│   ├── diagrams/
│   └── bringup/
├── vivado/
│   └── soc_fpga_robot/
├── petalinux/
│   └── soc_fpga_robot/
├── rtl/
│   ├── common/
│   ├── axi/
│   ├── pwm/
│   ├── spi/
│   ├── i2c/
│   ├── motor/
│   └── top/
├── constraints/
├── tb/
├── sw/
│   ├── userspace/
│   └── utilities/
└── scripts/
```

This layout keeps hardware, Linux, software, and documentation close enough to evolve together without becoming mixed together.

## Immediate Next Steps

1. Create the Vivado base hardware platform for the Arty Z7
2. Export the XSA for PetaLinux
3. Create the PetaLinux project and confirm Linux boots from SD
4. Document the boot and build flow as it becomes stable
5. Add one minimal AXI4-Lite peripheral as the first PS-to-PL integration milestone

## Version 1 Scope

Version 1 is not the finished robot. It is the first stable platform release with:

- Linux booting from SD card
- Ethernet working
- at least one custom FPGA peripheral mapped and exercised from Linux
- a documented bring-up flow that can be repeated from a clean setup

That foundation will make the later robot-specific work faster, cleaner, and easier to explain.

## Project Notes

This platform is expected to grow in layers. Each new capability should build on a working baseline so the system evolves as a continuation of a stable platform rather than a restart.