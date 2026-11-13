# Bilingual port: working notes (PAUSED 2026-11-13)

CERN-OHL-S-2.0. Work stopped by user decision until a broad parts and price
search is done. This file records the state at the stop. No design doc and no
pull request exist yet. Prices are no longer tracked here: see `bom.csv` on
branch `hardware/bilingual-port-bom` and the request list in
[PARTS-TO-PRICE.md](PARTS-TO-PRICE.md).

Status words used below: **checked** = read in the named datasheet;
**simulated** = a result from `spice/run.py` that ran; **reasoning** = not
checked or simulated, [verify].

## 1. Datasheet facts checked

TSB81BA3E (TI SLLS783C), the bilingual reference PHY:

- Beta and legacy share one external termination: 2 x 56 ohm per pair, TPA
  centre to TPBIAS with 1 uF, TPB centre to 5 kohm || 270 pF. So the standard
  itself runs 983.04 Mbaud over the legacy termination; no switch is implied.
- 1394b: differential output 700 mV, common-mode output 1.5 V, receiver input
  200..800 mV. Whether those are peak or peak-to-peak is not stated [verify].
- Legacy: VOD 172..265 mV into 56 ohm; arbitration thresholds +/-89..168 mV;
  data threshold +/-30 mV; speed thresholds 49..131 and 314..396 mV.
- Speed-signal currents 2.53..4.84 mA (S200) and 8.1..12.4 mA (S400) carry
  footnote 2, "absolute limit of **each** of TPB+ and TPB- driver currents".
  That settles the open question: **per conductor**. The soft-phy-afe README
  is right, the low-cost note's per-pair suspicion is wrong. The +/-1.05 mA
  figure is the algebraic sum of the two conductor currents.
- Unpowered, the PHY presents high impedance to the cable.

ECP5 (FPGA-DS-02012-3.4, FPGA-TN-02206-1.8):

- SERDES 270 Mb/s..3.2 Gb/s; receiver sensitivity 150 mV p-p; RX termination
  50 / 75 / high impedance and TX 50 / 75 / 5k; per-channel divide-by-2 for
  S400b; `tx_idle`; loss-of-signal detector; reference = rate / {8,10,16,20,25},
  so 49.152 MHz x 20.
- LVDS inputs: threshold +/-100 mV, common mode 0.05..2.35 V, pin 5 pF typ
  (8 max).
- **Left/right banks, the only ones with true differential inputs, are not
  hot-socket capable**: a pin above VCCIO is a low-impedance path. Wiring the
  cable pairs to FPGA differential inputs therefore back-feeds an unpowered
  board. Top/bottom banks are hot-socket (1 mA max leakage) but single-ended.
- GDDRX2 maximum 800 / 656 / 556 Mb/s for speed grades 8 / 7 / 6.

TLK1221 (TI SLLS713C): 0.6..1.3 Gb/s, REFCLK 60..130 MHz (98.304 MHz for
S800), 10-bit interface, comma alignment can be disabled, 2.5 V supply.
Receiver inputs are high impedance (2 pF, common mode 1.0..2.25 V) and need
external termination, which suits the shared legacy termination. TXP/TXN go
high impedance with ENABLE low or LOOPEN high. VOD 600..1100 mV into 50 ohm.
S400b (491.52 Mbaud) is below its range and would need 2x bit repetition
(reasoning).

SN65LVDS33/34 (TI SLLS490B): threshold +/-50 mV with 50 mV hysteresis over
-4..5 V common mode, power-off input current 20 uA, 5 pF, 400 Mbps, delay
2.5..6 ns, pulse skew 200 ps typ, channel skew 150 ps typ. An active failsafe
forces the output high when |VID| stays under 32..100 mV for 0.3..1.5 us.

Socket PI4FW-R22B-003: the datasheet is a drawing titled "Mini 1394b, 9 pin".
It does not say bilingual or beta, and gives no key dimension.
**Keying is unconfirmed** and needs a physical 9-to-6 cable or the 1394b
connector figures.

## 2. Architecture reached (reasoning unless marked)

- **Beta path:** a SerDes behind 10 nF series capacitors on the same pairs,
  sharing the legacy termination. Receiver pins high impedance; transmitter
  high impedance outside beta mode; 75 ohm series pads on the transmit side
  set the launch level and hide pin capacitance. Either the ECP5-UM DCU or a
  TLK1221 beside a non-SERDES FPGA fits this line-side circuit unchanged.
- **Legacy receive:** one SN65LVDS34 on TPA and TPB instead of FPGA
  differential inputs. It answers three open issues at once on datasheet
  numbers: 68 mV margin at the 118 mV minimum signal (was 18 mV), common mode
  to 2.515 V, and no unpowered back-feed. It also sees the 49 MHz tones.
- **Legacy drive:** emitter-switched current legs per conductor (RF PNP
  source, RF NPN sink), emitters through 91 ohm to hot-socket FPGA pads,
  bases on two diode-connected references built through the same pad and
  resistor so pad resistance and Vbe track. Releasing the reference pads
  parks the PNP bases at 3.3 V and the NPN bases at 0 V, so in beta and tone
  states no junction can conduct at any line common mode.
- **Arbitration:** two TLV3202 with resistive offset networks (10k series,
  267k to rail, threshold 3.3 V x 10k/267k = 124 mV, tracks the rail, not the
  cable common mode).
- **S400 additions:** four NPN speed-signal sinks on TPB, one more TLV3202 on
  the TPA common mode against thresholds divided from TPBIAS.
- **Bias:** 1.8 V LDO with enable and no output discharge for TPBIAS; a slow
  dual comparator for connect detect (47k pull-up on the TPBIAS node) and
  bias detect (TPB common mode against 0.8 V).
- **Beta common mode:** weak pad-driven dividers set about 1.5 V on both
  pairs in beta mode only, because the SerDes is AC coupled and a peer's
  centre taps may be floating.
- **Port state machine (outline only, not written up):** disconnected ->
  send tone bursts and watch for tones on TPA and for peer bias on TPB ->
  either beta (speed negotiation, training, 8B10B) or legacy (enable TPBIAS,
  release SerDes, enable driver references, bus reset).
- **Logic split:** all PHY and link timing in the FPGA; USB and control in
  the MCU.

## 3. Simulation state (`spice/`, run with `spice/run.sh`)

`run.sh` currently **exits nonzero**: two studies are broken (below).
`results.json` and RESULTS.md have not been generated. Models: transistor
cards written from datasheet headline numbers, behavioural pads, comparators,
SerDes and switch; cable is an R-L ladder fitted to the 1394a attenuation
limit. None is a vendor model.

Ran and gave usable numbers:

| Study | Result |
|---|---|
| Driver DC, 3 supplies x 3 temperatures x 3 peer biases | VOD 205.8..246.6 mV (limit 172..265); current sum 0.07 mA (limit 1.05); pad and resistor mismatch not yet included |
| Legacy transmit S100, RF transistors | worst sample 184 mV at the peer, pass |
| Legacy transmit S400, RF transistors | worst sample 121..129 mV (minimum 118), width 0.74..0.78 UI, rise about 1.0..1.1 ns (limit 1.2), common-mode disturbance 18..24 mV (limit 49) with +/-0.3 ns pad skew. Margin to 118 mV is thin and was run at nominal amplitude only |
| Legacy transmit, MMBT3904/3906 class | S400 eye closed; S100 eye fine but rise about 4.3 ns against a 3.2 ns limit [verify]. No jelly-bean cost-down |
| Legacy receive, peer at 172 mV | S100 worst sample 145 mV; S400 106..119 mV against the +/-50 mV receiver, width 0.66..0.72 UI |
| Speed signal transmit | S200 3.44..4.12 mA per conductor, droop 223..268 mV; S400 8.72..10.54 mA, droop 567..685 mV; data VOD stays above 203 mV |
| Unpowered, peer bias 2.015 V | 0.99 mA drawn with pins open, 2.27 mA with worst-case pin leakage, of which 0.39 mA is the standard 5k. Negative control (FPGA inputs on a clamping bank): 31.8 mA |
| Connect detect | TPBIAS node 1.51 V open, 0.43 V with a peer: works against a 1.2 V threshold |
| False speed negative control | a missing source leg gives 67.7 mV droop, above the 49 mV threshold, as intended |

Broken or not run:

- **Arbitration classification:** 82 of 90 wrong with zero overdrive. This
  looks like a harness fault (saved comparator nodes read back as zero), not
  a circuit result. Not diagnosed.
- **Speed detect receive:** all outputs zero, same symptom, not diagnosed.
- **Bias detect:** open-socket TPB common mode came out at 0.598 V, against
  the 0.6 V lower threshold limit. The arbitration networks pull it up; the
  network values need changing. This one is a real finding.
- **Beta eye at 983.04 Mbaud** (bare line, legacy attached, with a switch)
  and the legacy eye with idle SerDes branches: code written, **never run**.
  Whether the 2:1 switch is needed is therefore still unanswered.

## 4. Open questions and risks

- Beta-mode amplitude units, transmit common-mode range and tone amplitude
  need the 1394b text; the TI datasheet is not enough.
- SerDes transmitter off-state impedance (ECP5 5k setting, TLK1221 LOOPEN) is
  taken from one-line datasheet statements.
- S400 data-strobe capture in the FPGA from single-ended 393 Mbit/s receiver
  outputs is unproven.
- The SN65LVDS34 failsafe could misfire on a long constant line state if the
  settled level were under 100 mV.
- Socket keying (above).
