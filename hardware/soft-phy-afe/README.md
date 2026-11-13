# One-port S100 analog front end (research revision A)

CERN-OHL-S-2.0; see [hardware licence](../LICENSE). Workstream B of #13.
**Architecture experiment, not a fabrication-ready or electrically qualified PHY.**
Receiver circuitry is specified down to candidate parts and threshold networks;
the active current-steering stage still needs transistor-level design and bench
validation. No KiCad manufacturing files are supplied for that unqualified stage.
The generic adapter should use a chip PHY at S100/S200/S400; this experiment
removes the chip only for profiles that actually fit S100. Protocol-family speed
and bandwidth limits are researched in [PR #14](https://github.com/Efllux/fw2usb/pull/14).
No particular audio brand or protocol is assumed by this electrical port.

## Sourced requirements

The reference is [TI TSB41AB1 SLLS423I](https://www.ti.com/lit/ds/symlink/tsb41ab1.pdf),
printed pp.2–3,16–20. These are published **chip limits**, not an assertion that
every number is an IEEE normative conformance limit. [Philips PDI1394P23](https://media.digikey.com/pdf/Data%20Sheets/NXP%20PDFs/PDI1394P.pdf)
§§9–14 corroborates the principal thresholds. See IEEE 1394-1995 §4.2/4.3 and
1394a-2000 §4 for final cable compliance requirements.

| Function | Reference-chip behavior / requirement |
|---|---|
| Differential TX | 172–265 mV into 56 ohm; <=20 mV when disabled (AB1 p.17) |
| Differential current | Derived 3.07–4.73 mA through 56 ohm; nominal 4 mA chosen here |
| CM current imbalance | Algebraic sum of+/- driver currents within±1.05 mA, speed off; this is **not** differential signal current |
| Data RX | Threshold -30..+30 mV, minimum recommended signal 118 mV |
| Arbitration RX | Positive threshold 89..168 mV, negative -168..-89 mV; recognize 0, 1, Z |
| TPBIAS | 1.86 V nominal, loaded 1.665..2.015 V; source/sink -5.6..+1.3 mA |
| TPB common mode | 0.4706..2.515 V source-power or 0.4706..2.015 V nonsource-power |
| Bias detection | TPB CM threshold 0.6..1.0 V |
| Speed detection | Peer compares its TPBIAS with TPA CM: S200 droop 49..131 mV; S400 314..396 mV |
| Speed signaling | TPB current sink per conductor: S200 2.53..4.84 mA; S400 8.1..12.4 mA; S100 must add neither |
| Termination | 110-ohm cable; TI uses 2x56 ohm per pair per end, including its internal RX load |
| Bias networks | TPA center to TPBIAS + 1 uF; TPB center to 5 kohm parallel 220 pF |
| S100 timing | 98.304 Mb/s; input jitter ±1.08 ns; pair skew ±0.8 ns (p.16) |
| TX edges | AB1 specifies 0.5..1.2 ns (p.20); BA3F-EP specifies 0.3..0.8 ns (§6.8), so do not treat either as a universal IEEE limit |

Data is transmitted on TPB, strobe on TPA. The cable crosses A to B; receive data
is therefore local TPA and receive strobe local TPB (AB1 p.2). This distinction
also applies to termination and speed detectors. Opposing equal endpoint currents
cancel differential voltage; interpreted arbitration still applies one's-dominance
using our own transmitted state (IEEE 1394-1995 §4.3.3, public
[EPO tables 3–5](https://data.epo.org/publication-server/rest/v1.2/publication-dates/20010425/patents/EP1094638NWA2/document.pdf)).

## Topology comparison and decision

| Choice | Assessment |
|---|---|
| FPGA LVCMOS + series resistors | Reject as cable TX: low output impedance, voltage clamping, poor cancellation and large CM switching |
| Ordinary tri-state LVDS buffer | Reject as drop-in: e.g. [SN65LVDS31](https://www.ti.com/lit/ds/symlink/sn65lvds31.pdf) regulates near 1.2 V and ~350 mV differential; disabling it does not fix active CM/amplitude |
| Fast CMOS analog switch | Do not confuse signal bandwidth with control speed: [TMUX1511](https://www.ti.com/lit/ds/symlink/tmux1511.pdf) specifies 25 ns typical/55 ns maximum control transition; unsuitable as S100 per-bit switch |
| Complementary source/sink steering | Chosen research path: both conductors see equal opposite currents, high impedance and explicit Z/dummy-load selection; matching, headroom and skew remain difficult |
| Commercial1394 PHY | Reference/bring-up choice; already provides port-monitor, speed signaling, protection behavior and qualified timing |

### Proposed balanced driver, one copy per pair

A high-side 4 mA source and low-side 4 mA sink feed steering trees with three
collector destinations: P, N, or dummy load. Use complementary RF transistors
**MMBTH81** (PNP) and **MMBTH10LT1G** (NPN), emitter degeneration and trimmable
current references. Candidate RF devices and public transistor specifications:
[MMBTH81](https://www.onsemi.com/download/data-sheet/pdf/mmbth81-d.pdf),
[MMBTH10](https://www.onsemi.com/pdf/datasheet/mmbth10-d.pdf). The published fT
(600 MHz for MMBTH81) does not prove switching time in this circuit.

| Logic state | Source destination | Sink destination | Differential result |
|---|---|---|---|
| 1 | P | N | positive |
| 0 | N | P | negative |
| Z | dummy | dummy | both cable collectors high impedance |

Source and sink remain biased during Z to avoid reference start-up transients.
Dummy loads should reproduce the ~1.86 V collector operating point. Hardware
interlocks must prohibit connecting two collectors simultaneously. Level shifting
and complementary timing must be designed together; FPGA CMOS outputs cannot
be wired directly to every transistor base. Source/sink switching should be
matched to much less than a nanosecond, to be established by measurement.

Two 110-ohm terminations in parallel give 55 ohm, so nominal 4 mA gives 220 mV.
Identical endpoint drives add (~440 mV), opposing drives cancel (~0 mV), and one
Z passes the other drive. The comparators must tolerate both collision amplitudes
and ordinary data, even though the data amplitude specification describes a
single transmitter. Drive cancellation is verified in the behavioral sweep.

Use separate **+5 V and negative analog headroom** (proposed -5 V) for a
complementary steering prototype; these are engineering choices. A stacked
source/sink stage on 3.3 V cannot claim compliance across the full published
0.4706..2.515 V cable CM range. The rail generator, fast base level shifting,
current references, temperature compensation, transistor count and powered-off
isolation remain **unqualified**. The SPICE model has a finite CM-compliance
window and finite differential output impedance, but is not a model of these
transistors or a completed driver schematic. Do not manufacture this active
stage from the behavioral netlist.

### Termination, receive and FPGA connections

Per port:

```
TPA+ --55R--+--55R-- TPA-       TPB+ --55R--+--55R-- TPB-
            |                              |
       buffered TPBIAS                 5k || 220pF
         with 1uF                          |
            |                             GND
           1.86V

Each pair -> zero-crossing DS comparator -> FPGA
          -> +125mV / -125mV window comparators -> FPGA
          <- balanced 1/0/Z current-steering stage
```

Use 2x55 ohm 0.1% initially for external high-impedance receivers, then recalculate
loaded impedance. TI's 2x56 ohm compensates its different internal RX loading
(AB1 pp.2–3); copying that value without considering our receivers is unjustified.
Short matched differential traces, continuous return paths and connector-side
protection are layout requirements to validate, not breadboard connections.

Use three **TLV3602DGKR** dual comparators: one dual for two DS receivers, two
duals for the four arbitration thresholds. [TI TLV3602 SNOSDB1E](https://www.ti.com/lit/gpn/TLV3602)
§6.5 pp.7–8 specifies rail-to-rail input CM (to 0.2 V outside supply), maximum
±5 mV offset, 1 pF typical input capacitance, 2.5 ns typical propagation delay
(4.5 ns maximum under stated 50 mV-overdrive conditions), and 24 ps **typical**
dual-channel skew. Fixed hysteresis 1.5–5 mV. Typical skew is not a guaranteed
full-temperature DS timing budget.

For arbitration use one **AD8421ARZ** instrumentation amplifier per pair at
G=1 (RG open), REF=1.65 V, on proposed +5/-5 V rails. Its high-impedance inputs
avoid driving the cable from local threshold references. Feed its output to the
two TLV3602 window inputs against 1.775 V and 1.525 V references (+/-125 mV).
The reference divider/buffers are entirely behind the amplifier and cannot
source cable-bias current. Match divider ratios and budget offset/hysteresis;
the DC sweep checks 110/125/140 mV equivalent thresholds.

[AD8421 Rev.A pp.3–4, input/response tables](https://www.analog.com/media/en/technical-documentation/data-sheets/AD8421.pdf)
specifies 30 Gohm||3 pF input impedance and 10 MHz bandwidth at G=1. Supply
range is 5–36 V total. The input CM and output swing depend on supply and REF;
+/-5 V is proposed to accommodate the cable CM and 1.65 V output reference.
Check the datasheet diamond plot at worst-case temperature/offset and the
actual output load before layout. Bandwidth does not guarantee all transient
settling times; the simulator's 10 MHz single pole is **an assumption**, not a
vendor macromodel. Only arbitration uses this slower path; DS goes directly to
the fast TLV comparator. Window flags 10=1, 01=0, 00=Z, 11=invalid.

Do not use low-resistance mixing from cable pins to fixed local references to
make offsets: it can force TPB CM above the connection-detect threshold even
with no powered peer. A tracking-CM offset network could avoid that fault but
requires its own high-impedance buffer and rail/error analysis. The chosen
instrumentation amplifier makes that separation explicit. Only enable DS capture
in packet states; zero-crossing outputs during Z are not valid packet bits.

The FPGA sees 3.3 V LVCMOS comparator outputs and supplies digital state commands.
Choose an independent capture strategy (DDR/oversampling/delay calibration) and
prove metastability and D/S skew tolerance. Matching latency through comparators
matters more than a common fixed delay. The ideal DS codec does not demonstrate
FPGA input timing closure.

| FPGA direct LVDS option | Guaranteed limits / decision |
|---|---|
| ECP5 | [FPGA-DS-02012-3.4 §3.14.1 table3.13](https://www.latticesemi.com/view_document?document_id=50461): CM 0.05..2.35 V, differential threshold ±100 mV, input 0..2.4 V. Nominal 1.86 V could work but source-power maximum 2.515 V exceeds range; minimum 118 mV signal leaves only 18 mV threshold margin. External comparator chosen |
| iCE40 LP/HX | [FPGA-DS-02029 §4.16.1 table4.14](https://www.latticesemi.com/view_document?document_id=49312): CM 0.95..1.55 V at 2.5 V bank, 250..450 mV differential input; unsuitable directly |
| iCE40 UltraPlus | [datasheet §4.18](https://www.latticesemi.com/api/document/download?id=51968): differential comparator ±250 mV; unsuitable for minimum cable amplitude |

### TPBIAS and connect detect

**REF3318AIDCKR** 1.8 V reference plus **OPA320AIDBVR** gain
`1+1k/30k=1.03333` yields 1.86 V. Include feedback/load error and full source/sink
current range in the next circuit revision. The 1 uF bias capacitor requires loop
stability analysis: [OPA320 SBOS513F §7.3/Figure 36](https://www.ti.com/lit/gpn/OPA320)
uses output isolation for capacitive loads (10–20 ohm examples). A series resistor
creates DC load error; dual feedback or compensation must handle both stability
and bias accuracy. [REF3318 specifications](https://www.ti.com/lit/gpn/REF3318)
support the reference choice. SPICE's 5-ohm source plus 1 uF is a modeling
assumption, **not** a stability verification of OPA320.

Use **TLV7012DGKR** for a ~0.8 V TPB-center-tap bias detector, with high input
impedance. Device-side thresholds are 0.6..1.0 V; verify hysteresis and error
against those bounds. Apply standard port debounce and reset logic in FPGA
(1394a §4.3.5). A bias detector detects a **powered peer**; unpowered-peer connect
probing and suspend/resume TPBIAS handshakes are separate functions. Philips
PDI1394P23 §11 lists a 76 uA maximum connect-detect current. That active probe
is not implemented or claimed by this prototype.

## Power, ESD and isolation

**Leave cable VP unconnected.** Segregate its connector pad and preserve clearance
for this design's 33 V envelope. [TI SLVA449 §1](https://www.ti.com/lit/pdf/slva449)
describes 8–30 V IEEE 1394a cable power and late-ground damage. 33 V is our design
margin, not a replacement for the cited standard limit. Leaving VP open does
not prevent a faulty connector/cable or late signal-ground contact from imposing
an electrical overstress condition on data pairs.

**TPD4E05U06DQAR**, one four-line array, is a low-capacitance ESD candidate:
[TI](https://www.ti.com/product/TPD4E05U06) gives 0.5 pF typical, 5.5 V standoff and
±12 kV contact rating. Its 10–14 V clamp is above comparator input ratings. It
therefore does **not** solve sustained 33 V shorts or all late-ground EOS. Secondary
clamps/current limiting, return-path design and fault testing are unresolved;
adding series resistance/capacitance must be included in the signal budget.

Power separation is **not galvanic isolation**: the cable signal ground remains
part of this AFE. Full galvanic isolation would need an isolated AFE supply and
adequate digital barrier bandwidth/latency. No isolation voltage or IEC immunity
rating is claimed. First passive tests should use a known cable/device with
external power and controlled ground engagement. Powered-off transistor junctions
and comparator backfeed need transistor-level and bench tests.

## Candidate BOM and current procurement evidence

Inherited snapshot 2026-11-09 [verify]; indicative unit prices [verify], tax/shipping extra unless noted.
Every inherited stock count and price in the table is [verify]. Production status of each exact orderable suffix is [verify]; a live product page is not a lifecycle guarantee. Stock is regional and must be rechecked before purchase. This is a research BOM,
not a production quantity/price promise. No parts were purchased.

| Part | Qty / use | Observed price and source |
|---|---|---|
| TLV3602DGKR | 3 duals | [$10.12 each, DigiKey](https://www.digikey.com/en/products/detail/texas-instruments/TLV3602DGKR/17748367),1958 stock; comparator subtotal$30.36 |
| AD8421ARZ | 2 differential arbitration stages | [$9.90 each, DigiKey](https://www.digikey.com/en/products/detail/analog-devices-inc/AD8421ARZ/3340511),8631 stock; EUR 10.46 incl. VAT in regional listing |
| OPA320AIDBVR | 1 bias buffer | [$2.90, Mouser](https://www.mouser.com/en/ProductDetail/Texas-Instruments/OPA320AIDBVR?qs=g5raLcSarObYYXG7KaVGxQ%3D%3D),25539 stock |
| REF3318AIDCKR | 1 reference | [$2.36, Mouser list](https://www.mouser.com/en/c/semiconductors/integrated-circuits-ics/power-management-ics/voltage-references/?m=Texas+Instruments&series=REF3318); [DigiKey stocked](https://www.digikey.com/en/products/detail/texas-instruments/REF3318AIDCKR/1900129) |
| TLV7012DGKR | 1 bias detector | [$1.87, Mouser](https://www.mouser.com/en/c/semiconductors/amplifier-ics/analog-comparators/?series=TLV7012),16777 stock |
| MMBTH81 | steering/current-source prototype; quantity TBD | [EUR 0.09, DigiKey IE](https://www.digikey.ie/en/products/detail/onsemi/MMBTH81/458884),76131 stock; newer NSV variant was not stocked |
| MMBTH10LT1G | steering/current-sink prototype; quantity TBD | [EUR 0.10, DigiKey GR](https://www.digikey.gr/en/products/detail/onsemi/MMBTH10LT1G/1139840),4194 regional stock; US listing differed |
| TPD4E05U06DQAR | 1 ESD array | [$0.82, DigiKey](https://www.digikey.com/en/products/detail/texas-instruments/TPD4E05U06DQAR/3996774),237991 stock |
| Matched 55-ohm 0.1%, threshold reference networks, capacitors | 4 termination resistors and threshold networks | Select footprints/tolerances after layout; no verified quote |
| Analog rails, compensation, fast level shifting, connector, PCB | TBD | Unqualified; cannot honestly give an assembled cost |

The comparator/instrumentation-amplifier/reference subtotal alone exceeds $58. This AFE is presently a
research route to supply independence, **not demonstrated cheaper** than a
commercial PHY. A KiCad breakout should start as receive-only and include probe
points/driver-disable interlocks; adding the active stage waits for its qualification.

## Reproduce and interpret the simulation

```sh
brew install ngspice                 # if needed
hardware/soft-phy-afe/spice/run.sh
```

Python standard library and ngspice are required; matplotlib is optional for the
eye plot. `spice/afe.lib` specifies the architecture, `dc.cir` is an inspectable
nine-state example, and `run.py` generates all decks/raw logs in ignored `build/`.
`results.json` records numeric outcomes, including an intentional false-speed
negative control. The script fails on unexpected classification/data errors or
if the negative control does not expose the expected threshold crossing.

Cable assumptions: two uncoupled 55-ohm lossless conductor transmission lines,
22.725 ns delay (`4.5m*5.05ns/m`), 1 ohm total series resistance per conductor,
5 pF shunt at each endpoint. Length/delay are informed by
[public P1394a draft](https://citeseerx.ist.psu.edu/document?doi=dc3becb9ff261ec9f39d4095bb88e3b73d234cde&repid=rep1&type=pdf);
resistance/capacitance are **engineering assumptions** (5 pF budgets the DS
comparator, instrumentation input, protection and stray loading), not measured cable data.
The model omits frequency-dependent cable loss, modal coupling, connector
geometry and compliance masks. It is deliberately transparent and cannot prove
S100 compliance with an ideal eye.

Tests cover:

- 81 two-pair port-drive combinations, each at nominal and two ±10% current/bias
 corners, both cable ends, three comparator thresholds 110/125/140 mV.
- 1024-bit PRBS, all-zero, all-one and alternating DS patterns in **both**
 directions. Bit-center amplitude, a ±1.88 ns sampling window, errors and XOR
 clock-edge count are checked. This window combines published jitter/skew
 magnitudes as a stress assumption; actual random jitter and comparator
 propagation distributions are not simulated.
- TPA CM droop for balanced operation, 100 uA net mismatch, and an intentionally
 missing 4 mA leg for 20 ns. The 49 mV comparison is a raw threshold crossing;
 speed-detector filtering/state qualification remain digital work.
- Dynamic arbitration through the assumed 10 MHz differential stage, tested
 200 ns after each of nine state changes at both ends.
- Powered-peer bias extremes and zero-bias detection. Unplugged capacitive
 behavior, active unpowered-peer probing and semiconductor off-state backfeed
 are unqualified.

See [results](spice/RESULTS.md) and [raw summary](spice/results.json). The chosen
architecture's limitations are part of the result: no transistor qualification,
no measured board, no universal false-speed immunity, no ESD/EOS certification,
and no production schematic yet.

## Verification ledger and normative-source gap

All proposed component values, rails, timing margins, cable parasitics and model
parameters are **[verify]** unless explicitly attributed above to a datasheet.
Simulation outputs are reproducible model results, not measured specifications.
The IEEE clause pointers above identify the research area; the numeric comparator
limits are from public transceiver datasheets. The exact normative electrical
subclauses/table identifiers in IEEE 1394-1995 and amendments remain **[verify]**.
Do not relabel these as spec-confirmed thresholds without inspecting the standard.

Hobby assembly: SOT-23 transistors and SOT-23-5 buffers/reference are practical
with magnification; SOIC-8 AD8421 is easiest. VSSOP-8 comparators need an adapter
or fine-pitch PCB; the DQA protection array needs reflow and is not a hand-solder
first choice. An alternative protection footprint remains [verify].

Completion boundary: runnable behavioral research is supplied. A buildable,
qualified active AFE is still an open engineering task: base-drive schematic,
transistor models/corners, bias compensation, unpowered-peer probe and EOS
protection must be designed before connecting a transmitting prototype.
