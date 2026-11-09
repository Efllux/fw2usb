"""TI SLLS424G Figs18–19/Table20 receive-only byte adapter.

Numeric bus representation: data[7] = physical D0; ctl[1] = CTL0.
No backpressure exists on PHY-LINK: downstream must consume each valid byte.
All strobes registered, sampled in PHY SYSCLK domain. No packet CRC checking.
"""
from amaranth import Cat, Elaboratable, Module, Signal


class ReceiveAdapter(Elaboratable):
    def __init__(self):
        self.ctl = Signal(2)
        self.data = Signal(8)
        self.byte = Signal(8)
        self.valid = Signal()
        self.start = Signal()
        self.end = Signal()
        self.error = Signal()
        self.speed = Signal(2)  # 0=S100, 1=S200, 2=S400

    def elaborate(self, platform):
        m = Module()
        in_rx = Signal()
        have_speed = Signal()
        discard = Signal()
        count = Signal(range(4))
        shift = Signal(8)
        m.d.sync += [self.valid.eq(0), self.start.eq(0), self.end.eq(0), self.error.eq(0)]
        with m.If(self.ctl != 2):
            m.d.sync += [in_rx.eq(0), have_speed.eq(0), discard.eq(0), count.eq(0)]
            with m.If(in_rx):
                m.d.sync += [self.end.eq(1), self.error.eq(count != 0)]
        with m.Else():
            m.d.sync += in_rx.eq(1)
            with m.If(~have_speed & ~discard):
                with m.If(~self.data[7]):  # Table20 data-on: 1YYY YYYY
                    with m.If(self.data[6:8] == 0):
                        m.d.sync += [self.speed.eq(0), have_speed.eq(1), self.start.eq(1)]
                    with m.Elif(self.data[4:8] == 4):
                        m.d.sync += [self.speed.eq(1), have_speed.eq(1), self.start.eq(1)]
                    with m.Elif(self.data == 0x50):
                        m.d.sync += [self.speed.eq(2), have_speed.eq(1), self.start.eq(1)]
                    with m.Else():
                        m.d.sync += [discard.eq(1), self.error.eq(1)]
            with m.Elif(have_speed):
                with m.Switch(self.speed):
                    with m.Case(0):
                        value = Cat(self.data[6:8], shift[:6])
                        m.d.sync += [shift.eq(value), count.eq(count + 1)]
                        with m.If(count == 3):
                            m.d.sync += [self.byte.eq(value), self.valid.eq(1)]
                    with m.Case(1):
                        value = Cat(self.data[4:8], shift[:4])
                        m.d.sync += [shift.eq(value), count.eq(count ^ 1)]
                        with m.If(count == 1):
                            m.d.sync += [self.byte.eq(value), self.valid.eq(1)]
                    with m.Case(2):
                        m.d.sync += [self.byte.eq(self.data), self.valid.eq(1)]
        return m
