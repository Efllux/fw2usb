# Digidesign Digi 002/003

Research, not fw2usb device support. Primary source snapshots are pinned below.

Stream: CIP-like DOT PCM transform + MIDI quadlet. Control: Vendor register/session protocol. Linux: `snd-digi00x`.

## Start, clock and recovery

Select supported rate/source and reserve resources; write capture/playback channel word; read streaming state (zero interpreted as two), decrement through streaming-set states with 20-ms waits; add playback then capture; transmit priming packets and replay event counts, then wait ready. Device does not transmit before receiving. Failure stops domain and finishes session.

18 PCM at 44.1/48 kHz and 10 at 88.2/96, plus MIDI slot. Digi003 DOT sample transformation is mandatory and differs from AM824 labels; preserve MIDI/control framing and device clock behavior.

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
| Digidesign | Digi 002 | see ROM match table | 18/18 / 10/10 / unsupported | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/digi00x.c#L1-L176) |
| Digidesign | Digi 002 Rack | see ROM match table | 18/18 / 10/10 / unsupported | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/digi00x.c#L1-L176) |
| Digidesign | Digi 003 | see ROM match table | 18/18 / 10/10 / unsupported | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/digi00x.c#L1-L176) |
| Digidesign | Digi 003 Rack | see ROM match table | 18/18 / 10/10 / unsupported | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/digi00x.c#L1-L176) |

## Primary implementation references

- [sound/firewire/digi00x/digi00x-stream.c:1–450](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/digi00x-stream.c#L1-L450)
- [sound/firewire/digi00x/digi00x.c:1–176](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/digi00x.c#L1-L176)
- [sound/firewire/digi00x/amdtp-dot.c:1–412](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/amdtp-dot.c#L1-L412)

### Sequence and layout audit anchors

- [digi00x/digi00x-stream.c:145–192](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/digi00x-stream.c#L145-L192)
- [digi00x/digi00x-stream.c:335–400](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/digi00x-stream.c#L335-L400)
- [digi00x/amdtp-dot.c:1–127](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/digi00x/amdtp-dot.c#L1-L127)
