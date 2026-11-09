"""Isolation-free streaming TX adapter, TI SLLS424G Figs20–21.

Upstream must prebuffer a packet: once started there is no byte backpressure
from the PHY. Missing a byte terminates the packet and pulses underrun; caller
must discard that packet. No LREQ scheduling, concatenation or CRC insertion.
"""
from amaranth import Elaboratable, Module, Mux, Signal


class TransmitAdapter(Elaboratable):
    def __init__(self):
        self.grant = Signal()  # sampled PHY CTL=11, caller qualifies ownership
        self.speed = Signal(2)
        self.allow_hold = Signal()  # permit up to 47 initial wait cycles
        self.valid = Signal()
        self.ready = Signal()
        self.byte = Signal(8)
        self.last = Signal()
        self.ctl = Signal(2)
        self.data = Signal(8)
        self.oe = Signal()
        self.done = Signal()
        self.underrun = Signal()

    def elaborate(self, platform):
        m = Module()
        speed = Signal(2)
        index = Signal(2)
        saved = Signal(8)
        last = Signal()
        tail = Signal(2)
        started = Signal()
        allow_hold = Signal()
        holds = Signal(range(48))
        current = Signal(8)
        final_lane = Signal()
        m.d.comb += [current.eq(Mux(index == 0, self.byte, saved)),
                     final_lane.eq(Mux(speed == 0, index == 3,
                                       Mux(speed == 1, index == 1, 1)))]
        m.d.sync += [self.done.eq(0), self.underrun.eq(0)]
        with m.FSM():
            with m.State('WAIT'):
                with m.If(self.grant):
                    m.d.sync += [speed.eq(self.speed), index.eq(0), started.eq(0),
                                 allow_hold.eq(self.allow_hold), holds.eq(0)]
                    m.next = 'TURN'
            with m.State('TURN'):
                # PHY drives idle following grant; LLC remains high impedance.
                m.next = 'SEND'
            with m.State('SEND'):
                m.d.comb += self.oe.eq(1)
                with m.If((index == 0) & ~self.valid & allow_hold &
                          ~started & (holds < 47) & (speed != 3)):
                    m.d.comb += self.ctl.eq(1)
                    m.d.sync += holds.eq(holds + 1)
                with m.Elif(((index == 0) & ~self.valid) | (speed == 3)):
                    # First idle of termination is driven in this cycle.
                    m.d.sync += [self.underrun.eq(1), tail.eq(~started & (holds == 0))]
                    m.next = 'TAIL'
                with m.Else():
                    m.d.comb += [self.ctl.eq(2), self.ready.eq(index == 0)]
                    m.d.sync += started.eq(1)
                    with m.Switch(speed):
                        with m.Case(0):
                            m.d.comb += self.data.eq((current << (index << 1)) & 0xc0)
                        with m.Case(1):
                            m.d.comb += self.data.eq((current << (index << 2)) & 0xf0)
                        with m.Case(2):
                            m.d.comb += self.data.eq(current)
                    with m.If(index == 0):
                        m.d.sync += [saved.eq(self.byte), last.eq(self.last)]
                    with m.If(final_lane):
                        m.d.sync += index.eq(0)
                        with m.If(Mux(index == 0, self.last, last)):
                            m.d.sync += tail.eq(1)
                            m.next = 'TAIL'
                    with m.Else():
                        m.d.sync += index.eq(index + 1)
            with m.State('TAIL'):
                m.d.comb += self.oe.eq(1)  # terminating idle samples
                with m.If(tail == 0):
                    m.d.sync += self.done.eq(1)
                    m.next = 'WAIT'
                with m.Else():
                    m.d.sync += tail.eq(tail - 1)
        return m
