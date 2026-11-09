"""PHY status receiver, SLLS424G Fig 17/Table 19 (MSB-first lane pairs).

Use in the SYSCLK domain. pair[1] is physical D0, pair[0] physical D1.
CTL is encoded as physical CTL0*2+CTL1. Does not own bidirectional IO.
"""
from amaranth import Cat, Elaboratable, Module, Signal


class StatusReceiver(Elaboratable):
    def __init__(self):
        self.ctl = Signal(2)
        self.pair = Signal(2)
        self.flags = Signal(4)
        self.flags_valid = Signal()
        self.flags_mask = Signal(4)
        self.address = Signal(4)
        self.data = Signal(8)
        self.register_valid = Signal()

    def elaborate(self, platform):
        m = Module()
        count = Signal(range(9))
        shift = Signal(16)
        value = Cat(self.pair, shift[:14])
        m.d.sync += [self.flags_valid.eq(0), self.flags_mask.eq(0), self.register_valid.eq(0)]
        with m.If(self.ctl != 1):
            m.d.sync += count.eq(0)
        with m.Elif(count < 8):
            m.d.sync += [shift.eq(value), count.eq(count + 1)]
            # Flags become delivered pair-by-pair, even if RX interrupts
            # before the second pair. Consumers must honor flags_mask.
            with m.If(count == 0):
                m.d.sync += [self.flags[2:4].eq(self.pair), self.flags_valid.eq(1),
                             self.flags_mask.eq(0b1100)]
            with m.If(count == 1):
                m.d.sync += [self.flags[:2].eq(self.pair), self.flags_valid.eq(1),
                             self.flags_mask.eq(0b0011)]
            with m.If(count == 7):
                m.d.sync += [self.address.eq(value[8:12]), self.data.eq(value[:8]),
                             self.register_valid.eq(1)]
        return m
