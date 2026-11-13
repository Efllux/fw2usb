# DICE / TCAT

Research, not fw2usb device support. Primary source snapshots are pinned below.

Stream: CIP AM824, multiple streams, high-rate dual-wire variants. Control: DICE register sections, owner/notification transactions, vendor extensions. Linux: `snd-dice`.

## Start, clock and recovery

Claim owner/notification address, discover register sections and stream counts, set clock/rate and wait notification; reserve resources and program each channel/speed; start required capture then playback streams, set global enable, start timestamp replay domain and wait ready. Reset requires resource generation updates; failure disables/finishes session and stops all streams.

Channel layouts depend on firmware and rate mode, not model name alone. PRO40 original and TCD3070 revisions differ. Cache extension tables and retain clock-source lock notification semantics.

Firmware upload: No routine Linux stream-start upload; revision-specific boot/recovery unknown.

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
| Loud Technologies Inc. | Onyx 1640i (DICE) | 0x000ff2/0x000006 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L26-L32) |
| Loud Technologies Inc. | Onyx Blackbird | 0x000ff2/0x000007 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L33-L39) |
| Presonus | Firestudio 26x26 | 0x000a92/0x00000008 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L125-L132) |
| Presonus | Firestudio Project | 0x000a92/0x0000000b | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L133-L140) |
| Presonus | Firestudio Tube | 0x000a92/0x0000000c | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L141-L148) |
| PreSonus | Firestudio Mobile | 0x000a92/0x00000011 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L149-L156) |
| PreSonus | STUDIOLIVE_2442 | 0x00000A92/0x00000012 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L157-L163) |
| PreSonus | STUDIOLIVE_1602 | 0x00000A92/0x00000013 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L164-L170) |
| PreSonus | STUDIOLIVE_3242_mk2 | 0x00000a92/0x00000014 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L171-L177) |
| M-Audio | ProFire 2626 | 0x000d6c/0x00000010 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L333-L340) |
| M-Audio | ProFire 610 | 0x000d6c/0x00000011 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L341-L348) |
| TCAT | DiceII EVM (1) | 0x000166/0x0001 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L540-L546) |
| TCAT | DiceII EVM (2) | 0x000166/0x0002 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L547-L553) |
| TCAT | DiceII EVM (4) | 0x000166/0x0004 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L554-L560) |
| TC Electronic | Konnekt 24D | 0x000166/0x00000020 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L561-L567) |
| TC Electronic | Konnekt 8 | 0x000166/0x00000021 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L568-L574) |
| TC Electronic | Studio Konnekt 48 | 0x000166/0x00000022 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L575-L581) |
| TC Electronic | Konnekt Live | 0x000166/0x00000023 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L582-L588) |
| TC Electronic | Desktop Konnekt 6 | 0x000166/0x00000024 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L589-L595) |
| TC Electronic | ImpactTwin | 0x000166/0x00000027 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L596-L602) |
| Alesis | io|14 | 0x000595/0x00000001 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L603-L609) |
| Alesis | MultiMix-12 / MultiMix-16 Firewire | 0x000595/0x00000000 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L610-L618) |
| PreSonus | STUDIOLIVE_1642 | 0x000a92/0x00000010 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L619-L626) |
| Focusrite | Saffire PRO 40 | 0x00130e/0x00000005 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L627-L634) |
| Focusrite | Saffire PRO 24 | 0x00130e/0x00000007 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L635-L642) |
| Focusrite | Saffire PRO 24 DSP | 0x00130e/0x00000008 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L643-L650) |
| Focusrite | Saffire PRO 14 | 0x00130e/0x00000009 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L651-L658) |
| Focusrite | Saffire PRO 26 | 0x00130e/0x00000012 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L659-L666) |
| Focusrite | Saffire PRO 40-1 | 0x00130e/0x000000DE | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L667-L676) |
| Focusrite | Saffire PRO 40-1 | 0x00130e/0x00000013 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L677-L687) |
| Weiss Engineering Ltd. | ADC 2 | 0x001C6A/0x00000001 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L688-L694) |
| Weiss Engineering Ltd. | Vesta | 0x001C6A/0x00000002 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L695-L701) |
| Weiss Engineering Ltd. | Minerva | 0x001C6A/0x00000003 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L702-L708) |
| Weiss Engineering Ltd. | AFI 1 | 0x001C6A/0x00000004 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L709-L715) |
| Weiss Engineering Ltd. | TAG DAC1 | 0x001C6A/0x00000005 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L716-L722) |
| Weiss Engineering Ltd. | INT 202 | 0x001C6A/0x00000006 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L723-L729) |
| Weiss Engineering Ltd. | DAC 202 | 0x001C6A/0x00000007 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L730-L736) |
| FlexRadio_Systems | Flex-5000 | 0x001c2d/0x00000001 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L737-L744) |
| DnR | Axum_FireWire_IO_card_16x16 | 0x00000F64/0x00000003 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L770-L776) |
| Lexicon | I-ONIX_FW810S | 0x00000FD7/0x00000001 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L777-L784) |
| Allen and Heath | Zed R16 | 0x000004C4/0x00000000 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L810-L817) |
| Midas | Venice F32 | 0x0010C73F/0x00000001 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L818-L825) |

Note: the "Saffire PRO 26" above (DICE, ROM 0x130e/0x12) is a different product
from the "Saffire PRO 26 I/O" (BeBoB, see [bebob.md](bebob.md)). Do not merge their
profiles or channel counts. The PRO 40 also exists in a TCD3070-based variant
with a different, fixed layout (see below).

## Primary implementation references

- [sound/firewire/dice/dice-stream.c:1–699](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/dice/dice-stream.c#L1-L699)
- [sound/firewire/dice/dice.c:1–501](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/dice/dice.c#L1-L501)
- [libffado/src/dice/dice_avdevice.cpp:1–2073](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/src/dice/dice_avdevice.cpp#L1-L2073)

### Sequence and layout audit anchors

- [dice/dice-stream.c:382–490](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/dice/dice-stream.c#L382-L490)
- [dice/dice-transaction.c:1–160](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/dice/dice-transaction.c#L1-L160)
- [dice/dice-focusrite.c:8–25](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/dice/dice-focusrite.c#L8-L25)

### Known fixed-layout exception

The TCD3070 Saffire PRO40 variant has 20/20 PCM at single rate and 16/16 at
double rate, plus MIDI; it lacks the TCAT format extension. This does not
establish the layout of older TCD2220 firmware. Use dice-focusrite.c:8–25,
not the product name, to select this profile.
