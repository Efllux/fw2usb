# Capture provenance inventory

No real FireWire capture is included yet. Tests under gateware/tests are synthetic.
A source being publicly downloadable does not establish permission to redistribute
it, and an IP-over-1394 pcap is not a PHY-LINK or AMDTP bus trace.

Discovery pass, 2026-11-09 (not exhaustive):

| Candidate source | Content / limitation | Licence / ingestion status |
|---|---|---|
| [Wireshark SampleCaptures](https://wiki.wireshark.org/SampleCaptures), Apple_IP-over-IEEE_1394_Packet.pcap | Apple IP encapsulation sample; lacks PHY-LINK edges, reset and audio timing | Individual-file terms not established; not vendored |
| [Wireshark IEEE_1394](https://wiki.wireshark.org/IEEE_1394) | Explains capture limitations and dumpiso format distinction | Reference only; no packet fixture extracted |
| [FFADO-user Audiophile/410 thread](https://sourceforge.net/p/ffado/mailman/ffado-user/thread/5187BDB2.8030705%40sakamocchi.jp/) | Candidate textual bus dump; device/byte completeness and timing need inspection | Author/attachment rights not established; not vendored |

Next search targets: FFADO-devel/user attachments, linux1394 bug attachments,
firewire-tools logs and Linux firewire trace examples. Confirm payload coverage,
byte order, omitted CRCs/acks and timestamps before choosing replay layer.
For each accepted file record original URL, author, retrieval date, SHA-256,
explicit redistribution licence or permission, device/firmware, capture tool,
loss/truncation, timebase, expected decoded observations and regression test.
Derived fixtures must identify the transform and retain provenance. Do not label
synthetic or reconstructed packets as captured hardware data.
