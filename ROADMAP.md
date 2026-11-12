# Roadmap

Milestones are deliberately small so several people can work in parallel. Details in
[docs/DESIGN.md](docs/DESIGN.md).

## M0: Foundations ✅ partly done
- [x] `fw-amdtp`: CIP/AM824 packets, cycle time, SYT scheduler, builder/parser
- [ ] `fw-1394`: no_std async packet formats (tcodes, read/write/lock, headers, **CRC-32 with spec test vectors**)
- [ ] Config ROM parser (bus info block, root directory, unit directories)
- [x] CI cross-builds `no_std` crates for `thumbv7em-none-eabihf`
- [ ] Collect real captures from Saffire PRO 10/26/24/40 into `captures/` (needs volunteers with old FireWire machines)

## M1: Talk to the bus (FPGA + PHY dev setup)
- [ ] Pick reference dev hardware: FPGA board + PHY breakout (TSB41AB2 or TSB41BA3F) and publish a wiring guide
- [ ] Gateware: PHY-LINK interface (register read/write, LREQ, status, receive/transmit)
- [ ] Bus reset + self-ID decode, dumped over UART
- [ ] Read a device's config ROM (async quadlet read)

## M2: Be the root
- [ ] Cycle master (cycle-start every 125 µs)
- [ ] IRM CSRs (BANDWIDTH_AVAILABLE / CHANNELS_AVAILABLE, lock compare-swap)
- [ ] CMP: connect oPCR/iPCR, receive an isochronous stream, dump PCM to UART/file

## M3: Raw-link USB
- [ ] ULPI USB 2.0 HS device in gateware (or MCU companion)
- [ ] Vendor-class protocol for async + iso tunnelling (spec in `docs/`)
- [ ] `host/fw2usb-cli` (Rust, libusb): bus info, ROM dump, record WAV from a Saffire

## M4: Class-compliant audio
- [ ] UAC2 asynchronous device with feedback endpoint
- [ ] Clock recovery from device SYT → MCLK/feedback
- [ ] Full-duplex 8×8 @ 48 kHz without dropouts for 1 hour
- [ ] Device profiles (BeBoB first, then DICE)

## M5: The dongle
- [ ] KiCad PCB: PHY + FPGA + ULPI + FW400/FW800 ports, USB-C
- [ ] Optional bus power (12 V boost) for bus-powered devices
- [ ] Small batch, testers, assembly guide

## Research track: soft PHY (no PHY chip)
See [docs/SOFT-PHY.md](docs/SOFT-PHY.md). Runs in parallel; the chip-PHY path stays the fallback.
- [x] `fw-phy-model`: DS line code, arbitration line resolution, self-ID packet #0
- [ ] Transcribe arbitration signal tables + PHY state machines (reset, tree-ID, self-ID) from the spec
- [ ] SPICE the analog front-end (driver, window comparators, TPBIAS, connect detect)
- [ ] Passive bring-up: see a Saffire's bus reset/self-ID through the AFE
- [ ] Active: send our self-ID, become root at S100

## Later
- SBP-2 disks over raw-link (host-side), DV capture, MOTU/RME/Apogee profiles, Windows/Linux host support.
