# Broad parametric parts search

Date of search: 2026-11-22. Target: about 15 EUR parts cost per board at quantity 100. Prices are USD (LCSC and TI list USD).

Full candidate list: [parts-search.csv](parts-search.csv). Every number below is either read from a live source on the date above, or marked `unverified` with the reason.

## Method

- **Parametric catalogue.** CDFER/jlcpcb-parts-database SQLite (built from yaqwsx/jlcparts, file dated 2026-11-22, 593k parts, only parts with 5 or more in stock) queried with `sqlite3`/python by category, sorted by price at the 100 tier. Opened read-only; nothing from it was executed.
- **Live LCSC check** (`wmsc.lcsc.com/ftps/wm/product/detail`) for every shortlisted part. Finding: catalogue stock and price drift from live (examples: EF2L45UG132B catalogue stock 10, live 0; LFE5U-25F-6BG256C catalogue stock 153, live 0; TLK1221RHAR catalogue $2.68, live $3.22 at 100). The catalogue price is the JLCPCB-assembly price; the LCSC live ladder is used in all tables. Where LCSC shows no 100 tier, the highest tier at or below 100 is used and noted.
- **TI live data** (`opninventory`, `part-details` price tiers, `ACTIVE_true` page marker).
- **Datasheets** downloaded and read as text for the specs quoted (TLK1221, TNETE2201B, TLK1501, ECP5 DS, GW2A DS102 via efo.ru copy, Artix-7 DS181 via SparkFun copy). Gowin product pages for GW5A/GW5AT.
- **Lifecycle.** Only TI lifecycles were verified (TI page markers). For all other makers the lifecycle is written `unknown`, because their pages were not retrievable or do not state it; no part is assumed Active.
- **Not retrievable.** Mouser-hosted and Arrow-hosted PDFs return an access-denied page. This blocked the Gowin GW1N and GW5A datasheets and the Lattice CrossLink-NX datasheet.
- Zero-stock LCSC listings are reported separately ("Zero-stock factory listings").

## A. Fast serial receive/transmit for 1394b beta

Requirement: 983.04 Mbaud (and 491.52 Mbaud for S400b), 8B10B, AC-coupled.

### A3. Standalone SerDes (cheapest solution found)

| Rank | Part | Key specs | Lifecycle | Price at 100 | Stock | Source |
|---|---|---|---|---|---|---|
| 1 | TLK1221RHAR (LCSC C527435) | 0.6-1.3 Gbps, 10-bit TBI, comma alignment, REFCLK 60-130 MHz full rate (98.304 MHz for 983.04), 2.5 V core, 3.3 V tolerant LVTTL, hot-plug protected, 40-VQFN 6x6 | Active (TI) | **$3.22** (LCSC live) | 588 (LCSC) | [TI](https://www.ti.com/product/TLK1221), [LCSC](https://www.lcsc.com/product-detail/C527435.html) |
| 1b | TLK1221RHAR direct from TI | same | Active | $8.244 | 821 | TI opninventory |
| 2 | TLK1221RHAT (LCSC C2865066) | same, small reel | Active | $2.40 (LCSC live) | 15 only | LCSC |
| 3 | TNETE2201BPJD | 1.25 Gbps GbE transceiver, 3.3 V, fixed 125 MHz REFCLK; 98.304 MHz lock range not specified (`unverified`) | Active (TI page marker) | $7.259 | 6400 | [TI](https://www.ti.com/product/TNETE2201B) |
| 4 | TLK1211RCP | same core as TLK1221 plus JTAG, 64-pin | Active | $13.321 | 7232 | [TI](https://www.ti.com/product/TLK1211) |
| 5 | TLK1501IRCP | 0.6-1.5 Gbps but 16-bit interface at 30-75 MHz with built-in 8B10B (not raw TBI) | Active | $26.025 | 3115 | [TI](https://www.ti.com/product/TLK1501) |

Rejected: TLK2201B (TI lists Obsolete), TLK1201A (no TI page), TLK2501 (minimum 1.6 Gbps), SN65LV1023A/1224B (max 660-792 Mbps), HOTLink II CYP15G0101DXB (aggregators list Obsolete; $22-$212), Ethernet PHYs with 1000BASE-X/SGMII (fixed 1.25 Gbaud PLL with 125 MHz reference).

Caveats for TLK1221:
- Minimum 600 Mbps: **491.52 Mbaud (S400b) is outside the specified range.** S400b would need the SerDes running at 983.04 with something upstream, which a 1394b S400b link cannot do; so the TLK1221 path covers S800 only.
- It is a 10-bit parallel interface: about 10 data pins each way plus clocks (RBC0/RBC1 half-rate clocks at 49.152 MHz or 98.304 MHz). The FPGA needs about 25 I/O.
- LCSC price is 2.5x below TI's own price at the same quantity. LCSC shows the stock as first-party (`hasThirdPartyStock` false), but confirm provenance before ordering 100.

### A1. FPGAs with hard transceivers

None is near the 15 EUR budget. All were checked live on LCSC.

| Rank | Part | Transceivers / specs | Lifecycle | Price at 100 (tier used) | Stock | Source |
|---|---|---|---|---|---|---|
| 1 | XC7A15T-1FGG484I (C1550990) | Artix-7, 4 GTP, min 0.500 Gb/s (DS181), 983.04 OK via the /4 divider range 0.8-1.65G, 491.52 below the spec minimum | unknown | $22.43 (30+ tier) | 30 | LCSC |
| 2 | GW5AT-LV15MG132C1/I0 (C54067362) | Gowin, 4 transceivers 270 Mbps-12.5 Gbps, 15k LUT, 8x8 mm MG132 | unknown | $27.02 (30+) | 341 | [Gowin](https://www.gowinsemi.com/en/product/detail/58/) |
| 3 | XC7A35T-2FGG484I (C1521727) | Artix-7 35T, 4 GTP | unknown | $30.64 (30+) | 797 | LCSC |
| 4 | LFE5UM-45F-8BG381C (C1550814) | ECP5-UM, SerDes 270 Mb/s-3.2 Gb/s | unknown | $34.12 (10) | 2 | LCSC |
| 5 | LFE5UM-25F-8MG285C (C1551627) | ECP5-UM 25k | unknown | $55.18 (30+) | 9 | LCSC |

Not priced (not on LCSC, no price found by web search): CertusPro-NX, PolarFire, Efinix Ti180, Pango Logos2, Anlogic PH1A90, Spartan UltraScale+ SU45P/SU60P. Spartan UltraScale+ SU10P/SU25P/SU35P have no GTH transceivers. All unverified for price and lifecycle.

Open toolchain: only ECP5 (Yosys/nextpnr-ecp5, SerDes via DCU is experimental) has any. Artix-7 GTP and Gowin GW5AT transceivers need vendor tools.

Conclusion: a transceiver FPGA costs 2 to 8 times the TLK1221 path. Not viable at 15 EUR.

### A2. FPGAs without transceivers: fast I/O for soft CDR

| Part | Datasheet-specified max I/O rate | Price at 100 | Stock | Note |
|---|---|---|---|---|
| GW2AR-LV18QN88C8/I7 (C380550) | GW2A-18 gearbox: IDES10 1200 Mbps, IDES7 1000, IDES4 800 (DS102 2.7.3E) | $41.33 (30+) | 87 | Apicula supports GW2A; 22 LVDS pairs in QN88 |
| GW5A-LV25MG121NC1/I0 (C45617374) | LVDS RX 2.0 Gbps at 3.3 V, 1.8 at 2.5 V (Gowin product page); EasyCDR claimed up to 2.5G | $42.92 (30+) | 459 | datasheet table not read |
| Efinix Titanium Ti60 | LVDS 1000 Mbps full / 1500 Mbps half rate (C4, I3, Q3) per search of datasheet v3.7 | unverified (no price found) | unverified | Efinity only |
| GW1N-LV4 (C31900351) | unverified (datasheet blocked) | $12.38 | 88 | Apicula |
| ECP5 LFE5U-25F | GDDRX2 800 Mb/s (-8), 700 (-7), 624 (-6): **fails** | $22.19 | 1091 | open toolchain |
| Spartan-7, CrossLink-NX, Certus-NX, MachXO, Anlogic EG4/SF1 | unverified (datasheets not retrievable) | | | |

Only the Gowin GW2A/GW5A and Efinix Titanium have a verified spec at or above 1 Gb/s, and none is cheap on LCSC. Soft CDR at 983.04 Mbaud means about 1.2x oversampling headroom at best on GW2A, not a comfortable 3x. Treat soft CDR as unproven.

## B. FPGA logic

Requirement: Active, in stock, DDR inputs with delay taps for 393 Mbit/s single-ended capture, hot-socket-tolerant 3.3 V I/O. All prices LCSC live, 2026-11-22.

| LUT class | Part | Specs | Price at 100 | Stock | Toolchain | Caveat |
|---|---|---|---|---|---|---|
| ~5k | XC6SLX9-2TQG144C (C27408) | Spartan-6, 5.7k LUT6, IODELAY2, ISERDES2, 3.3 V | $5.90 (60+ tier) | 2221 | ISE only | 2009 design; AMD extended lifecycle to at least 2030 |
| ~5k | ICE40UP5K-SG48I (C2678152) | 5.3k LUT4, no delay taps | $9.56 | 166 | Yosys/nextpnr | fails delay-tap requirement |
| ~5k | GW1N-LV4QN88C6/I5 (C31900351) | 4.6k LUT4 | $12.38 | 88 | Apicula | I/O rate unverified |
| ~10k | AG10KL144 (C133763) | AGM 10k LUT | $3.40 (60+ tier) | 381 | proprietary | DDR/delay/hot-socket specs unverified |
| ~10k | XC6SLX16-2FTG256C (C39313) | Spartan-6, 9.1k LUT6 | $5.85 (90+) | 579 | ISE only | as above |
| ~10k | EP4CE10E22I7N (C569007) | Cyclone IV E | $16.46 | 159 | Quartus | |
| ~25k | AG16KL144A (C41397170) | AGM 16k LUT | $4.62 (60+) | 264 | proprietary | unverified I/O |
| ~25k | XC6SLX25-2CSG324I (C169795) | Spartan-6, 15k LUT6 (24k LC) | $11.27 | 309 | ISE only | |
| ~25k | **LFE5U-25F-7BG256I (C1550762)** | ECP5 24k LUT4, GDDRX1 500 Mb/s, delay taps, hot-socketing section in DS | $22.19 (30+) | 1091 | **Yosys/nextpnr-ecp5, mature** | most expensive of the three |

Observations:
- Spartan-6 is by far the cheapest verified-capable logic on LCSC, but it is a legacy part and has no open toolchain. The user's no-obsolete-parts rule decides whether it is acceptable; AMD's own blog says production continues to at least 2030.
- ECP5 is the only candidate with a confirmed 393 Mbit/s DDR input spec, delay taps, a hot-socketing section, and an open toolchain, but costs 4 times the Spartan-6. Its 24k LUT size is more than needed.
- AGM AG10K/AG16K are cheapest of all ($3.40 and $4.62) but I could not verify any I/O spec; they would need datasheet review.
- Lifecycle is `unknown` for everything except Spartan-6 (AMD commitment); no maker page confirming "Active" was retrievable.

## C. Dual LVDS / line receiver

Requirement: threshold +/-50 mV or better, common mode at least 0.4 to 2.6 V, 400 Mbps or more, power-off input high impedance (leakage tens of uA), CI 5 pF or less, pulse skew 300 ps or less.

| Rank | Part | Verified specs (datasheet) | Lifecycle | Price at 100 | Stock | Source |
|---|---|---|---|---|---|---|
| 1 | **SN65LVDS34DR** (reference) | threshold +/-50 mV with hysteresis; CM -4 to 5 V; Ioff +/-50 uA; CI 5 pF; tsk(p) 200 ps; 400 Mbps; 4 channels | Active | **$1.75** (TI direct, 100-249 tier) | 2500 (TI) | [TI](https://www.ti.com/product/SN65LVDS34), SLLS490B |
| 2 | SN65LVDS33PWR (LCSC C200355) | same family specs, TSSOP-16 | Active | $2.43 (LCSC live; TI $3.159) | 133 | LCSC |
| 3 | SN65LVDS2DBVR (C38204), 2 needed | threshold +/-100 mV and CI 5.8 pF: **fails both** | Active | $0.468 each | 3720 | LCSC |
| 4 | DS90LV028ATM (C133847) | dual, 400 Mbps; datasheet not read, threshold expected +/-100 mV (`unverified`) | unknown | $1.78 | 21 | LCSC |

Finding: SN65LVDS34 is a **quad** receiver, not dual, so one device covers two differential pairs with two spare channels (about $1.75 for the part; two spare channels can serve a second pair). No dual receiver with +/-50 mV threshold was found in the LCSC catalogue. The cheap SOT-23 single receivers fail the threshold requirement.

## D. RF transistors (complementary pair)

Requirement: fT 600 MHz or more, Ccb 1 pF or less, VEBO 3 V or more.

LCSC catalogue filter (stock 50 or more, fT 600 MHz or more): 175 NPN parts, **only 2 PNP**.

| Polarity | Part | fT | Ccb | VEBO | Price at 100 | Stock | Notes |
|---|---|---|---|---|---|---|---|
| PNP | **MMBTH81 onsemi (C190349)** | 600 MHz min | 0.85 pF max | 3 V | $0.094 (50 tier; $0.081 at 150) | 10180 | only viable PNP; lifecycle `unknown` (onsemi page not retrievable) |
| PNP | 50A02CH-TL-E (C890136) | 690 MHz typ | Cob 3.8 pF: **fails** | 5 V | $0.304 | **0 (factory)** | rejected |
| PNP | BFT92/BFT92W | 5 GHz | n/a | 2 V: **fails** | n/a | n/a | obsolete / no longer manufactured |
| NPN | MMBTH10LT1G onsemi (C16204) | 650 MHz min | 0.7 pF max | 3 V | $0.113 | 2868 | fully verified |
| NPN | MMBTH10 UMW (C545531) | 650 MHz (LCSC attr) | unverified | 3 V | $0.014 | 3150 | second source |
| NPN | MMBTH10 YTL (C53059515) | 650 MHz (LCSC attr) | unverified | 3 V | $0.011 | 2850 | |
| NPN | S9018 (many makers, e.g. C53261047) | 600-1100 MHz | unverified | 4-5 V | $0.009 | 1600+ | cheapest; Ccb unverified |

Conclusion: the pair MMBTH10 (NPN) plus MMBTH81 (PNP) is the only fully datasheet-verified complementary set. Its cost is negligible (about $0.2 per pair). The PNP stays scarce: the single source is onsemi MMBTH81.

## E. Comparators

Requirement: dual, 40 ns or less, rail-to-rail input at 3.3 V, offset 5 mV or less; note input leakage with supply at 0 V.

| Rank | Part | Verified specs | Lifecycle | Price at 100 | Stock | Verdict |
|---|---|---|---|---|---|---|
| 1 | **TLV3202AIDR** (C129325) | tPD 42-47 ns typ, **50 ns max**; Vos 5 mV max (1 mV typ); input range to 200 mV beyond both rails; 2.7-5.5 V | Active (TI) | **$0.610** (LCSC); TI $2.013 | 4215 (LCSC), 44350 (TI) | meets all but a strict 40 ns max |
| 2 | TLV3502AIDR (C131165) | tPD 4.5 ns typ, 6.4 ns max; **Vos 6.5 mV max**; rail-to-rail I/O | Active (TI) | $1.411 (LCSC); TI $3.074 | 226 (LCSC), 39337 (TI) | fails offset by 1.5 mV (1 mV typical) |
| 3 | MAX9142ESA+T (C18567) | 40 ns per LCSC; Vos and input range not read | unknown | $1.857 | 20 | `unverified` |
| - | RS393XK, TP2012, LM393 | tPD 205 ns, 13 us, 1.3 us | | $0.05-0.33 | | too slow |

Input leakage with the supply at 0 V is **not specified** for either TI part. Their ESD diodes conduct when an input is more than about 300 mV above the supply, so neither is power-off high impedance. If the comparator inputs see a live signal while the board is unpowered, add series resistance or a different part.

## F. Other parts

### 1.8 V LDO with enable and no output discharge

| Part | Notes | Lifecycle | Price at 100 | Stock |
|---|---|---|---|---|
| **TLV70018DCKR** (C133796) | TI, 200 mA, enable, SC-70-5. Datasheet lists no discharge feature, but a revision note mentions deleting an "active pulldown resistance" parameter: confirm on the 1.8 V option | Active (TI) | $0.127 (LCSC), TI $0.198 | 13150 (LCSC), 34312 (TI) |
| TLV70018DDCR (C79924) | same, SOT-23-5 | Active | $0.128 | 5570 |
| DS8571-18S5, MG6228T5-18, XC6219B182MR, ... | 241 fixed 1.8 V enable LDOs in LCSC at about $0.03; discharge behaviour not checked | unknown | $0.026-0.040 | 5000+ |
| TLV755xxP, TLV733xxP | rejected: active discharge | | | |

### 9-pin FireWire 800 socket

| Part | Finding | Price at 100 | Stock |
|---|---|---|---|
| PI4FW-R22B-003 (C55061496, YUWENFA) | datasheet is a mechanical drawing titled "Mini 1394b, 9 pin"; it does not say bilingual and shows no key detail. **Bilingual still unconfirmed** | $1.924 | 1326 |
| Newnex RFB-9002 | Newnex page names it a "vertical bilingual" 9-pin receptacle. Price and stock `unverified` (DigiKey page returned 403) | unverified | unverified |

No other 9-pin 1394b socket was found in the LCSC catalogue. TE 5787956-1 was not verified as 9-pin. Recommendation: order a sample of both and test with a 6-pin 1394a cable, or get written confirmation from YUWENFA.

### 2:1 differential analog switch (Con 2 pF or less, common mode to 2.6 V)

62 LCSC catalogue parts list Con 2 pF or less; most are 4000-series CMOS switches (not suitable) or 74HC types at 70-290 MHz. The high-speed ones:

| Part | Con | Range | Lifecycle | Price at 100 | Stock |
|---|---|---|---|---|---|
| **TS3USB3000RSER** (C882807, TI) | 1.4 pF typ (USB path), 6.1 GHz, power-off leakage +/-10 uA | 0-3.6 V, Vcc 2.3-4.8 V | Active | $0.471 | 963 (LCSC), 59840 (TI) |
| CBTL01023GM,115 (C2150887, NXP) | 1.5 pF, 9 GHz (LCSC attrs) | 3.0-3.6 V supply | unknown | $0.315 | 682 |
| TS3USB3000RSER-HXY (C49108280) | 1.5 pF (LCSC attrs) | | unknown | $0.351 | 2563 |
| TMUX121NKGR (C22428404, TI) | 1.7 pF (LCSC attrs) | 3.0-3.6 V | unknown | $0.524 | 4873 |

Con values are typical, not maximum.

## G. Microcontrollers with high-speed USB and built-in PHY

| Rank | Part | HS USB evidence | Lifecycle | Price at 100 | Stock | Notes |
|---|---|---|---|---|---|---|
| 1 | CH32V305GBU6 (C19100608), WCH | datasheet V3.6 lists USBHS (+PHY) for CH32V305; **QFN28 pin availability of USBHS not confirmed** | unknown | **$1.116** | 2380 | verify pinout first |
| 2 | **AT32F405KBU7-4** (C47090436), Artery, QFN32 | Artery page: "1 x OTGHS (including on-chip PHY)" | unknown | **$1.213** | 337 | best verified |
| 3 | AT32F405CCT7 (C47115471), LQFP48 | same | unknown | $1.347 (250 tier; $1.552 at 30+) | 95 | |
| 4 | AT32F405RBT7 (C47090500), LQFP64 | same | unknown | $1.457 (160 tier) | 116 | |
| 5 | CH32V317WCU6 (C49188393), WCH, QFN68 | datasheet: USBHS+PHY, plus Ethernet | unknown | $2.243 (30 tier; $1.951 at 260+) | 3082 | |
| 6 | CH32V307RCT6/VCT6 | datasheet: USBHS+PHY | unknown | $2.36-2.71 | 1342 / 5097 | |
| 7 | HPM5301IEG1 (C49451864), HPMicro | not verified | unknown | $2.473 | 494 | |
| - | CH32H417MEU6/QEU6 | not read | unknown | $3.77 / $4.10 | **0** | factory listing |

Rejected: AT32F402 and AT32F455/456/457 (full speed only; Artery pages/datasheet), WCH CH32V208 (stock 0).

"Lite" S100-only candidates (USB full speed is enough): RP2350A $1.172 (stock 5994) and RP2350B $1.139 (stock 3089), both full speed. CH570 and CH569 could not be priced: no bare part is listed on LCSC.

## Zero-stock factory listings

Live LCSC stock was 0 for these, so they cannot be bought at quantity 100 without a factory order. Do not count them in the architecture costs.

| Part | Category | Live price at 100 | Note |
|---|---|---|---|
| EF2L45UG132B (C7471967), Anlogic | A2/B | $6.215 | catalogue said stock 10 |
| LFE5U-25F-6BG256C (C1521614), Lattice | B | $11.513 | catalogue said stock 153 |
| TLK1501IRCP (C47334), TI | A3 | $12.335 | TI itself has 3115 at $26.025 |
| 50A02CH-TL-E (C890136), onsemi PNP | D | $0.304 | also fails Ccb |
| CH32H417MEU6 / QEU6, WCH | G | $3.77 / $4.10 | |
| CH32V208GBU6, WCH | G | $0.994 | |
| 10M02SCU169C8G, Intel | B | $16.674 | |

## Architectures for the S800 path

"High-speed portion" means SerDes or transceiver, logic FPGA and the 1394a legacy receiver (SN65LVDS34 at $1.75, TI direct). The USB MCU is listed separately (AT32F405KBU7-4 at $1.213). Prices are LCSC live at 100 unless noted. The TLK1221 is $3.22 on LCSC but $8.244 from TI directly; both are shown.

| # | Architecture | High-speed portion parts cost | With USB MCU | Open toolchain | Main risks |
|---|---|---|---|---|---|
| 1 | TLK1221 + AGM AG10KL144 + SN65LVDS34 | $3.22 + $3.40 + $1.75 = **$8.37** (TI price for TLK1221: $13.39) | $9.58 | no | AGM I/O specs, lifecycle and hot-socket behaviour all `unverified`; 491.52 Mbaud (S400b) not covered by TLK1221 |
| 2 | TLK1221 + Spartan-6 XC6SLX9-2TQG144C + SN65LVDS34 | $3.22 + $5.90 + $1.75 = **$10.87** (TI: $15.89) | $12.08 | no (ISE) | legacy 2009 part, may conflict with the no-old-parts rule; S400b not covered |
| 3 | TLK1221 + iCE40UP5K-SG48I + SN65LVDS34 | $3.22 + $9.56 + $1.75 = **$14.53** (TI: $19.55) | $15.74 | yes (Yosys/nextpnr-ice40) | no delay taps, 393 Mbit/s capture margin unproven; S400b not covered |
| 3b | TLK1221 + ECP5 LFE5U-25F-7BG256I + SN65LVDS34 | $3.22 + $22.19 + $1.75 = **$27.16** | $28.37 | yes (mature) | over budget; the one confirmed 393 Mbit/s DDR-input spec |
| 4 | Transceiver FPGA alone: XC7A15T-1FGG484I $22.43 (30 in stock), GW5AT-LV15MG132 $27.02 (341 in stock), ECP5-UM-45 $34.12 (2 in stock) | $22-34 plus $1.75 for legacy | $24-36 | only ECP5 | 2 to 4 times the TLK1221 path; BGA-484 oversize for Artix; S400b 491.52 below GTP minimum 0.5 Gb/s |

Reading: only architectures 1 to 3 are anywhere near the 15 EUR board budget (these are parts for the high-speed path and USB MCU only; socket, passives, PCB and power are extra), and only with a TLK1221 supplied from LCSC at $3.22. At TI's $8.244 the high-speed portion rises by $5.02 in every row. A soft-CDR design on FPGAs without transceivers gains nothing: the fastest verified I/O (GW2A 1.2 Gb/s) costs $41.

## Surprises

- LCSC sells the TLK1221 at $3.22 against TI's own $8.244 at 100, and TLK1201A/TLK2201B (the usual 1394b suspects) are absent or Obsolete. TLK1221 is Active, TBI, 0.6-1.3 Gbps, and runs on a 98.304 MHz reference.
- SN65LVDS34 is a quad receiver, not dual.
- Only one PNP RF transistor (MMBTH81) qualifies in the whole LCSC catalogue.
- The Artery AT32F455/456/457 and AT32F402 are full speed; AT32F405 has the HS PHY.
- Catalogue stock and price drifted from live checks for several parts (see Method), so always check live.

## What I could not verify

- Maker lifecycle status for all non-TI parts (written `unknown`); no part was assumed Active.
- Datasheet I/O rates for Gowin GW1N and GW5A (Mouser blocked), Lattice CrossLink-NX/Certus-NX, Spartan-7, Anlogic, AGM AG10K/AG16K. Spartan-6 DS162 is only the 2009 advance copy.
- Prices for Efinix Titanium, Pango, Anlogic PH1, PolarFire, CertusPro-NX, Spartan UltraScale+ (not on LCSC, web search found none).
- Whether TLK1221 on LCSC is first-party stock at 2.5 times below TI list.
- Whether PI4FW-R22B-003 is truly bilingual-keyed; RFB-9002 price and stock.
- Whether the CH32V305 QFN28 package exposes USBHS; HS USB on HPM5301; CH570 and CH569 pricing.
- Common-mode and power-off behaviour of the TLV3202 comparator (not specified), and whether TLV70018 has no discharge.
- Ccb of Chinese MMBTH10/S9018 second sources.
