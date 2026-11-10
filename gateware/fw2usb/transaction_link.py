"""Local async service from PHY pins through link and bounded CSR responder."""
from amaranth import Elaboratable, Module, Signal
from fw2usb.link_layer import LinkLayer
from fw2usb.responder import TransactionResponder


class TransactionLink(Elaboratable):
    def __init__(self):
        self.link = LinkLayer()
        self.responder = TransactionResponder()

    def elaborate(self, platform):
        m = Module()
        m.submodules.link = self.link
        m.submodules.responder = self.responder
        posted = Signal();started=Signal()
        speed = Signal(2)
        m.d.comb += [self.responder.rx.start.eq(self.link.phy.rx.start & ~self.link.selfid_phase),
                     self.responder.rx.valid.eq(self.link.phy.rx.valid & ~self.link.selfid_phase),
                     self.responder.rx.byte.eq(self.link.phy.rx.byte),
                     self.responder.rx.end.eq(self.link.phy.rx.end & ~self.link.selfid_phase),
                     self.responder.rx.phy_error.eq(self.link.phy.rx.error),
                     self.responder.node_id.eq(self.link.cycle.node_id),
                     self.responder.bus_reset.eq(self.link.phy.bus_reset | ~self.link.phy.enable),
                     self.responder.csr.cycle_time.eq(self.link.cycle.timer.value),
                     self.link.request.valid.eq(self.responder.tx_valid & ~posted),
                     self.link.request.kind.eq(3),self.link.request.speed.eq(speed << 1),
                     self.link.tx_valid.eq(self.responder.tx_valid),
                     self.link.tx_byte.eq(self.responder.tx_byte),self.link.tx_last.eq(self.responder.tx_last),
                     self.responder.tx_ready.eq(self.link.tx_ready)]
        with m.If(self.link.phy.rx.start):
            m.d.sync += speed.eq(self.link.phy.rx.speed)
        with m.If(self.link.request.valid & self.link.request.ready):
            m.d.sync += posted.eq(1)
        with m.If(self.link.user_grant):m.d.sync += started.eq(1)
        with m.If(posted & ~started & self.link.request.ready):m.d.sync += [posted.eq(0),started.eq(0)]
        with m.If(self.responder.tx_valid & self.responder.tx_ready & self.responder.tx_last):
            m.d.sync += [posted.eq(0),started.eq(0)]
        with m.If(self.link.phy.bus_reset | ~self.link.phy.enable):
            m.d.sync += [posted.eq(0),started.eq(0)]
        return m
