# TASCAM vendor protocol

Research, not fw2usb device support. Primary source snapshots are pinned below.

Stream: CIP-like PCM plus capture counter/status quadlets. Control: Vendor registers, separate async control/MIDI. Linux: `snd-firewire-tascam`.

## Start, clock and recovery

Outline of the start sequence, summarized from the pinned implementation below (specific register addresses and values are intentionally not reproduced and are [verify] against that source and captures): select the format and rate and reserve bus resources; configure the device's transmit and receive channels and enable streaming through its vendor registers; set a device option word [verify]; enable PCM multiplexing; add the playback stream at the peer's speed and the capture stream at S400; start an event-count replay domain, which may need an initial number of skipped cycles [verify value]; then wait until the stream is ready. On failure, stop the domain and finish the session.

Capture includes two non-PCM quadlets; MIDI/status is not a generic AM824 layout. Firmware can delay event multiplexing after rate change; received SYT ignored, packet cadence matters. Unknown register purposes must remain explicit.

Firmware upload: No routine Linux stream-start upload; boot/recovery unknown.

## Tier-1 profile requirements

Match ROM IDs and firmware revisions, include per-rate/per-optical-mode capture
and playback wire layouts, PCM slot map, MIDI/control placement, peak packet
size, bus-speed requirements, clock source/lock operations, packet cadence and
timestamp rules, resource acquisition, bounded startup waits, error teardown
and generation-reset recovery. Encode family-specific quirks above explicitly.
Do not expose unsupported rates or infer channel count from the product name.

## Model evidence

Counts below are capture/playback PCM, excluding MIDI; ? means **[verify]** from
capability queries or captures, not zero channels. Clock behavior, upload needs
and quirks inherit the family discussion; per-model exceptions need verification.
FFADO registration indicates a source match, not fw2usb or current FFADO validation.

| Vendor | Model | ROM vendor/model | PCM at <=48 / 88.2–96 / 176.4–192 kHz | Source |
|---|---|---|---|---|
| TASCAM | FW-1884 | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam.c#L1-L235) |
| TASCAM | FW-1082 | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam.c#L1-L235) |
| TASCAM | FW-1804 | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam.c#L1-L235) |

## Primary implementation references

- [sound/firewire/tascam/tascam-stream.c:1–551](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam-stream.c#L1-L551)
- [sound/firewire/tascam/tascam.c:1–235](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam.c#L1-L235)
- [sound/firewire/tascam/amdtp-tascam.c:1–252](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/amdtp-tascam.c#L1-L252)

### Sequence and layout audit anchors

- [tascam/tascam-stream.c:222–280](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam-stream.c#L222-L280)
- [tascam/tascam-stream.c:435–510](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam-stream.c#L435-L510)
- [tascam/tascam.c:14–43](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/tascam/tascam.c#L14-L43)

### Channel derivation

The model table tascam.c:14–43 gives FW1884 analog 8/8, FW1082 8/2,
FW1804 8/2. tascam-stream.c:306–324 adds eight slots for ADAT-equipped
models and two for S/PDIF-equipped models: FW1884 18/18, FW1082 10/4,
FW1804 18/12 wire PCM slots. Capture adds two counter/status quadlets.
These fixed wire slots must not be confused with active optical channel count
at each rate; validate digital-mode operation at 88.2/96 kHz [verify].
