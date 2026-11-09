# FireWire device-family research index

No listed model is verified on fw2usb hardware. This catalog records source
matches and implementation behavior, not a compatibility promise. All missing
per-rate counts/firmware/clock observations are [verify]. No GPL code, vendor
binary or NDA material is incorporated; prose summarizes public implementations.

| Family | Linux | Codec / control |
|---|---|---|
| [BeBoB](bebob.md) | snd-bebob | AM824, AV/C/CMP + vendor |
| [DICE/TCAT](dice.md) | snd-dice | AM824 multi-stream, DICE registers |
| [Oxford FW970/971](oxfw.md) | snd-oxfw | AM824, AV/C/CMP |
| [Echo Fireworks](fireworks.md) | snd-fireworks | AM824 quirks, EFW/CMP |
| [MOTU](motu.md) | snd-motu | packed chunks/SPH, vendor DSP |
| [RME Fireface](fireface.md) | snd-ff | no CIP, vendor + async MIDI |
| [Digi002/003](digi00x.md) | snd-digi00x | DOT transform, vendor |
| [TASCAM](tascam.md) | snd-firewire-tascam | counter/status blocks, vendor |
| [Generic AV/C](avc.md) | device-dependent | discover formats; no universal codec |

[models.csv](models.csv) preserves every device registration in the inspected
FFADO configuration, including families outside this first nine-family survey,
plus explicit Linux-model additions. Duplicate names with different IDs are
intentional. Family pages link match-table line ranges and stream implementations.

Snapshot: Linux 7475ea8b58616b33c04afb976cf0fbaad9dd63fb;
FFADO 4b7f9e86e59ce95f5c60d5eb3070bc75a3dfdd3f (adiknoth mirror).
Registry coverage is finite: generic matches do not enumerate all products,
rebrands, firmware revisions or unsupported devices. Model count does not prove
complete worldwide coverage. Next research must fill per-rate channel layouts
from capability queries and manuals, and derive register-level, captured-vector
profiles for each firmware revision. The family start descriptions identify
ordering/quirks, not complete executable register scripts.

Shared rules: read config ROM and identify units after every reset; use generation
checks; allocate/release IRM resources; keep device clock master where supported;
report external clock unlock. SYT alone cannot serve all custom protocols and
several devices ignore incoming SYT in favor of event-count cadence. Preserve
packet-count/timestamp replay rules without SRC. Reject streams that exceed
FireWire peak or measured USB2 capacity. See PR #14 for cross-family airtime.

Optional Rust packet crates are deferred until normative/capture vectors can
validate CRC, ROM bounds and FCP/CMP semantics independently of encode/decode
round trips. No new crate is necessary to publish this research catalog.
