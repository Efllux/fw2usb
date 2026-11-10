# Legacy PHY breakout — engineering WIP

**M is incomplete. This is not a fabrication release.** KiCad8.0.9 reports zero
ERC errors/warnings. The placed PCB has zero geometric DRC violations but186
unconnected items and lacks J1's mechanical footprint. This is not a clean routed
DRC result. No exclusions suppress unconnected items. The reports are retained.

Choose TI TSB41BA3F-EP, order code TSB41BA3FTPFPEP, because TI lists it ACTIVE
and it supports a legacy1394a link at49.152MHz/3.3V. The AB2 model remains a
separate simulation target: BA3F register differences, reset and timing must be
cross-checked before hardware attachment. No register-map equivalence is assumed.
No beta PHY-link operation or9-pin connector is included in this revision.

Strap BMODE=0 and LCLK_PMC=0. Table5-1 mode20 sets S5/S4=1, S3/S2/S1/S0=0:
ports1/2 are DS-only, unused port0 bilingual, power class000. The six-pin FW400
connector is on port2, never a bilingual port. Unused DS port1 TPB pins are tied
to GND and TPA/bias unconnected; unused bilingual port0 analog pins are NC as
permitted by TI. TESTM high, SE/SM/PD/VREG_PD low; ENHANCE_EN high disables the
new enhancement defaults. S5_LKON has a1k strap and1k header series resistor.

The active port uses56.2Ω1% split termination (112.4Ω differential). TPA midpoint
to TPBIAS2 with1µF bypass; TPB midpoint to4.99kΩ in parallel with270pF to GND.
6.34kΩ1% R0–R1 sets internal current. VP pin1 is NC, CPS held low; this board
neither consumes nor sources cable power. VG connects circuit ground. Shell has
1MΩ ||10nF ||1nF to circuit ground; chassis/ESD/EMC/fault behavior remains[verify].

J3 requires an external regulated3.3V supply. All3.3V PHY supplies share the rail;
DVDD_CORE and PLLVDD_CORE remain separate internally regulated rails, with bypass
and1µF regulation capacitors. Each power terminal has100nF+1nF bypass candidates
and the3.3V rail has10µF bulk candidates. Their final loop inductance/placement
requires routing review. Exposed pad81 is GND,6x6mm per TI; grounded thermal land
and vias still need implementation. Nominal pad geometry is independently drawn,
not imported vendor CAD.

The49.152MHz fundamental crystal candidate is Abracon
ABM8W-49.1520MHZ-6-K1Z-T3. Initial6.8pF loads are[verify], not a guaranteed6pF
network: tune with measured board/PHY parasitics and verify PCLK within±100ppm.
RESET has220nF; verify startup/ramp against TI's formula and hold open-drain reset
for at least2ms after valid power/clock. FPGA output must be high impedance until
its supply/reset policy is established. This is a common-ground, nonisolated link.

## J2 signal header

Pin numbers below are header positions. ULX3S names are silkscreen nets, not its
connector positions. The pin plan matches gateware/README.md. Use a designed
interposer; SI/turnaround/setup/hold and bank supply compatibility remain[verify].

| J2 | Signal | ULX3S net |
|---|---|---|
|1|GND|GND|
|2|SCLK via22Ω source series|GP0|
|3|D0|GN0|
|4|D1|GP1|
|5|D2|GN1|
|6|D3|GP2|
|7|D4|GN2|
|8|D5|GP3|
|9|D6|GN3|
|10|D7|GP4|
|11|CTL0|GN4|
|12|CTL1|GP5|
|13|LREQ|GN5|
|14|LPS via1k|GP6|
|15|LinkOn via1k|GN6|
|16|RESET_N open-drain|GP7|
|17|GND|GND|
|18|3V3 reference/test only|do not tie to ULX3S supply|
|19|GND|GND|
|20|NC|NC|

## Reproduction and remaining work

`python3 tools/design.py` emits net/BOM data; `python3 tools/schematic.py` emits the
cached-symbol schematic and original library. Run `tools/pcb.py` using KiCad8's
bundled pcbnew Python. It places69 parts and explicitly omits J1 rather than
inventing unknown retention-hole/pad dimensions. Re-running overwrites placement.
Use KiCad CLI `sch erc --severity-all --exit-code-violations` and `pcb drc` on the
files; neither a zero geometric-violation count nor ERC establishes connectivity
or signal integrity. Source/report paths stay relative to this directory.

Finish J1 against the public Molex534600639 customer drawing, then route/fill
planes/thermal vias, verify all connections and diff-pair/skew rules, require
zero ERC/DRC/unconnected items, audit schem→PCB connectivity, and review BOM order
codes/availability. The drawing URL is indexed but direct downloads currently
fail/reset/timeout in this environment. This is a source-access task, not a
hardware-only blocker. Other J/K integration work must continue meanwhile.
No official/third-party binary, CAD model, NDA or vendor PDF is vendored here.

## Primary sources

- [TI active product](https://www.ti.com/product/TSB41BA3F-EP), checked2026-11-10.
- [TI SLLSFA1 datasheet](https://www.ti.com/lit/ds/symlink/tsb41ba3f-ep.pdf), pin tables pp3–8, Table5-1, Fig13-3/4, reset/crystal/thermal sections. Internal download SHA256 `a4f2257e9fcfab9cab41dbbc7fdd911f1baffc562d1cdaf1150bfdd1121fe9fb`.
- [Molex53460 series](https://www.molex.com/en-us/products/series-chart/53460), orderable connector identity; [public customer drawing](https://www.molex.com/content/dam/molex/molex-dot-com/products/automated/en-us/salesdrawingpdf/534/53460/534600639_sd.pdf), not yet visually verified.
- [KiCad8.0.9 release](https://www.kicad.org/blog/2025/02/KiCad-8.0.9-Release/), official macOS DMG downloaded via downloads.kicad.org; SHA256 `865a96ff02e9dc4d5e6d3554d8224b7d780aae7b2975329d911dfe57820ba07a`.

BOM.csv lists candidate manufacturer order codes and[verify] items. No purchase,
stock guarantee, electrical compliance or working hardware is claimed.
