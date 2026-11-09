# MOTU proprietary v1/v2/v3

Research, not fw2usb device support. Primary source snapshots are pinned below.

Stream: CIP with SPH and packed 3-byte chunks; not AM824. Control: Vendor registers, register-DSP or command-DSP messages. Linux: `snd-motu`.

## Start, clock and recovery

Cache formats/optical modes and clock, reserve both resources, ensure packet formats, initialize appropriate DSP parser; read-modify-write communication control with both channels/activation bits; add capture then playback to domain; replay packet event-count and per-block SPH sequences; wait ready then enable fetching. Failure stops domain, disables fetching and communication.

Block size is 4-byte SPH plus aligned 3-byte chunks (including message/padding chunks). MIDI uses message bytes/flags, not an AM824 MIDI quadlet. Wire slots and user PCM count differ. Timestamp replay must preserve device clock.

Firmware upload: No routine stream-start upload; revision-specific boot states unknown.

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
| Motu | All pre-mark3 devices | 0x0001f2/0x00000000 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L467-L474) |
| Motu | All mark3 devices | 0x0001f2/0x00000001 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L475-L482) |
| MOTU | 828 | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | 828mkII | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | 896 | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | 896HD | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | Traveler | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | UltraLite | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | 8pre | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | 828mk3 | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | 896mk3 | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | UltraLite mk3 | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | Audio Express | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | 4pre | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |
| MOTU | Track16 | see ROM match table | ? / ? / ? | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207) |

## Primary implementation references

- [sound/firewire/motu/motu-stream.c:1–429](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu-stream.c#L1-L429)
- [sound/firewire/motu/motu.c:1–207](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu.c#L1-L207)
- [sound/firewire/motu/amdtp-motu.c:1–485](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/amdtp-motu.c#L1-L485)
- [libffado/src/motu/motu_avdevice.cpp:1–2057](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/src/motu/motu_avdevice.cpp#L1-L2057)

### Sequence and layout audit anchors

- [motu/motu-stream.c:62–112](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu-stream.c#L62-L112)
- [motu/motu-stream.c:227–315](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu-stream.c#L227-L315)
- [motu/amdtp-motu.c:55–100](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/amdtp-motu.c#L55-L100)
- [motu/motu-protocol-v2.c:229–320](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu-protocol-v2.c#L229-L320)
- [motu/motu-protocol-v3.c:200–350](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/motu/motu-protocol-v3.c#L200-L350)
