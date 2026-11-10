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
| `sim.phy.LreqDecoder` | Tables 12–18: serial receive including 7-cycle bus form; Table 15 invalid speed→null-packet indication; pp35–36 pending bus exclusion, fair/priority clear/ignore on RX, iso retained, grant/reset clear, acceleration request latch | Register semantics/status replies; actual null-packet transmission; gap/arbitration timing; read-pending state; packet-length detection is external; acceleration/NPA cancellation is exercised only via completed-packet fixture | Compare PHY grants and captured LREQ/RX/reset sequences |
| `fw2usb.status.StatusReceiver` / `sim.phy.StatusSource` | Fig 17/Table 19 pp36–37: 4/16-bit emission, pairwise flag delivery (`flags_mask`), interrupted register retry, read-pending exclusion/reset persistence, idle separation; literal RTL tests at every interruption position | Real register map/value sampling, event priority, complete RX model, IO turnaround | Capture interrupted status reads and reset while read pending |
| `fw2usb.receive.ReceiveAdapter` / `sim.phy.receive_samples` | Figs 18–19/Table 20 pp37–39: variable data-on prefix, speed decode with ignored X fields, S100/S200/S400 lane widths, MSB-first bytes, null packets, invalid speed discard, incomplete-byte error | Cable resynchronization latency, packet CRC, buffering, backpressure, active self-ID synthesis; no malformed-prefix checking | Compare real packet bytes and prefix duration against simultaneous PHY-LINK capture |
| `sim.registers.PhyRegisters` / `sim.phy.RegisterPhy` | TI Tables 1–8 pp21–27: base/page masks, W1C, straps, two-reset gap rule, port selection, vendor identity, software hard reset; LREQ RTL→register→status tests | Register-only subset: no debounce, cable event generation, LinkOn, timed reset, unsolicited self-ID status; revision bytes require explicit fixture; read snapshots at request completion are unverified model policy | Read/write/reset traces on identified silicon revision |
| `fw2usb.transmit.TransmitAdapter` / `sim.transmit.TransmitPhy` | TI Tables 10–11/Figs20–21 pp32/39–41: explicit ownership, grant/idle turnaround, widths, optional idle, hold bound, termination, cancellation and multispeed concatenation diagnostics | RTL streams prebuffered bytes, terminates underrun with explicit error; external arbitration/grant and concatenation separation; RTL concatenation terminator present; actual regrant scheduling absent; no analog high impedance or CRC validation | Capture output enables and literal TX traces at each speed |
| `sim.power.InterfacePower` / `sim.phy.PoweredRegisterPhy` | TI Table21/Fig27 pp42–47: rational wall-time level-LPS recognition, selected min/max timing corners, stopped-clock wake, seven zero cycles then data-on/idle, interface reset flush vs bus reset persistence | ISO=1 level LPS only; no pulse decoder/clock waveform; standalone LinkOn latch below, external full-cycle samples, software reset disables/restarts clock; no full chip cable reset sequencing | Compare startup, low-power wake and LPS timing at clock pins |
| `sim.power.LinkOn` | TI p7 C/LKON terminal definition: interrupt gating, addressed wake latch, bus-reset clearing, eight-SYSCLK period and hardware-reset high impedance | Power/register latch integrated; cable packet recognition absent; initial wave phase is declared model convention | Capture activation phase, wake behavior and strap handoff |
| `sim.clocks.Clock` / library FIFO research harness | Exact rational independent frequency/phase offsets and deterministic edge jitter; tests Amaranth AsyncFIFOBuffered under opposite ±100 ppm SCLK/USB, burst stalls and coordinated testbench reset | Synthetic stimulus; no bridge CDC/epoch controller, metastability, reset release circuit or physical clock source | CDC structural review and physical drift/reset captures |
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
| Status/registers | TI Fig 17, Table 19 pp36–37; register Tables 1–9 | Status primitives present; LREQ/register masks/pages/reset/interrupt subset implemented; cable-driven events/debounce absent; explicit self-ID-complete event emits register0 status |
| Receive/transmit | TI Figs 18–21, Table 20 | RX formatting primitive present; integrate packet FIFO/CRC; TX grant/turnaround and underrun adapter present; integrated scheduling and RTL concatenation terminator present; actual regrant scheduling absent; pin-by-pin independent reference traces still needed |
| Power and isolation-free mode | TI p2, Figs 13/22/23, Table 21, LPS/LCtrl sections | Level LPS and software reset/LinkOn composition present; pulsed LPS and actual clock phase/edges still absent; startup trace comparison |
| Multi-node cable bus | IEEE 1394/1394a arbitration clauses [exact clauses verify] | 24.576-MHz tick scheduler, independent PHY clocks, ack/subaction/arbitration-reset gaps and gap_count, fairness intervals, cycle-start priority and iso/async phase boundaries; no invented constants |
| Reset/topology | IEEE self-ID clauses; TI PHY register behavior | Reset→tree-ID→self-ID timing, complements, root/node derivation, automatic physical-ID status has explicit event hook only; topology engine and reset during active cable operations absent |
| BeBoB device | [family sources](devices/bebob.md) pinned Linux/FFADO anchors | ROM/CSR/AVC/FCP/CMP registers, bounded stream start, packet layouts and real SYT; identify model/revision and obtain trace before claiming realism |
| DICE device | [family sources](devices/dice.md) pinned Linux/FFADO anchors | Distinct register protocol/ownership/notification, clock locks and streaming; no generic BeBoB emulation |
| CDC and clock recovery | Domain plan in gateware README; measured oscillators | SCLK/USB library FIFO research harness present; device-audio domain, bridge FIFO/reset epochs and synchronizer structure checks absent; digital sims cannot prove analog metastability immunity |
| Full-system co-simulation | TI + family sources + USB/LUNA specification | RTL PHY-LINK/link/transaction/iso/USB against models, Rust host simulated USB transport: reset→self-ID→ROM→CMP→audio→bit-exact WAV; currently absent |
| Soft-PHY sampling | AFE research PR15 | Feed analog threshold/delay waveforms to independent-clock sampler; distinguish analog inaccuracies from sampling/CDC failures |

Model register/packet behavior from public documentation and independently written
algorithms; cite Linux/ALSA/FFADO observations without copying GPL implementation
into MIT/Apache code. Capture replay must carry source, licence, device/revision,
clock/cycle metadata and known omissions. See [capture inventory](../captures/README.md).

## Reproduction

Run commands in gateware/README.md. CI additionally synthesizes LREQ independently;
status, RX and TX are synthesized too; only the safe heartbeat is routed to real pins. No model failure may be waived
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

TX RTL tests send all byte values at every width into the independent observer,
including missing next byte and missing first byte (three-idle cancellation per
TI recommendation). TX adapter has no CRC insertion or packet queue: upstream
must prebuffer, and an underrun packet is invalid even if its prefix was sent.
The byte handshake accepts a byte at its first symbol; subsequent symbols use
a latch, so upstream may change immediately after acceptance. TX synth/check
passes with CI-pinned tools; no external PHY pins are constrained or driven.

Power tests cover TI recognition/wake timing corners and short LPS dropouts.
Clock waveform generation remains external: power model consumes elapsed wall
time and full-cycle samples; it does not generate analog edge/phase behavior.
Powered composition flushes read/status on interface reset and discards inactive
bus-reset flags. Software-hard-reset now flushes decoder/status and restarts the power model;
cable-side consequences and actual waveform phase remain absent.
Status source preserves new flag bits arriving after its active snapshot.

Status source now enforces the required idle after RX before retrying status.
LinkOn tests exhaust all 256 interrupt/control combinations and check waveform,
latch, bus reset and hardware reset. The standalone model receives the decoded
addressed-wake event; it does not recognize cable packets by itself.

CDC research uses [Amaranth 0.5.8 FIFO documentation](https://amaranth-lang.org/docs/amaranth/v0.5.8/stdlib/fifo.html).
The test transfers 1024 ordered words with independent jittered 49.152/60 MHz
clocks and opposite drift signs, forces full/backpressure, and verifies old words
are flushed by a testbench-coordinated reset. This validates the simulation
harness/library use, not an implemented bridge reset/epoch protocol.

Register interrupt fixtures now propagate detected CPS/port/injected timeout
events to status flag 3 without inferring cable detectors. W1C cause clearing
does not generate an interrupt; inactive interface events are discarded.

Self-ID completion fixtures now emit unsolicited register0 status (TI p36),
including retry after RX interruption. The status source distinguishes automatic
register transfers from requested reads so a read arriving during an automatic
transfer is not cleared accidentally. Requested reads take priority at a new
transfer boundary as an explicit scheduler policy, not verified silicon priority.
Disposition of an unfinished unsolicited transfer across a second bus reset is
still unverified: the model currently preserves its snapshot. Tree-ID/self-ID
timing and actual packet production are not supplied by this event hook.

LREQ request-loss fixtures additionally cover TI Table8 NPA and ACK/null/short
packet distinctions with EAA and temporary acceleration enable/disable. In
accelerated mode RX alone cannot determine request loss: the model waits for
an explicit completed-packet bit-length event. This is not yet connected to
a complete cable receiver and does not claim exact early-cancellation timing.

TX RTL now optionally waits in hold before its first data byte, bounded at
47 cycles (TI Fig20); wait48 cancels with underrun. Tests cover zero/one/47
holds and the timeout boundary against the independent observer. A hold does
not permit gaps inside packet data.

TX RTL supports hold+idle packet-end concatenation, with optional EMC speed
code. All single/multispeed transitions and reserved codes are checked against
the independent observer. Illegal faster→S100/reserved concatenation releases
the bus and pulses config_error (a bridge policy, not silicon behavior).
The arbiter must still enforce separation and issue the next grant; the adapter
does not schedule a second packet autonomously.

Normative cross-check: [IEEE 1394a-2000, indexed primary-text mirror](https://citeseerx.ist.psu.edu/document?doi=197480bd36a167bcaf92f105894b48496237a795&repid=rep1&type=pdf),
Table4-35 pp61–62 says interface reset leaves node variables intact. The
composition therefore preserves temporary acceleration control across interface
reset, unlike bus/hardware reset. Clauses4.3.5/4.3.6 expose gap equations, and
5A provides normative PHY-LINK behavior for further cross-check. Direct PDF
download and screenshot returned403 here; RESET_DETECT units remain unresolved
because extracted text still reports ms. No corrected constant was guessed.

## F integration boundary (owner scope update)

`fw2usb.phy_link.PhyLink` composes LREQ, status, RX and TX with explicit shared-bus
output enable, one outstanding bus request/read, legacy RX request cancellation,
bus-reset TX abort and interface disable. A composed test serializes a request,
accepts grant, checks TX against the independent PHY observer, receives bytes and
reads register status. It synthesizes/checks independently in CI.
F is sufficient to begin G; it is **not full-chip conformance**. Residual gaps:
board startup sequencer/pulsed LPS and actual IO timing, accelerated NPA scheduling
in RTL, exact cable latency/phase, full grant arbiter and packet FIFO overflow.
Unsupported bus speed codes are rejected by the composed request-ready contract.
Existing primitives still permit invalid-code research fixtures independently.

## G implementation checkpoints

`fw-1394` now supplies independently authored MSB-first packet CRC, header/iso
wire encoders/parsers, quadlet-read requests, bounded packet-zero topology
reduction and force-root PHY configuration pairs. Source: IEEE1394-2008
§6.2.2/6.2.3/6.2.5.15, §16.3.2.3 and IEEE1394a §4.4.3.3; primary text available
at the linked mirrors above. No Linux/FFADO implementation copied.

RTL CRC is compared with 257 Rust-generated byte fixtures (length0..256); the
Rust reference checks the standard checking remainder C704DD7B. The ASCII check
value FC891918 is an algorithm check, not a captured FireWire packet. Actual
independent captured packet vectors remain needed. RTL self-ID capture rejects
bad complements and unsupported extended self-ID packets; topology reduction
rejects missing parents/children and discontinuous IDs. RTL cycle timer divides
SCLK by2, wraps3072/8000/128 and queues cycle-start demand only when enabled/root,
counting missed deadlines under backpressure. Packet scheduling/ack handling and
actual cycle-start wire transmission are not yet integrated.

G packet checkpoint: streaming RX validates header CRC, data CRC, padded wire
length and supported tcode layouts; output bytes remain provisional until good.
Streaming TX inserts separate CRCs and zero padding with backpressure. Rust wire
fixtures cover zero/unaligned ISO and async quadlet read; corrupt/truncated frames
are rejected. ACK checksum receiver and response-capacity/CRC decision logic are
present; request matching, retry timeout and response scheduling remain next.
CycleMaster emits the 16-byte header of IEEE1394-2008 Fig6-10 (broadcast CYCLE_TIME
write, tcode8, priF) plus CRC. It delays grant eligibility until offset17, snapshots
time at grant per §8.3.2.3, and requires an external priority arbiter. Physical
PHY latency compensation and real capture correlation remain unverified.

`sim.bus.Bus` adds an epoch-aware event-level tree bus: postorder physical IDs,
self-ID/complement broadcast, cable-hop propagation, reset invalidation, one
pending request/node, priority classes, nominal gap_count delays and fairness
intervals. Multi-node tests cover branching, propagation and reset during queued
traffic. This is **not cycle-accurate cable arbitration**: tree handshakes and
arbitration ties are abstract policies, no analog lines, dribble bits, repeating
port elastic buffers, suspend or accelerated arbitration are modeled. Generic
nodes support up to3 ports; they are not all TSB41AB2 instances. Prefix/end/reset
corners and nominal gap equations are sourced in SOFT-PHY.md; no uncertain
RESET_DETECT constant is used. Independent PHY clocks remain in the pin-level
harness rather than this opaque-frame scheduler.

Remote protocol fixtures: `sim.devices` uses synthetic ROMs with computed CRC16,
CSR/IRM values and bounded atomic compare-swap. BeBoB models PCR connections,
playback-before-capture priming and FCP rejection of unsupported opcodes. DICE
models section pointers, 64-bit owner CAS, clock acceptance notification, channel/
speed/enable ordering and bus-reset ownership loss. DICE wire facts were checked
against [pinned interface definitions](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/dice/dice-interface.h),
not copied as executable code. Actual vendor ROMs, mixer controls, model-specific
AV/C capability replies, autonomous clock timers and audio engines remain absent.

`sim.transactions` connects remote fixtures through real async wire headers,
header/data CRCs, ACK pending/complete, quadlet/block reads/writes, CAS32/CAS64,
transaction labels, timeout tokens and reset-generation cancellation. A three-node
test reads the complete remote ROM, connects a BeBoB PCR and claims DICE ownership.
CRC checking uses polynomial long division independently of Rust/RTL LFSRs.
These transaction peers are behavioral models, not the H hardware transaction
engine. Busy/retry protocol and wire-level turnaround/response deadlines remain
unmodeled; repeated host writes are never silently replayed.

G integrated datapath: LinkLayer routes PHY RX to packet/self-ID validation,
serializes root cycle priority requests and sends actual cycle-start bytes through
PHY TX. Speculative immediate ACK request completes during RX; bad header causes
null cancellation; valid request/response ACK policies use pending/complete.
Pin-level integration tests include bus-generated self-IDs and remote ROM response,
and CRC failure cancellation. Self-ID phase and local node/root state are supplied
by controller policy; Rust derives topology. Busy ACK retry/timeout state, full
transaction scheduling and cable response-deadline verification remain residual
integration work rather than claims of full normative conformance.

## H transaction implementation

Choice: bounded gateware, no soft CPU. CSR/IRM atomic CAS32, CSR quadlet/block
read/write, synthetic config ROM and CRC-framed responses have a directly tested
finite resource surface. TransactionResponder is one-request/64-quadlet capacity;
arrivals while busy increment dropped. Block writes commit one quadlet at a time;
a later error reports failure without inventing rollback. Production RX buffering/
credits still need integration. TransactionLink joins PHY pins, ACK scheduling,
CSR engine and response TX; a pin-level test reads the ROM header end to end.

RomReader emits actual quadlet-read wire packets, matches source/label/rcode and
bounds timeout/capacity; a bus-model test reads all bus-info/root-directory words
of a remote BeBoB fixture. Nested unit-directory/leaf traversal and ROM CRC16
validation remain controller work. Local ROM identity is synthetic, not a claimed
registered production GUID. Controller/node/phase startup policy remains external.
The zero-wait grant test exposed an ACK pipeline delay, now fixed by forwarding
new ACK data before its retention latch. New bus requests are held until active
PHY TX ends so a queued request cannot switch the active packet source mid-frame.

## I ISO / AMDTP hardware

AM824 RX/TX and exact-rational blocking SYT engine are cross-checked with Rust
fw-amdtp-generated shared fixtures at44.1/48kHz (including NO-DATA and DBC wrap).
ISO TX adds wire headers/CRCs; profile-bounded ISO RX stores payload in synchronous
RAM and validates the complete ISO/CIP shape before replaying PCM. CRC corruption
emits no PCM; sample/busy loss counters are explicit. Hardware PCR CAS connections
reset with the bus. FIFO/USB downstream backpressure and duplex scheduling remain
integration work; capacity/DBS must be selected for each profile (default2 slots,
512-byte payload). MIDI labels are skipped by RX; TX currently emits PCM slots.

`sim.audio.AudioClock` uses independent absolute sample-event times, true frequency
error and configurable SYT jitter. It matches Rust packet bytes at nominal rate;
one-second tests bound sample drift at±100ppm. BeBoB/DICE fixtures expose separate
stream-enable gates and this synthetic source. No capture or actual device-clock
lock correlation is claimed. IEC61883-1/6 wire facts cross-checked against the
[IEC sample](https://cdn.standards.iteh.ai/samples/15699/bfd68180020e438b92a73cda964485be/IEC-61883-1-2008.pdf).
PCR payload defaults are development fixtures; per-device overhead/admission
values still require profile validation. DBS=0/256-slot generic streams are outside
these bounded audio profiles.

## J USB / host and end-to-end byte-stream co-simulation

Pinned LUNA0.2.3 ULPI HS core supplies standard enumeration, vendor GET_CAPS and
512-byte bulk endpoints. Descriptor/control-handler tests and ECP5 synthesis pass.
Explicit exported USB clock/reset prevent synthesis from pruning an undriven
clock domain; only a real nonempty USB core is counted. Board clock/reset polarity,
HS electrical/token interoperability and physical throughput remain unverified.
The standalone core advertises capability0 until bridge command-worker integration.

Rust nusb host discovers raw endpoints and implements list/bus-info/self-ID,
quadlet reads/writes, root ROM dump with CRC/bounds checking, and ISO-to-PCM24 WAV.
Bounded transcript replay is a no-hardware backend, not a vendor capture. USB
framing is transfer-boundary independent; labels/cookies/generations are checked.
A separate bounded event queue prevents control calls from silently consuming
active ISO records. Recording destroys its handle on success and failure.

`sim/cosim.py` executes model reset/self-ID, real wire ROM/CMP/DICE ownership
transactions, drifting/jittered device audio, RTL PHY RX/CRC, retained RAM,
AM824 decode, SCLK→USB async FIFO and RTL FW2R framing, then the actual Rust CLI
produces bit-exact WAVs for both families. SCLK/USB have independent frequency
errors and deterministic edge jitter. The64-cycle local run passed392 BeBoB and
384 DICE frames; malformed sequence/generation transcripts fail without publishing
new WAVs. Control operations use behavioral transaction peers and recorded USB
request/response transcripts; the USB boundary is bulk bytes, not LUNA token/
electrical simulation. Full live command-worker, credit/reset-epoch integration,
realistic vendor AV/C capabilities and real captures remain explicit gaps.

### Native command worker checkpoint

RawUsbBridge now attaches a single-outstanding PHY/link worker to LUNA bulk CDC.
Real PHY-pin tests cover self-ID/local-ID discovery, quadlet and block operations,
CAS, timeout, ISO lease creation/destruction and generation/session resets. Async
payloads are bounded to256 bytes; opaque RX ISO payloads to4096 bytes. Whole-frame
arbitration preserves headers under backpressure. Lease/generation/time metadata
snapshot at packet start, including empty/non-CIP streams. USB session reset
flushes endpoint FSM/PID/queues, CDC queues and audio framer together; native bus
reset retains USB framing and reports a new generation. Native bridge advertises
capability7; standalone transport remains capability0.69 gateware tests, integrated
ECP5 synthesis/check, Rust1.99 checks and8-cycle WAV co-sim pass locally.

Remaining J work: explicit host credit records/admission, incoming async/FCP leases,
raw ISO TX/deadlines, label quarantine after timeout and token-level USB co-sim.
These are software/verification gaps, not hardware-only blockers. The native worker
pin test and transcript WAV test exercise different integration boundaries; no
claim that the WAV test currently enumerates LUNA or executes the native worker.

## K clock/UAC2 component validation

no_std fw-clock tests cover SYT wrap, independent bus/USB/audio drift, bounded
jitter, frequency-step FIFO displacement, clock loss, feedback quantization and
MCLK NCO phase. LUNA audio descriptors/control/alt gates/packet-atomic underflow
have HDL tests; standalone audio USB core synthesizes/checks (1564 LUT4,2DP16KD
at this checkpoint; no placement/timing claim). FIREBOX and Konnekt6 conservative
stereo48k profiles require runtime slot-map/firmware binding. See
[audio design and exact residuals](audio/CLOCK-UAC2.md).73 gateware tests pass.
Rust estimator and HDL audio endpoints are separate components: native-to-UAC2
sample/control integration and token-level/OS validation remain unimplemented.

## L host compatibility boundary

Independent Rust libraw1394 ABI subset now uses FW2R for synchronous reads/writes,
CAS32/64, IRM resource reservation and ISO receive/reset callbacks. A concurrent
IRM compare-mismatch test verifies bounded retry without retrying transport errors.
C ABI handle/error smoke and mock-transport callback tests pass. The full pinned
FFADO source API audit and missing surface are in
[shim README](../host/libraw1394-shim/README.md). No FFADO streaming claim: pollable
reactor, FCP/ARM, rawTX and clock snapshots are still absent.

The CoreAudio public-SDK vtable skeleton builds and passes factory/COM/property/
IO-rejection tests on macOS. It publishes zero devices. Its
[design](../host/coreaudio/README.md) specifies daemon/rings/clock epochs and
realtime constraints; actual audio driver/daemon implementation is outside this
skeleton. CI checks both C ABI and macOS bundle build. No HAL installation occurred.

## M reference-hardware work in progress

Original KiCad8 schematic/net/BOM generator selects active TSB41BA3F-EP legacy
link and DS-only port2, with TI-sourced bias/termination/power/reset/straps.
ERC passes with zero warnings/errors. Placed PCB is **unrouted**, lacks the
connector footprint and has186 unconnected items, although geometric violations
are zero. This is NOT M completion or fabrication-ready. See
[hardware status and source-access gap](../hardware/phy-breakout/README.md).
BA3F/AB2 behavioral equivalence is not established by a compatible link pinout.
