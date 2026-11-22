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
