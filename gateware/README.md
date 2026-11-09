# gateware

FPGA design: IEEE 1394a PHY-LINK interface, link layer (packet TX/RX, CRC, cycle timer,
cycle master), isochronous FIFOs, async engine, and later USB 2.0 HS (ULPI).

Not started. See ROADMAP M1–M3. Preferred toolchain: open source (yosys / nextpnr) targeting
ECP5 or iCE40, so anyone can build without vendor licences. HDL choice (Verilog, Amaranth,
SpinalHDL) is open for discussion. Prior art worth studying: the JHU dVRK FPGA1394 board
([mechatronics-firmware](https://github.com/jhu-cisst/mechatronics-firmware)), which implements
a 1394 link layer in an FPGA next to a TI PHY.
