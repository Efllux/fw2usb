# Research: an FPGA "soft PHY" for IEEE 1394a (S100)

**Goal:** replace the obsolete/expensive PHY chip with FPGA logic + a small analog front-end
(AFE) of jelly-bean parts. As far as we can find, no open implementation of a 1394 cable
PHY exists. This is new territory, so every electrical number below must be checked
against IEEE 1394-1995 §4 / 1394a-2000 and against a real device on a scope before we trust
it. Items marked **[verify]** are from memory/secondary sources.

## Why S100 only

Every 1394 node must support S100 (98.304 Mb/s). At S100 the DS signals toggle at
≤ ~49 MHz, which plain FPGA I/O handles easily. We simply never signal S200/S400 speed during
arbitration or self-ID, so peers talk to us at S100.

**Bandwidth budget (rough):** an isochronous cycle is 125 µs, of which ~100 µs may be iso.
At S100 that's ~1,200 bytes on the wire, minus per-packet overhead (prefix, header, CRCs,
gaps). For AM824 at 48 kHz, a data packet carries 8 frames: `8 + 8 × 4 × channels` bytes.

| Stream | Channels | Payload/packet |
|---|---|---|
| Saffire PRO 26 capture (approx.) | 18 | ~584 B |
| Saffire PRO 26 playback (approx.) | 10 | ~328 B |
| Sum | | ~912 B + overhead: **tight but plausibly fits** |

Smaller interfaces fit easily; big ones (Pro 40 at full channel count) may need S200 later.
This must be confirmed against the actual stream formats (`fw-amdtp` can compute it).

## What a cable PHY does, and how we'd do each part

| Function | Chip PHY | Soft PHY plan |
|---|---|---|
| Data-strobe TX/RX | LVDS-like current drivers, receivers | FPGA I/O + external drivers/receivers; DS encode/decode in logic (`fw-phy-model::ds`) |
| Arbitration line states (1, 0, Z on each pair) | window comparators, tri-state drivers | 2 fast comparators per pair (window ±threshold) + tri-statable current drivers |
| Arbitration signals (TX_REQUEST, PARENT_NOTIFY, …) | state machine | FPGA state machine, tables from 1394-1995 §4.4 **[to transcribe from spec]** |
| Bus reset, tree-ID, self-ID | state machine | FPGA state machine; self-ID packets modelled in `fw-phy-model::selfid` |
| TPBIAS (≈1.86 V on TPA) | bias generator | precision reference + op-amp buffer **[verify value/tolerance]** |
| Connection detect | comparator on TPB common mode | comparator on TPB centre tap |
| Speed signalling (CM current) | current sinks | **not implemented**: S100 only |
| 49.152 MHz PHY-link interface | external pins | internal to the FPGA (link layer talks to the soft PHY directly) |
| 24.576 MHz reference | crystal | crystal/oscillator into FPGA PLL |

## Analog front-end sketch (to be designed and simulated)

Per port (one port is enough for the dongle):

```
            ┌── TPA± ── 2×55 Ω termination, centre tap = TPBIAS (buffered ref)
 cable ─────┤
            └── TPB± ── 2×55 Ω termination, centre tap → R‖C to GND, → connect-detect comparator

 RX data/strobe : TPx± → LVDS receiver (or FPGA LVDS input if CM range allows) → FPGA
 RX arbitration : TPx± → window comparator pair (+th, −th) → FPGA  (1 / 0 / Z)
 TX             : FPGA → tri-statable current-steering driver → TPx±
```

Open questions:
1. **Driver**: 1394 drivers are current-mode, tri-statable, and must not disturb common mode
   (or the far end may see a speed signal). Candidates: discrete transistor current switches;
   an LVDS driver with high-Z output plus level shifting; resistor networks from FPGA pins for a
   first bring-up. Needs SPICE.
2. **Receiver common mode**: TPBIAS puts lines near ~1.9 V **[verify]**; check the chosen
   LVDS receiver/FPGA input CM range.
3. **Arbitration thresholds**: window comparator levels and hysteresis **[verify from spec]**.
4. **Timing**: arbitration and reset have µs-scale timeouts. Easy in logic, but list them
   all from the spec.
5. **Isolation/ESD**: add TVS diodes; the cable can carry up to ~30 V of bus power, which we
   never connect to the AFE.

## Plan

1. ✅ Bit-level reference model in Rust (`crates/fw-phy-model`): DS codec, line-state
   resolution, self-ID packets. This is the golden model for FPGA testbenches.
2. Transcribe the arbitration signal tables and PHY state machines from the spec into the model.
3. SPICE the AFE (driver, receiver, comparators, bias) with ngspice/KiCad.
4. Breadboard-ish proto: FPGA board + AFE on a small PCB. First goal: **detect connection and
   see the Saffire's bus reset / self-ID on the comparators**. Receiving is easier than
   transmitting, so start passive.
5. Transmit our own self-ID, become root, and run cycle master.
6. Swap in for the chip PHY in the main design.

Fallback at every step: the chip-PHY path (TSB41AB2/FW802/TSB41BA3F-EP) keeps the project moving.
