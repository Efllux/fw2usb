# Raw tunnel v0 (development implementation and remaining draft surface)

Distinct PID, vendor interface only plus DFU runtime. Reuse control framing with
magic FW2R on HS bulk OUT 0x01 / IN 0x81. EP0 GET_CAPS negotiates max outstanding
transactions, maximum payload, ring capacity, supported PHY speeds and ISO modes.
All integers little endian. USB endpoint numbers are proposed, discovered from
descriptors. No USB transport retry may replay a FireWire write automatically.

Async SUBMIT 0x0100 payload: destination node u16, tcode u8, speed u8, 48-bit
CSR offset stored in u64 (upper bits zero), extended lock code u16, reserved u16,
data length u32, timeout-us u32, followed by wire-order data bytes. Request ID
is the correlation cookie. Adapter assigns transaction labels, builds headers
and CRCs, performs protocol ack/retry handling within bounded timeout, and returns
COMPLETE 0x0101 with ack u8, rcode u8, flags u16, response length u32,
completion timestamp u64 and data. Transport status is separate from bus rcode.
Cancellation 0x0102 may race completion: exactly one terminal event per cookie;
CANCELLED does not prove a posted write never reached the device.

Every submission contains the current bus generation in the outer header. On
reset abort outstanding requests as STALE_GENERATION, retire label mappings,
invalidate node IDs and ISO reservations, increment generation, then emit RESET
and SELF_ID_COMPLETE before accepting new traffic. SELF_ID_COMPLETE carries raw
big-endian self-ID quadlets, validated/inverse-checked by adapter, local node ID,
root ID and generation. Also expose incoming async requests with request cookies;
host replies have deadlines, and adapter reports missed deadlines. FCP response
registration/address windows must be explicitly leased with bounded lengths.

ISO_CREATE 0x0200 specifies direction (adapter RX/TX), channel, speed, maximum
packet size, desired latency/ring depth and policy; adapter returns handle and
actual resource allocation. ISO_DESTROY releases it. Default transport is bulk
multiplexed ISO_DATA 0x0201, with optional dedicated isochronous endpoints only
after descriptor/bandwidth design is validated. Each record: handle u32,
generation u32, sequence u32, cycle timer u32, monotonic ticks u64, data length
u32, channel u8, tag u8, sy u8, flags u8, then exact FireWire data-field bytes.
CRC/header validity flags accompany RX; wire CRCs are not in the data field.
Custom families and DV remain opaque. TX timestamp is a deadline/target cycle;
late packets are discarded with an event, never silently moved to another cycle.

The 1394 cycle timer is the native seconds/cycle/offset register. Monotonic ticks
are extended 24.576 MHz adapter ticks, correlated to each bus generation and USB
SOF by CLOCK_SNAPSHOT; never infer absolute wall clock from wrapped cycle time.
ISO queues are credit-based in bytes and packets, with explicit CREDIT and LOSS
records. A gap in sequence, reset, overflow or underrun is observable. Packet
records may span bulk transfers. Max framing 65536 bytes; aggregate only within
negotiated latency. Host scheduling cannot meet 125-us cycle timing reliably;
FPGA schedules queued TX locally and sends cycle-start independently.

Measure Mac libusb round-trip latency, queue depth and jitter before freezing
credits or FFADO period sizes. USB2 cannot carry every S400/S800 workload.
Admission sums both directions, endpoint overhead and measured sustainable bulk
throughput; reject excess instead of dropping secretly. Bus resets, removal,
app death, out-of-order completion and exhausted credits are mandatory tests.

## Executable v0 refinements

Host framing and RTL encoder/decoder now implement the24-byte FW2R header. The
bounded hardware decoder halts on invalid magic/version/kind/cookie/length and
requires an interface/session reset. USB short packets never delimit records.
Opcode0003 returns bus-info (`local u16, root u16, nodes u16, flags u16`, LE);
0004 returns raw big-endian self-ID/inverse pairs. ISO_CREATE's initial bounded
fixture request is direction/channel/speed/reserved bytes, max packet u32 and
ring packets u32; its response starts with handle u32. ISO_DESTROY payload is
handle u32. ISO_DATA flag bit0 means valid header, bit1 valid data CRC; a host must
reject missing validity flags, sequence gaps and mismatched generations.

Live transport streams and synthetic transcript replay share the Rust parser.
The standalone LUNA transport currently advertises capability0 until the full
bridge worker is attached. No physical USB transfer or device support claim follows
from byte-stream co-simulation. Credit negotiation and fully attached live command
handling remain tracked implementation work.

Native bridge checkpoint: single outstanding async request, maximum256-byte data;
quadlet/block reads/writes and compare-swap supported. ISO_CREATE RX only returns
`handle u32, max_payload u32, ring_packets u32` with at most4096-byte payload/ring1.
Handles advance on each lease. ISO_DESTROY requires the current live handle.
Generation0 is discovery-only for bus-info; other operations require the current
generation. Session reset discards framing state and leases; native reset reports
RESET without splitting a USB record. Explicit CREDIT, raw TX and incoming async
leases are still unimplemented and must not be inferred from capability7.


### Explicit RX credits

Native ISO_CREATE returns four LE u32 values: handle, actual maximum payload,
retained-ring packets(1), flags(bit0=credit admission required). Credits start at0.
0204 CREDIT request payload is handle u32, additional packets u32, additional
USB-record bytes u32. Both increments must be positive; totals cannot exceed32
packets/8192 bytes. Empty success response acknowledges the grant. Each CRC-valid
selected-channel packet consumes1 packet and56+payload bytes before replay.
Oversized/no-credit packet candidates generate LOSS rather than partial records.
Reset/destroy/new lease discards credits. Capability bit3 advertises this behavior;
bits0–2 retain the initial development command/RX subset. Returned ring1 describes
retained PHY packet RAM, not the output FIFO/host-credit budget. Raw TX remains
unsupported. Older short ISO_CREATE responses are accepted by host replay without
credit mode; no missing CREDIT transaction is synthesized by the replay backend.

Capture arms on the first successful credit grant. Packets before that start boundary
are outside the lease observation window. Once armed, credit exhaustion remains
observable as LOSS until destroy/reset; it never silently disarms the capture.
