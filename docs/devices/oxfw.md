# Oxford FW970 / FW971

Research, not fw2usb device support. Primary source snapshots are pinned below.

Stream: CIP AM824, nonblocking/jumbo quirks. Control: AV/C/FCP stream format + CMP; model mixer commands. Linux: `snd-oxfw`.

## Start, clock and recovery

Enumerate AV/C stream formats (or infer only where driver quirk allows), choose rate, reserve CMP resources; start playback; start capture only when device has an output plug; select jumbo/voluntary-recovery skip/replay policy, start domain and wait ready. Failure breaks both applicable connections.

FireWave is playback-only. Some capture devices skip cycles then emit jumbo payloads. Several ignore received SYT and recover clock from packet event cadence. Preserve model-specific startup timing.

Firmware upload: No routine Linux stream-start upload; other firmware states unknown.

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
| Loud Technologies Inc. | Onyx 1640i (Oxford) | 0x000ff2/0x001640 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L40-L49) |
| Loud Technologies Inc. | Onyx-i | 0x000ff2/0x081216 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L50-L57) |
| Behringer | FCA202 | 0x1564/0xFC22 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L450-L456) |
| Griffin | FireWave | see ROM match table | 0/6 / unsupported [verify] / unsupported [verify] | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/oxfw/oxfw.c#L1-L404) |

## Primary implementation references

- [sound/firewire/oxfw/oxfw-stream.c:1–889](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/oxfw/oxfw-stream.c#L1-L889)
- [sound/firewire/oxfw/oxfw.c:1–404](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/oxfw/oxfw.c#L1-L404)
- [libffado/src/oxford/oxford_device.cpp:1–307](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/src/oxford/oxford_device.cpp#L1-L307)

### Sequence and layout audit anchors

- [oxfw/oxfw-stream.c:332–425](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/oxfw/oxfw-stream.c#L332-L425)
- [oxfw/oxfw-stream.c:155–195](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/oxfw/oxfw-stream.c#L155-L195)
