"""Safe, standalone board toolchain check; does not drive either external PHY."""
from amaranth import Elaboratable, Module, Signal


class Heartbeat(Elaboratable):
    def __init__(self, bits=25):
        if bits < 1:
            raise ValueError("counter must have at least one bit")
        self.counter = Signal(bits)
        self.led = Signal()

    def elaborate(self, platform):
        m = Module()
        m.d.sync += self.counter.eq(self.counter + 1)
        m.d.comb += self.led.eq(self.counter[-1])
        return m
