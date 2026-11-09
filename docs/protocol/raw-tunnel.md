# Raw tunnel v0 (draft, not implemented)

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
