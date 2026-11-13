# RME Fireface former/latter

Research, not fw2usb device support. Primary source snapshots are pinned below.

Stream: No CIP; proprietary little-endian PCM/event blocks. Control: Vendor async registers + async MIDI/status. Linux: `snd-ff`.

## Start, clock and recovery

Query source/rate, allocate resources and select former (400/800) or latter protocol; execute model begin_session channel/rate writes; add playback then capture, start domain with incoming packet-count replay and initial transmit priming; wait ready then enable fetching. Device sends nothing until it receives packets. Failure finishes session and releases resources on final stop.

No SYT can be assumed: use custom cadence/clock status estimator. Async MIDI is separate from PCM. FF800 speed flags do not prove arbitrary lower-speed operation; reference target remains S400.

Firmware upload: No routine stream-start upload; flash recovery unknown.

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
| RME | FireFace800 | 0x000a35/0x0001 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L483-L493) |
| RME | FireFace400 | 0x000a35/0x0002 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L494-L504) |
| RME | FireFace UFX | 0x000a35/0x0003 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L505-L515) |
| RME | FireFace UCX | 0x000a35/0x0004 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L516-L527) |
| RME | FireFace 802 | 0x000a35/0x0005 | ? / ? / ? | [match](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/configuration#L528-L539) |
| RME | Fireface 400 | see ROM match table | 18/18 / 14/14 / 10/10 | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff.c#L1-L266) |
| RME | Fireface 800 | see ROM match table | 28/28 / 20/20 / 12/12 | [match](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff.c#L1-L266) |

## Primary implementation references

- [sound/firewire/fireface/ff-stream.c:1–276](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff-stream.c#L1-L276)
- [sound/firewire/fireface/ff.c:1–266](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff.c#L1-L266)
- [sound/firewire/fireface/amdtp-ff.c:1–167](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/amdtp-ff.c#L1-L167)
- [libffado/src/rme/rme_avdevice.cpp:1–1186](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/src/rme/rme_avdevice.cpp#L1-L1186)

### Sequence and layout audit anchors

- [fireface/ff-stream.c:168–240](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff-stream.c#L168-L240)
- [fireface/ff.c:134–175](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff.c#L134-L175)
- [fireface/ff-protocol-former.c:373–392](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff-protocol-former.c#L373-L392)
- [fireface/ff-protocol-former.c:486–528](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff-protocol-former.c#L486-L528)
- [fireface/ff-protocol-latter.c:248–312](https://github.com/torvalds/linux/blob/7475ea8b58616b33c04afb976cf0fbaad9dd63fb/sound/firewire/fireface/ff-protocol-latter.c#L248-L312)

### Rate-mode counts and clock details

Linux ff.c:134–175 defines FF800 28/28, 20/20, 12/12; FF400
18/18, 14/14, 10/10; UCX 18/18, 14/14, 12/12; UFX/802
30/30, 22/22, 14/14 across single/double/quad rate modes.
These are wire PCM slots; connector availability can depend on digital mode.
The configuration spellings FireFace400/FireFace800 are aliases of the spaced
names above, not different models. Former and latter protocols expose clock
source and synchronization status; do not switch a locked external source to
internal solely to satisfy a requested USB rate.
