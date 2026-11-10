# libraw1394 ABI subset over FW2R

This independently written MIT/Apache library implements handle/port0 discovery,
userdata, node/generation getters, bus-reset callbacks, synchronous quadlet/block
read/write, compare-swap32/64, IRM contender discovery/resource CAS and single-channel
ISO receive callbacks over the existing nusb/replay transport. Read/write buffers
and lock scalar memory representation are wire-order, matching the libraw1394
contract. Block reads split at256 bytes; writes above256 bytes fail rather than
partially commit. IRM contention retries only confirmed CAS mismatches, at most8;
transport failure never triggers a write replay. Negative results set errno.

`cargo build -p fw2usb-raw1394` produces `libfw2usb_raw1394`, deliberately a
separate library name during development. Include the supported declaration subset
from `include/`; it is independently declared, not the LGPL library header.
`FW2USB_REPLAY=...` selects synthetic FW2R transcripts; `FW2USB_SERIAL` selects a
live prototype. Multiple adapters currently require serial selection; port0 is
the selected adapter. Use one handle per thread; concurrent use/destruction is
invalid. A callback may update generation/userdata but must not destroy the handle
or reenter IO. ISO callback data expires on return. Reset invalidates cached IDs,
ISO leases and sequence; the default callback updates generation. A custom callback
must call update_generation. Rebind/discover after reset before reusing node IDs.

ISO RX supports immediate start with tag=-1/sync=0, not scheduled start or filtering.
Sequence/generation/CRC validity/length are checked before callbacks; loss fails
with EOVERFLOW. STOP dispositions release the lease. Successful init does not
reserve CMP resources; caller must connect separately. This is not yet a drop-in
FFADO backend: get_fd/wake_up/reset_bus return ENOTSUP. Missing functions are not
exported or represented as success. In particular, reactor pollability, incoming
FCP/ARM windows, ISO TX and correlated cycle-clock snapshots remain unfinished.

## FFADO API audit

A symbol scan of all `libffado/src` at pinned revision below produced the following
function surface. Type names/struct fields and the local variable `raw1394_poll`
are excluded. The scan is reproducible with `rg -o 'raw1394_[A-Za-z0-9_]+'` followed
by review against the public header. No implementation code is imported.

| Group | Functions | State |
|---|---|---|
| Lifetime/discovery | new_handle, new_handle_on_port, destroy_handle, get_port_info, get_local_id, get_irm_id, get_nodecount | implemented, selected adapter/port0 |
| User/generation | get_userdata, set_userdata, get_generation, update_generation, set_bus_reset_handler | implemented |
| Async | read, write, lock64 | implemented; compare-swap only |
| IRM | bandwidth_modify, channel_modify | bounded CAS implementation |
| Receive | iso_recv_init, iso_recv_start, iso_stop, iso_shutdown, loop_iterate | implemented immediate RX subset |
| Receive flush | iso_recv_flush | missing |
| Transmit | iso_xmit_init, iso_xmit_start | missing |
| Event reactor | get_fd, wake_up | ENOTSUP; independent USB reader/notification fd needed |
| Reset | reset_bus | ENOTSUP; native command missing |
| FCP | set_fcp_handler, start_fcp_listen, stop_fcp_listen | missing; bounded remote-write lease needed |
| ARM | arm_register, arm_unregister, arm_request_response, set_arm_tag_handler | missing |
| Clock | read_cycle_timer, read_cycle_timer_and_clock | missing; CLOCK_SNAPSHOT correlation needed |
| Local ROM | get_config_rom, update_config_rom | missing |

Each function name in the table is prefixed `raw1394_`. ABI callback/enum types
are tracked by the supported subset header. Remaining symbols require explicit
ABI/API implementation before an FFADO binary can link and stream. FFADO startup
and duplex streaming have not been validated. Current tests cover actual exported
C handle/error ABI plus Rust transport-based read/write/CAS/ISO/reset callbacks.

Primary API facts: [libraw1394 public header](https://kernel.googlesource.com/pub/scm/libs/ieee1394/libraw1394/+/master/src/raw1394.h),
[project documentation](https://ieee1394.docs.kernel.org/en/latest/libraw1394.html).
Pinned consumers: [FFADO service](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/src/libieee1394/ieee1394service.cpp),
[ISO manager](https://github.com/adiknoth/ffado/blob/4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f/libffado/src/libieee1394/IsoHandlerManager.cpp),
plus all other source files at that revision. LGPL/GPL source remains external;
only public ABI and protocol facts inform this original implementation.
