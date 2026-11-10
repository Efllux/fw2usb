# fw2usb host and CLI

`cargo run -p fw2usb-cli -- list` enumerates development adapters with nusb.
Endpoints and interface numbers are descriptor-discovered. Prototype VID/PIDs
1209:0001/0002 are test identifiers, not a production allocation. The raw CLI
claims only the raw vendor protocol interface; it does not detach a UAC driver.

Commands: `bus-info`, `self-id`, `config-rom NODE [FILE]`, `read NODE ADDR`,
`write NODE ADDR VALUE`, `record CHANNEL FILE.wav RATE CHANNELS [PACKETS]`.
Options before command: `--serial SERIAL`, `--generation N`, `--replay FILE`.
The default record bound is8000 ISO packets. Output is PCM24 little-endian WAV;
no SRC. Stop destroys the ISO handle. CRC/shape, source rate, sequence, DBC and
bus-generation errors fail; invalid recordings are not published as new WAVs.

No-hardware reproduction:

```
PYTHONPATH=gateware .venv/bin/python gateware/sim/cosim.py --cycles 64
cargo run -p fw2usb-cli -- --replay gateware/build/cosim/bebob.fw2r bus-info
cargo run -p fw2usb-cli -- --replay gateware/build/cosim/bebob.fw2r self-id
```

The script also executes ROM dump and recording for BeBoB and DICE fixtures,
compares every output PCM byte, and rejects corrupted sequence/generation
transcripts. `report.json`, `.rom`, `.fw2r` and `.wav` artifacts are under the
output directory. These are synthetic **simulation transcripts**, not captures.
Replay exchanges require an exact recorded request payload/generation and cannot
invent or automatically replay a write. Each recorded cookie is used once/session.

The live nusb backend and LUNA HS core are implemented, but the current standalone
USB core advertises capability0: it is a transport without the complete bridge
command worker attached (the integrated RawUsbBridge now has native commands and
credit-based RX; the standalone transport intentionally has no command service). Physical enumeration, throughput and board IO constraints
remain unvalidated. The co-sim USB boundary is bulk bytes, not electrical USB tokens.
Do not infer a working physical adapter from the replay result.

Credit-mode leases prefill32 packets/8192 record bytes and return credits in bounded
batches after consumption. Recording aborts on reset/loss and destroys its lease;
no FireWire write is automatically retried after a transport error.
