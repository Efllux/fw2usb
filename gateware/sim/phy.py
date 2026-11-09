"""TI SLLS424G LREQ receiving subset; NOT a complete chip/bus model.

Call sample once per SCLK rising edge using the value driven before the edge.
The decoder accepts both Table 14 seven- and eight-cycle bus forms. Register
requests are decoded but register side effects are deliberately unimplemented.
"""
from dataclasses import dataclass
from enum import IntEnum


class RequestKind(IntEnum):
    IMMEDIATE = 0
    ISOCHRONOUS = 1
    PRIORITY = 2
    FAIR = 3
    READ = 4
    WRITE = 5
    ACCELERATION = 6


@dataclass(frozen=True)
class Request:
    kind: RequestKind
    payload: int

    @property
    def null_packet(self):
        return self.kind < 4 and self.payload not in (0, 2, 4)


class LreqDecoder:
    """Raises on malformed streams; diagnostic strictness is not silicon behavior."""
    def __init__(self):
        self.bits = []
        self.receiving_during_request = False
        self.pending_bus = None
        self.acceleration_enabled = True

    def bus_reset(self):
        # p36: pending bus requests cleared; acceleration reenabled (EAA gated
        # externally). A real PHY's pending register read survives reset.
        self.pending_bus = None
        self.acceleration_enabled = True

    def grant(self):
        request = self.pending_bus
        self.pending_bus = None
        return request

    def sample(self, bit, *, receiving=False):
        if bit not in (0, 1):
            raise ValueError('LREQ must be binary')
        # p35: RX clears fair/priority, but not iso/immediate requests.
        if receiving and self.pending_bus and self.pending_bus.kind in (2, 3):
            self.pending_bus = None
        if not self.bits and bit == 0:
            return None
        self.bits.append(bit)
        self.receiving_during_request |= receiving
        if len(self.bits) < 4:
            return None
        kind = int(''.join(map(str, self.bits[1:4])), 2)
        if kind == 7:
            self.bits = []
            self.receiving_during_request = False
            raise ValueError('reserved request type')
        length = (8, 8, 8, 8, 9, 17, 6)[kind]
        # A zero LR6 may also serve as the stop bit (Table 14).
        if kind < 4 and len(self.bits) == 7 and bit == 0:
            length = 7
        if len(self.bits) < length:
            return None
        bits, interrupted = self.bits, self.receiving_during_request
        self.bits, self.receiving_during_request = [], False
        if bit != 0:
            raise ValueError('missing stop bit')
        payload_bits = bits[4:7] if kind < 4 else bits[4:-1]
        request = Request(RequestKind(kind), int(''.join(map(str, payload_bits)), 2))
        if kind < 4:
            if self.pending_bus is None and not (kind in (2, 3) and interrupted):
                self.pending_bus = request
            if kind == 1:
                self.acceleration_enabled = True
        elif kind == 6:
            self.acceleration_enabled = bool(request.payload)
        return request


class StatusSource:
    """Fig17/Table19 status emission with RX interruption and mandatory idle.

    tick returns (CTL0*2+CTL1, D0*2+D1) for one rising-edge sample.
    It does not synthesize receive packets: receiving=True returns CTL=RX,
    and the caller must provide the remainder of that packet from another model.
    Register values are supplied by the test until the real register map exists.
    """
    def __init__(self):
        self.flags = 0
        self.read_pending = None
        self.active = None
        self.index = 0
        self.idle_required = False

    def request_read(self, address, value):
        if not 0 <= address <= 15 or not 0 <= value <= 255:
            raise ValueError('register field out of range')
        if self.read_pending is None:
            self.read_pending = (address, value)

    def bus_reset(self):
        # p36: register read persists; reset indication is status bit 2.
        self.flags |= 0b0010

    def tick(self, *, receiving=False):
        if receiving:
            self.active = None
            self.index = 0
            return 2, 0
        if self.idle_required:
            self.idle_required = False
            return 0, 0
        if self.active is None:
            if not self.flags and self.read_pending is None:
                return 0, 0
            flag_pairs = [(self.flags >> 2) & 3, self.flags & 3]
            pairs = flag_pairs
            if self.read_pending is not None:
                address, data = self.read_pending
                pairs = flag_pairs + [address >> 2, address & 3] + [
                    (data >> shift) & 3 for shift in (6, 4, 2, 0)]
            self.active = pairs
            self.index = 0
        pair = self.active[self.index]
        # p36: flags delivered immediately; interrupted transfer retries only
        # unsent flags and/or a register whose last data pair was not sent.
        if self.index == 0:
            self.flags &= 0b0011
        elif self.index == 1:
            self.flags &= 0b1100
        self.index += 1
        if self.index == len(self.active):
            if len(self.active) == 8:
                self.read_pending = None
            self.active = None
            self.index = 0
            self.idle_required = True
        return 1, pair
