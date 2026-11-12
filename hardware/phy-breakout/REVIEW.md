# PHY breakout: chip decision and schematic review

Status: working notes for the `hardware/phy-breakout-complete` branch. The
decisions below are made; the generator scripts, schematic and PCB are being
brought into line with them in later commits on this branch. Until those
commits land, `design.py`, the schematic and the PCB still describe the old
unrouted design.

## Sources

Datasheets are not stored in git (TI licence). Page numbers below are the
printed page numbers of these files.

| Document | URL | SHA-256 of the copy used |
|---|---|---|
| TSB41BA3F-EP, SLLSFA1, Sept 2020 | https://www.ti.com/lit/ds/symlink/tsb41ba3f-ep.pdf | `a4f2257e9fcfab9cab41dbbc7fdd911f1baffc562d1cdaf1150bfdd1121fe9fb` |
| TSB41AB2, SLLS424G, Dec 2004 | no longer on ti.com (404). Copy used: Internet Archive capture `20200214195138` of `http://www.ti.com/lit/ds/symlink/tsb41ab2.pdf` | `a15dddecadd4f78d578d06c9c32e5e19a533753e87e74bdb69b1111b555c0174` |
| TPD4E05U06, SLVSBO7O, Aug 2024 | https://www.ti.com/lit/ds/symlink/tpd4e05u06.pdf | not recorded |
| Assmann WSW A-IES-SMT-U/R drawing ASS 8005 CO rev06 | https://www.assmann-wsw.com/uploads/datasheets/ASS_8005_CO.pdf | not recorded |
| Keystone catalog p.90 (927TR, 929, 930 FireWire sockets) | third-party copy: https://pdf3.datasheet.su/Keystone%20Electronics/929.pdf (keyelco.com blocks automated download) | not recorded |

The Molex 53460-0639 drawing could not be downloaded (connection reset or
timeout from two different clients), so that part is dropped; see J1 below.

## 1. Which PHY

**Decision: the first breakout targets TI TSB41BA3F-EP (TSB41BA3FTPFPEP),
with BMODE low so that the PHY-LINK interface is the 1394a-2000 one.**

### What ti.com says today (checked 2026-11-12)

| Part | ti.com status | ti.com list price shown |
|---|---|---|
| TSB41BA3F-EP (80-pin HTQFP) | ACTIVE | about $54 to $72 each |
| TSB41AB2 (64-pin HTQFP) | product page gone (404) | none |
| TSB41AB1, TSB41AB3 | OBSOLETE | residual prices only |
| TSB41BA3D, TSB81BA3E | OBSOLETE | residual prices only |

Every 1394a-only PHY from TI is obsolete. TSB41BA3F-EP is the only discrete
PHY in this family that TI still lists as active. Distributor stock was not
verified: ti.com shows stock only to logged-in users and distributor sites
block automated queries. **Stock and real price must be checked by a person
before ordering.**

### Why TSB41BA3F-EP

- It is the only part a second builder can buy new with traceability. A board
  that depends on salvaged or broker stock cannot be reproduced reliably, and
  the final product will need a part that is in production anyway. Moving the
  gateware to this PHY now retires that risk at M1 instead of at M5.
- With BMODE low the interface is the same 1394a-2000 PHY-LINK interface the
  gateware was written against (SLLSFA1 section 12, pp33-45). The differences
  are listed in section 2 and are small.
- Its link-side input timing is easier than TSB41AB2: setup 2.5 ns and hold
  0 ns (SLLSFA1 section 6.8, p14) against setup 5 ns and hold 2 ns
  (SLLS424G switching characteristics, p14).
- Ports can be forced to 1394a data-strobe-only mode by straps (Table 5-1,
  p9), which is what TI requires for a 6-pin connector (p18).
- Both chips are 0.5 mm pitch HTQFP with an exposed pad, so hand assembly is
  equally hard for both: fine-pitch drag soldering plus hot air or a via
  window for the pad.

### Why not TSB41AB2

It matches the simulation model exactly and is cheap, but it can only be had
as old stock of unknown origin or by desoldering it from a donor PCI card.
Most cheap PCI FireWire cards use single-chip controllers with no separate
PHY, so finding a donor is a lottery.

### Both on one board?

Not realistic as a footprint option: 64 pins against 80, different pinouts,
a 24.576 MHz crystal against 49.152 MHz, and a single 3.3 V rail against a
PHY with internal core regulators. A second board variant generated from the
same scripts is realistic later, because the header pinout and the cable-side
circuit are the same. It is not part of this branch.

### Decision that belongs to the project owner

Spending roughly $55 to $75 on one PHY chip. Options: (a) buy TSB41BA3F-EP
(recommended, this board), or (b) find a TSB41AB2 and ask for the AB2 board
variant. Everything on this branch proceeds under (a).

## 2. Gateware and simulation changes implied (not made here)

The gateware is unchanged on this branch. Each item names what differs
between SLLS424G (TSB41AB2) and SLLSFA1 (TSB41BA3F-EP, BMODE low).

Same in both, no change needed:

- LREQ request formats and lengths: SLLSFA1 Tables 12-3 to 12-9 (pp34-36)
  match SLLS424G Tables 12-18, including the 7- or 8-bit bus request and the
  acceleration control request.
- CTL encodings (Tables 12-1, 12-2, p34), status transfer of 4 or 16 bits on
  D0/D1 (section 12.2, Table 12-10, pp37-38), receive speed codes
  (Table 12-11, p39).
- LPS timing: Table 12-19 (p43) has the same numbers as SLLS424G Table 21:
  reset 2.6 to 2.68 us, disable 26.03 to 26.11 us, restore 15 to 23 us, clock
  activation 60 ns or 5.3 to 7.3 ms. Initialization is the same seven low
  cycles, then receive with data-on, then idle (p45).
- Link-on output is a square wave of about 163 ns period (p7).
- There is no ISO pin; the interface is always the direct, non-isolated kind
  the gateware already assumes (p60: Annex J isolation is not supported).

Changes needed:

1. **Transmit, end-of-packet hold cycle** (`fw2usb/transmit.py`, `TAIL`
   state). With multispeed concatenation on, the gateware drives the
   TSB41AB2 speed code on D during the final hold (0x40 for S200, 0x50 for
   S400). TSB41BA3F-EP instead reads D during that hold as a link request:
   D1-D3 request type, D5-D6 speed, D0 format, D4 end of subaction
   (Tables 12-12 to 12-15, pp40-41). The AB2 code would be misread. Drive the
   BA3F encoding, or drive zero ("no request") and do not concatenate, until
   this is implemented and tested.
2. **Transmit, grant to first drive.** TSB41AB2 allows up to 47 hold cycles
   before transmit (SLLS424G p40). TSB41BA3F-EP takes the interface back if
   it does not see hold or transmit within eight PCLK cycles of the grant
   (p39). `allow_hold` may still be used, but the first hold or transmit must
   start within eight cycles.
3. **Grant cycle carries data.** During the grant cycle TSB41BA3F-EP puts the
   grant type and speed on D (Tables 12-16 to 12-18, pp41-42). The gateware
   only looks at CTL, which stays correct; the simulation model should drive
   these values so that the receive path is proven to ignore them.
4. **Register map** (`sim/registers.py`, and any code that reads identity):
   - register 2 reads 0xE3 (three ports), not 0xE2 (Table 13-1, p47);
   - register 3 has PHY_Speed 111b, a writable SREN bit and a non-zero Delay
     field, not 0x40 (pp47-48);
   - register 4: the contender bit resets to 0 and can only be set by a
     register write; there is no contender strap (p48);
   - register 5: CPSI resets to 1 (p48). With CPS grounded on this board the
     PHY will report an interrupt after reset; write 1 to CPSI to clear it;
   - register 6 is no longer reserved: Max Legacy SPD, BLINK, Bridge (p49);
   - page 0 has port registers up to address 1111b, and three ports
     (Tables 13-3, 13-4, pp49-52);
   - page 1: compliance 02h, vendor 08 00 28h, product 83 40 07h (p53);
   - page 7 register 8 has no NPA and no Link_Speed field. It holds
     MAX_INVALID_EXT instead (p53). The model's `value & 0x83` write mask and
     the NPA behaviour in `sim/phy.py` do not apply. SWR stays at 1110b.
5. **Self-ID.** The PHY sends a 1394b-style self-ID packet in every usable
   strap mode (Table 5-1, "SELF-ID" column, p9) and reports three ports. The
   self-ID capture must accept the speed code 11b and three port fields. The
   present check in `SelfIdCapture` should be reviewed against that.
6. **No CNA pin** (p19). Use port interrupts instead if cable-not-active is
   ever wanted.
7. **Link-on after power-up.** With power class 0 to 4 the PHY drives link-on
   for about 167 us after a power cycle (p7, p19). Harmless, but the model's
   `LinkOn` latch does not do this.
8. **Bus reset on LPS wake.** After LPS has been low long enough to disable
   the interface, raising it makes the PHY issue a bus reset (p19).
9. **I/O timing constraints** for the ECP5 pins: PHY input setup 2.5 ns, hold
   0 ns; PHY clock-to-output 0.5 to 1.6 ns (section 6.8, p14); clock period
   20.345 ns. PHY outputs are rated for only 4 mA (p12). Use LVCMOS33 with
   the lowest drive and slow slew on the FPGA outputs. The board adds series
   resistors on every bus line.
10. **Erratum** (p46): restoring from standby as a leaf node causes a bus
    reset. Not relevant unless standby is used.

Not compared: the TSB41AB2 clock-to-output delay. The numbers for that row
did not survive text extraction from the archived PDF.

## 3. Schematic review against SLLSFA1

### Errors found in the existing schematic

1. **Strap mode is wrong.** The README says mode 20 gives two data-strobe
   ports and a bilingual port 0. Table 5-1 (p9) says mode 20 (S5=1, S4=1,
   S3=0, S1=0, S0=0) gives port 2 data-strobe, port 1 **bilingual**, port 0
   **Beta-only S100** with its TPBIAS0_SD0 pin turned into a signal-detect
   input. That input is left floating in the schematic, but p18 requires it
   to be pulled to ground through 1.2 kOhm or less on an unused Beta-only
   port. The schematic also grounds TPB1+/TPB1-, which p18 describes only for
   a port forced to data-strobe mode.
   **Fix: mode 3 (S5=0, S4=1, S3=0, power class from S2-S0).** Ports 2 and 1
   are data-strobe only, port 0 is bilingual, all three TPBIAS pins are bias
   outputs. Then the existing treatment is correct: TPB1+/TPB1- grounded,
   port 0 pins open (p18). Change: the S5_LKON strap resistor goes to ground
   instead of 3.3 V.
2. **Only the clock has a series resistor.** D0-D7, CTL0-CTL1 and LREQ go
   straight to the header. **Fix: 22 Ohm in series on all twelve bus lines.**
3. **LPS floats when the cable is unplugged or the FPGA is unconfigured.**
   **Fix: 10 kOhm from the header side of LPS to ground**, so the PHY-LINK
   interface stays disabled until the FPGA drives LPS high. (Figure 13-6,
   p60, shows 10 kOhm resistors in the non-isolated LPS circuit.)
4. **No ESD protection on the cable pairs.** The PHY is rated 2 kV human-body
   model only (section 6.2, p11). **Fix: TPD4E05U06 four-channel array** on
   TPA+, TPA-, TPB+, TPB-, 0.5 pF per line, 10 nA leakage, flow-through
   pinout. Its pin pitch equals the PHY pin pitch for port 2, so the pairs
   run straight through it.
5. **J1 has no footprint and the Molex drawing is unobtainable.** **Fix:
   Keystone 927TR, second source Assmann WSW A-IES-SMT-U/R.** Both drawings
   give the same land pattern: six pads at 1.00 mm pitch, two 1.60 mm
   locating holes 10.0 mm apart, two plated 1.0 x 2.5 mm slots 11.7 mm apart
   and 4.65 mm toward the board edge. The Keystone drawing numbers the pads
   1 to 6 and shows which contact is which.

### Values confirmed, with the `[verify]` removed

| Item | Value | Citation |
|---|---|---|
| TPA and TPB termination | 56 Ohm from each line to the midpoint (56.2 Ohm 1% fitted) | p18; Figure 13-3, p59 |
| TPA midpoint | to TPBIAS2 | p18 |
| TPBIAS decoupling | 1 uF to ground on each port in use | pin table p7; p18 |
| TPB midpoint | 5 kOhm in parallel with 270 pF to ground (4.99 kOhm 1% fitted) | p18; Figure 13-3 note A, p59 |
| R0-R1 | 6.34 kOhm 1% | pin table p6 |
| Shield | 1 MOhm, 10 nF and 1 nF in parallel to ground | Figure 13-4, p59 |
| Unused data-strobe port 1 | TPB+ and TPB- tied together to ground, TPA and TPBIAS open | p18 |
| Unused bilingual port 0 | all pins open | p18 |
| BMODE | ground | pin table p4; p60 |
| LCLK_PMC | ground, directly | p61 |
| PINT | open | p60 |
| TESTM | 1 kOhm to 3.3 V | p8, p19 |
| SE, SM | ground | p6, p19 |
| VREG_PD | ground (internal regulator on) | p8 |
| PD | ground | p5 |
| ENHANCE_EN | high; affects Beta-mode ports only, high keeps standard behaviour | p6, section 13.2.3 |
| Strap resistors | 1 kOhm | p6 |
| Supplies | AVDD, DVDD-3.3, PLLVDD-3.3 tied together; DVDD-CORE and PLLVDD-CORE separate from each other, each with 1 uF | pin table pp3-6; p17 |
| Supply current | 110 mA typical, 150 mA maximum | section 6.7, p13 |
| Reset capacitor | 0.22 uF. The formula gives 0.1 uF minimum for a crystal and a 2 ms supply ramp; 0.22 uF covers ramps up to about 17 ms | section 13.2.6, p61 |
| Thermal pad | 6 x 6 mm, grounded, ground pins tied to it | section 13.2.9, pp64-65 |
| Power class | 000: does not need and does not repeat cable power | Table 13-9, p58 |

### Values changed

- **Crystal load capacitors: 8.2 pF, not 6.8 pF.** Section 13.2.7 (p62)
  gives CL = C9*C10/(C9+C10) + CPHY + CBD with CPHY about 1 pF and CBD about
  0.8 pF per cm of trace. For the 6 pF crystal and about 1 cm of trace,
  C9 = C10 = 2 x (6 - 1 - 0.8) = 8.4 pF, nearest value 8.2 pF.
- **Decoupling.** TI suggests 0.1 uF plus 1 nF at each supply pin. The board
  fits 0.1 uF at every supply pin (adjacent pins of the same rail share one)
  and adds 1 nF at the analog and PLL pins. The 1 nF is left off the digital
  3.3 V and digital core pins to keep the capacitors close to the pins on a
  hand-assembled board.

### Cable power and CPS

The board neither takes nor supplies cable power. VP (pin 1 of J1) is left
unconnected and VG goes to ground. CPS is held low through 1 kOhm, so the
PHY reports "cable power absent" and sets CPSI at reset (see gateware item
4). TI's normal circuit is 400 kOhm from cable power to CPS (p4, Figure
13-3); it is not fitted because nothing on this board uses the result.
A bus-powered device must use its own power supply.

Connection detect needs no parts beyond the termination network: in 1394a
mode it works through TPBIAS and the TPB common-mode level (p18).

### Header J2

The pin order is changed so that the bus routes without crossings and the
clock sits between two ground wires in a ribbon cable. The 3.3 V pin is
removed; power comes in only on J3. The new table will be in the README.

### Still needs a measurement

| What | Measurement |
|---|---|
| Crystal load capacitors | PCLK frequency with a counter of six digits or better; must be 49.152 MHz within 100 ppm (p63). Raise both capacitors if high, lower if low. |
| Reset timing | Scope RESET against 3.3 V at power-up with the real bench supply; at least 2 ms low after the supply is valid (p12, p61). |
| Bus signal quality | Scope PCLK, one data line and LREQ at the FPGA end of the real cable; adjust the 22 Ohm values and FPGA drive strength if there is ringing. |
| Pair impedance | 110 Ohm differential is calculated, not measured. Ask the board house for impedance control or measure with a TDR if S400 shows errors. |
| J1 pad order on the Assmann part | Continuity check from each pad to each contact before using the second-source connector. |
| ESD and cable-fault behaviour | Not testable on the bench without equipment; treat the port as protected against handling only. |
