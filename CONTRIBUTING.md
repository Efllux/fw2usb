# Contributing to fw2usb

Thanks for helping bring FireWire back. 🔥

## Ground rules
- Be kind and assume good faith. We follow the
  [Contributor Covenant](CODE_OF_CONDUCT.md).
- **Never paste vendor firmware, driver binaries or NDA documents** into the repo. Write
  clean-room descriptions of behaviour instead (what goes on the bus, what it means). Public
  datasheets, standards references and open-source code (with compatible licences) are fine
  to cite.
- Claims about hardware need evidence: a capture, a log or a photo. "Works on my Saffire PRO 26
  at 48 kHz, capture attached" beats "should work".

## Ways to contribute

### 1. Report a device (no coding needed)
Open a **Device report** issue with the exact model, chipset (BeBoB / DICE / Oxford / other)
if known, and what you can test. If you still have a machine with working FireWire
(old Mac, Linux box), traffic captures are gold:
- Linux: `firewire-ohci` + `nosy` (needs a PCILynx-based FireWire card) or `wireshark` with the `firewire` dissector
- Kernel logs of `snd-bebob` / `snd-dice` / `snd-firewire-*` when the device is attached
- Config ROM dump: `/sys/bus/firewire/devices/fw*/config_rom`

### 2. Code
- Rust: `cargo fmt`, `cargo clippy -- -D warnings`, `cargo test` must pass.
- `crates/*` used by firmware stay `no_std` and allocation-free.
- Every protocol detail gets a unit test with a reference (spec section, FFADO/ALSA source
  line, or a capture in `captures/`; this directory will be created when the first capture is contributed).
- Gateware: include a testbench; simulate against `fw-amdtp` vectors where possible.

### 3. Hardware
KiCad only, so everyone can open the files. Put new boards under `hardware/<board-name>/` with a
README listing the revision, status and known errata.

## Workflow
1. Comment on (or open) an issue before large work so we don't duplicate effort.
2. Fork, branch, keep PRs focused.
3. Describe **how you tested**, and on what hardware.

## Where to talk
GitHub Discussions for design questions and show-and-tell; issues for concrete work.
