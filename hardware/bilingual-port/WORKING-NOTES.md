# Bilingual port: working notes (in progress, 2026-11-13)

CERN-OHL-S-2.0. Interim findings, written down so they survive an interrupted
session. Superseded by `docs/BILINGUAL-PORT.md` when that lands. Anything not
marked as looked up is reasoning and is [verify].

## Live prices and stock looked up 2026-11-13

LCSC = `https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=<C>`;
JLC = JLCPCB parts search API; TI = `ti.com/product/<P>/part-details/<OPN>`
`data-value` tiers and `storeservices/cart/opninventory`.

| Part | Source | Price | Stock | Note |
|---|---|---:|---:|---|
| LFE5UM-25F-7MG285C (C1551668) | LCSC | $6.09 @200 ($15.74 @1) | 0 | factory-order listing, 200 minimum tier |
| LFE5UM-25F-6MG285C (C1552182) | JLC | $5.79 @200 | 0 | cheapest ECP5-UM listing seen |
| LFE5UM-25F-6BG381C (C1551663) | JLC | $5.86 @200 | 0 | |
| LFE5UM-25F-8MG285C (C1551627) | JLC | $55.45 @30 | 9 | only in-stock ECP5-UM-25; broker-level price |
| LFE5UM5G-25F-8MG285C (C1551932) | JLC | $7.70 @200 | 0 | |
| LFE5U-25F-7BG256I (C1550762) | LCSC | $22.19 @30 | 1111 | non-SERDES ECP5, in stock, expensive |
| LFE5U-12F-7BG256C (C1551115) | JLC | $3.38 @200 | 0 | factory-order listing |
| GW5AT-LV15MG132C1/I0 (C54067362) | LCSC | $27.02 @30 | 343 | Gowin with transceivers |
| PGL22G-6IFBG256 (C42886432) | JLC | $5.22 @120 | 90 | Pango, no transceivers |
| PG2L50H-6IFBG484 (C44407746) | JLC | $14.67 @120 | 8 | Pango with transceivers |
| XC7A15T-1CSG325C (C1521719) | JLC | $12.20 @200 | 0 | Artix-7 GTP |
| TLK1221RHAR (C527435) | LCSC | $3.22 @100 | 602 | TI 0.6..1.3 Gb/s 10-bit SerDes; TI store 821 in stock, $8.244 @100 |
| CH32V307VCT6 (C2943979) | LCSC | $2.41 @90 | 5513 | |
| PI4FW-R22B-003 (C55061496) | LCSC | $1.92 @100 | 1326 | 9-pin socket; keying not yet confirmed |
| TLV3202AID (C2878318) | LCSC | $0.64 @100 | 0 | TI store TLV3202AIDR $2.013 @100, 44350 in stock |
| TPD4E05U06DQAR | TI | $0.226 @100 | 2600 | |

Observation: every sub-$10 Lattice/AMD FPGA price on LCSC/JLC is a zero-stock
listing whose low tier starts at 200 pieces. In-stock FPGAs with transceivers
start at about $27 (GW5AT-15) and $55 (ECP5-UM).

## Architecture direction (reasoning so far, not yet simulated)

- Beta path: SerDes (ECP5-UM DCU, or TLK1221 + non-SERDES FPGA as the fallback)
  behind series DC-blocking capacitors, sharing the legacy 2x55 ohm
  terminations. TX must be high impedance outside beta mode.
- Legacy path stays DC-connected to the pairs: emitter-switched current-mirror
  drivers (PNP source, NPN sink per conductor), FPGA differential inputs for DS
  receive, TLV3202-class comparators for arbitration and speed detect, LDO
  TPBIAS, NPN speed-signal sinks.
- Tones (about 49 MHz) can be sent with the legacy drivers and received on the
  legacy differential input, so the SerDes needs no fast electrical idle.
- S200/S400 sink current: the droop windows (49..131 mV, 314..396 mV) with
  27.5 ohm common-mode impedance only make sense for 2.53..4.84 mA and
  8.1..12.4 mA **per conductor**; the README wording is right and the
  low-cost note's per-pair suspicion is wrong. To confirm in simulation.

## Still to do

Datasheet checks (TSB81BA3E beta electricals, ECP5 SERDES/sysIO limits,
TLK1221, socket keying), lifecycle for every part, ngspice harness, doc, PR.
