# Generic AV/C

Research, not fw2usb device support. Primary source snapshots are pinned below.

Stream: Discover IEC 61883 format; AM824 only if advertised. Control: AV/C/FCP, plug discovery, CMP. Linux: `no single universal ALSA driver`.

## Start, clock and recovery

Read ROM unit directories, enumerate subunits and plugs, query supported/current stream formats and clock sources, negotiate a supported format, allocate IRM bandwidth/channel and establish CMP connections; prime correct packet sequence, await valid capture and lock. Reverse connections/resources on error. This is a framework, not a universal tested start sequence.

Generic AV/C identifies control structure, not a guaranteed codec or mixer. Devices can require undocumented vendor steps. Use raw mode until captured vectors and a validated profile exist.

Firmware upload: Unknown; do not infer from AV/C compliance.

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
| Stanton DJ | SCS.1m | 0x00001260/0x00001000 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L457-L466) |

## Primary implementation references

- [libffado/src/genericavc/avc_avdevice.cpp:1–941](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/src/genericavc/avc_avdevice.cpp#L1-L941)
