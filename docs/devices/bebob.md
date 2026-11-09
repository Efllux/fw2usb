# BeBoB / BridgeCo

Research, not fw2usb device support. Primary source snapshots are pinned below.

Stream: CIP AM824. Control: AV/C/FCP extended stream/plug commands, CMP, vendor mixer. Linux: `snd-bebob`.

## Start, clock and recovery

Discover plug formats and clock; choose supported rate and reserve both CMP resources; establish device input/playback then output/capture connection; attach both streams, start replay domain, apply M-Audio special rate command if applicable, then wait ready. On error stop domain and break both connections. Lightbridge can require 16000 initial skip cycles. This order includes silence/NODATA priming and is not equivalent to writing one PCR.

Initial discontinuous DBC on Lightbridge; wrong high-rate empty-packet DBC on FW1814/ProjectMix; Saffire and SaffireLE need separate matching. External-clock operation must query current source/rate and preserve lock.

Firmware upload: Some M-Audio bootloader identities require host firmware loading; others unknown until firmware identity checked.

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
| Mackie | Onyx Firewire | 0x00000f/0x00010065 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L2-L9) |
| Mackie | Onyx Firewire | 0x00000f/0x00010067 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L10-L18) |
| Tascam | IFFWDM | 0x0022E/0x10067 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L19-L25) |
| Behringer | X32 | 0x001564/0x00000006 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L58-L65) |
| Behringer | UFX-1604 mixer | 0x001564/0x00001604 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L66-L73) |
| Apogee Electronics | Rosetta 200 | 0x0003db/0x00010048 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L74-L81) |
| BridgeCo | RD Audio1 | 0x0007f5/0x00010048 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L82-L89) |
| BridgeCo | Audio 5 | 0x0007f5/0x00010049 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L90-L98) |
| PreSonus | FIREBOX | 0x000a92/0x00010000 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L99-L107) |
| PreSonus | Inspire1394 | 0x000a92/0x00010001 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L108-L115) |
| PreSonus | FirePOD | 0x000a92/0x00010066 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L116-L124) |
| TerraTec Electronic GmbH | Phase 88 FW | 0x000aac/0x00000003 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L178-L186) |
| TerraTec Electronic GmbH | Phase X24 FW (model version 4) | 0x000aac/0x00000004 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L187-L195) |
| TerraTec Electronic GmbH | Phase X24 FW (model version 7) | 0x000aac/0x00000007 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L196-L204) |
| ESI | Quatafire 610 | 0x000f1b/0x00010064 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L205-L213) |
| Focusrite | Saffire Pro26IO | 0x00130e/0x00000003 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L214-L222) |
| Focusrite | Saffire Pro10IO | 0x00130e/0x00000006 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L223-L231) |
| Focusrite | Saffire (LE) | 0x00130e/0x00000000 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L232-L241) |
| EDIROL | FA-66 | 0x0040ab/0x00010049 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L242-L250) |
| EDIROL | FA-101 | 0x0040ab/0x00010048 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L251-L259) |
| M-Audio | Ozonic | 0x000d6c/0x0000000a | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L260-L268) |
| M-Audio | FW Solo | 0x000d6c/0x00010062 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L269-L277) |
| M-Audio | NRV10 | 0x000d6c/0x00010081 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L278-L286) |
| M-Audio | FW Audiophile | 0x000d6c/0x00010060 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L287-L295) |
| M-Audio | FW 410 | 0x000d6c/0x00010046 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L296-L304) |
| M-Audio | FW 1814 | 0x000d6c/0x00010071 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L305-L314) |
| M-Audio | ProjectMix I/O | 0x000d6c/0x00010091 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L315-L324) |
| M-Audio | ProFire Lightbridge | 0x000d6c/0x000100A1 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L325-L332) |
| Acoustic Reality | eAR Master One | 0x000aac/0x00000002 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L349-L356) |
| CME | Matrix K FW | 0x0000000A/0x00030000 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L357-L364) |
| Phonic | HB 24U | 0x001496/0x000000 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L745-L752) |
| Yamaha | GO44 | 0x0000A0DE/0x0010000B | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L753-L760) |
| Yamaha | GO46 | 0x0000A0DE/0x0010000C | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L761-L769) |
| Digidesign | Mbox 2 Pro | 0x0000A07E/0x000000A9 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L785-L800) |
| ICON | FireXon | 0x00001A9E/0x00000001 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L826-L834) |

## Primary implementation references

- [sound/firewire/bebob/bebob_stream.c:1–987](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/bebob/bebob_stream.c#L1-L987)
- [sound/firewire/bebob/bebob.c:1–510](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/bebob/bebob.c#L1-L510)
- [libffado/src/bebob/bebob_avdevice.cpp:1–927](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/src/bebob/bebob_avdevice.cpp#L1-L927)

### Sequence and layout audit anchors

- [bebob/bebob_stream.c:593–690](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/bebob/bebob_stream.c#L593-L690)
- [bebob/bebob.c:145–210](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/bebob/bebob.c#L145-L210)
- [bebob/bebob_maudio.c:1–90](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/bebob/bebob_maudio.c#L1-L90)
