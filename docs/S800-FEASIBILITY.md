# S800 feasibility: TLK1221 + non-transceiver FPGA + AT32F405

Date: 2026-11-22. Scope: check the architecture proposed in
[PARTS-SEARCH.md](PARTS-SEARCH.md) (draft PR #38) against datasheets before any
schematic work. Inputs: [SOFT-PHY.md](SOFT-PHY.md), and on branch
`hardware/bilingual-port` the files `WORKING-NOTES.md`, `PARTS-TO-PRICE.md`
and `spice/`.

Status words: **checked** = read in the cited datasheet; **reasoning** =
engineering inference, not checked; **[verify]** = needs a document we do not
have (mostly IEEE 1394b-2002) or a bench test. Prices are not re-searched here.

## 1. TLK1221 as the 1394b beta SerDes

Source: TI TLK1221 datasheet SLLS713C, Sept 2009,
<https://www.ti.com/lit/ds/symlink/tlk1221.pdf> (package addendum dated
11-Nov-2025 lists TLK1221RHAR / RHAT / RHATG4 as **Active**). Beta reference:
TI TSB81BA3E datasheet SLLS783C, March 2016,
<https://www.ti.com/lit/ds/symlink/tsb81ba3e.pdf>.

### 1.1 Raw 10-bit code groups and comma handling: **OK** (checked)

- Pure TBI: TD0..TD9 are serialized as given, TD0 first; RD0..RD9 come out
  undecoded, RD0 first (p.3 "Detailed Description", Table 2). No internal
  8B10B encoder or decoder, so 1394b control symbols, which are not standard
  IBM 8B10B K-codes (IEEE 802 tutorial on 1394,
  <https://grouper.ieee.org/groups/802/802_tutorials/04-July/NewTechIntroTo1394.pdf>),
  pass through untouched.
- Comma alignment is optional: SYNCEN high aligns on the 7-bit comma
  `0011111` with **negative beginning disparity only**; SYNCEN low gives
  unframed data (p.5 "Comma Character Not on Expected Boundary", Table 2).
  During realignment RBC is stretched by up to 20 bit times and the character
  after the comma is truncated (p.5, Figure 4).
- 1394b acquires symbol alignment from K28.5 that the receiver substitutes for
  a periodic scrambled D28.0 training symbol (secondary source: US patent
  7079717, <https://image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/7079717>)
  [verify against 1394b-2002 clause 14]. Whether the comma on the wire is
  always of negative disparity is unknown, so **recommendation: tie SYNCEN
  low and align in the FPGA** (20-bit window, 10-way shift, about 100 to 150
  LUT4). This works for any comma polarity and keeps RBC free-running.

### 1.2 Rate range: S800 OK, S400b not specified (checked)

- 0.6 to 1.3 Gb/s (p.1). REFCLK 60 to 130 MHz, accuracy ±100 ppm, duty
  40..60 % (p.8 "Reference Clock (REFCLK) Timing Requirements").
  983.04 Mbaud = 98.304 MHz × 10: inside the range.
- RX data must be within ±200 ppm of the local REFCLK (p.4). 1394 allows
  ±100 ppm per node, so two worst-case nodes sit exactly on the TLK1221 edge:
  use a ±50 ppm (or better) oscillator to keep margin on our side.
- 491.52 Mbaud (S400b) is below 600 Mb/s. Transmit could be done by sending
  every bit twice at 983.04 Mbaud (exact). Receive by 2× oversampling makes
  run lengths up to 10 UI, beyond the 5-UI design case of the CDR; whether it
  still locks is unknown [verify on bench]. Practical impact is small
  (reasoning): S800 beta peers negotiate S800, bilingual peers can fall back
  to legacy, and only beta-only S400b equipment (rare) would be lost.

### 1.3 Reference clock and jitter (checked)

- REFCLK jitter limit: **40 ps, random plus deterministic** (p.8). The table
  does not say peak-to-peak or RMS; read it as peak-to-peak (conservative).
- TX parallel data is registered on the **rising edge of REFCLK**: setup
  1.6 ns, hold 0.8 ns (p.11 "Transmitter Timing Requirements"). The FPGA must
  therefore run its TX path from the same clock that feeds REFCLK.
- Comparison: TSB81BA3E asks for 5 ps RMS on its 98.304 MHz XI (p.9, XI pin).
- An FPGA PLL output is not a suitable REFCLK (PLL jitter of iCE40, Spartan-6
  and Cyclone-class parts is in the 100..300 ps peak-to-peak range, see §3).
  REFCLK must come straight from a 98.304 MHz oscillator; see §3.

### 1.4 Line levels and termination vs 1394b beta (checked, with one risk)

| Quantity | TLK1221 (p.9) | TSB81BA3E beta (p.10) | Verdict |
|---|---|---|---|
| TX differential | VOD 600..1100 mV, Rt = 50 Ω per side | 700 mV typ, no limits given | overlaps; see load note |
| TX common mode | 1.0..1.4 V | 1.5 V typ | irrelevant: AC coupled |
| RX differential | 200..1600 mV required | 200..800 mV | **same 200 mV floor** |
| RX common mode | 1.0..2.25 V, self-biased (5 k/7.5 k network, Figs 10, 11) | n/a | AC coupled, self-biases near 1.5 V [verify that network is internal] |
| RX input capacitance | 2 pF | 4 pF (legacy RX) | good for coexistence |
| TX rise/fall | 100..250 ps | n/a (legacy 0.5..1.2 ns) | fast; check EMI |
| Coupling | AC mode shown in Fig 11/12 | TSB81BA3E shares legacy termination | matches the planned 10 nF series caps |

- Termination: the beta port must keep the legacy 2 × 56 Ω networks (TSB81BA3E
  p.15, termination paragraph; WORKING-NOTES §1). The TLK1221 RX needs only that termination (its
  inputs are high impedance, 2 pF), so **RX fits with no extra parts**.
- **TX amplitude risk.** TLK1221 VOD is specified into 50 Ω per side (100 Ω
  differential). On the bilingual port TPB is terminated locally (112 Ω) and by
  the far end (112 Ω via the 110 Ω cable), so the driver sees about 56 Ω
  differential. If the output is current-mode (the note "no pulldown resistors
  are required on the TXP/TXN outputs", p.2, suggests it is, unlike the
  emitter-follower TNETE2201) the launch amplitude scales to about
  56/100 × 600..1100 = **340..620 mV**, against the TSB81BA3E 700 mV typical and
  a 200 mV floor at the far receiver after cable loss. At the minimum corner and
  a 4.5 m cable this may be marginal [verify: TLK1221 output structure is not
  documented; bench measure eye at the far end of a 4.5 m S800 cable].
  Consequence for the front end: **do not add the 75 Ω series pads proposed in
  WORKING-NOTES §2** on the TX side; they lower the amplitude further.
- Unpowered board: TXP/TXN, RD and RBC are high impedance at power-on reset
  (p.2 "hot-plug capable"). Absolute maximum on the high-speed pins is
  -0.3 V..VDD+0.3 V (p.8); the 10 nF series caps block the cable DC bias, so
  only AC transients reach the pins (reasoning).

### 1.5 TX disable for sharing TPB with the legacy driver (checked, timing not specified)

- Two ways: **LOOPEN high** puts TXP/TXN in high impedance and routes TX to RX
  internally, PLL stays running (Table 2 LOOPEN; p.6 "Loopback Testing").
  **ENABLE low** powers everything down, including RD and RBC; leaving it costs
  up to 500 µs of PLL lock (p.8 "PLL Startup lock time") and 500 µs receiver
  acquisition (p.9).
- The LOOPEN-to-high-Z time is **not specified**. It is a static mode pin, so
  expect nanoseconds to a few hundred nanoseconds [verify on bench]. That is
  fast enough: 1394b toning is a burst of 667 µs every 42.7 ms (secondary
  source above, [verify]), and the port switches between beta and legacy once
  per connection, not per packet.
- High-Z leakage and output capacitance in LOOPEN mode are not specified
  [verify]. The legacy S400 driver sees this load through the 10 nF caps; the
  coexistence study in `spice/` (beta eye and legacy eye with idle SerDes) has
  been written but never run, and needs this capacitance.

### 1.6 Loss of signal / tone detection: **not provided by TLK1221** (checked)

- The pin list (Table 2) has no LOS or signal-detect pin. SYNC/PASS only
  reports commas (SYNCEN high) or PRBS results.
- Tone **generation** works: alternate words `1111111111` and `0000000000`
  give a 20-UI period, i.e. exactly 49.152 MHz at 983.04 Mbaud, the tone
  frequency given for S800 in the secondary sources [verify the 1394b tone
  frequency tolerance].
- Tone **detection**: use the SN65LVDS34 channel already on TPA. It has a
  ±50 mV threshold and 400 Mb/s (SLLS490B) and so passes a 49 MHz tone of
  ≥200 mV easily; the FPGA counts transitions per microsecond. Its active
  failsafe (output high when |VID| < 32..100 mV for 0.3..1.5 µs) gives a
  coarse squelch for free. In beta operation, loss of sync is detected in the
  FPGA from 8B10B code and disparity errors (reasoning).

### 1.7 Parallel interface timing (checked)

| Mode (RBCMODE) | RBC | RD valid window at 125 MHz (p.11) |
|---|---|---|
| 1, full rate | RBC0 = 98.304 MHz, rising edge | setup 2.5 ns, hold 2 ns (5 / 4 ns at 61.44 MHz) |
| 0, half rate | RBC0/RBC1 = 49.152 MHz, 180° apart, one word per rising edge of each | setup 2.5 ns, hold 1.5 ns |

At 98.304 MHz the window is at least 4.5 ns of a 10.17 ns period (interpolated
between the 125 MHz and 61.44 MHz rows). RD/RBC are LVTTL from a 2.5 V supply:
VOH ≥ VDD - 0.2 V = 2.1 V at 2.3 V supply (p.9), so put the FPGA bank that
receives them at 2.5 V VCCIO rather than relying on LVCMOS33 VIH = 2.0 V.
TD inputs are 3.3 V tolerant (VIH 1.7 V). Pins needed: TD 10, RD 10, RBC0
(and RBC1 in half-rate mode), SYNC (optional), LOOPEN, ENABLE, PRBSEN: about
25 FPGA I/O. RBC is the recovered clock, not REFCLK, so the FPGA needs an
elasticity buffer between the two domains (1394b PHYs have one anyway).

### Verdict on TLK1221: **go (S800 only), with two bench risks**

It is Active, takes raw 10-bit groups, its comma logic can be switched off,
runs at 98.304 MHz REFCLK, and its receiver threshold equals the 1394b
floor. Risks: (1) TX amplitude into the double-terminated bilingual port,
(2) high-Z loading of TPB in legacy mode. No tone or LOS detector: solved with
the SN65LVDS34 that is already in the design. S400b is not covered.

## 2. FPGA candidates

### 2.1 What the FPGA has to do (requirements derived here)

**TLK1221 bus (both directions):** 10 bits SDR at 98.304 MHz, or two
49.152 MHz half-rate clocks; RD window about 4.5 ns of 10.17 ns (§1.7); TD
setup 1.6 ns / hold 0.8 ns to REFCLK.

**Legacy DS at S400:** data and strobe arrive as two single-ended LVTTL lines
from the SN65LVDS34, 393.216 Mb/s, so one bit cell is 2.54 ns. Two methods:

- *XOR clock recovery:* D xor S gives a 196.608 MHz clock that has to go
  through a global buffer, with D captured on both edges. The clock has to
  arrive half a bit (1.27 ns) after the data, through a fabric path whose
  delay varies over process, voltage and temperature. It needs delay taps on
  the data and calibration.
- *Oversampling (preferred, reasoning):* sample D and S at the same instants
  and treat each change of the (D, S) pair as one bit. Every bit cell has to
  contain at least one sample. The worst-case cell is 2.54 ns minus 2 × 0.315 ns
  receive jitter (TSB81BA3E p.10) minus about 0.2 ns receiver pulse skew,
  about 1.7 ns. The sample period therefore has to be under about 1.4 ns with
  margin: **786.432 MS/s (8 × 98.304 MHz) per signal**. This needs a hard
  deserializer, because a fabric clock of that speed is out of reach.

**Legacy DS transmit at S400:** 393.216 Mb/s per pin into the transistor
driver. With a serializer at 786.432 Mb/s each bit is sent twice.

**Hot socketing:** the driver-reference and emitter pads face the cable
through transistors and 91 Ω (WORKING-NOTES §2). The spice unpowered study
measured 31.8 mA back-feed into a clamping bank against 0.99..2.27 mA
without one, so these pads must be on a bank with no clamp diode to VCCIO.

### 2.2 Logic size: measured on the existing Amaranth gateware

All existing cores were synthesized with Yosys 0.5x from branch
`gateware/timing-closure` (Amaranth 0.5.8). Targets: `synth_ice40`,
`synth_xilinx -family xc6s`, and `synth_intel -family cycloneiv`, which stands
in for AGM (see §2.5). These are synthesis counts only, without place and route.

| Core | iCE40 LUT4 | Spartan-6 LUT6 (FF) | Cyclone IV LE |
|---|---|---|---|
| `link_layer` (packet RX/TX, CRC, cycle timer, self-ID) | 1547 | 1029 (1015) | 2479 |
| `transaction_link` (link + async responder, CSR, config ROM) | 6571 | 5048 (5221) | 11773 |
| `raw_worker` (transaction_link + raw USB tunnel worker) | 21485 | 15641 (17681) | 38850 |
| `iso_rx` / `iso_tx` | 646 / 392 | 890* / 380 | n/a / 573 |
| `amdtp_rx` / `amdtp_tx` / `syt` | 139 / 227 / 46 | small | 281 / 338 / 87 |
| `cycle_follower` | 637 | 318 | 1121 |

(*sum includes a duplicate hierarchy line; treat as approximate.) Finding:
`transaction_link` and `raw_worker` keep their buffers in flip-flops (Amaranth
`Array` of `Signal`, e.g. `transaction.py:113`, `responder.py:41..43`,
`raw_worker.py:60,139,145`), so they **do not fit any of the three FPGAs as
written**. In the MCU architecture, transactions, config ROM, CSRs and the raw
worker belong in MCU firmware; the FPGA keeps link, iso, AMDTP and cycle logic.

Estimate for the FPGA side (reasoning; the new blocks have no code yet):

| Block | LUT4 |
|---|---|
| Link layer, iso RX/TX, AMDTP, SYT, cycle follower (measured above) | ~3 600 |
| 1394b port: comma align, 2 × 8B10B enc/dec, scrambler, elasticity buffer | ~800 |
| 1394b port state machine: toning, speed negotiation, training, BOSS arbitration, request/grant symbols | 1 500..2 500 |
| 1394a PHY: DS encode/oversampled decode, arbitration states R0..A2/TX/RX, timers, speed signalling | 1 500..2 500 |
| Shared PHY: registers, self-ID, gap count, config packets | 500..800 |
| MCU interface (QSPI slave, register file, FIFOs into block RAM) | 300..600 |
| **Total** | **~8 200..10 800 LUT4**, roughly 5 500..7 500 LUT6 |

### 2.3 Xilinx Spartan-6 XC6SLX9-2TQG144C

Source: DS162 v3.1.1, 30 Jan 2015 (third-party copy,
<https://p.globalsources.com/IMAGES/PDT/SPEC/400/K1215939400.pdf>; the AMD
portal <https://docs.amd.com/v/u/en-US/ds162> only serves a script page to
non-browsers).

- **Deserializer and serializer:** ISERDES2/OSERDES2 4:1..8:1 with BUFPLL,
  **950 Mb/s on speed grade -2** (1050 on -3); IDDR2 750 Mb/s on -2 (Table 25).
  BUFPLL and PLL output up to 950 MHz on -2 (Tables 51, 52). So 786.432 MS/s
  oversampling of D and S (PLL VCO = 786.432 MHz from the 98.304 MHz
  oscillator, in the 400..1000 MHz range of Table 52) and 786.432 Mb/s DS
  transmit are **within specification**. One limitation: Table 25 lists LVDS. The
  SN65LVDS34 outputs are single-ended LVCMOS33 that toggle at ≤ 393 Mb/s, and
  the sampling rate is set by BUFPLL, not by the input standard [verify on
  bench]. An 8:1 ISERDES2 uses the slave site of a pair, so each oversampled
  signal costs two pins.
- **Delay taps:** IODELAY2 with calibration (Table 39: tap 8 = 322..424 ps max;
  variable mode needs ≥ 188 Mb/s). Usable to align D and S, and to centre
  RD in the TLK1221 window.
- **Clocking:** 2 CMTs (2 PLL + 4 DCM in LX9), BUFGMUX up to 375 MHz on -2
  (Table 48). DCM output period jitter ±100..150 ps (Table 54), so an FPGA
  clock is not good enough for TLK1221 REFCLK.
- **TLK1221 bus:** IOB registers at 98.304 MHz with IODELAY2 or DCM phase
  adjustment fit easily. RBC enters on a GCLK pin, and an async FIFO crosses
  into the REFCLK domain.
- **Hot socket: good.** IHS = ±20 µA on all pins with the FPGA unpowered
  (HSWAPEN = 1), and VIN up to 4.0 V regardless of VCCO except for the PCI
  standard (Tables 1 and 4). This is the best of the three candidates.
- **Logic:** 5 720 LUT6 and 11 440 FF (DS160 family table [verify]), against
  5 500..7 500 LUT6 estimated. **Tight to not fitting.** The next size up,
  XC6SLX16 (9 152 LUT6), only comes in BGA (FTG256, CSG324, CPG196).
- **Toolchain:** ISE 14.7 only (free WebPACK covers LX9 and LX16), closed,
  frozen since 2013, Linux or Windows VM. No open place-and-route for
  Spartan-6. Amaranth's `XilinxPlatform` supports Spartan-6 through ISE, so
  the gateware can target it after the ECP5 `BB`/IOLOGIC instances in
  `timing_top.py` are replaced.
- **Lifecycle:** a 2009 design. AMD states production to at least 2030
  (PARTS-SEARCH.md) [verify the current AMD statement].

### 2.4 Lattice iCE40UP5K-SG48I

Source: FPGA-DS-02008-2.4,
<https://www.latticesemi.com/view_document?document_id=51968>.

- **I/O speed:** maximum 250 MHz toggle (Table 4.19). **Global buffer
  fMAX 185 MHz** (Table 4.21), so an XOR-recovered 196.6 MHz DS clock is out of
  specification. No SERDES and no input delay taps (the only fine delay is in
  the single PLL, DYNAMICDELAY, Table 3.3). SB_IO DDR registers are limited by
  the same GBUF. The best case is 370 MS/s per pin, against 786 MS/s needed.
  **S400 DS receive: no.** S200 (196.6 Mb/s) would be plausible.
- **TLK1221 bus:** worst-case PIO input window is tSU -0.5 ns / tH 5.55 ns
  without PLL (5.05 ns), or 7.3 / -1.1 ns with PLL (6.2 ns), from Table 4.21.
  Both are wider than the ~4.5 ns the TLK1221 guarantees. **Not closable on
  datasheet numbers**, though real silicon may work [verify].
- **Fabric:** 16-bit counter 100 MHz worst case, 64-bit counter 40 MHz
  (Table 4.16). A 98.304 MHz 1394b datapath would have to run at 49.152 MHz,
  two symbols wide.
- **PLL:** one; period jitter 450 ps p-p above 100 MHz (Table 4.22).
- **Hot socket: no.** "Input pins are clamped to VCCIO and GND by a diode"
  (§4.9 Table 4.5, note 4).
- **Logic:** 5 280 LUT4 against ~8 200..10 800 needed. **Does not fit.**
- **Toolchain:** Yosys + nextpnr-ice40, mature and open. Amaranth has
  `LatticeICE40Platform`.

### 2.5 AGM AG10KL144

Source: "AGM FPGA — Low Cost and High Performance FPGA", Data Sheet Rev 1.1,
20 Sep 2015, 18 pages, the only document found (LCSC copy,
<https://atta.szlcsc.com/upload/public/pdf/source/20171113/C133763_15105610808631115448.pdf>).
It is a family sheet for AG6K/AG10K and does not name the AG10KL144 or give
its speed grade.

- **Architecture as described:** LUT4 slices, M9K block RAM (414 kbit), 2 PLLs
  (VCO 500..1200 MHz, output to global clock ≤ 402.5 MHz, phase step 96 ps),
  10 global clocks, "True-LVDS", programmable input/output delay, "serialization
  and deserialization through internal logic" (§1.5, §1.6, §1.10, Table 4-2).
  The text and tables closely follow Altera Cyclone IV documents (M9K, LVDS
  table 3-5). The part is widely described as a Cyclone IV E clone [verify].
- **Missing from the datasheet:** I/O timing (no tSU/tH/tCO), DDR I/O rates,
  delay-tap values, PLL output jitter, hot-socket behaviour (only ±10 µA
  leakage for VI = 0..VCCIO, Table 3-3), and any lifecycle statement.
  Recommended VI max 3.6 V, absolute 4.2 V (Tables 3-1, 3-2).
- **DS at S400:** no hard SERDES. If it behaves like Cyclone IV, oversampling at
  786 MS/s would need DDIO with two PLL phases at 196.6 MHz and fabric
  registers near the pins: possible in principle, **not designable from this
  datasheet**.
- **TLK1221 bus:** a 98.304 MHz SDR bus is probably easy (clock tree
  402..500 MHz, Table 4-1), but there are no I/O timing numbers to check it
  against.
- **Logic:** about 10k LUT4 against ~8 200..10 800 needed (yosys Cyclone IV
  mapping is less efficient; see table). **Borderline.** AG16KL144A (16k) would fit.
- **Toolchain:** AGM "Supra", Windows/Linux (§6). Public reports describe a
  flow where Quartus synthesizes and Supra places and routes [verify]. Closed.
  Amaranth has no AGM platform; the route would be Amaranth → Verilog → Supra.

### 2.6 FPGA verdicts

| | Spartan-6 LX9 | iCE40UP5K | AGM AG10K |
|---|---|---|---|
| TLK1221 bus at 98.304 MHz | yes, IOB + IODELAY2 | not closable on datasheet | unknown (no I/O timing) |
| DS RX at S400 (786 MS/s oversampling) | yes, ISERDES2 950 Mb/s | **no** (185 MHz GBUF, 250 MHz I/O) | not designable from datasheet |
| DS TX at S400 | yes, OSERDES2 | no | unknown |
| Delay taps / PLL | IODELAY2 / 2 PLL + 4 DCM | none / 1 PLL | "programmable delay" / 2 PLL |
| Hot socket | ±20 µA unpowered | clamp diodes | not specified |
| Logic vs ~8..11k LUT4 | 5 720 LUT6: tight | 5 280 LUT4: no | ~10k LUT4: borderline |
| Toolchain | ISE (closed, frozen); Amaranth yes | open; Amaranth yes | closed; no Amaranth platform |
| **Verdict** | **go with risk** | **no-go** | **no-go** (data missing) |

## 3. Clocking

Needs: 98.304 MHz REFCLK for the TLK1221 (≤ 40 ps jitter, ±100 ppm, 40..60 %
duty; §1.3); 98.304 MHz for the FPGA TX path, because TD is registered on REFCLK;
49.152 MHz for the 1394a side (BASE_RATE ±100 ppm, SOFT-PHY.md timing table);
786.432 MHz for the DS serializers; 12 MHz for the AT32F405 HS PHY, which
"requires a dedicated 480 MHz clock … generated by a PLL connected to HEXT
12 MHz oscillator. Internal clock sources or other external oscillators are not
supported" (AT32F405 DS v2.02 §2.13.6).

**An FPGA PLL cannot make REFCLK.** iCE40UP period jitter is 450 ps p-p
(Table 4.22), Spartan-6 DCM ±100..150 ps (DS162 Table 54; PLL jitter only in
the Clocking Wizard), and AGM gives no output-jitter figure. All exceed 40 ps, so
a cheap crystal multiplied in the FPGA is ruled out. A Si5351-class synthesizer
was not checked and would cost more than an oscillator anyway.

**Chosen solution:** one 98.304 MHz CMOS oscillator, ±30..50 ppm, drives both
the TLK1221 REFCLK and an FPGA global clock pin. Use two short point-to-point
traces with series resistors, or a single trace with the TLK1221 at its end. In
the Spartan-6, one PLL makes 786.432 MHz (×8, VCO in range) for
BUFPLL/ISERDES2/OSERDES2 and 49.152 MHz (÷2). The MCU keeps its own 12 MHz
crystal. The audio media clock is handled as in `docs/audio/CLOCK-UAC2.md`.

| Candidate | Spec | Price at 100 (LCSC live, 2026-11-22) | Note |
|---|---|---|---|
| JGHC O7598304153033 (C479181), 7050, 3.3 V CMOS | ±30 ppm tolerance, -40..85 °C, rise ≤ 5 ns, duty 45..55 %, aging ±3 ppm/yr (maker spec sheet 2022-09-23) | **$0.827** | stock 93; **no jitter figure** [verify on bench, need < 40 ps p-p]; 3.3 V output is fine (REFCLK VIH 1.7 V, 3.3 V tolerant) |
| SiTime SiT9120AC-2B3-25S98.304000 (C805371), 3225 | low-jitter MEMS XO family (jitter spec not re-read here) | $1.568 at 200 | stock 0 at LCSC |
| Diodes FK9830002 (C1680946), 3225, 3.3 V CMOS | not read | $2.451 at 200 | stock 0 |

The 5 ns maximum rise time of the JGHC part is slow for a 10.17 ns period.
Duty cycle is still specified and REFCLK only uses the rising edge, but a slow
edge turns supply noise into jitter. Prefer a part with a stated jitter figure
if the bench result is marginal.

## 4. MCU: AT32F405

Source: AT32F405/402 datasheet Ver 2.02, 2025-01-17 (LCSC copy,
<https://atta.szlcsc.com/upload/public/pdf/source/20250815/5EA8CFDFE464A83C11E08A951E81FF4A.pdf>).

- **No parallel memory bus.** The AT32F405 has no XMC/FSMC; the feature
  list and peripheral table list QSPI, SPI, I²S, USART, I²C, CAN, OTGHS and
  OTGFS only (pp.1..3, Table 1). The XMC exists on AT32F407/F435/F437.
- **QSPI:** one, up to **108 MHz** SCK, input setup 2 ns / hold 4.5 ns, output
  valid ≤ 3 ns (§4.3.16 Table 43). Indirect, status-polling and memory-mapped
  modes, DMA-capable (§2.2.4, §2.7). The FPGA acts as a QSPI "memory": 4 bits ×
  54..72 MHz = 216..288 Mb/s raw, half duplex. A more comfortable 54 MHz SCK
  keeps the FPGA slave timing easy. Command and address overhead roughly halves
  this for small transfers, so use ≥ 256-byte bursts per direction per 125 µs.
- **SPI:** 3 × up to 36 Mb/s (p.1), or 32 Mb/s (§2.13.x). Fine for control or
  a status channel, too slow for audio.
- **OTGHS with on-chip PHY:** device mode HS/FS, 8 IN + 8 OUT endpoints,
  **dedicated 4 KB FIFO RAM**, internal DMA (§2.13.6).

**UAC2 capacity (reasoning).** With 4 KB of FIFO for all endpoints, one
1024-byte isochronous packet per microframe per direction is realistic
(EP0 64 B + IN 1024 B + feedback + RX FIFO about 1.2 KB). High-bandwidth
(2..3 × 1024 B) isochronous needs more FIFO than exists. One 1024-byte
packet per microframe is 8.19 MB/s per direction:

| Rate | Frames per microframe (max) | 24-bit in 3-byte subslots | 24-bit in 4-byte subslots |
|---|---|---|---|
| 44.1/48 kHz | 7 | 48 ch | 36 ch |
| 88.2/96 kHz | 13 | 26 ch | 19 ch |
| 192 kHz | 25 | 13 ch | 10 ch |

That covers the FireWire interfaces in `docs/` (e.g. Saffire PRO 26/40 at
48 kHz) but not the largest ones at 96 kHz. Each direction needs ≤ 66 Mb/s,
so the QSPI link (≥ 100 Mb/s effective, both directions) is adequate for
audio plus control at these rates, but not for raw 1394 at S400/S800 line
rate. Raw (non-audio) tunnelling is limited to about 50..60 Mb/s, either by
QSPI efficiency or by bulk USB through the 4 KB FIFO. [verify: Artery OTGHS
FIFO allocation rules; TinyUSB/CherryUSB support for AT32F405 OTGHS
isochronous.]

**Implication:** the existing gateware does USB in the FPGA (LUNA over ULPI,
`usb_device.py`, `uac2.py`). With the AT32F405, UAC2 moves to MCU firmware,
and the FPGA ↔ MCU QSPI link replaces the ULPI PHY. This is a large
software change, but it also removes the oversized `transaction_link` and
`raw_worker` logic from the FPGA (§2.2).

## 5. Overall verdict

| Option | Verdict | Top risks |
|---|---|---|
| TLK1221 + **Spartan-6 XC6SLX9** + SN65LVDS34 + AT32F405 | **go with risk** | (1) logic fit: 5 720 LUT6 vs 5 500..7 500 estimated, next size is BGA-only; (2) closed, frozen ISE toolchain, no open alternative; (3) single-ended LVCMOS ISERDES2 at 786 MS/s not explicitly specified; (4) 2009 part, lifecycle relies on the AMD 2030 statement |
| TLK1221 + **iCE40UP5K** | **no-go** | S400 DS impossible (185 MHz GBUF, 250 MHz I/O, no SERDES or taps); TLK1221 bus timing not closable on datasheet; 5 280 LUT4 too small; clamp diodes |
| TLK1221 + **AGM AG10KL144** | **no-go as specified** (could be revisited with real data) | 2015 family datasheet has no I/O timing, DDR, jitter, hot-socket or lifecycle data; logic borderline; closed toolchain, no Amaranth platform |

**TLK1221** itself: **go for S800** (§1). Bench risks: TX amplitude into the
double-terminated bilingual port, high-Z loading of TPB in legacy mode, and
REFCLK jitter of the cheap oscillator. S400b is not covered.

**Recommended architecture (if Spartan-6 is acceptable to the no-old-parts
rule):** TLK1221 (SYNCEN low, full-rate RBC) + XC6SLX9-2TQG144C (ISERDES2/
OSERDES2 at 786.432 Mb/s for legacy DS, IOB capture for the TLK1221) +
SN65LVDS34 (legacy receive and tone detect) + AT32F405 over QSPI at
54..72 MHz, with one 98.304 MHz oscillator for TLK1221 and FPGA and a 12 MHz
crystal for the MCU. Partition: soft PHYs, link, iso/AMDTP and cycle in the
FPGA; transactions, config ROM, CSRs, raw tunnel and UAC2 in the MCU.

**Alternative families that would probably beat all three (not priced here):**

- **Gowin GW1N-9 / GW1NR-9 (LittleBee):** about 8.6k LUT4, IDES/OSER gearboxes
  and IODELAY in the I/O logic, PLLs. Open flow through Apicula +
  nextpnr-himbaechel, and Amaranth has a Gowin platform. The GW1N datasheet
  could not be retrieved earlier (Mouser block), so gearbox rates and
  hot-socket behaviour are [verify]. This is the first family to check.
- **Lattice ECP5 LFE5U-12F:** 12k LUT4, IDDRX2/ODDRX2 gearing, DELAYF taps,
  top/bottom banks hot-socket. This is the same family and toolchain as the
  current gateware (zero porting). GDDRX2 is 624/700/800 Mb/s for grades
  -6/-7/-8 (PARTS-SEARCH.md), so 786 MS/s needs grade -8 or a 2-phase scheme
  [verify]. Price is the open question; the 25F was $22.19.

## Bench tests needed before layout

1. TLK1221 TX eye at the far end of a 4.5 m S800 cable with 2 × 56 Ω
   termination at both ends (amplitude ≥ 200 mV at the receiver).
2. TLK1221 in LOOPEN high-Z: capacitance and leakage on TPB, and the S400
   legacy eye with the idle SerDes attached (the unrun `spice/` study, then
   hardware).
3. TLK1221 lock and RX on a real 1394b peer: comma polarity, alignment in
   fabric, ±200 ppm margin with ±30 ppm oscillators.
4. Tone generation (49.152 MHz pattern) and detection via the SN65LVDS34
   against a real bilingual PHY (TSB81BA3E-based card).
5. Oscillator REFCLK jitter (JGHC part) under board noise.
6. Spartan-6 ISERDES2 8:1 at 786.432 MS/s on LVCMOS33 inputs fed from the
   SN65LVDS34: DS decode BER at S400 with ±0.315 ns injected jitter.
7. AT32F405 OTGHS: 1024-byte isochronous IN + OUT + feedback in the 4 KB FIFO
   at 8 kHz microframes, with QSPI DMA running.
