"""Direct ISO=1 PHY-LINK composition; SCLK domain, numeric bit7 is D0.

Qualified PHY enable/reset comes from board startup control. Request scheduling
supports one pending bus request and one register read. RX cancellation here is
legacy (EAA disabled); accelerated NPA/ACK policy belongs to the future link
scheduler. No external pins are constrained by this protocol composition.
"""
from types import SimpleNamespace
from amaranth import Elaboratable, Module, ResetInserter, Signal
from fw2usb.lreq import LreqSerializer
from fw2usb.receive import ReceiveAdapter
from fw2usb.status import StatusReceiver
from fw2usb.transmit import TransmitAdapter


class PhyLink(Elaboratable):
    def __init__(self):
        self.enable = Signal(init=1)
        self.bus_reset = Signal()
        self.ctl_in = Signal(2)
        self.data_in = Signal(8)
        self.ctl_out = Signal(2)
        self.data_out = Signal(8)
        self.oe = Signal()
        self.lreq = Signal()
        self.request = SimpleNamespace(valid=Signal(), ready=Signal(), kind=Signal(3),
                                       speed=Signal(3), address=Signal(4),
                                       data=Signal(8), accel=Signal())
        self.rx = ReceiveAdapter()
        self.status = StatusReceiver()
        self.tx = TransmitAdapter()
        self.pending = Signal()
        self.read_pending = Signal()

    def elaborate(self, platform):
        m = Module()
        serializer = LreqSerializer()
        m.submodules.serializer = ResetInserter(~self.enable)(serializer)
        m.submodules.rx = ResetInserter(~self.enable)(self.rx)
        m.submodules.status = ResetInserter(~self.enable)(self.status)
        m.submodules.tx = ResetInserter(~self.enable | self.bus_reset)(self.tx)
        read_address = Signal(4)
        kind = Signal(3)
        speed = Signal(2)
        grant = Signal()
        phy_ctl = Signal(2)
        allowed = Signal()
        m.d.comb += [
            allowed.eq(((self.request.kind >= 4) | ~self.pending) &
                       ((self.request.kind != 4) | ~self.read_pending) &
                       ((self.request.kind >= 4) | (self.request.speed == 0) |
                        (self.request.speed == 2) | (self.request.speed == 4))),
            serializer.valid.eq(self.request.valid & allowed & self.enable),
            self.request.ready.eq(serializer.ready & allowed & self.enable),
            serializer.kind.eq(self.request.kind), serializer.speed.eq(self.request.speed),
            serializer.address.eq(self.request.address), serializer.data.eq(self.request.data),
            serializer.accel.eq(self.request.accel), self.lreq.eq(serializer.lreq & self.enable),
            grant.eq(self.enable & self.pending & ~self.tx.busy & (self.ctl_in == 3)),
            self.tx.grant.eq(grant), self.tx.speed.eq(speed),
            self.ctl_out.eq(self.tx.ctl), self.data_out.eq(self.tx.data),
            self.oe.eq(self.enable & self.tx.oe),
            phy_ctl.eq(self.ctl_in),
        ]
        # The link's own CTL=transmit is not an incoming RX operation.
        with m.If(self.tx.busy | ~self.enable):
            m.d.comb += phy_ctl.eq(0)
        m.d.comb += [self.rx.ctl.eq(phy_ctl), self.rx.data.eq(self.data_in),
                     self.status.ctl.eq(phy_ctl), self.status.pair.eq(self.data_in[6:8])]
        with m.If(~self.enable):
            m.d.sync += [self.pending.eq(0), self.read_pending.eq(0)]
        with m.Else():
            with m.If(self.request.valid & self.request.ready):
                with m.If(self.request.kind < 4):
                    m.d.sync += [self.pending.eq(1), kind.eq(self.request.kind),
                                 speed.eq(self.request.speed[1:3])]
                with m.Elif(self.request.kind == 4):
                    m.d.sync += [self.read_pending.eq(1), read_address.eq(self.request.address)]
            with m.If(grant | self.bus_reset |
                      ((phy_ctl == 2) & ((kind == 2) | (kind == 3)))):
                m.d.sync += self.pending.eq(0)
            with m.If(self.status.register_valid & (self.status.address == read_address)):
                m.d.sync += self.read_pending.eq(0)
        return m
