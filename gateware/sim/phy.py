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
        self.eaa_enabled = False
        self.npa = False

    def receive_packet(self, bit_length):
        """Completed-packet fixture for Table8 NPA/ACK request preservation.

        Accelerated mode defers loss until this explicit packet-length event;
        the boolean RX marker alone cannot distinguish an ACK from data.
        """
        if bit_length < 0:
            raise ValueError('negative packet length')
        accelerated = self.eaa_enabled and self.acceleration_enabled
        lost = not accelerated or (bit_length > 8 if self.npa else bit_length != 8)
        if lost:
            if self.pending_bus and self.pending_bus.kind in (2, 3):
                self.pending_bus = None
            if self.bits:
                self.receiving_during_request = True

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
        accelerated = self.eaa_enabled and self.acceleration_enabled
        if receiving and not accelerated and self.pending_bus and self.pending_bus.kind in (2, 3):
            self.pending_bus = None
        if not self.bits and bit == 0:
            return None
        self.bits.append(bit)
        self.receiving_during_request |= receiving and not accelerated
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
        self.unsolicited = []
        self.register_origin = None
        self.active = None
        self.index = 0
        self.idle_required = False

    def notify_register(self, address, value):
        if not 0 <= address <= 15 or not 0 <= value <= 255:
            raise ValueError('register field out of range')
        self.unsolicited.append((address, value))

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
            self.idle_required = True  # TI Figs18–19: idle after receive
            self.active = None
            self.index = 0
            return 2, 0
        if self.idle_required:
            self.idle_required = False
            return 0, 0
        if self.active is None:
            if not self.flags and self.read_pending is None and not self.unsolicited:
                return 0, 0
            flag_pairs = [(self.flags >> 2) & 3, self.flags & 3]
            pairs = flag_pairs
            register = self.read_pending
            self.register_origin = 'read' if register is not None else None
            if register is None and self.unsolicited:
                register = self.unsolicited[0]
                self.register_origin = 'automatic'
            if register is not None:
                address, data = register
                pairs = flag_pairs + [address >> 2, address & 3] + [
                    (data >> shift) & 3 for shift in (6, 4, 2, 0)]
            self.active = pairs
            self.index = 0
        pair = self.active[self.index]
        # p36: flags delivered immediately; interrupted transfer retries only
        # unsent flags and/or a register whose last data pair was not sent.
        if self.index == 0:
            self.flags &= ~(pair << 2)
        elif self.index == 1:
            self.flags &= ~pair
        self.index += 1
        if self.index == len(self.active):
            if len(self.active) == 8:
                if self.register_origin == 'read':
                    self.read_pending = None
                else:
                    self.unsolicited.pop(0)
            self.active = None
            self.index = 0
            self.idle_required = True
        return 1, pair


def receive_samples(payload=b'', *, speed=0, prefix_cycles=1, null=False):
    """Synthetic Figs18–19 pin samples; data[7]=D0, ctl[1]=CTL0.

    No cable propagation/resynchronization latency is inferred. Caller provides
    the payload delivered by the cable model; this only formats PHY-LINK cycles.
    """
    if speed not in (0, 1, 2) or prefix_cycles < 1:
        raise ValueError('invalid speed or missing data-on prefix')
    yield from ((2, 255) for _ in range(prefix_cycles))
    if not null:
        yield 2, (0x00, 0x40, 0x50)[speed]
        width = (2, 4, 8)[speed]
        for byte in payload:
            for bit in range(8 - width, -1, -width):
                yield 2, ((byte >> bit) & ((1 << width) - 1)) << (8 - width)
    yield 0, 0  # at least one idle after RX


class RegisterPhy:
    """SCLK-stepped LREQ/register/status composition, isolation-free subset.

    Reads snapshot on request completion (explicit model policy, not verified
    silicon timing). RX preempts status; bus reset preserves the captured read.
    No arbitration grant, LPS clock gating or cable state machine is implied.
    """
    def __init__(self, **straps):
        from sim.registers import PhyRegisters
        self.registers = PhyRegisters(**straps)
        self.requests = LreqDecoder()
        self.status = StatusSource()
        self._interrupt_sequence = self.registers.interrupt_sequence

    def self_id_complete(self, physical_id, *, root=False):
        self.registers.self_id_complete(physical_id, root=root)
        self.status.notify_register(0, self.registers.read(0))

    def sync_interrupts(self, *, deliver=True):
        sequence = self.registers.interrupt_sequence
        if deliver and sequence != self._interrupt_sequence:
            self.status.flags |= 1
        self._interrupt_sequence = sequence

    def bus_reset(self):
        self.registers.bus_reset()
        self.requests.bus_reset()
        self.status.bus_reset()

    def tick(self, lreq=0, *, receiving=False):
        self.requests.eaa_enabled = bool(self.registers.read(5) & 2)
        self.requests.npa = bool(self.registers.vendor & 0x80)
        request = self.requests.sample(lreq, receiving=receiving)
        if request is not None:
            if request.kind == RequestKind.READ and self.status.read_pending is None:
                address = request.payload
                self.status.request_read(address, self.registers.read(address))
            elif request.kind == RequestKind.WRITE:
                epoch = self.registers.reset_epoch
                self.registers.write(request.payload >> 8, request.payload & 255)
                if epoch != self.registers.reset_epoch:
                    self.requests = LreqDecoder()
                    self.status = StatusSource()
                    self._interrupt_sequence = self.registers.interrupt_sequence
        self.sync_interrupts()
        return self.status.tick(receiving=receiving)


class PoweredRegisterPhy:
    """Direct ISO=1 level-LPS composition; no cable/arbitration engine yet."""
    def __init__(self, *, power=None, **straps):
        from sim.power import InterfacePower, LinkOn
        self.linkon = LinkOn()
        self.ports_active = True
        self.power = power if power is not None else InterfacePower()
        self.phy = RegisterPhy(**straps)
        self._epoch = self.power.reset_epoch

    def update(self, now_ns, *, lps, ports_active=True):
        self.ports_active = ports_active
        self.power.update(now_ns, lps=lps, ports_active=ports_active)
        if self._epoch != self.power.reset_epoch:
            # Interface reset differs from bus reset: pending reads and all
            # status events are discarded, but register configuration survives.
            accelerating = self.phy.requests.acceleration_enabled
            self.phy.requests = LreqDecoder()
            self.phy.requests.acceleration_enabled = accelerating
            self.phy.status = StatusSource()
            self._epoch = self.power.reset_epoch
        if not self.power.operational:
            self.phy.sync_interrupts(deliver=False)
        self.linkon_pin()

    def bus_reset(self):
        self.phy.bus_reset()
        self.linkon_pin(bus_reset=True)
        if not self.power.operational:
            self.phy.status = StatusSource()  # inactive events are not queued

    def sample_sclk(self, lreq=0, *, receiving=False):
        forced = self.power.sample_sclk()
        if forced is not None:
            self.phy.sync_interrupts(deliver=False)
            return forced
        epoch = self.phy.registers.reset_epoch
        pins = self.phy.tick(lreq, receiving=receiving)
        if epoch != self.phy.registers.reset_epoch:
            # SWR is a hardware reset, including SYSCLK disable and startup.
            lps = self.power.lps
            self.power.hardware_reset(self.power.now)
            self.linkon.update(self.power.now, link_active=False, register5=0,
                               hardware_reset=True)
            self._epoch = self.power.reset_epoch
            self.update(self.power.now, lps=lps, ports_active=self.ports_active)
            return 0, 0
        self.linkon_pin()
        return pins

    def linkon_pin(self, *, addressed_packet=False, bus_reset=False):
        lps_active = self.power.state in ('normal', 'initializing')
        return self.linkon.update(
            self.power.now,
            link_active=lps_active and bool(self.phy.registers.read(4) & 0x80),
            register5=self.phy.registers.read(5),
            addressed_packet=addressed_packet, bus_reset=bus_reset)
