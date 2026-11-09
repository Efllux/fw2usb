"""G link primitives. CRC IEEE1394-2008 §6.2.5.15; timer §8.3.2.3.
All logic uses SCLK=49.152MHz; tick enable divides by two for 24.576MHz.
"""
from amaranth import Cat, Const, Elaboratable, Module, Mux, Signal


class Crc32(Elaboratable):
    def __init__(self):
        self.clear = Signal()
        self.valid = Signal()
        self.byte = Signal(8)
        self.value = Signal(32)
        self.raw = Signal(32, init=0xffffffff)

    def elaborate(self, platform):
        m = Module()
        stages = [Signal(32, name=f'crc_stage{i}') for i in range(9)]
        m.d.comb += [stages[0].eq(self.raw ^ (self.byte << 24)), self.value.eq(~self.raw)]
        for i in range(8):
            m.d.comb += stages[i+1].eq((stages[i] << 1) ^ Mux(stages[i][31], 0x04c11db7, 0))
        with m.If(self.clear):
            m.d.sync += self.raw.eq(0xffffffff)
        with m.Elif(self.valid):
            m.d.sync += self.raw.eq(stages[8])
        return m


class CycleTimer(Elaboratable):
    def __init__(self):
        self.load = Signal()
        self.load_value = Signal(32)
        self.value = Signal(32)
        self.root = Signal()
        self.enable = Signal()
        self.cycle_start_valid = Signal()
        self.cycle_start_ready = Signal()
        self.missed = Signal(32)

    def elaborate(self, platform):
        m = Module()
        offset = Signal(range(3072))
        cycle = Signal(range(8000))
        seconds = Signal(7)
        divider = Signal()
        m.d.comb += self.value.eq(Cat(offset, Const(0, 0), cycle, seconds))
        # offset has width12 and cycle width13: register layout 7:13:12.
        m.d.sync += divider.eq(~divider)
        with m.If(~self.enable | ~self.root):
            m.d.sync += self.cycle_start_valid.eq(0)
        with m.Elif(self.cycle_start_valid & self.cycle_start_ready):
            m.d.sync += self.cycle_start_valid.eq(0)
        with m.If(self.load):
            m.d.sync += [offset.eq(self.load_value[:12]), cycle.eq(self.load_value[12:25]),
                         seconds.eq(self.load_value[25:]), divider.eq(0)]
        with m.Elif(divider):
            with m.If(offset == 3071):
                m.d.sync += offset.eq(0)
                with m.If(cycle == 7999):
                    m.d.sync += [cycle.eq(0), seconds.eq(seconds + 1)]
                with m.Else():
                    m.d.sync += cycle.eq(cycle + 1)
                with m.If(self.root & self.enable):
                    m.d.sync += self.cycle_start_valid.eq(1)
                    with m.If(self.cycle_start_valid & ~self.cycle_start_ready):
                        m.d.sync += self.missed.eq(self.missed + 1)
            with m.Else():
                m.d.sync += offset.eq(offset + 1)
        return m


class SelfIdCapture(Elaboratable):
    def __init__(self):
        self.start = Signal()
        self.valid = Signal()
        self.byte = Signal(8)
        self.end = Signal()
        self.packet = Signal(32)
        self.accept = Signal()
        self.error = Signal()
        self.physical_id = Signal(6)
        self.ports = Signal(6)

    def elaborate(self, platform):
        m = Module()
        shift = Signal(64)
        count = Signal(range(10))
        m.d.comb += [self.physical_id.eq(self.packet[24:30]), self.ports.eq(self.packet[2:8])]
        m.d.sync += [self.accept.eq(0), self.error.eq(0)]
        with m.If(self.start):
            m.d.sync += [count.eq(0), shift.eq(0)]
        with m.Elif(self.valid):
            m.d.sync += shift.eq(Cat(self.byte, shift[:56]))
            with m.If(count < 9):
                m.d.sync += count.eq(count + 1)
        with m.If(self.end):
            with m.If((count == 8) & (shift[:32] == ~shift[32:]) &
                      (shift[62:64] == 2) & ~shift[55]):
                m.d.sync += [self.packet.eq(shift[32:]), self.accept.eq(1)]
            with m.Else():
                m.d.sync += self.error.eq(1)
        return m


class AckReceiver(Elaboratable):
    """ACK code/complement validation. Caller identifies the one-byte ACK frame."""
    def __init__(self):
        self.valid = Signal()
        self.byte = Signal(8)
        self.code = Signal(4)
        self.accept = Signal()
        self.error = Signal()

    def elaborate(self, platform):
        m = Module()
        m.d.sync += [self.accept.eq(0), self.error.eq(0)]
        with m.If(self.valid):
            m.d.sync += [self.code.eq(self.byte[4:8]),
                         self.accept.eq((self.byte[:4] ^ self.byte[4:8]) == 15),
                         self.error.eq((self.byte[:4] ^ self.byte[4:8]) != 15)]
        return m


class AckDecision(Elaboratable):
    """End-of-packet ACK policy; transaction responses use ack_pending.

    Header failure, broadcast, stream and cycle-start never generate ACKs.
    Address match and response capacity are supplied by the transaction layer.
    """
    def __init__(self):
        self.end = Signal()
        self.addressed = Signal()
        self.broadcast = Signal()
        self.header_good = Signal()
        self.data_good = Signal()
        self.capacity = Signal(init=1)
        self.tcode = Signal(4)
        self.valid = Signal()
        self.byte = Signal(8)

    def elaborate(self, platform):
        m = Module()
        code = Signal(4)
        response = (self.tcode == 2) | (self.tcode == 6) | (self.tcode == 7) | (self.tcode == 11)
        m.d.comb += code.eq(Mux(~self.data_good, 13, Mux(~self.capacity, 4, Mux(response, 1, 2))))
        m.d.sync += self.valid.eq(0)
        with m.If(self.end & self.addressed & ~self.broadcast & self.header_good &
                  (self.tcode != 10) & (self.tcode != 8)):
            m.d.sync += [self.valid.eq(1), self.byte.eq(Cat(~code, code))]
        return m
