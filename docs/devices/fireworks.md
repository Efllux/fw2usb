# Echo Fireworks / EFW

Research, not fw2usb device support. Primary source snapshots are pinned below.

Stream: CIP AM824 with EFW DBC/SYT quirks. Control: EFW command/response over async transactions, CMP. Linux: `snd-fireworks`.

## Start, clock and recovery

Register EFW response address; query hardware capabilities/clock/rate, reserve CMP resources, start playback then capture; replay event-count sequence, skip 6000 initial cycles on affected Fireworks3 AudioFire2/4, wait ready. On failure stop domain and break CMP connections.

Received SYT is ignored by device; cadence matters. AudioFire9 differs from other Fireworks3. Capabilities contain per-rate channel groups, so AudioFire8 marketing count is insufficient.

Firmware upload: Flash firmware state/version queried; no routine stream-start upload.

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
| Echo | AudioFire2 | 0x1486/0xAF2 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L365-L373) |
| Echo | AudioFire4 | 0x1486/0xAF4 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L374-L382) |
| Echo | AudioFire8 | 0x1486/0xAF8 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L383-L391) |
| Echo | AudioFire8a | 0x1486/0xAF9 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L392-L400) |
| Echo | AudioFire12 | 0x1486/0xAF12 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L401-L409) |
| Echo | AudioFire12HD | 0x1486/0xAF12D | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L410-L417) |
| Echo | Fireworks 8 | 0x1486/0xF8 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L418-L425) |
| Echo | FW HDMI | 0x1486/0xAFD1 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L426-L433) |
| Mackie | Onyx 400F | 0xFF2/0x400F | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L434-L441) |
| Mackie | Onyx 1200F | 0xFF2/0x1200F | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L442-L449) |

## Primary implementation references

- [sound/firewire/fireworks/fireworks_stream.c:1–368](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireworks/fireworks_stream.c#L1-L368)
- [sound/firewire/fireworks/fireworks.c:1–366](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireworks/fireworks.c#L1-L366)
- [libffado/src/fireworks/fireworks_device.cpp:1–991](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/src/fireworks/fireworks_device.cpp#L1-L991)

### Sequence and layout audit anchors

- [fireworks/fireworks_stream.c:247–320](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireworks/fireworks_stream.c#L247-L320)
- [fireworks/fireworks_command.c:1–110](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireworks/fireworks_command.c#L1-L110)
