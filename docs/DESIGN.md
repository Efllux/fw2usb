# fw2usb: a FireWire → USB bridge with no Linux inside

Goal: plug FireWire audio interfaces across BeBoB, DICE, Oxford, Fireworks, MOTU,
RME, Digi00x, TASCAM and generic AV/C families into an Apple-silicon Mac
over **plain USB**, with no Thunderbolt dongles, no Mac mini or Raspberry Pi running Linux,
and no kernel driver on the Mac.

## Alternatives considered

| Route | Problem |
|---|---|
| Wire FireWire pins to MCU GPIO | 400 Mb/s data-strobe signalling with analog arbitration. GPIO can't do it, and no clever software makes it possible |
| Pi CM4/Pi 5 + PCIe FireWire card + UAC2 gadget | Works, but it's a whole Linux computer in the middle. Not the goal |
| Pinnacle MovieBox | DV-only firmware, rare second-hand, no audio |
| Tap the I²S inside the interface with a Pico | Loses mixer/routing, Pico is USB full-speed (≈1 MB/s), so fewer than 8 ch @ 24/48 |
| Apple TB→FW adapter chain + ASFireWire | Fine fallback, but it's dongles and DriverKit, not a USB device |

## Architecture

```
 Saffire ──FW400──┐
                  │  6-pin → 9-pin cable
          ┌───────▼────────┐  PHY–LINK interface (IEEE 1394a §5B):
          │ FireWire PHY   │  49.152 MHz SCLK, D[0:7], CTL[0:1], LREQ, LPS, LinkOn
          │ TSB41AB2/BA3   │  — a documented, slow, parallel digital bus
          └───────┬────────┘
          ┌───────▼────────────────────────────────────────────┐
          │ FPGA                                               │
          │  • 1394 link layer: packet TX/RX, CRC, cycle timer │
          │  • cycle master (we're root: send cycle-start/125µs│
          │  • iso RX/TX FIFOs (AMDTP, model = crates/fw-amdtp)│
          │  • async request/response engine (CSR, AV/C, CMP)  │
          │  • audio clock recovery from device SYT → MCLK     │
          └───────┬────────────────────────────────────────────┘
          ┌───────▼────────┐
          │ USB 2.0 HS     │  ULPI PHY (USB3300) driven by the FPGA,
          │ device         │  or an XMOS/STM32H7 fed over TDM
          └───────┬────────┘
                  ▼ USB-C → Mac
```

The key insight: **you don't have to implement the physical layer.** The PHY chip turns the
FireWire cable into a ~49 MHz parallel bus with a fully specified protocol. Everything above
it (the link layer) is digital logic that fits in a cheap FPGA. The JHU dVRK "FPGA1394"
boards already do exactly this (FPGA link layer + discrete TI PHY), with
[open Verilog](https://github.com/jhu-cisst/mechatronics-firmware), so we can study a proven
reference instead of starting from a blank page.

### Three product tiers

The reference adapter supports all audio protocol families through per-family
profiles, plus raw transactions for other devices. Chip-PHY S100/S200/S400 is the
reference path; experimental S100 soft PHY does not set the product speed ceiling.
No Linux runs inside the adapter. USB2 payload and FireWire peak reservations
must both pass admission checks before exposing an audio alternate setting.

1. **Out of the box:** one composite USB configuration includes UAC2 asynchronous
   capture/playback and explicit playback feedback, plus the vendor interface.
   The attached FireWire device is clock master. Use SYT-derived actual rate for
   timestamped AMDTP; custom families need their own timestamp/clock estimator.
   Feedback follows that measured clock, never USB SOF. No SRC. Missing external
   clock causes a reported unlock and bounded stream stop, not silent clock drift.
2. **Companion app:** the vendor-specific interface is always present in that
   same configuration. Mixer, routing, clock, sample-rate, configuration and
   update preparation use it while audio continues. Rate/layout changes requiring
   new descriptors require an explicit stopped-stream transition; mixer writes
   cannot silently reset the bus or USB device. See [control protocol](protocol/control.md).
3. **Raw FireWire port:** explicit app command persists the selected personality,
   quiesces DMA and re-enumerates with a different PID. UAC2 is absent in raw mode.
   Hold the physical button at plug-in to override persistence and recover tier 1.
   A libraw1394-compatible shim over libusb supplies FFADO's raw access; investigate
   its other Linux dependencies before claiming drop-in FFADO compatibility.
   A CoreAudio AudioServerPlugIn supplies user-space Mac audio without DriverKit
   entitlement. Signing, installation and Apple Silicon hosting still need a
   working prototype. A Linux kernel driver is a later option. Raw mode can support
   obscure audio, SBP-2 storage, DV and HDV through separate host protocol stacks;
   tunneling alone does not mount a disk or create an OS camera device.

Raw-link is built early as the diagnostic path. The tiers describe user experience,
not three simultaneous audio engines. USB2 cannot transparently forward full
FireWire S800 line rate. See [raw protocol](protocol/raw-tunnel.md).

### Updates and recovery

Expose USB DFU runtime detach in either personality. Enter a dedicated DFU
configuration only after stopping streams; updating flash is not an uninterrupted
live-audio operation. Use two SPI image slots plus a write-protected factory golden
image, with ECP5 multiboot/fallback supervised by the boot controller. Exact flash
map, bitstream offsets and watchdog fallback mechanism require board selection.
An FPGA configuration CRC detects damage, not authenticity.

Proposed signed manifest: canonical CBOR with schema, board ID/revision, component,
version, monotonic security epoch, length, SHA-256 payload digest and dependencies;
Ed25519 signature over a domain separator and the canonical manifest. Verify with
an immutable boot trust anchor before marking a slot pending. Boot pending once,
require health acknowledgement, then atomically commit; interrupted download or
failed self-test rolls back. Duplicate journal records with sequence/CRC tolerate
power loss. Rollback protection needs protected monotonic storage; plain SPI flash
alone cannot enforce it against physical rewriting. Define offline root rotation
and recovery authorization before production. Golden recovery must validate updates
and must never be overwritten by normal DFU.

Profiles are separately signed, bounded data blobs, independently versioned from
firmware/gateware. No arbitrary downloaded code or vendor binaries. Firmware
interprets a finite allowlisted operation set; length, ranges and timeouts are
validated before applying register operations. See [profile schema](protocol/profiles.md).

### Clocking (the hard part, and the plan for it)

- Let the **Saffire be the clock master** (internal clock). Its transmitted SYT timestamps
  tell us its true sample rate in 24.576 MHz bus ticks.
- The FPGA measures SYT progression and drives an NCO/fractional PLL (or an external
  Si5351/CS2100) to produce an audio MCLK locked to the Saffire.
- The USB side runs **UAC2 asynchronous**: the feedback endpoint reports our actual rate
  to the Mac, so the Mac adapts. No sample-rate conversion anywhere.
- Our transmitted (playback) stream gets SYT = event time + transfer delay. That's
  `fw_amdtp::stream::PacketBuilder` / `SytScheduler`, which is exact for 44.1k.

### Bus roles we must implement because there's no OHCI/Linux

With only two nodes, we will usually be root (we can force it with the PHY's RHB bit +
PHY config packet), so we must provide:
- **Cycle master**: a cycle-start packet every 125 µs carrying our cycle timer.
- **IRM / bus manager CSRs**: `BANDWIDTH_AVAILABLE`, `CHANNELS_AVAILABLE`, `BUS_MANAGER_ID`
  (BeBoB firmware may lock-compare-swap these before streaming).
- **Self-ID handling, config ROM** (ours, small) and reading the device's config ROM.
- **CMP**: write the device's oPCR/iPCR (0xFFFF_F000_0904 / 0x0984) to start streams.
- **AV/C (FCP)** commands for sample rate / plug formats (FFADO's BeBoB code documents
  these for the Saffire PRO 10/26).

## Research: no PHY chip at all

We're also exploring an FPGA "soft PHY" at S100 with a small analog front-end, which would remove the
dependency on obsolete PHY chips. See [SOFT-PHY.md](SOFT-PHY.md).

## Hardware bring-up plan

| Phase | Hardware | Proves | Rough cost |
|---|---|---|---|
| 0 | none | `fw-amdtp` packet model + tests (**done**) | €0 |
| 1 | FPGA board w/ ≥30 free IOs (e.g. iCE40/ECP5 board, or Tang Primer) + **TSB41AB2** module or a PHY chip lifted from an old **PCI** FireWire card that has a separate PHY (TSB41AB1/2 next to a TSB12LV2x link chip) | Bus reset, self-ID, our node seen by the Saffire, read its config ROM | €25–60 |
| 2 | same + logic analyser on PHY-LINK bus | Async read/write/lock, become cycle master, CMP connect, receive iso stream → dump over UART | — |
| 3 | + USB3300 ULPI module (≈€5) | Raw-link mode over USB HS; Rust host tool on the Mac records audio to WAV | €5 |
| 4 | — | UAC2 async firmware personality; class-compliant recording/playback | — |
| 5 | custom PCB: PHY + small FPGA + ULPI + FW400 socket + 12 V for bus power | the actual dongle | ~€40–80 per proto run |

PHY notes: TSB41AB2 is obsolete at TI but widely available as pulls/old stock; it's 1394a
(matches FW400 directly). TSB41BA3F-EP is still active (1394b, bilingual ports, talks to
1394a devices) but pricier and EP-grade. Old PCI cards with discrete PHY + link chips are the
cheapest source and give you a known-good PHY layout to tap.

## Open questions to settle next
- Exact interface model you'll buy first (PRO 10 vs PRO 26 vs Pro 40: BeBoB vs DICE affects
  the control protocol; DICE is a different stream-start sequence).
- FPGA family: I'd use **ECP5 or iCE40-UP** for the fully open toolchain (yosys/nextpnr), and
  the link layer could be written in Amaranth/SpinalHDL or plain Verilog.
- Whether bus power is needed (Saffire PRO 10/26 have their own PSU, so no).
