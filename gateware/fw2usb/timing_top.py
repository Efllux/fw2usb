"""Timing-closure top level for the complete raw bridge on ECP5.

This is not a board image. It gives the full design (LUNA ULPI device, CDC
FIFOs, raw worker, link layer and PHY-LINK) real pads and the two real clocks
so place-and-route can be held to 49.152 MHz (SCLK) and 60 MHz (ULPI clock).
Pin locations are left to the placer because the PHY interposer does not exist
yet; see gateware/README.md for what that leaves unconstrained.

The PHY-LINK pads are explicit ECP5 ``BB`` buffers so that the per-pin input,
output and tristate flip-flops inside PhyLink can be packed into the I/O cells.
"""
from amaranth import ClockDomain, ClockSignal, Elaboratable, Instance, Module, ResetSignal, Signal
from amaranth.hdl import IOPort
from amaranth.lib.cdc import FFSynchronizer, ResetSynchronizer
from fw2usb.usb_bridge import RawUsbBridge

CLOCKS_MHZ = {'sclk': 49.152, 'usb_clk': 60.0}


class TimingTop(Elaboratable):
    def __init__(self):
        self.bridge = RawUsbBridge()
        self.sclk = Signal()
        self.usb_clk = Signal()
        self.rst = Signal()
        self.phy_ctl = IOPort(2, name='phy_ctl')
        self.phy_data = IOPort(8, name='phy_data')
        self.phy_lreq = Signal()
        self.phy_enable = Signal()
        self.epoch_reset = Signal()
        self.cycle_master_enable = Signal()
        self.ulpi_data = IOPort(8, name='ulpi_data')
        self.ulpi_dir = Signal()
        self.ulpi_nxt = Signal()
        self.ulpi_stp = Signal()
        self.ulpi_rst = Signal()

    def ports(self):
        return [self.sclk, self.usb_clk, self.rst, self.phy_lreq, self.phy_enable,
                self.epoch_reset, self.cycle_master_enable, self.ulpi_dir, self.ulpi_nxt,
                self.ulpi_stp, self.ulpi_rst]

    def elaborate(self, platform):
        m = Module()
        m.domains.sync = ClockDomain()
        m.domains.usb_reset = ClockDomain()
        m.d.comb += [ClockSignal('sync').eq(self.sclk), ClockSignal('usb_reset').eq(self.usb_clk)]
        m.submodules.sync_reset = ResetSynchronizer(self.rst, domain='sync')
        m.submodules.usb_reset = ResetSynchronizer(self.rst, domain='usb_reset')
        m.submodules.bridge = bridge = self.bridge
        m.d.comb += [bridge.usb.clock.eq(self.usb_clk), bridge.usb.reset.eq(ResetSignal('usb_reset'))]

        phy = bridge.worker.link.phy
        ctl_in = Signal(2)
        data_in = Signal(8)
        for i in range(2):
            m.submodules[f'phy_ctl{i}'] = Instance(
                'BB', i_I=phy.ctl_out[i], i_T=phy.ctl_t[i], o_O=ctl_in[i], io_B=self.phy_ctl[i])
        for i in range(8):
            m.submodules[f'phy_data{i}'] = Instance(
                'BB', i_I=phy.data_out[i], i_T=phy.data_t[i], o_O=data_in[i], io_B=self.phy_data[i])
        m.d.comb += [phy.ctl_in.eq(ctl_in), phy.data_in.eq(data_in), self.phy_lreq.eq(phy.lreq)]
        # Slow board-control inputs: synchronized, never timing critical.
        m.submodules.enable_sync = FFSynchronizer(self.phy_enable, phy.enable, init=1)
        m.submodules.epoch_sync = FFSynchronizer(self.epoch_reset, bridge.worker.epoch_reset)
        m.submodules.master_sync = FFSynchronizer(self.cycle_master_enable,
                                                  bridge.worker.cycle_master_enable)

        ulpi = bridge.usb.ulpi
        ulpi_in = Signal(8)
        for i in range(8):
            m.submodules[f'ulpi_data{i}'] = Instance(
                'BB', i_I=ulpi.data.o[i], i_T=~ulpi.data.oe, o_O=ulpi_in[i], io_B=self.ulpi_data[i])
        m.d.comb += [ulpi.data.i.eq(ulpi_in), ulpi.dir.i.eq(self.ulpi_dir),
                     ulpi.nxt.i.eq(self.ulpi_nxt), self.ulpi_stp.eq(ulpi.stp.o),
                     self.ulpi_rst.eq(ulpi.rst.o)]
        return m
