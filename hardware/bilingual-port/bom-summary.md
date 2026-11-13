# Bilingual port: BOM summary (2026-11-13)

Data is in `bom.csv` (one row per part per source). Prices are USD at quantity 100 unless the `price_tier_note` says otherwise. Sources: LCSC product JSON API, TI store pages and inventory API, all queried 2026-11-13.

Currency: 1 EUR = 1.1052 USD (ECB euro foreign exchange reference rate, 2026-11-13, `data-api.ecb.europa.eu`). EUR = USD / 1.1052.

## What the totals cover

Only the parts named in `WORKING-NOTES.md` plus the generic parts: USB MCU, 3.3 V and 1.1 V regulators, USB-C receptacle, 24 MHz crystal, SPI flash, ESD array. `PARTS-TO-PRICE.md` did not exist on `hardware/bilingual-port` at the time of lookup.

NOT priced, so every total below is a lower bound: passives, the discrete legacy drivers (PNP/NPN), TPBIAS LDO, series capacitors, terminations, the PCB, assembly, and any extra ESD protection for the FireWire port. Quantity assumptions: 1 of each part (comparator and ESD counts are assumptions; see notes in the CSV).

"In stock" means stock of at least 100 pieces at the chosen source. The cheapest option per role is chosen; for the FPGA role the options are either a single SerDes FPGA or a non-SerDes FPGA plus TLK1221RHAR.

## Total A: in-stock parts only

| Role | Part | USD |
|---|---|---:|
| FPGA + SerDes | LFE5U-25F-7BG256I (C1550762, stock 1111, 30 tier) + TLK1221RHAR (C527435, stock 602) | 25.4111 |
| USB MCU | CH32V307VCT6 | 2.4123 |
| FireWire socket | PI4FW-R22B-003 | 1.9240 |
| Comparator | TLV3202AIDR (TI store) | 2.0130 |
| ESD | TPD4E05U06DQAR | 0.2260 |
| 3.3 V | AP2112K-3.3TRG1 | 0.1300 |
| 1.1 V | TLV71211DBVR (TI store) | 0.2800 |
| USB-C | TYPE-C 16PIN 2MD(073) | 0.0735 |
| 24 MHz crystal | X322524MMB4SI | 0.0761 |
| SPI flash | W25Q32JVSSIQ | 1.0408 |
| **Total** | | **33.59 USD = 30.39 EUR** |

Gap to the EUR 15 target: **EUR 15.39 over**, before any unpriced items. The FPGA line is 76% of the total. The alternative in-stock SerDes FPGA (GW5AT-LV15, 27.02 USD) is 1.61 USD more expensive.

## Total B: allowing ZERO-STOCK factory-order listings

This total is not buyable today. Every low-priced FPGA/comparator/flash line in it has stock 0 on LCSC; the price assumes LCSC/JLCPCB will build to order. The FPGA price is the 200-piece tier (the listing has no tier below 200), so you would have to buy 200 chips, not 100.

| Role | Part | USD | Stock |
|---|---|---:|---|
| FPGA + SerDes | LFE5UM-25F-6MG285C (C1552182, 200 tier) | 5.4863 | **0** |
| USB MCU | CH32V307VCT6 | 2.4123 | 5513 |
| FireWire socket | PI4FW-R22B-003 | 1.9240 | 1326 |
| Comparator | TLV3202AID (C2878318) | 0.6355 | **0** |
| ESD | TPD4E05U06DQAR | 0.2260 | 2600 |
| 3.3 V | AP2112K-3.3TRG1 | 0.1300 | 31035 |
| 1.1 V | TLV71211DBVR | 0.2800 | 65138 |
| USB-C | TYPE-C 16PIN 2MD(073) | 0.0735 | 1013700 |
| 24 MHz crystal | X322524MMB4SI | 0.0761 | 10385 |
| SPI flash | W25Q16JVSSIQ (90 tier) | 0.7542 | **0** |
| **Total** | | **12.00 USD = 10.86 EUR** | |

Versus EUR 15: EUR 4.14 under, which leaves about EUR 4.14 (4.6 USD) for everything unpriced above (passives, discrete drivers, PCB, assembly). That is unlikely to be enough on its own. The result depends on the ECP5-UM zero-stock listing becoming available.

## Lifecycle caveat

The requirement is parts the maker lists as Active. Only TI parts could be confirmed from the maker's own page: TLK1221RHAR, TLV3202AIDR, TPD4E05U06DQAR, TLV71211DBVR, TLV75801PDBVR and TLV75733PDBVR (all ACTIVE_true). For all other parts the maker page either states no status (Lattice ECP5, WCH CH32V307) or could not be read (Diodes 403, Winbond sign-in, AMD timeout, Gowin/Pango/YUWENFA/SHOU HAN/YXC not found or not fetched), so the CSV says `unknown`. Neither total is therefore proven to use Active-only parts. TSB81BA3EPFP showed no Active marker (badge OBSOLETE_false) and is flagged `unknown`. It is priced for reference and counted at quantity 0.

## Other notes

- WORKING-NOTES JLCPCB prices (for C1552182, C1551663, C1551932, C1551115, C1521719, C42886432, C44407746) were not re-verified; the CSV uses the LCSC API for the same C numbers, which differ slightly (for example 5.4863 vs 5.79 for C1552182).
- TLK1221RHAR is 3.2214 USD on LCSC but 8.244 USD at TI's own store; the cheaper figure is used.
- PGL22G-6IFBG256 (5.78 USD at the 60 tier, no SerDes) would make a cheap fallback with TLK1221, but its stock is 90, under the 100 needed.
- TLV71211DBVR gives only 300 mA; confirm ECP5 core current. TLV75801PDBVR (adjustable) is cheaper but needs two resistors.
