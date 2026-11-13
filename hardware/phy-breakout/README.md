# FireWire PHY breakout, revision 0.2

One FireWire 400 (6-pin) port and a TI TSB41BA3F-EP PHY, cabled to an FPGA
board through a 2x10 header. It exists for milestone M1: bus reset, self-ID
and reading the configuration ROM of a real device.

**Status.** Schematic and 4-layer board are complete and checked with KiCad
8.0.9: ERC 0 errors and warnings; DRC 0 violations, 0 unconnected items,
0 schematic-parity issues, with no exclusions. Fabrication files are in
`fab/`. **No board has been built or tested.** Before ordering, read
"Check before ordering" below.

Why this PHY, how it differs from the TSB41AB2 the gateware was written
against, the gateware changes that follow, and every schematic value with
its datasheet page are in [REVIEW.md](REVIEW.md).

## What is on the board

- U1 TSB41BA3F-EP, PHY-LINK interface in 1394a mode (BMODE low), 49.152 MHz
  crystal, internal core regulators, single 3.3 V supply.
- Strap mode 3 (S5=0, S4=1, S3=0): ports 2 and 1 are data-strobe only, port 0
  is bilingual. Only port 2 is used. Power class 000.
- J1 FireWire 400 receptacle on port 2, with 56.2 Ohm termination, 1 uF on
  TPBIAS, 4.99 kOhm and 270 pF on the TPB midpoint, and a TPD4E05U06 ESD
  array next to the connector. Shield goes to ground through 1 MOhm, 10 nF
  and 1 nF in parallel.
- Cable power is **not connected** in either direction. A bus-powered device
  needs its own power supply.
- J2 2x10 header: the PHY-LINK bus with 22 Ohm in series on the clock, D0-D7,
  CTL0-CTL1 and LREQ, 1 kOhm in series on LPS and LinkOn, and a 10 kOhm
  pull-down on LPS so the interface stays off until the FPGA drives it.
- J3 two-pin 3.3 V supply input. There is no regulator and no reverse-polarity
  protection: use a current-limited bench supply, 3.0 to 3.6 V, 200 mA.
  The PHY draws 110 mA typical, 150 mA maximum.

## J2 header

Odd pins are the column nearer the board edge; pin 1 is square and marked.
In a ribbon cable the clock and LREQ each lie between two ground wires.
The ULX3S column is the wiring plan from `gateware/README.md`; those are
silkscreen net names on the ULX3S, not connector positions. Keep the cable
short (10 cm or less) or use a small adapter board.

| J2 pin | Signal | ULX3S net | | J2 pin | Signal | ULX3S net |
|---|---|---|---|---|---|---|
| 1 | GND | GND | | 2 | RESET_N, open drain, active low | GP7 |
| 3 | LinkOn (from PHY) | GN6 | | 4 | LPS (to PHY) | GP6 |
| 5 | GND | GND | | 6 | LREQ | GN5 |
| 7 | GND | GND | | 8 | SCLK 49.152 MHz (from PHY) | GP0 |
| 9 | GND | GND | | 10 | CTL0 | GN4 |
| 11 | D0 | GN0 | | 12 | CTL1 | GP5 |
| 13 | D2 | GN1 | | 14 | D1 | GP1 |
| 15 | D4 | GN2 | | 16 | D3 | GP2 |
| 17 | D6 | GN3 | | 18 | D5 | GP3 |
| 19 | GND | GND | | 20 | D7 | GP4 |

This pin order is new in revision 0.2 (it lets the bus route on one layer
without crossings). There is no 3.3 V pin on J2. The grounds of the two
boards are common; the link is not isolated.

FPGA side: 3.3 V LVCMOS, lowest drive strength and slow slew on outputs.
RESET_N must be driven low or left floating, never driven high; hold it low
for at least 2 ms after the supply and clock are stable. Keep D, CTL and
LREQ undriven until the PHY has finished its interface start-up.

## Board

- 57.8 x 32.6 mm, 4 layers, 1.6 mm, four 3.2 mm mounting holes.
- Layers: top signals and parts; inner 1 unbroken ground; inner 2 3.3 V plane
  (the digital core rail is a 0.4 mm track on this layer); bottom ground fill
  and the decoupling capacitors, placed under the PHY pin rows.
- Cable pairs: top layer only, no vias, over unbroken ground, 12.43 mm from
  PHY pin to connector pad, both lines of each pair the same length. Lines
  0.22 mm, gap 0.28 mm. With 0.21 mm of 7628 prepreg (dielectric constant
  4.4) to the ground layer the usual microstrip formulas give about 110 Ohm
  differential. This is calculated, not measured.
- PHY-LINK bus: top layer only, no vias, 0.2 mm lines over ground. Lengths
  from PHY pin to header pin are 14.7 to 19.8 mm, a spread of 5.1 mm or
  about 35 ps, against a 20.3 ns clock period (`reports/lengths.txt`).
- U1 thermal pad: 6 x 6 mm land with 25 vias to the ground plane; ground
  pins run straight into the land.

### Board-house rules used

Checked against JLCPCB's published 4-layer limits (read 2026-11-13), with
margin. PCBWay's standard 4-layer service has similar limits.

| | This board | JLCPCB limit |
|---|---|---|
| Track width | 0.2 mm minimum used | 0.09 mm |
| Copper spacing | 0.15 mm net-class rule, 0.127 mm absolute | 0.09 mm |
| Via | 0.3 mm hole, 0.5 mm pad (0.6 mm in the thermal land) | 0.15 / 0.25 mm |
| Via hole to other copper | 0.2 mm | 0.2 mm |
| Hole to hole | 0.25 mm | 0.2 mm |
| Copper to board edge | 0.3 mm | 0.2 mm |
| Plated slots | 1.0 x 2.5 mm | 0.35 mm wide |
| Silkscreen | 1.0 mm text, 0.15 mm lines | 1.0 mm, 0.15 mm |

Order as: 4 layers, 1.6 mm, 1 oz outer copper, a stackup with 7628 prepreg
(about 0.2 mm) under the outer layers, any finish (ENIG is easier for hand
soldering the 0.5 mm pitch parts).

## Check before ordering

1. **U1 stock and price.** ti.com listed the part as active at about $54 to
   $72 on 2026-11-12; stock was not verified.
2. **J1 part in hand.** The footprint is the land pattern of Keystone 927TR,
   which the Assmann WSW A-IES-SMT-U/R drawing matches. The Keystone drawing
   gives the pad numbering used here. If the Assmann part is bought, check
   with a continuity meter that pads 1 to 6 reach contacts 1 to 6.
3. **Stackup.** Confirm the prepreg thickness in the order form. A much
   thinner prepreg lowers the pair impedance.

## Assembly notes

- 71 parts: 46 on top, 25 capacitors on the bottom. Mostly 0402.
- U1 and U2 are 0.5 mm pitch. U1 has an exposed pad that must be soldered:
  use paste and hot air or a hotplate; an iron alone cannot reach it.
- Solder the bottom capacitors first, then the top.
- `fab/assembly/` has the BOM, the placement file and drawings of both sides.

- Part numbers for resistors, capacitors, headers and the crystal are
  candidates and were not checked for stock. Any part with the same value,
  package and dielectric will do; the crystal must be a 49.152 MHz
  fundamental-mode part.

## Cost estimate

Estimates, not quotes; nothing was ordered.

| Item | Estimate |
|---|---|
| Five bare boards, JLCPCB 4-layer, before shipping | $10 to $30 |
| U1 TSB41BA3F-EP (ti.com list price) | $54 to $72 |
| J1, U2, crystal, headers | about $6 |
| 65 resistors and capacitors | about $3 |
| **Parts for one board** | **about $65 to $80** |

The PHY is most of the parts cost.

## After assembly: measurements still needed

| What | How |
|---|---|
| Crystal load capacitors C6, C7 | Frequency counter on J2 pin 8 with LPS high: 49.152 MHz within 100 ppm. Raise both capacitors if high, lower if low. |
| Reset time | Scope RESET_N against 3.3 V at power-up: low for at least 2 ms after the supply is valid. |
| Supply current | About 110 mA with a device connected. |
| TPBIAS | 1.67 to 2.02 V on C2 with a cable connected. |
| Bus signal quality | Scope SCLK, one data line and LREQ at the FPGA end of the real cable. Adjust the 22 Ohm resistors or FPGA drive strength if they ring. |
| Pair impedance | Only if S400 traffic shows errors: time-domain reflectometer, or order with impedance control. |

ESD and cable-fault behaviour cannot be tested on the bench. Treat the port
as protected against handling, not against miswired cables.

## Rebuilding

Everything except the two documents is generated. With KiCad 8.0.9:

```
tools/build.sh /Applications/KiCad/KiCad.app
```

This runs `tools/design.py` (net list, placement, BOM), `tools/schematic.py`
(schematic and symbol library), `tools/pcb.py` (footprints, placement, all
routing, zones, project rules), then ERC and DRC into `reports/`, then the
fabrication files into `fab/`. The scripts need the Python that ships inside
KiCad. KiCad does not have to be installed: the official disk image can be
mounted and the path to `KiCad.app` inside it given to the script. The
official 8.0.9 image has SHA-256
`865a96ff02e9dc4d5e6d3554d8224b7d780aae7b2975329d911dfe57820ba07a`.

No autorouter is used. To change the layout, edit the coordinates in
`design.py` and the routes in `pcb.py`, rebuild, and read `reports/drc.txt`.

The schematic is a labelled-pin drawing of the net list, not a drawn
circuit diagram. It is correct for ERC and for the parity check against the
board, but it is hard to read; REVIEW.md describes the circuit.

## Files

| | |
|---|---|
| `REVIEW.md` | PHY choice, gateware changes implied, datasheet citations |
| `tools/` | generator scripts and `build.sh` |
| `design.json`, `BOM.csv` | generated net list and grouped BOM |
| `phy-breakout.kicad_sch`, `.kicad_pcb`, `.kicad_pro` | KiCad 8 project |
| `fw2usb.kicad_sym`, `fw2usb.pretty/` | generated symbols and footprints |
| `reports/` | ERC, DRC and routed-length reports |
| `fab/gerbers/` | Gerbers and drill files for the board house |
| `fab/assembly/` | BOM, pick-and-place, assembly drawings |

No vendor CAD, datasheet or other third-party file is stored here. Hardware
licence: CERN-OHL-S v2.
