"""Blocking AM824 hardware, IEC61883-1/-6; cross-checked with fw-amdtp.
CIP-only interfaces. ISO framing/CRC belong to link packet modules.
"""
from amaranth import Array, Cat, Const, Elaboratable, Module, Mux, Signal


class AmdtpReceiver(Elaboratable):
    def __init__(self):
        self.start = Signal()
        self.valid = Signal()
        self.byte = Signal(8)
        self.end = Signal()
        self.sample_valid = Signal()
        self.sample = Signal(24)
        self.channel = Signal(8)
        self.frame = Signal(16)
        self.syt = Signal(16)
        self.dbc = Signal(8)
        self.dbs = Signal(8)
        self.error = Signal()
        self.dbc_gap = Signal()

    def elaborate(self, platform):
        m = Module()
        count = Signal(17)
        shift = Signal(32)
        slot = Signal(8)
        frames = Signal(16)
        invalid = Signal()
        expected = Signal(8)
        known = Signal()
        word = Cat(self.byte,shift[:24])
        m.d.sync += [self.sample_valid.eq(0),self.error.eq(0),self.dbc_gap.eq(0)]
        with m.If(self.start):
            m.d.sync += [count.eq(0),slot.eq(0),frames.eq(0),invalid.eq(0)]
        with m.Elif(self.valid):
            m.d.sync += [count.eq(count+1),shift.eq(word)]
            with m.Switch(count):
                with m.Case(0):
                    with m.If(self.byte[6:8] != 0):
                        m.d.sync += invalid.eq(1)
                with m.Case(1):
                    m.d.sync += self.dbs.eq(self.byte)
                with m.Case(2):
                    with m.If(self.byte != 0):
                        m.d.sync += invalid.eq(1)
                with m.Case(3):
                    m.d.sync += self.dbc.eq(self.byte)
                with m.Case(4):
                    with m.If(self.byte != 0x90):
                        m.d.sync += invalid.eq(1)
                with m.Case(5):
                    with m.If((self.byte != 255) & (self.byte > 6)):
                        m.d.sync += invalid.eq(1)
                with m.Case(6):
                    m.d.sync += self.syt[8:16].eq(self.byte)
                with m.Case(7):
                    m.d.sync += self.syt[:8].eq(self.byte)
            with m.If((count >= 8) & (count[:2] == 3)):
                with m.If((self.dbs == 0) | invalid):
                    m.d.sync += invalid.eq(1)
                with m.Else():
                    with m.If(count == 11):
                        m.d.sync += self.dbc_gap.eq(known & (expected != self.dbc))
                    with m.If((word[24:32] >= 0x40) & (word[24:32] <= 0x43)):
                        m.d.sync += [self.sample_valid.eq(1),self.sample.eq(word[:24]),
                                     self.channel.eq(slot),self.frame.eq(frames)]
                    with m.If(slot+1 == self.dbs):
                        m.d.sync += [slot.eq(0),frames.eq(frames+1)]
                    with m.Else():
                        m.d.sync += slot.eq(slot+1)
        with m.If(self.end):
            m.d.sync += self.error.eq(invalid | (count < 8) | (count[:2] != 0) | (slot != 0))
            with m.If((frames != 0) & ~invalid & (slot == 0) & (count[:2] == 0)):
                m.d.sync += [known.eq(1),expected.eq(self.dbc+frames)]
        return m


class AmdtpTransmitter(Elaboratable):
    def __init__(self):
        self.start = Signal()
        self.sid = Signal(6)
        self.dbs = Signal(8)
        self.dbc = Signal(8)
        self.fdf = Signal(8)
        self.syt = Signal(16)
        self.frames = Signal(6)
        self.sample = Signal(24)
        self.sample_valid = Signal()
        self.sample_ready = Signal()
        self.valid = Signal()
        self.ready = Signal()
        self.byte = Signal(8)
        self.last = Signal()
        self.busy = Signal()

    def elaborate(self, platform):
        m = Module()
        header = Signal(64)
        pos = Signal(3)
        lane = Signal(2)
        remaining = Signal(14)
        saved = Signal(24)
        with m.FSM() as fsm:
            m.d.comb += self.busy.eq(~fsm.ongoing('IDLE'))
            with m.State('IDLE'):
                with m.If(self.start):
                    m.d.sync += [header.eq(Cat(self.syt,self.fdf,Const(0x90,8),self.dbc,Const(0,8),self.dbs,self.sid,Const(0,2))),
                                 remaining.eq(self.frames*self.dbs),pos.eq(7),lane.eq(0)]
                    m.next = 'HEADER'
            with m.State('HEADER'):
                m.d.comb += [self.valid.eq(1),self.byte.eq(header >> (pos << 3)),
                             self.last.eq((pos == 0) & (remaining == 0))]
                with m.If(self.ready):
                    with m.If(pos == 0):
                        with m.If(remaining == 0):
                            m.next = 'IDLE'
                        with m.Else():
                            m.next = 'DATA'
                    with m.Else():
                        m.d.sync += pos.eq(pos-1)
            with m.State('DATA'):
                m.d.comb += [self.valid.eq(Mux(lane == 0,self.sample_valid,1)),
                             self.sample_ready.eq((lane == 0) & self.ready),
                             self.byte.eq(Mux(lane == 0,0x40,saved >> ((3-lane).as_unsigned() << 3))),
                             self.last.eq((lane == 3) & (remaining == 1))]
                with m.If(self.valid & self.ready):
                    m.d.sync += lane.eq(lane+1)
                    with m.If(lane == 0):
                        m.d.sync += saved.eq(self.sample)
                    with m.If(lane == 3):
                        m.d.sync += remaining.eq(remaining-1)
                        with m.If(remaining == 1):
                            m.next = 'IDLE'
        return m


class SytEngine(Elaboratable):
    """SYT/blocking schedule, one decision per ``advance`` (one per 125 us cycle).

    The reference model keeps ``phase`` and derives the timestamp offset as
    ``phase // rate``. Dividing a 32-bit value by the sample rate in one SCLK
    cycle is far too slow, so the quotient and remainder are carried instead:
    every phase step is a constant, hence its quotient and remainder by
    ``rate`` are elaboration-time constants and the update is two small adds.
    """
    def __init__(self, *, rate=48000, code=2):
        self.rate,self.code = rate,code
        self.interval = 8 if rate <= 48000 else (16 if rate <= 96000 else 32)
        if 24_576_000*self.interval < 3072*rate:
            raise ValueError('sample rate too high for the SYT interval')
        self.cycle = Signal(13)
        self.advance = Signal()
        self.data = Signal()
        self.syt = Signal(16)
        self.fdf = Signal(8)
        self.frames = Signal(6)

    def elaborate(self, platform):
        m = Module()
        # phase == quotient*rate + remainder, with remainder < rate.
        step_quotient,step_remainder = divmod(24_576_000*self.interval,self.rate)
        quotient = Signal(range(step_quotient+3072+2))
        remainder = Signal(range(self.rate))
        wrapped = Signal()
        m.d.comb += wrapped.eq(remainder+step_remainder >= self.rate)
        # offset+0x2e00 split into cycles and ticks; offset < 3072 when used
        # and 0x2e00 == 3*3072+2560, so the carry is 3 or 4.
        late = Signal()
        ticks = Signal(12)
        carry = Signal(3)
        m.d.comb += [late.eq(quotient >= 512),
                     ticks.eq(Mux(late,quotient-512,quotient+2560)),carry.eq(Mux(late,4,3))]
        with m.If(self.advance):
            with m.If(quotient < 3072):
                m.d.sync += [quotient.eq(quotient+step_quotient-3072+wrapped),
                             remainder.eq(Mux(wrapped,remainder+step_remainder-self.rate,remainder+step_remainder)),
                             self.data.eq(1),self.fdf.eq(self.code),self.frames.eq(self.interval),
                             self.syt.eq(Cat(ticks,(self.cycle[:4]+carry)[:4]))]
            with m.Else():
                m.d.sync += [quotient.eq(quotient-3072),self.data.eq(0),self.fdf.eq(255),
                             self.frames.eq(0),self.syt.eq(65535)]
        return m
