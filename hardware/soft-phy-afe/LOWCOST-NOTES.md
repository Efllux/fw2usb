# Low-cost S100 AFE: interim notes (work stopped 2026-11-13)

CERN-OHL-S-2.0. **On hold**: the project now requires S800 (1394b), so this
S100/1394a low-cost AFE study was stopped early. This file records what existed
at the stop. **No simulation was run and no datasheet limit was checked for the
proposal below.** Everything in "Candidate topology" is paper reasoning and is
[verify] throughout. Only the prices in "Live prices" were actually looked up.

Requirements are those in [README.md](README.md) and
[docs/SOFT-PHY.md](../../docs/SOFT-PHY.md). Target was about EUR 3 per port.

## Live prices (looked up 2026-11-13)

LCSC = `https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=<C-number>`.
JLC = JLCPCB parts search API
(`https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList`).
Manufacturer lifecycle status was **not** checked for any part here [verify].

| Part | Source | Price @100 | Stock | Note |
|---|---|---:|---:|---|
| GW1NZ-LV1QN48C6/I5 (C5799569) | LCSC | $4.4832 | 650 | Baseline FPGA; LVDS-input capability not yet confirmed |
| GW1N-LV4QN88C6/I5 (C31900351) | LCSC | $12.3821 | 90 | Too expensive |
| GW1N-LV2QN32C6/I5 (C7429167) | JLC | $2.2904 | 0 | LCSC detail returned nothing; availability doubtful |
| GW1N-LV4QN32C6/I5 (C380546) | JLC | $3.6827 | 0 | LCSC detail returned nothing; availability doubtful |
| GW1N-LV1QN48C6/I5 (C5799563) | JLC | $24.53 | 0 | Not viable |
| LCMXO2-256HC-6SG48I (C1551155) | JLC | $5.7571 | 0 | Cheapest MachXO2 listing seen |
| LCMXO2-640HC-4TG100I (C5680157) | JLC | $4.5187 | 29 | TQFP-100; other 640HC listings $9..48 |
| LCMXO2-256HC-6SG32C (C1551166) | JLC | $9.4234 | 93 | |
| T8F81C2X (C3273010) | JLC | $5.268 | 0 | Efinix Trion; LVDS pins on this package unconfirmed |
| TLV3202AID (C2878318) | JLC | $0.6741 | 0 | Dual 40 ns comparator candidate for arbitration |
| PI4FW-R23A-001 (C55061495) | LCSC | $0.57 | 1195 | 6-pin socket, matches the brief |

AGM AG1KLP and GW1N-UV1P5 had only placeholder JLC listings (no real price).
LCSC has no usable public search endpoint; the JLC search API works and returns
LCSC C-numbers, which the LCSC detail endpoint then prices.

## Candidate topology (unverified, not simulated)

Estimated semiconductor cost about $0.7..1.0 per port, but this estimate rests
on parts that were never priced (transistors, LDO, ESD array, passives) and one
comparator price. Treat it as a guess.

- **DS receivers:** two FPGA true-differential input pairs wired to TPA and TPB
  through small series resistors. Depends on the FPGA guaranteeing about
  +/-100 mV threshold with input common mode up to roughly 2.25 V. That leaves
  only 18 mV against the 118 mV minimum signal. Gowin DS841 (GW1NZ) and DS100
  (GW1N) were downloaded but **not read**; whether GW1NZ-1 has usable
  differential inputs is still open.
- **Arbitration comparators:** four cheap ~40 ns comparators (two duals, e.g.
  TLV3202) rather than FPGA inputs. A +/-100 mV FPGA threshold tolerance cannot
  be guaranteed to stay inside the 89..168 mV window. Offset network per
  comparator: series Ra on both legs, Rb from one input to GND and an equal Rb
  from the other input to 3.3 V. Then the threshold is `3.3 V * (1-k)/k` with
  `k = Rb/(Ra+Rb)`, independent of cable common mode. About Ra = 4.7 k,
  Rb = 124 k gives 125 mV. Each conductor then sees roughly 64 k to 1.65 V, so an
  unconnected TPB sits near 0.2 V, below the 0.6 V bias-detect threshold.
- **Drivers:** emitter-switched current mirrors, one PNP source and one NPN sink
  per conductor (four transistors per pair, MMBT3904/3906 class). Each emitter
  goes through about 100 ohm to an FPGA LVCMOS pin; one logic level turns the
  leg on, the other reverse-biases it. Bases sit on a shared diode-connected
  reference string so source and sink currents match. Estimated compliance is
  about 1.0..2.2 V common mode, which does not cover the 2.515 V
  cable-power ground-shift corner.
- **Resistor-only driver (FPGA pins through resistors):** hand calculation says
  common-mode imbalance reaches about -1.3 mA at TPBIAS 2.015 V with a 3.135 V
  rail, outside the +/-1.05 mA limit, and it loads the termination by about
  770 ohm differential while driving. Expected to be rejected; not simulated.
- **TPBIAS:** fixed 1.8 V LDO with enable plus a ~1 k bleeder for the sink
  requirement. 1.8 V is inside 1.665..2.015 V but below the 1.86 V nominal.
- **Bias detect:** an FPGA differential input comparing the TPB centre tap with
  a 0.8 V divider.
- **ESD:** TPD4E05U06 or an equivalent array; not priced.

## Known open risks at the stop

- Unpowered board: the PNP collector-base junctions conduct from the peer's
  TPBIAS into the reference string, estimated up to about 2 mA. FPGA input
  clamp behaviour with a dead rail is unknown.
- Driver edge rate and source/sink skew with 300 MHz-class transistors.
- Driver amplitude spread from rail tolerance and Vbe drift, estimated
  +/-11..13% by hand.
- The existing README lists the S200 sink current "per conductor"; the droop
  window suggests it is per pair. Not checked against the standard.

## Not done

Lifecycle checks, pricing of transistors/LDO/ESD/passives, FPGA datasheet
confirmation, all ngspice work, the requirement pass/fail table, the board-total
estimate, and the pull request.
