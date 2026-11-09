# Gateware development

Milestone E: Amaranth 0.5.8, Python 3.13, Yosys + nextpnr-ecp5 + Trellis
(ecppack). Amaranth aligns with LUNA and provides fast native simulation; plain
Verilog remains an export/interoperability option. No USB stack is integrated yet.
The lock file pins Python tools, CI pins OSS CAD Suite 2026-11-09.

Reference target: ULX3S v2/v3, LFE5U-85F-6BG381C. The 85K part gives resource
headroom while link/USB FIFO needs are measured; fitting this smoke circuit does
not establish that the bridge fits. No Linux or CPU is instantiated.

```
python3.13 -m venv .venv
.venv/bin/pip install -r gateware/requirements.lock
PYTHONPATH=gateware .venv/bin/python -m unittest discover -s gateware/tests -v
.venv/bin/python gateware/build.py          # native Yosys on PATH
.venv/bin/python gateware/build.py --route  # also nextpnr-ecp5 and ecppack
```

Use the [OSS CAD Suite](https://github.com/YosysHQ/oss-cad-suite-build) for the
native executables (the Python builtin Yosys package alone does not supply the
ECP5 technology libraries). CI simulates, synthesizes, routes at 25 MHz and packs
a safe heartbeat, retaining artifacts. The smoke image uses only onboard 25 MHz
G2, LED0 B2 and active-high FIRE1/reset R1. It does not drive PHY header pins.
Programming a board is deliberately a separate manual step. No hardware tested.

## Provisional expansion wiring

Net labels below refer to GP/GN silkscreen, **not connector position numbers**:
header orientation swaps odd/even positions. Common 3.3-V digital IO and common
ground assumed. Confirm actual board revision, PHY supply/strap configuration,
power sequencing and voltage compatibility before connection [verify]. Use a
short purpose-built PCB/interposer; long jumper wires are unsuitable for timing
validation. Use separate externally powered FireWire devices; cable VP unconnected.

| Function | ULX3S net(s), in ascending signal index |
|---|---|
| 1394 SCLK input (49.152 MHz) | GP0 (B11, PCLK) |
| 1394 D[0:7] bidirectional | GN0, GP1, GN1, GP2, GN2, GP3, GN3, GP4 |
| 1394 CTL[0:1] bidirectional | GN4, GP5 |
| 1394 LREQ output / LPS output / LinkOn input | GN5 / GP6 / GN6 |
| PHY reset output, active low | GP7 |
| ULPI CLK input (60 MHz) | GN17 (L17, PCLK) |
| ULPI DATA[0:7] bidirectional | GP18, GN18, GP19, GN19, GP20, GN20, GP21, GN21 |
| ULPI DIR input / NXT input / STP output | GP22 / GN22 / GP23 |
| USB PHY reset output, active low | GN23 |

Reserve these nets; they are not implemented IO resources yet. Avoid GP/GN9–13
(shared ESP32 pins). GN17 is also an ADC input: disconnect/disable conflicting
analog circuitry [verify schematic loading]. SCLK and ULPI are independent clock
domains; use async FIFOs for packets and explicit synchronized control/reset
handshakes. Never sample their buses through individual two-flop synchronizers.
Reset must flush both sides of a FIFO with a coordinated epoch before traffic
resumes. Exact IO delays, clock routing, setup/hold, PCB skew and turnaround
constraints await the selected PHY and interposer; this smoke build establishes
none of them. LPS/LinkOn startup and isolation-free PHY straps belong to F.

Primary references:
- [Amaranth installation](https://amaranth-lang.org/docs/amaranth/v0.5.8/install.html)
- [ULX3S constraints snapshot](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/doc/constraints/ulx3s_v20.lpf)
- [ULX3S manual](https://github.com/emard/ulx3s/blob/6a92cec6b177191c5b0f80e260013a1f8ec147dd/doc/MANUAL.md)
- [nextpnr ECP5 flow](https://github.com/YosysHQ/nextpnr#nextpnr-ecp5)

Next: F, a datasheet-timed PHY-LINK core and behavioral PHY model; then packet
CRC/link operations. E does not yet claim packet reception, USB enumeration or
physical timing closure of either external interface.
