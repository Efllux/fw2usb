# S100 cable soft PHY: evidence and executable research model

Research for #13, 2026-11-09. **No interoperable PHY or tested hardware yet.**
The Rust model is allocation-free and `no_std`. It separates physical voltages,
interpreted arbitration, and an event-level two-node initialization simulation.
An S100 implementation still needs analog receivers/drivers and a measured
asynchronous DS capture strategy; it cannot be implemented with bare GPIO.

## Evidence and limits

References below are public; no firmware, proprietary RTL, or NDA documents were
used. Source facts are distinguished from engineering choices. The IEEE amendment
is not a replacement for the 1995 base standard. Publicly indexed copies have OCR
errors; unresolved units are explicitly excluded from implementation constants.

- [IEEE 1394-1995](https://standards.ieee.org/ieee/1394/2094/), §4.3.3
  tables 4-25 through 4-28 (arbitration), §4.4 (cable PHY behavior).
- [IEEE 1394a-2000, public exhibit](https://ptacts.uspto.gov/ptacts/public-informations/petitions/1529228/download-documents?artifactId=2qSeKUEx7ZRTEisZvIoxlrWEYhYwYZ_EIh9dIpj4AT7ROjNofRFGl0o),
  §4.3.3, §4.3.5 tables 4-32..34, §4.4.3 figures 4-22..25,
  annex E table E-1. Access may be blocked; indexed text was available.
- [Sony EP1094638A2, EPO publication](https://data.epo.org/publication-server/rest/v1.2/publication-dates/20010425/patents/EP1094638NWA2/document.pdf),
  pp.2..4 tables 1..5: independent public transcription of base arbitration.
  [EP0923209B1](https://patents.google.com/patent/EP0923209B1/en), tables 3..5,
  gives the same codes. Patents are evidence of signaling descriptions, not a
  freedom-to-operate opinion or a substitute for conformance testing.
- [TI TSB41AB1, SLLS423I](https://www.ti.com/lit/ds/symlink/tsb41ab1.pdf),
  pp.2..3,16..20; [TSB41AB2](https://www.ti.com/lit/ds/symlink/tsb41ab2.pdf),
  electrical characteristics and PHY registers;
  [TSB41AB3](https://www.ti.com/lit/ds/symlink/tsb41ab3.pdf).
- [TI TSB41LV02A, SLLS400A](https://dtsheet.com/doc/40517/ti-tsb41lv02apap),
  PHY register descriptions; [Agere FW802BF](https://dtsheet.com/doc/724335/agere-fw802bf-09-db),
  tables 9..10; [Agere FW803, rev.3](https://datasheet4u.com/pdf/92703/FW803.pdf),
  p.13 table 3; [Philips PDI1394P23, 2001-09-06](https://media.digikey.com/pdf/Data%20Sheets/NXP%20PDFs/PDI1394P.pdf),
  §§9..14. These corroborate chip behavior, with revision-dependent limits.
- [MindShare, FireWire System Architecture, 2nd ed.](https://www.informit.com/store/firewire-system-architecture-ieee-1394a-9780201485356):
  useful chapter map, but full text was not available; no numeric requirement is
  asserted solely from its preview. No thesis was found that independently
  establishes a conformant FPGA analog cable PHY.

## Coordinate system and arbitration tables

Each pair carries differential **0**, **1**, or **Z** (driver disabled). Cable
crossing maps local TPA to peer TPB, and local TPB to peer TPA, preserving polarity.
TX data is on TPB, strobe on TPA; at the receiver data is TPA, strobe TPB
(TSB41AB1 p.2). Do not interchange the transmitting and receiving coordinates.

`line::resolve` models equal ideal currents: Z passes the other driver, equal
values double voltage, opposite values cancel to analog Z. Its enum collapses
voltage magnitude, so it cannot predict analog margins. `infer_remote` returns
one possible explanation, not a unique remote state.

The **interpreted** arbitration state additionally uses our own drive. It is not
just the comparator result (EPO table 3). This table is implemented in `arb.rs`:

| Our drive | Comparator | Interpreted |
|---|---|---|
| Z | Z / 0 / 1 | Z / 0 / 1 respectively |
| 0 | 0 | 0 (peer may be 0 or Z) |
| 0 | Z | 1 (peer opposes us) |
| 1 | 1 | 1 (peer may be 1 or Z) |
| 1 | Z | 1 (one's dominance, despite cancellation) |
| 0 | 1 | inconsistent in the ideal model |
| 1 | 0 | inconsistent in the ideal model |

Transmit line states, **(local TPA, local TPB)**, per base table 4-27 / EPO table 4;
1394a §4.3.3 supplies the last two additions:

| Signal | TX pair |
|---|---|
| IDLE | (Z,Z) |
| TX_REQUEST | (Z,0) |
| TX_GRANT | (Z,0) |
| TX_SELF_ID_GRANT | (Z,0) |
| TX_PARENT_NOTIFY | (0,Z) |
| TX_CHILD_NOTIFY | (1,Z) |
| TX_IDENT_DONE | (1,Z) |
| TX_DATA_PREFIX | (0,1) |
| TX_DATA_END | (1,0) |
| BUS_RESET | (1,1) |
| TX_DISABLE_NOTIFY | (Z,1) |
| TX_SUSPEND | (0,0) |

Receive states, **(interpreted local TPA, interpreted local TPB)**, per base
table 4-28 / EPO table 5 and 1394a §4.3.3. Meanings depend on PHY phase and what
we are transmitting; aliases must not be decoded without that context.

| RX pair | Meaning(s) |
|---|---|
| (Z,Z) | IDLE |
| (Z,0) | RX_PARENT_NOTIFY / RX_REQUEST_CANCEL |
| (Z,1) | RX_IDENT_DONE |
| (0,Z) | RX_SELF_ID_GRANT / RX_REQUEST |
| (0,0) | RX_ROOT_CONTENTION / RX_GRANT / RX_SUSPEND |
| (0,1) | RX_PARENT_HANDSHAKE / RX_DATA_END |
| (1,Z) | RX_CHILD_HANDSHAKE / RX_DISABLE_NOTIFY |
| (1,0) | RX_DATA_PREFIX |
| (1,1) | BUS_RESET |

For example, both endpoints transmitting PARENT_NOTIFY gives (0,0), not IDLE;
REQUEST and GRANT also produce (0,0). Reset's ones dominate every other state.
`arb` tests exercise every drive combination, every TX code, and both handshakes.

## Initialization and normal arbitration

Behavioral reference: 1394a §4.4.3.1..4, figures 4-22..25. Summary written
independently; the normative diagrams/C are not copied into this repository.

| State family | Required externally visible behavior |
|---|---|
| R0 reset start | Detect or initiate reset, propagate to active ports, discard topology/IDs and pending link traffic; long and arbitrated short resets are distinct |
| R1 reset wait | Stop transmitting reset when duration expires; wait for all active peers to be idle or already requesting a parent, and the reset-wait delta |
| T0 tree start | Identify children from parent-notify; a sole `force_root` node delays seeking a parent, allowing all its ports to become children |
| T1 child handshake | CHILD_NOTIFY to marked children, wait for their PARENT_NOTIFY to clear |
| T2 parent handshake | PARENT_NOTIFY on the remaining parent candidate; handshake completes on (0,1), or (0,0) starts contention |
| T3 root contention | Release drive; independently choose fast/slow interval; at expiry either reassert parent-notify on idle or accept peer's parent-notify as a child; tied choices retry |
| S0 self-ID start | Wait for parent grant, or act as root; receive packets from other branches if necessary |
| S1 self-ID grant | Grant lowest unidentified child; leaf/all-children-done advances to own transmission |
| S2 self-ID receive | Repeat/count self-IDs; IDENT_DONE marks a child identified |
| S3 speed capabilities | Exchange per-port capability while completing child identification; S100 adds no higher-speed sink |
| S4 self-ID transmit | Send own packet plus complement at S100, then IDENT_DONE toward parent; root transmits last |
| A0 idle | Qualify gaps; arbitrate only for permitted link/PHY requests; observe reset at any time |
| A1 request | Nonroot requests parent; root resolves competing requests; no immediate ACK needs ordinary request arbitration |
| A2 grant | Grant winning child and prevent an unrelated branch from taking the bus |
| TX / RX | Prefix and speed qualification, DS data, end; handle ACK, timeout and repeat paths before idle |

Root, IRM and bus manager are separate roles. Advertising contender and becoming
root does not implement the lockable IRM CSRs. A single force-root guarantees
root selection; both nodes setting it requires contention (1394a table 4-35).
Forcing root must be coordinated by PHY config and a new reset, with topology and
gap count revalidated; it is not a way to skip tree-ID.

`two_node::Bus` implements the one-port path from R0 through S4 to A0, with
simultaneous sampling of previous outputs, 10 ns steps, actual crossed-pair
arbitration handshakes and ordered, validated self-ID quadlets. Tests cover our
sole force-root case (peer ID0, bridge ID1), remote force-root, unbiased
contention, reset during tree-ID and reinitialization. **Simplifications:** ports
already connected; reset detection is an input event; self-ID data are opaque
660 ns events, not DS bits; capability exchange is timed but S100 only; entropy
is deterministic test input. Normal A1/A2/TX/RX, port debounce/suspend, repeater
queues, variable oscillator error, gap-count reset history and a complete
malformed-waveform fault model remain unimplemented. This model is not a
waveform-accurate or compliance simulation.

## Timing inventory

All values below are from 1394a §4.3.5 table 4-32, printed pp.56..58, unless
stated otherwise. Ranges are not targets to round arbitrarily; actual RTL needs
clock-tolerance-aware counts. Superseded names are retained here to prevent
accidental use of an old requirement.

| Constant | Range / relationship |
|---|---|
| BASE_RATE | 98.304 Mb/s nominal, ±100 ppm |
| ARB_RESPONSE_DELAY | Repeat arbitration at least as quickly as data, at most 80 ns faster |
| ARB_SPEED_SIGNAL_START | >= -20 ns relative to prefix |
| BIAS_FILTER_TIME | 41.6..52.1 us |
| BIAS_HANDSHAKE | 5.3..16 ms |
| CONCATENATION_PREFIX_TIME | >=160 ns before next speed indication |
| CONFIG_TIMEOUT | 166.6..166.9 us (loop detection) |
| CONNECT_TIMEOUT | 330..350 ms debounce |
| DATA_END_TIME | 240..260 ns |
| DATA_PREFIX_HOLD | >=40 ns after speed signaling |
| FORCE_ROOT_TIMEOUT | 83.3 us..CONFIG_TIMEOUT; recommended maximum162 us |
| MAX_ARB_STATE_TIME | 200..400 us, excluding idle/tree-start/explicitly timed states |
| MAX_BUS_HOLD | <=1.63 us concatenation hold |
| MAX_DATA_TIME | <=84.34 us continuous clocked data |
| MIN_DATA_PREFIX | >=140 ns; >=180 ns recommended for legacy interoperability |
| MIN_IDLE_TIME | >=40 ns |
| MIN_PACKET_SEPARATION | >=340 ns prefix between concatenated packets |
| NOMINAL_CYCLE_TIME | 124.988..125.013 us average |
| PHY_DELAY | >=60 ns, maximum encoded by PHY register |
| PORT_ENABLE_TIME | <=1 ms for bias valid |
| RESET_TIME | 166.6..166.7 us |
| RESET_WAIT | >=160 ns **delta**, added to long/short reset duration |
| RESPONSE_TIME | 40 ns..PHY_DELAY+100 ns |
| ROOT_CONTEND_FAST | 760..850 ns |
| ROOT_CONTEND_SLOW | 1.59..1.67 us |
| SHORT_RESET_TIME | 1.26..1.40 us |
| SID_SPEED_SIGNAL_START | -20..+20 ns relative to IDENT_DONE |
| SPEED_SIGNAL_LENGTH | 100..120 ns |
| RESET_DETECT | **UNCONFIRMED**: public indexed text says80..85.3 ms, inconsistent with a166.7 us pulse; obtain and visually check authoritative text/errata before implementation |
| ACK_RESPONSE_TIME | removed; use RESPONSE_TIME |
| DATA_PREFIX_TIME | removed; use concatenation/hold/min-prefix requirements |
| MAX_BUS_OCCUPANCY | removed; use MAX_DATA_TIME |
| MAX_DATA_PREFIX_DELAY | removed; use ARB_RESPONSE_DELAY |

The simulation selects reset166660 ns, reset delta170 ns, force-root100 us,
contention810/1630 ns, prefix180 ns and end250 ns. Its 10 ns time grid is a test
choice, not an implementation oscillator specification.

### Gap count

1394a tables 4-33/34: in base-bit-time units, subaction detection is bounded by
`(27+16g)/BASE_RATE_max - PHY_DELAY_max` and
`(29+16g)/BASE_RATE_min + PHY_DELAY_max`. Arbitration-reset detection substitutes
`51+32g` / `53+32g`. Add `arb_delay=4g/BASE_RATE` before originating arbitration;
the originating subaction minimum is `(27+20g)/BASE_RATE_max`, arbitration-reset
minimum `(51+36g)/BASE_RATE_max`. Nominal detection formulas use28/52 instead of
27/29 or51/53; do not confuse nominal values with tolerance bounds.

Start at63, not a hard-coded two-node optimization. A measured/verified one-hop
legacy topology may use5 (1394a annex E; Linux
[`core-card.c:400..402,518..542`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/drivers/firewire/core-card.c#L400)).
PHY config, reset history and all peers' self-ID gap counts must agree. Two
consecutive resets without configuration can restore63 (TSB41AB2 PHY registers).

## Electrical requirements ledger

These are **confirmed reference-chip limits**, not a claim that every number is
an IEEE conformance limit. Unless another source is identified, TSB41AB1
SLLS423I pp.16..20 provides the entry. PDI1394P23 §§9..14 corroborates these
thresholds and explicitly specifies driver and comparator conditions.

| Quantity | Confirmed reference value |
|---|---|
| TX differential output into56 ohm | 172..265 mV |
| Driver-off differential voltage | <=20 mV |
| Signal current, derived | about3.07..4.73 mA through56 ohm; **not** the ±1.05 mA entry below |
| Driver algebraic sum current, speed off | -1.05..+1.05 mA (sum of+ and- conductor currents) |
| S200 speed sink on TPB | -4.84..-2.53 mA **per conductor** |
| S400 speed sink on TPB | -12.4..-8.1 mA per conductor |
| Data receiver threshold | -30..+30 mV |
| Arbitration comparator thresholds | positive89..168 mV; negative-168..-89 mV |
| Recommended differential RX amplitude | data118..260 mV; arbitration168..265 mV |
| TPBIAS | nominal1.86 V; loaded1.665..2.015 V; source/sink range-5.6..+1.3 mA |
| TPB common mode | source-power node0.4706..2.515 V; nonsource0.4706..2.015 V |
| Bias/connect recognition | TPB bias detector threshold0.6..1.0 V; this alone does not implement unpowered-peer connect detection |
| Speed comparator, TPBIAS minus TPA CM | S20049..131 mV; S400314..396 mV |
| Termination |110 ohm cable; TI uses112 ohm split as2x56 at both ends to include internal RX loading |
| TPA midpoint | TPBIAS,1 uF stabilization |
| TPB midpoint |5 kohm parallel220 pF to ground |
| RX input loading | differential4..7 kohm and4 pF; common-mode20 kohm and24 pF |
| S100 input jitter / pair skew |±1.08 ns / ±0.8 ns |
| AB1 TX rise/fall |0.5..1.2 ns at connector; BA3F-EP §6.8 specifies0.3..0.8 ns for that device |

FW803 table3 differs in some speed/common-mode limits (e.g. S20045..139 mV),
so matching a single chip's thresholds is not proof of universal compatibility.
S100 means **no S200/S400 common-mode sink**, not that common-mode errors are
harmless: a49 mV droop can already trip a peer's speed detector. Unpowered
backfeed, TPBIAS connection probing (Philips ICD max76 uA), debounce and safe
VP handling remain AFE work. See the independent workstream-B AFE PR.

## Full-duplex 48 kHz AMDTP at S100

Use **peak blocking packets**, not average `48000/8000=6` frames. `fw-amdtp`
produces8 event blocks in a data packet at48 kHz, with a no-data slot every
fourth cycle (`stream` tests). Both directions may peak in the same cycle; we
cannot assume favorable phase alignment. Each AM824 MIDI data channel costs
one full quadlet per event block even when no MIDI byte is active.

For each stream, CIP payload `P=8 + 8*4*(PCM+MIDI_slots)`; on-wire isochronous
header/headerCRC/dataCRC add12 bytes. At S100 the resource reservation is
`4*align4(P+12)+overhead` bandwidth units. One unit is1/49.152 MHz seconds.
Linux [`iso-resources.c:48..76,114..130`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/iso-resources.c#L48)
reserves512 overhead units per stream at default gap63, or
`floor(9.7*g)+89` for optimized gaps. This accounts conservatively for
arbitration, prefix/end, propagation and interpacket timing. The IRM budget is
4915 units (about100 us); cycle-start and asynchronous reserve occupy the
remaining cycle, so **do not subtract them again from4915**. Source:
[`drivers/firewire/core.h:51`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/drivers/firewire/core.h#L51).

| Device/profile | PCM capture/playback | MIDI slots | CIP payloads B | Units atgap63 | Time us | Fits4915? |
|---|---:|---|---|---:|---:|---|
| PRO10 i/o |10/10 |1 each |360+360 |4000 |81.380 |yes |
| PRO26 i/o, ADAT off |10/10 |1 each |360+360 |4000 |81.380 |yes |
| PRO26 i/o, all ADAT |26/26 |1 each |872+872 |8096 |164.714 |**no** |
| PRO24 /24 DSP |16/8 |1 each |552+296 |4512 |91.797 |yes, limited reserve |
| PRO40 original four-stream layout |(10+10)/(12+8) |1 in first stream ofeachdirection |360+328+424+264 |7744 |157.552 |**no** |

Atgap5 the corresponding units are3250,3250,7346,3762,6244: optimization cannot
rescue the two failures. Even an unrealistically perfect aggregation of PRO40
into two20PCM+MIDI streams exceeds4915 before ordinary overhead. Each individual
48k packet above fits the S1001024-byte isochronous data limit; the failure is
**duplex aggregate time/reservation**. S200 is the conservative target for full
PRO26/40. Actual S100 operation also depends on firmware accepting that speed.

Channel sources: Focusrite
[PRO10 guide p.14](https://fael-downloads-prod.focusrite.com/customer/prod/s3fs-public/downloads/saffire-pro10-user-guide-english0.pdf)
(10in/10out, through96k, no176.4/192k),
[PRO26 i/o guide pp.13,20..21](https://fael-downloads-prod.focusrite.com/customer/dev/s3fs-public/downloads/saffire-pro26-user-guide-english0.pdf)
(26/26 at48k,18/18 at96k,10/10 at192k, optional ADAT-off10/10);
[PRO24 DSP observed register dump, lines76..122,143..164](https://github.com/mrmidi/ASFireWire/blob/95413cf551893d04cc68d3c44628cbb8a0674af7/documentation/fixtures/DICE/spro24dsp.txt#L76)
(16/8 PCM plus MIDI);
[original PRO40 stream report](https://sourceforge.net/p/ffado/mailman/ffado-user/thread/56C832B1.7050600%40sakamocchi.jp/)
by ALSA maintainer (four-stream layout, observed not universal);
[Linux DICE Focusrite table](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/dice/dice-focusrite.c#L8)
(newer PRO40 TCD3070 aggregate20/20 plus MIDI). PRO24 assumptions require live
format verification, and PRO40 firmware layouts differ. The modern DICE **PRO26**
is a different device from the BeBoB **PRO26 i/o**.

`bandwidth.rs` uses `PacketBuilder::max_len()` and tests these exact totals,
alignment/overflow and per-packet limits. This replaces the old18/10 rough
estimate. No real audio stream or Saffire S100 compatibility has been tested.

## Cross-family link-speed envelope

The adapter targets FireWire devices generally. S100 is an experimental soft-PHY
milestone, **not the reference adapter's speed ceiling**. The chip-PHY/link path
must implement S100/S200/S400 and admit each stream profile against both cable
and USB capacity. Raw-link storage and DV/HDV do not pass through an audio codec.

The following are conservative peak reservations at gap63, generated by:

```sh
cargo run -p fw-amdtp --example bandwidth
```

Every entry includes all enabled directions,12 wire-overhead bytes per packet,
512 arbitration/timing units per stream, and CIP only when actually present.
Numbers exceeding4915 fail; also independently check the1024/2048/4096-byte
S100/S200/S400 packet ceilings. **Capacity minimum is not a claim of firmware
speed support.** Some hardware will insist on S400 even when payload fits below.

| Profile | Peak data bytes | S100 units | S200 units | S400 units | Capacity minimum |
|---|---|---:|---:|---:|---|
| BeBoB PRO10 48k | [360, 360] | 4000 | 2512 | 1768 | S100 |
| BeBoB PRO10 96k | [712, 712] | 6816 | 3920 | 2472 | S200 |
| BeBoB PRO26io 48k max | [872, 872] | 8096 | 4560 | 2792 | S200 |
| DICE PRO24 48k | [552, 296] | 4512 | 2768 | 1896 | S100 |
| DICE PRO40 48k 4-stream | [360, 328, 424, 264] | 7744 | 4896 | 3472 | S200 |
| DICE PRO40 TCD3070 48k | [680, 680] | 6560 | 3792 | 2408 | S200 |
| RME FF400 48k | [576, 576] | 5728 | 3376 | 2200 | S200 |
| RME FF800 48k | [896, 896] | 8288 | 4656 | 2840 | S200 |
| RME FF400 192k | [1280, 1280] | 11360 | 6192 | 3608 | S400 |
| RME FF800 192k | [1536, 1536] | 13408 | 7216 | 4120 | S400 |
| OXFW FireWave 6out 48k | [200] | 1360 | 936 | 724 | S100 |
| EFW AudioFire12 48k | [424, 424] | 4512 | 2768 | 1896 | S100 |
| MOTU 828mkII ADAT 48k | [616, 616] | 6048 | 3536 | 2280 | S200 |
| MOTU UltraLiteMk3 192k | [1288, 1672] | 12960 | 6992 | 4008 | S400 |
| Digi002/003 48k | [616, 616] | 6048 | 3536 | 2280 | S200 |
| TASCAM FW1884 48k | [648, 584] | 6048 | 3536 | 2280 | S200 |

Sources/derivations for the additional families (all Linux links are pinned):

- [RME `ff.c:134..174`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff.c#L134)
  gives FF40018/14/10 and FF80028/20/12 PCM each direction by rate family.
  [`amdtp-ff.c:15..28,165`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/amdtp-ff.c#L15)
  uses4 bytes per PCM, blocking packets, **no CIP**, and separate asynchronous
  MIDI. Thus48k block counts8,192k32. S100/S200 device-TX support is unconfirmed:
  [`ff-protocol-former.c:285..289,382..390,513..518`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff-protocol-former.c#L285)
  exposes an S800 flag for FF800 and fixed-format FF400 fields, not a verified
  arbitrary TX-speed selector. S400 is the safe implementation target.
- [OXFW speaker table, `oxfw-spkr.c:278..285`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/oxfw/oxfw-spkr.c#L278)
  gives FireWave six playback channels. This is **one-way**, no invented capture
  stream. The selected6PCM mode has24-byte AM824 blocks; Linux's max-payload
  reservation uses8 blocks, although nominal48k nonblocking emission has6.
  [`oxfw-stream.c:155..195`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/oxfw/oxfw-stream.c#L155).
  Other OXFW firmware can burst jumbo capture packets after skipped cycles;
  **do not extrapolate this row** to all Oxford products.
- [EFW AudioFire12 parameters, `audiofire.rs:37..54`](https://github.com/alsa-project/snd-firewire-ctl-services/blob/7654d40cb0e62426e460c0b94605e2a4b506d6bb/protocols/fireworks/src/audiofire.rs#L37)
  give12PCM each direction plus one MIDI port;52-byte blocks with8-byte CIP.
  [Linux `fireworks_stream.c:32..59,162..182`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireworks/fireworks_stream.c#L32)
  confirms blocking AM824 and special DBC/SYT behavior. AudioFire8's name is
  not its wire count: its10PCM includes digital channels. Query capabilities.
- [MOTU v2 format rules, `motu-protocol-v2.c:229..281`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu-protocol-v2.c#L229)
  add8 ADAT chunks to14 fixed chunks for828mkII at48k, plus2 message chunks.
  [`amdtp-motu.c:69..76`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/amdtp-motu.c#L69)
  gives block bytes=`4+align4(3*(PCM_chunks+message_chunks))`: SPH plus packed
  three-byte chunks, not AM824. MIDI is inside message chunks, **no extra MIDI
  quadlet**. For UltraLiteMk3 at192k,10TX/14RX PCM chunks and2 message chunks
  give40/52-byte blocks with32 events:
  [`motu-protocol-v3.c:243..247,310..317`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu-protocol-v3.c#L310).
  Wire chunks can include padding/unused optical slots; do not relabel all
  chunks as user-facing PCM connectors.
- [Digi002/003 rate table, `digi00x-stream.c:19..28`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/digi00x-stream.c#L19)
  gives18PCM at48k and10 at96k;
  [`amdtp-dot.c:113..127`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/amdtp-dot.c#L113)
  adds one MIDI channel before PCM. CIP resemblance does not remove the
  Digi003 DOT sample transformation requirement.
- [TASCAM FW1884 specification, `tascam.c:14..23`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam.c#L14)
  and [`tascam-stream.c:306..324`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam-stream.c#L306)
  provide18PCM each direction with digital ports enabled;
  [`amdtp-tascam.c:11..32`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/amdtp-tascam.c#L11)
  adds two counter/status quadlets only to capture. TX resources are explicitly
  **S400** in [`tascam-stream.c:287..293`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam-stream.c#L287).
  The lower-speed columns are hypothetical airtime, not a usable TASCAM mode.

Common conservative peak sizing comes from
[`amdtp-stream.c:300..330`](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/amdtp-stream.c#L300).
Nonblocking, jumbo payloads and DICE high-rate dual-wire modes need their own
peak formation; do not apply8/16/32 times advertised connector count blindly.
`bandwidth::stream_payload` and `minimum_speed` take **arbitrary data-field
sizes**, so custom stream modules can reuse the accounting without AM824 parsing.
The common accounting lives in fw-amdtp for now and can be shared/re-exported
without making that codec mandatory for other families.

This evidence makes S400 support essential for the generic adapter. In particular,
FF400/800 and UltraLiteMk3 high-rate duplex profiles exceed the conservative
S200 budget. Original four-stream PRO40 only leaves19 bandwidth units atS200
gap63; S400 or a validated gap optimization is the practical bring-up choice.
The physical speed ceiling also differs from transparent USB forwarding capacity;
no claim is made that USB2 can carry a full S800 line-rate stream.

## Exit criteria before active cable operation

1. Obtain a visually checked normative RESET_DETECT requirement and implement
   the full receive/reset qualifier, gap timers and port monitor.
2. Verify AFE levels, loading, cancellation and common-mode transients across
   process/voltage/temperature and powered-off states.
3. Capture passive reset/tree/self-ID and compare decoded state transitions to
   actual PHY traffic, including both force-root nodes and long cable cases.
4. Prove DS capture timing, metastability and FIFO clock-drift handling; the Rust
   XOR decoder is a codec model, not a timing closure argument.
5. Only then transmit self-ID/packets, test IRM and cycle master, and stream a
   profile that actually fits S100.
