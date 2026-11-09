# fw2usb: a FireWire → USB bridge with no Linux inside

Goal: plug a FireWire audio interface (Saffire PRO 10/26/24/40 first) into an M4 MacBook Air
over **plain USB**, with no Thunderbolt dongles, no Mac mini or Raspberry Pi running Linux,
and no kernel driver on the Mac.

## Why not the earlier suggestions

| Route from the ChatGPT/Codex chats | Problem |
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
                  ▼ USB-C → MacBook Air
```

The key insight: **you don't have to implement the physical layer.** The PHY chip turns the
FireWire cable into a ~49 MHz parallel bus with a fully specified protocol. Everything above
it (the link layer) is digital logic that fits in a cheap FPGA. The JHU dVRK "FPGA1394"
boards already do exactly this (FPGA link layer + discrete TI PHY), with
[open Verilog](https://github.com/jhu-cisst/mechatronics-firmware), so we can study a proven
reference instead of starting from a blank page.

### What the Mac sees: two firmware personalities

1. **Class-compliant mode (target for daily use):** USB Audio Class 2.0, asynchronous with a
   feedback endpoint. The Mac's built-in driver handles it, like your UR44. The bridge
   firmware knows the device's stream format (channel count, AV/C/BeBoB start sequence) and
   runs it standalone. Mixer/routing controls go to a Rust app over a vendor USB
   interface (same pattern as your UR44 app).
2. **Raw-link mode (for "universal"):** the bridge exposes a vendor-class USB interface that
   carries raw 1394 async transactions + iso packets. All intelligence lives in a Rust
   user-space library on the Mac (libusb, no kernel extension, no entitlements). That
   gives SBP-2 disks, DV cameras and other audio interfaces, all as software. Audio in this
   mode would surface through a user-space CoreAudio AudioServerPlugIn, which needs no
   DriverKit entitlement.

Same hardware for both, so build raw-link first (it's the debugging tool for everything else).

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
