# Simulation fidelity and validation ledger

Owner priority, 2026-11-09: accuracy takes precedence over milestone breadth.
E supplies the toolchain; F is **in progress**, beginning with LREQ. G–M must
not claim end-to-end behavior until the corresponding models and tests exist.
Tests below are synthetic unless explicitly labelled as captured hardware data.
No hardware correlation has been performed. There is no complete chip model yet.

## Sources and representation

TI **SLLS424G**, December 2004, TSB41AB2, is the chip reference. TI's
[canonical URL](https://www.ti.com/lit/ds/symlink/tsb41ab2.pdf) returned 404 during
this run; the same TI-authored document was read from a
[public mirror](https://ke9ns.com/tsb41ab2.pdf), SHA-256
`31ab1fff34512bedc4d5d3f19ac18f8238ce2173c62d75d425e138c21cbb4502`.
Page numbers below are printed datasheet pages. No datasheet binary is vendored.
IEEE 1394a interface clause/Annex cross-check remains outstanding; TI alone
must not be described as full normative conformance evidence.

D0 is the **most significant** physical lane, unlike conventional HDL vectors.
The present serializer has a scalar LREQ only. Future D/CTL adapters must state
lane mapping explicitly. Model `sample()` consumes the pin value immediately
before an SCLK rising edge; RTL outputs change following an edge, ready for the
next sample. Simulation uses 49.152 MHz with ideal phase; analog setup/hold and
metastability are not simulated by this test.

## Implemented fidelity

| Model / implementation | Reproduces and source | Does not reproduce | Hardware validation needed |
|---|---|---|---|
| `fw2usb.smoke.Heartbeat` | Onboard counter and wrap, ULX3S constraint snapshot linked in gateware README | PHY, USB, CDC, external timing | Board LED/reset observation |
| `fw2usb.lreq.LreqSerializer` | Fig 16, Tables 12–18, pp33–35: MSB-first start/type/payload/stop, all seven defined types, full 8-cycle bus form, 9/17/6-cycle other forms; inputs latched on valid/ready | Request scheduling, power/startup, differentiation; busy requests have no queue | Capture LREQ against SCLK with every type and boundary |
| `sim.phy.LreqDecoder` | Tables 12–18: serial receive including 7-cycle bus form; Table 15 invalid speed→null-packet indication; pp35–36 pending bus exclusion, fair/priority clear/ignore on RX, iso retained, grant/reset clear, acceleration request latch | Register semantics/status replies; actual null-packet transmission; gap/arbitration timing; read-pending state; EAA gating | Compare PHY grants and captured LREQ/RX/reset sequences |
| `fw2usb.status.StatusReceiver` / `sim.phy.StatusSource` | Fig 17/Table 19 pp36–37: 4/16-bit emission, pairwise flag delivery (`flags_mask`), interrupted register retry, read-pending exclusion/reset persistence, idle separation; literal RTL tests at every interruption position | Real register map/value sampling, event priority, complete RX model, IO turnaround | Capture interrupted status reads and reset while read pending |
| `fw2usb.receive.ReceiveAdapter` / `sim.phy.receive_samples` | Figs 18–19/Table 20 pp37–39: variable data-on prefix, speed decode with ignored X fields, S100/S200/S400 lane widths, MSB-first bytes, null packets, invalid speed discard, incomplete-byte error | Cable resynchronization latency, packet CRC, buffering, backpressure, active self-ID synthesis; no malformed-prefix checking | Compare real packet bytes and prefix duration against simultaneous PHY-LINK capture |
| `sim.registers.PhyRegisters` / `sim.phy.RegisterPhy` | TI Tables 1–8 pp21–27: base/page masks, W1C, straps, two-reset gap rule, port selection, vendor identity, software hard reset; LREQ RTL→register→status tests | Register-only subset: no debounce, cable event generation, LinkOn, timed reset, unsolicited self-ID status; revision bytes require explicit fixture; read snapshots at request completion are unverified model policy | Read/write/reset traces on identified silicon revision |
| `sim.transmit.TransmitPhy` | TI Tables 10–11/Figs20–21 pp32/39–41: explicit ownership, grant/idle turnaround, widths, optional idle, hold bound, termination, cancellation and multispeed concatenation diagnostics | Observer only; no TX RTL yet, external arbitration/grant and concatenation separation; no analog high impedance or CRC validation | Capture output enables and literal TX traces at each speed |
| Rust `fw-phy-model` | Research DS, line resolution and two-node initialization; see SOFT-PHY.md | Chip PHY-LINK timing or full cable arbitration | Compare cable-level traces after electrical qualification |
| AFE SPICE research | Behavioral cases described in hardware/soft-phy-afe/spice/RESULTS.md | Transistor/PVT compliance, digital sampler coupling | Scope skew/thresholds, calibrated models, sampling apertures |

`test_lreq.py` uses literal expected streams independently of the RTL builder and
decodes them with a separate Python implementation. It exercises all request
types, all eight speed codes, mid-request input changes, reserved-type rejection,
RX loss/preservation, grant and reset. Invalid stream exceptions are **test
harness diagnostics**, not a claim about unspecified silicon responses.
The decoder returns an observed request even when arbitration policy ignores it;
`pending_bus` is the separate accepted-request state. Synthetic bus reset here
only clears pending requests; it does not emulate reset timing or self-ID.

## Required next fidelity gates

| Area | Reference / evidence to extract | Missing behavior and acceptance test |
|---|---|---|
| Status/registers | TI Fig 17, Table 19 pp36–37; register Tables 1–9 | Status primitives present; integrate with LREQ and real register map; register masks/pages/reset subset implemented; cable-driven events, debounce and unsolicited self-ID status absent |
| Receive/transmit | TI Figs 18–21, Table 20 | RX formatting primitive present; integrate packet FIFO/CRC; TX grant/turnaround, hold, concatenation and underrun absent; pin-by-pin independent reference traces still needed |
| Power and isolation-free mode | TI p2, Figs 13/22/23, Table 21, LPS/LCtrl sections | ISO high, SYSCLK enable/phase/start/stop, LinkOn, reset sequencing; startup trace comparison |
| Multi-node cable bus | IEEE 1394/1394a arbitration clauses [exact clauses verify] | 24.576-MHz tick scheduler, independent PHY clocks, ack/subaction/arbitration-reset gaps and gap_count, fairness intervals, cycle-start priority and iso/async phase boundaries; no invented constants |
| Reset/topology | IEEE self-ID clauses; TI PHY register behavior | Reset→tree-ID→self-ID timing, complements, root/node derivation, automatic physical-ID status, reset during active requests |
| BeBoB device | [family sources](devices/bebob.md) pinned Linux/FFADO anchors | ROM/CSR/AVC/FCP/CMP registers, bounded stream start, packet layouts and real SYT; identify model/revision and obtain trace before claiming realism |
| DICE device | [family sources](devices/dice.md) pinned Linux/FFADO anchors | Distinct register protocol/ownership/notification, clock locks and streaming; no generic BeBoB emulation |
| CDC and clock recovery | Domain plan in gateware README; measured oscillators | Independent drift/jitter in SCLK, ULPI, device audio; FIFO assertions, reset epochs, synchronizer structure checks; digital sims cannot prove analog metastability immunity |
| Full-system co-simulation | TI + family sources + USB/LUNA specification | RTL PHY-LINK/link/transaction/iso/USB against models, Rust host simulated USB transport: reset→self-ID→ROM→CMP→audio→bit-exact WAV; currently absent |
| Soft-PHY sampling | AFE research PR15 | Feed analog threshold/delay waveforms to independent-clock sampler; distinguish analog inaccuracies from sampling/CDC failures |

Model register/packet behavior from public documentation and independently written
algorithms; cite Linux/ALSA/FFADO observations without copying GPL implementation
into MIT/Apache code. Capture replay must carry source, licence, device/revision,
clock/cycle metadata and known omissions. See [capture inventory](../captures/README.md).

## Reproduction

Run commands in gateware/README.md. CI additionally synthesizes LREQ independently;
status and RX are synthesized too; only the safe heartbeat is routed to real pins. No model failure may be waived
by substituting an encoder/decoder round trip for an independently sourced vector.

Receive test adds all 256 byte values at each of three speeds, a literal S100
A5 pin trace, data-on/null cases, ignored speed X fields, invalid codes and partial
byte termination. Error and end are independent strobes; an invalid speed reports
an error immediately, and the later end still closes that receive operation.
Consumers must retain error state for the packet. There is no backpressure: a
future packet FIFO must explicitly report overflow rather than dropping bytes.

Register tests use independent literal identity/default/status vectors and RTL LREQ
serialization. Unknown product revision bytes fail explicitly; no arbitrary chip
identity is substituted. Port line-state fixtures assume disconnected Z lines;
no cable debounce or fault detector is claimed. IBR/ISBR are stored requests only:
actual reset scheduling and durations remain absent. Software reset flushes the
composed decoder/status engine; bus reset preserves pending register snapshots.
