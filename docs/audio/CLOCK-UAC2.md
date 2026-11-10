# Clock recovery and experimental UAC2

`fw-clock` is a no_std numerical research model. It unwraps SYT in49152 ticks
(16cycles ×3072 ticks), with an extended sample index supplied by the AMDTP
controller. Offset>=3072 and missing SYT are rejected. Observations must be less
than1ms apart; a caller must preserve DBC continuity and invalidate after reset,
rate change, or500ms without timestamps. `elapse` implements the loss watchdog.

Each4096-frame window produces a rate estimate. First-order frequency filtering
uses alpha1/16 (nominal time constant about1.36s at48k,0.34s at192k). Lock is
conservatively reported after64 windows; this is a frequency-settling policy,
not a measured phase-lock guarantee. Outliers beyond±2000ppm are rejected. No SRC,
phase servo or FIFO correction changes PCM samples. USB SOF/bus-timer correlation
must supply measured bus ticks per USB second. Assuming24.576MHz would conceal
bus crystal drift. This controller is not appropriate for families without SYT.

Tests inject audio±200ppm, bus+75ppm, USB-40ppm and deterministic SYT jitter±9ticks
at44.1/48/96/192k. Settled frequency error is bounded below2ppm. HS16.16 feedback
rounding contributes at most0.0611frames/s. A separate48k ±150ppm step test holds
modeled FIFO displacement below64frames, starting centered in1024frames. This
is a controlled scenario, not a universal stability bound. Missing timestamps,
invalid offsets, reset, and32-bit MCLK phase continuity have tests.
`Recovery::mclk_increment` and `Nco` model256fs at196.608MHz; frequency quantization
is checked separately from feedback quantization. A fabric NCO is not a qualified
physical audio clock: clock-tree jitter/PLL integration remain hardware work.

The LUNA `AudioUsbDevice` supplies a stereo48k PCM24 UAC2 function with external
clock entity, frequency CUR/RANGE and Clock Validity, alternate0/1 capture/playback,
explicit feedback, and a continuously present vendor bulk companion interface3.
Descriptors use ADC2 Tables4-3/5/6/9/10/27/33/34/35. Endpoint addresses2/82/83 are
separate from companion1/81. Capture's packet-atomic FIFO emits a whole silent
packet on underflow and counts it; it never consumes half a packet then pads.
A controller must supply recovered feedback and assert both profile_ready and
clock_locked before alt1 can be selected. Clock loss clears both active alts.
USB bus reset resets endpoint queues/PIDs and capture buffering.

Profiles select conservative stereo subsets for PreSonus FIREBOX (BeBoB) and
Desktop Konnekt6 (DICE), from PR17 identities. Binding requires exact IDs, a
nonempty firmware identity and discovered PCM slot maps; unsupported rates and
insufficient/duplicate maps fail. The first two discovered PCM channels are used,
not assumed contiguous wire slots. These profiles are experimental and require
actual AV/C or DICE capability discovery; the current binder's tests use synthetic
capabilities. No vendor mixer/firmware script or hardware support is claimed.

Remaining integration: connect the numerical controller/profile binder to a
bounded production control plane, bridge native AM824 samples to both USB-domain
streams, packet-count accounting on playback overrun, full token-level enumeration
and host OS interoperability. Thus K has tested components but is not a complete
physical tier1 bridge. These remaining integration tasks are software work.

Primary sources:
- [USB-IF ADC2 with September2026 errata](https://www.usb.org/sites/default/files/Audio2_with_Errata_and_ECN_through_Sep_14_2026.pdf), descriptor tables and clock controls.
- [Apple TN3190](https://developer.apple.com/documentation/technotes/tn3190-usb-audio-device-design-considerations), HS feedback and clock design considerations.
- [Pinned DICE model facts](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/dice/dice-tcelectronic.c), Desktop Konnekt6 ID/layout evidence; no executable GPL code copied.
- [FIREBOX identity research](../devices/bebob.md), PR17 primary registration links.
