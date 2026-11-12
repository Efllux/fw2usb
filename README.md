# fw2usb: an open FireWire → USB adapter

Apple removed FireWire from macOS, Thunderbolt-to-FireWire dongles are discontinued, and
USB-C laptops never had it. Meanwhile there are thousands of excellent FireWire audio
interfaces, DV cameras and drives collecting dust.

**fw2usb is an open-hardware, open-source adapter that makes a FireWire device show up as a
normal USB device.** No Linux computer hidden in a box, no Thunderbolt dongle chain, no kernel
driver on your computer.

```
FireWire device ─ FW400/800 ─▶ [ PHY chip ─ FPGA link layer ─ USB 2.0 HS ] ─ USB-C ─▶ Mac / PC / Linux
```

- **Audio interfaces across all families** (BeBoB, DICE, Oxford, Fireworks, MOTU, RME, Digi, TASCAM and generic AV/C): the adapter presents itself as a
  class-compliant USB Audio 2.0 device, so it works with the OS's built-in driver.
- **Universal "raw link" mode**: FireWire packets tunnelled over USB to an open Rust host
  library, so disks, DV cameras and other devices can be supported in user-space software.

Three tiers: class-compliant UAC2 async audio out of the box; an always-present
companion interface for mixer/routing/configuration; and an explicit persistent
switch to a different USB PID for raw FireWire tunneling. Hold the button at plug-in
for audio-mode recovery. Profiles and signed DFU updates are planned; none of these
USB personalities is implemented yet. See [architecture](docs/DESIGN.md).

## Status

🧪 **Early: design + protocol core. No working hardware yet.** This is the best moment to
join and shape it.

| Piece | State |
|---|---|
| [Design](docs/DESIGN.md) | first draft |
| `crates/fw-amdtp` (audio packet format, timing) | ✅ tested |
| `crates/fw-phy-model` (soft-PHY research model) | ✅ tested, early |
| `gateware/` (FPGA 1394 link layer) | not started |
| `host/` (Rust host tools) | not started |
| `hardware/` (PCB) | not started |

See the [roadmap](ROADMAP.md) and the [device list](docs/DEVICES.md).

## How you can help

You don't need to be an FPGA wizard. We need:
- **People with FireWire devices** who can capture traffic or test builds → add yours to [DEVICES.md](docs/DEVICES.md)
- **FPGA / HDL** folks (link layer, USB ULPI)
- **Rust** developers (protocol, host tools, firmware)
- **PCB designers** (the eventual dongle)
- **Protocol archaeologists**: AV/C, BeBoB, DICE, SBP-2 know-how

Start with [CONTRIBUTING.md](CONTRIBUTING.md).

## Licensing

- Software, firmware and gateware: **MIT OR Apache-2.0**
- Hardware designs (`hardware/`): **CERN-OHL-S v2** (strongly reciprocal: anyone may build and sell adapters, but modified designs must be published under the same licence)

## Building

```sh
cargo test
```
