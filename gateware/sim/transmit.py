"""TI SLLS424G Figs20–21 pin-level TX observer, independently authored.

Arbitration winner and concatenation separation are external inputs. No cable
latency is invented. None means high impedance; output-enable collision is an
error even if both drivers would drive the same value. Invalid LLC sequences
raise test diagnostics, not predictions of undocumented silicon behavior.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Transmission:
    payload: bytes
    speed: int
    concatenate: bool
    next_speed: int


class TransmitPhy:
    def __init__(self):
        self.state = 'idle'
        self.speed = 0
        self.multispeed = False
        self.completed = []
        self.aborted = []
        self._clear_packet()

    def _clear_packet(self):
        self.payload = bytearray()
        self.partial = 0
        self.bits = 0
        self.holds = 0
        self.optional_idle = False
        self.concatenate = False
        self.next_speed = self.speed

    @property
    def phy_ctl(self):
        # Grant, turnaround and reclaim have driven idle; ownership transfers
        # only after the complete PHY idle following grant.
        if self.state == 'grant':
            return 3
        if self.state in ('idle', 'turnaround', 'reclaim'):
            return 0
        return None

    def grant(self, speed, *, multispeed=False):
        if self.state != 'idle' or speed not in (0, 1, 2):
            raise ValueError('grant while busy or invalid speed')
        self.speed = speed
        self.multispeed = multispeed
        self._clear_packet()
        self.state = 'grant'

    def bus_reset(self):
        if self.state != 'idle':
            self.aborted.append(bytes(self.payload))
        self.state = 'idle'
        self._clear_packet()

    def tick(self, ctl=None, data=0):
        """Sample one edge; return PHY CTL driven before that edge.

        Caller must drive LLC CTL only during high-impedance PHY cycles and
        release after the two terminating LLC cycles. Data numeric bit7 is D0.
        """
        driven = self.phy_ctl
        if not 0 <= data <= 255:
            raise ValueError('data out of range')
        if driven is not None:
            if ctl is not None:
                raise ValueError('PHY/LLC output enable collision')
            self.state = {'grant': 'turnaround', 'turnaround': 'prepare',
                          'reclaim': 'idle', 'idle': 'idle'}[self.state]
            return driven
        if ctl not in (0, 1, 2):
            raise ValueError('missing or reserved LLC CTL')
        if self.state == 'release':
            if ctl != 0:
                raise ValueError('second termination cycle must be idle')
            self.completed.append(Transmission(bytes(self.payload), self.speed,
                                               self.concatenate, self.next_speed))
            self.state = 'reclaim'
            return None
        if self.state == 'data':
            if ctl == 2:
                self._data(data)
            else:
                if self.bits:
                    raise ValueError('packet ends inside byte')
                self.concatenate = ctl == 1
                if self.concatenate and self.multispeed:
                    if data >> 6 == 0:
                        self.next_speed = 0
                    elif data >> 4 == 4:
                        self.next_speed = 1
                    elif data == 0x50:
                        self.next_speed = 2
                    else:
                        raise ValueError('invalid concatenated speed')
                    if self.speed > 0 and self.next_speed == 0:
                        raise ValueError('S100 concatenation after faster packet')
                self.state = 'release'
        elif ctl == 2:
            self.state = 'data'
            self._data(data)
        elif ctl == 1:
            self.holds += 1
            if self.holds > 47:
                raise ValueError('hold exceeds 47 cycles')
            self.state = 'hold'
        elif self.state == 'hold' or self.optional_idle:
            self.state = 'release'
        else:
            self.optional_idle = True
        return None

    def _data(self, data):
        width = (2, 4, 8)[self.speed]
        self.partial = (self.partial << width) | (data >> (8 - width))
        self.bits += width
        if self.bits == 8:
            self.payload.append(self.partial)
            self.partial = self.bits = 0
