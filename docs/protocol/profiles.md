# Family profile schema v0 (draft)

Signed canonical CBOR data; separately versioned from executable firmware and
bitstream. Envelope uses the update manifest described in DESIGN.md. The parser
must reject excessive arrays, recursion, sizes, timeouts, unsupported operations
and invalid address/rate/channel combinations before exposing USB descriptors.

Required fields:

| Field | Meaning |
|---|---|
| schema, id, revision, dependencies | Profile ABI and minimum interpreter/gateware versions |
| match | Vendor/model/specifier/version IDs, ROM unit directory tests and firmware-revision ranges; GUID only for overrides |
| family, codec | BeBoB/DICE/OXFW/EFW/MOTU/RME/Digi/TASCAM/AVC, packet format version and quirks |
| rates[] | Exact rates, capture/playback wire blocks, user PCM slots, MIDI slots, optical-mode layouts, padding and packet peak sizes |
| transport | CIP/FMT/FDF/SPH/DBC/SYT rules or custom header/timestamp/sample transform selector, endianness and PCM packing |
| clock | Sources, status/lock register definitions, timestamp estimator, transfer delay, loss policy and device-master capability |
| sequence | Bounded discovery, rate/clock selection, resource reservation, stream start/stop and bus-reset recovery operations |
| resources | Channel allocation rules, CMP plugs or vendor channel registers, minimum PHY speed, maximum payload, USB bandwidth estimate |
| controls | Stable IDs, names, units, min/max/enums, routing topology, atomicity and stream-safe flags |
| firmware | Whether upload is required, firmware identity/digest and redistributability metadata; no embedded vendor binary |
| validation | Source references, tested firmware, captures/vector digests, limitations and verified rates |

Sequences select compiled family handlers or bounded read/write/compare/wait
operations over allowlisted address ranges. No jumps, arbitrary native code or
unbounded polling. A model's marketing connector count is not its wire layout.
Unknown firmware or ambiguous ROM matches require app/raw mode, not guessed
register writes. Firmware upload is a distinct consented host workflow; only
user-provided legally obtained images can satisfy a profile's upload requirement.

Existing profile activation is transactional: validate signature and compatibility,
prepare descriptors, stop streams if needed, activate and self-test, then commit.
On failure retain previous profile. Profile changes cannot overwrite golden boot
or enlarge executable address permissions. Define per-family records and captured
vectors before claiming any tier-1 model works.
