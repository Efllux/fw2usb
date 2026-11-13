"""Isolation-free streaming TX adapter, TI SLLS424G Figs20–21.

Upstream must prebuffer a packet: once started there is no byte backpressure
from the PHY. Missing a byte terminates the packet and pulses underrun; caller
must discard that packet. No LREQ scheduling, cable separation timing or CRC insertion.

Registered I/O contract. ``grant`` is the PHY's CTL=11 as seen through the
link's input flip-flops, so it is high during the cycle in which the PHY drives
its turnaround idle on the pins. ``ctl``, ``data``, ``oe`` and ``tristate`` are
flip-flop outputs intended for the I/O cells: what is decided in the grant
cycle appears on the pins in the following cycle, which is exactly the first
link-owned cycle of Fig 20 (grant, one PHY idle, then the link). There is
therefore no internal turnaround state, and the first byte (or a hold) is
taken in the grant cycle itself. ``done``, ``underrun`` and ``config_error``
are aligned with the pins: ``done`` is high in the first released cycle.

The pad flip-flops carry no reset: an ECP5 I/O cell shares one set/reset among
its input, output and tristate flip-flops, and the input one has none. Instead
``abort`` (interface disabled or bus reset) forces the next pad values to
released/idle; the caller also resets the internal state in that cycle.
"""
from amaranth import Elaboratable, Module, Mux, Signal

IO_OUTPUT = {'syn_useioff': 1, 'ioff_dir': 'output'}


class TransmitAdapter(Elaboratable):
    PINS = 10  # CTL[0:1] and D[0:7] each get their own tristate flip-flop

    def __init__(self):
        self.busy = Signal()
        self.grant = Signal()  # registered PHY CTL=11, caller qualifies ownership
        self.abort = Signal()  # release the pads at the next edge
        self.speed = Signal(2)
        self.allow_hold = Signal()  # permit up to 47 initial wait cycles
        self.valid = Signal()
        self.ready = Signal()
        self.byte = Signal(8)
        self.last = Signal()
        self.concatenate = Signal()
        self.next_speed = Signal(2)
        self.multispeed = Signal()  # PHY EMC configuration, sampled on grant
        self.config_error = Signal()
        self.ctl = Signal(2, reset_less=True, attrs=IO_OUTPUT)
        self.data = Signal(8, reset_less=True, attrs=IO_OUTPUT)
        self.oe = Signal()
        # One active-high tristate control per pin so each fits an I/O cell.
        self.tristate = Signal(self.PINS, init=(1 << self.PINS) - 1, reset_less=True, attrs=IO_OUTPUT)
        self.done = Signal()
        self.underrun = Signal()

    def elaborate(self, platform):
        m = Module()
        WAIT, SEND, TAIL = range(3)
        state = Signal(2)
        speed = Signal(2)
        index = Signal(2)
        saved = Signal(8)
        last = Signal()
        tail = Signal(2)
        started = Signal()
        allow_hold = Signal()
        holds = Signal(range(48))
        multispeed = Signal()
        saved_concat = Signal()
        saved_speed = Signal(2)
        concat = Signal()
        concat_speed = Signal(2)
        requested_concat = Signal()
        requested_speed = Signal(2)
        invalid_concat = Signal()
        # In WAIT the latched grant parameters are stale: use the live inputs.
        first = Signal()
        sending = Signal()
        now_speed = Signal(2)
        now_hold = Signal()
        now_multispeed = Signal()
        m.d.comb += [first.eq((state == WAIT) & self.grant),
                     sending.eq(first | (state == SEND)),
                     now_speed.eq(Mux(state == WAIT, self.speed, speed)),
                     now_hold.eq(Mux(state == WAIT, self.allow_hold, allow_hold)),
                     now_multispeed.eq(Mux(state == WAIT, self.multispeed, multispeed))]
        m.d.comb += [requested_concat.eq(Mux(index == 0, self.concatenate, saved_concat)),
                     requested_speed.eq(Mux(index == 0, self.next_speed, saved_speed)),
                     invalid_concat.eq(now_multispeed & ((requested_speed == 3) |
                                      ((now_speed != 0) & (requested_speed == 0))))]
        current = Signal(8)
        final_lane = Signal()
        m.d.comb += [current.eq(Mux(index == 0, self.byte, saved)),
                     final_lane.eq(Mux(now_speed == 0, index == 3,
                                       Mux(now_speed == 1, index == 1, 1)))]
        # Pin values for the next cycle, and strobes one stage ahead of the pins.
        next_ctl = Signal(2)
        next_data = Signal(8)
        next_oe = Signal()
        early_done = Signal()
        early_underrun = Signal()
        early_error = Signal()
        echo = Signal()  # the input flip-flops still hold our own last cycle
        m.d.sync += [self.ctl.eq(next_ctl), self.data.eq(next_data), self.oe.eq(next_oe),
                     self.tristate.eq((~next_oe).replicate(self.PINS)), echo.eq(self.oe),
                     early_done.eq(0), early_underrun.eq(0), early_error.eq(0),
                     self.done.eq(early_done), self.underrun.eq(early_underrun),
                     self.config_error.eq(early_error)]
        m.d.comb += self.busy.eq((state != WAIT) | self.oe | echo)
        with m.If(first):
            m.d.sync += [speed.eq(self.speed), allow_hold.eq(self.allow_hold),
                         multispeed.eq(self.multispeed), concat.eq(0), state.eq(SEND)]
        with m.If(sending):
            m.d.comb += next_oe.eq(1)
            with m.If((index == 0) & ~self.valid & now_hold &
                      ~started & (holds < 47) & (now_speed != 3)):
                m.d.comb += next_ctl.eq(1)
                m.d.sync += holds.eq(holds + 1)
            with m.Elif(((index == 0) & ~self.valid) | (now_speed == 3)):
                # First idle of termination is driven in the next pin cycle.
                m.d.sync += [early_underrun.eq(1), tail.eq(~started & (holds == 0)),
                             state.eq(TAIL)]
            with m.Else():
                m.d.comb += [next_ctl.eq(2), self.ready.eq(index == 0)]
                m.d.sync += started.eq(1)
                with m.Switch(now_speed):
                    with m.Case(0):
                        m.d.comb += next_data.eq((current << (index << 1)) & 0xc0)
                    with m.Case(1):
                        m.d.comb += next_data.eq((current << (index << 2)) & 0xf0)
                    with m.Case(2):
                        m.d.comb += next_data.eq(current)
                with m.If(index == 0):
                    m.d.sync += [saved.eq(self.byte), last.eq(self.last),
                                 saved_concat.eq(self.concatenate), saved_speed.eq(self.next_speed)]
                with m.If(final_lane):
                    m.d.sync += index.eq(0)
                    with m.If(Mux(index == 0, self.last, last)):
                        m.d.sync += [tail.eq(1),
                                     concat.eq(requested_concat & ~invalid_concat),
                                     concat_speed.eq(requested_speed),
                                     early_error.eq(requested_concat & invalid_concat),
                                     state.eq(TAIL)]
                with m.Else():
                    m.d.sync += index.eq(index + 1)
        with m.Elif(state == TAIL):
            m.d.comb += next_oe.eq(1)
            with m.If((tail == 1) & concat):
                m.d.comb += next_ctl.eq(1)
                with m.If(multispeed):
                    m.d.comb += next_data.eq(Mux(concat_speed == 0, 0,
                                                 Mux(concat_speed == 1, 0x40, 0x50)))
            with m.If(tail == 0):
                m.d.sync += [early_done.eq(1), state.eq(WAIT), index.eq(0),
                             started.eq(0), holds.eq(0)]
            with m.Else():
                m.d.sync += tail.eq(tail - 1)
        with m.If(self.abort):
            m.d.comb += [next_oe.eq(0), next_ctl.eq(0), next_data.eq(0)]
        return m
