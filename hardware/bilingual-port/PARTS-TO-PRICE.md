# Parts to price (request list for the BOM agent)

One line per part: manufacturer part number | role | quantity per board |
acceptable alternatives. Prices, stock and lifecycle live in `bom.csv` on branch
`hardware/bilingual-port-bom`; this file only says what is needed and why.
"S400" marks parts that an S100-only build leaves unpopulated.

## Digital core

- LFE5UM-25F-6MG285C | FPGA with SERDES (beta 983.04 Mbaud, all PHY/link logic) | 1 | LFE5UM-25F-6BG381C; any -7/-8 or I grade of the same two packages; LFE5UM5G-25F-8MG285C / -8BG381C
- TLK1221RHAR | fallback beta SerDes (0.6..1.3 Gb/s, 10-bit interface) used with a non-SERDES FPGA | 1 (fallback build only) | TLK1221RHAT
- LFE5U-12F-6BG256C | fallback FPGA without SERDES, paired with TLK1221 | 1 (fallback build only) | LFE5U-12F or LFE5U-25F in BG256, MG285 or BG381, any speed/temperature grade
- CH32V307VCT6 | USB high-speed MCU | 1 | none
- W25Q32JVSSIQ | FPGA configuration flash, 32 Mbit SPI NOR, 3.3 V | 1 | any Active 16..64 Mbit 3.3 V SPI NOR in SOIC-8 or USON-8 (GD25Q32E, W25Q16JV, W25Q64JV)
- 49.152 MHz CMOS oscillator, 3.3 V, total stability within +/-50 ppm, 3225 or 2520 | SERDES reference (x20) and PHY clock for the ECP5-UM build | 1 | any Active part meeting the spec
- 98.304 MHz CMOS oscillator, 3.3 V or 2.5 V, +/-50 ppm, jitter below 40 ps p-p | TLK1221 REFCLK | 1 (fallback build only) | any Active part meeting the spec
- 1.1 V step-down regulator, at least 1 A, with inductor | FPGA core and SERDES supply | 1 | any Active part
- 2.5 V LDO, at least 150 mA | FPGA VCCAUX (and TLK1221 supply in the fallback build) | 1 | any Active part
- 3.3 V LDO or step-down from USB 5 V, at least 500 mA | board 3.3 V | 1 | any Active part

## Port and front end

- PI4FW-R22B-003 | 9-pin 1394b socket | 1 | any 9-pin socket confirmed bilingual-keyed
- SN65LVDS34D | dual line receiver, +/-50 mV threshold, -4..5 V common mode, power-off high impedance: legacy data/strobe receive and tone detect | 1 | SN65LVDS34DR; SN65LVDS33PWR or SN65LVDS33D (quad, two channels unused)
- TLV3202AIDR | dual 40 ns comparator: arbitration window comparators | 2 | TLV3202AIDGKR; TLV3502AIDR
- TLV3202AIDR | dual 40 ns comparator: S200/S400 speed-detect comparators (S400) | 1 | TLV3202AIDGKR; TLV3502AIDR
- LM393BIDR | dual slow comparator: TPB bias detect and TPA connect detect | 1 | LM2903BIDR; LM393 from any maker with Active status
- MMBTH81 | PNP RF transistor (about 600 MHz, Ccb under 1 pF): driver current-source legs and reference | 5 | PMBTH81; BFT93; MMBT3906 (S100-only builds)
- MMBTH10LT1G | NPN RF transistor (about 650 MHz, Ccb under 1 pF): driver current-sink legs and reference | 5 | PMBTH10; BFS17; BFR92A; MMBT3904 (S100-only builds)
- MMBTH10LT1G | NPN RF transistor: S200 and S400 speed-signal sinks (S400) | 4 | same as above
- 1.8 V fixed LDO with enable, at least 30 mA, stable with 1 uF ceramic, **no** active output discharge | TPBIAS | 1 | TLV70018DDCR (check it is the non-P variant); any Active equivalent
- TPD4E05U06DQAR | four-line 0.5 pF ESD array on TPA/TPB | 1 | any Active four-line array at or below 0.6 pF per line with 5 V standoff
- TMUXHS4212RKSR | optional 2:1 high-speed differential switch, only if bench results reject direct coexistence | 0 (optional 2) | HD3SS3212RKSR; PI3DBS12212A
- 54.9 ohm 0.1 % 0402 | pair termination | 4 | 54.9 or 56.2 ohm 0.5 %
- 1 % 0402 resistors, assorted | networks, about 60 pieces | 60 | any
- Ceramic capacitors 0402 (10 nF C0G/X7R coupling x4, 1 uF, 100 nF, 270 pF), about 45 pieces | coupling and decoupling | 45 | any
- USB-C receptacle, USB 2.0, 16-pin | host connector | 1 | any Active part
- PCB (4-layer, about 40 x 60 mm) and assembly with one 0.8 mm BGA | board | 1 | fab quote
