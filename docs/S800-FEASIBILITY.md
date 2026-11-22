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
