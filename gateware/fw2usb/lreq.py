"""Isolation-free LREQ serializer, TI SLLS424G Fig 16/Tables 12–18.

All fields numeric in wire order (MSB first); outputs change after SCLK rising
edges and are sampled by the PHY on the following rising edge. No arbitration
scheduler is implied: the caller must obey pending-request/idle restrictions.

LREQ is driven straight from a flip-flop (intended for the I/O cell). The start
bit still appears in the cycle after the request is accepted.
"""
from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


class LreqSerializer(Elaboratable):
    def __init__(self):
        self.valid = Signal()
        self.ready = Signal()
        self.kind = Signal(3)
        self.speed = Signal(3)
        self.address = Signal(4)
        self.data = Signal(8)
        self.accel = Signal()
        self.lreq = Signal(attrs={'syn_useioff': 1, 'ioff_dir': 'output'})

    def elaborate(self, platform):
        m = Module()
        frame = Signal(17)
        remaining = Signal(range(18))
        # Align start at bit 16. Include explicit stop even for bus speeds
        # whose final zero could double as the stop bit (Table 14).
        m.d.comb += self.ready.eq((remaining == 0) & (self.kind != 7))
        # self.lreq always equals the bit that frame[16] will hold next cycle.
        with m.If(remaining != 0):
            m.d.sync += [frame.eq(frame << 1), remaining.eq(remaining - 1),
                         self.lreq.eq(frame[15] & (remaining != 1))]
        with m.Elif(self.valid & self.ready):
            m.d.sync += self.lreq.eq(1)  # every request type starts with a one
            with m.Switch(self.kind):
                for kind in range(4):
                    with m.Case(kind):
                        m.d.sync += [frame.eq(Cat(Const(0, 10), self.speed,
                                                 self.kind, Const(1, 1))),
                                     remaining.eq(8)]
                with m.Case(4):
                    m.d.sync += [frame.eq(Cat(Const(0, 9), self.address,
                                             self.kind, Const(1, 1))), remaining.eq(9)]
                with m.Case(5):
                    m.d.sync += [frame.eq(Cat(Const(0, 1), self.data, self.address,
                                             self.kind, Const(1, 1))), remaining.eq(17)]
                with m.Case(6):
                    m.d.sync += [frame.eq(Cat(Const(0, 12), self.accel,
                                             self.kind, Const(1, 1))), remaining.eq(6)]
        return m
