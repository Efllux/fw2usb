# Companion protocol v0 (draft, not implemented)

USB vendor interface class 0xff/subclass 0x02/protocol 0x00 in the audio
configuration, present regardless of whether the app is connected. Interface and
endpoint numbers are descriptor-discovered. Proposed HS bulk OUT 0x01, bulk IN
0x81, interrupt IN 0x82 (16-byte payload, bInterval 4). UAC2 endpoints use other
addresses. EP0 vendor GET_CAPS (bRequest 0x01, IN, recipient interface) returns
protocol major/minor u16, max frame u32, capability mask u64, all little endian.
Unsupported versions stall; supported bulk framing is negotiated before writes.

Bulk byte stream frames have a 24-byte little-endian header:
magic `FW2C` (4), major u8, kind u8 (0=request,1=response,2=event), opcode u16,
request ID u32, payload length u32, status u32, generation u32. Length excludes
header, maximum 65536 bytes including header. Short USB packets are not frame
boundaries; accumulate header then exact length. Reject bad magic/oversize by
halting session until USB interface reset. IDs nonzero, unique until response;
events ID=0. A response echoes opcode/ID. No unsolicited success before completion.

Opcodes: 0x0001 capabilities; 0x0002 device/profile/clock status; 0x0010 read
controls; 0x0011 atomic control batch; 0x0012 set clock/rate; 0x0020 profile
stage; 0x0021 validate/activate profile; 0x0030 prepare DFU; 0x0040 set persistent
personality (0=audio,1=raw). Unknown opcode returns UNSUPPORTED. Status:
0 OK,1 INVALID,2 UNSUPPORTED,3 BUSY,4 STALE_GENERATION,5 NO_DEVICE,6 IO,
7 UNAUTHORIZED_IMAGE,8 CLOCK_UNLOCKED. Payloads are u16 type/u16 length TLVs,
4-byte padded with zeros. Unknown optional TLVs skipped, mandatory bit 15 rejects.
Publish an opcode-specific TLV registry before implementation freezes v1.

Control IDs and value domains come from the signed profile, never arbitrary
host-supplied device register addresses. Batch validation is all-or-nothing;
partial hardware failure reports which writes completed, re-reads state, and
never claims rollback unless supported. Generation changes on bus reset/device
replacement; stale writes fail. Interrupt records are 16 bytes: event type u16,
flags u16, generation u32, monotonic event sequence u32, detail u32. Bulk status
reconciles missed/overflowed events. App disconnect never stops ordinary audio.

Personality switch requires an explicit command, returns ACCEPTED/OK before USB
disconnect, and atomically journals the preference before re-enumeration. Discover
the new PID using stable adapter serial, not port order. Failures fall back to
last committed setting; hardware button overrides to tier 1. Commands requiring
stream teardown return BUSY unless the request contains an explicit stop consent
TLV. DFU uses the standard DFU state machine, not bulk flash-write commands.
