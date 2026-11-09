"""TI SLLS424G Table21/Fig27, direct ISO=1 level-LPS timing model.

Time is in exact rational nanoseconds and advances independently of SYSCLK so a
stopped PHY clock cannot deadlock its own wake-up. Delays are explicit selected
corners within TI's ranges, not claims of exact silicon values. Pulsed/isolation
LPS and C/LKON pulse generation are not implemented.
"""
from fractions import Fraction


class InterfacePower:
    def __init__(self, *, reset_ns=2680, disable_ns=26110,
                 wake_ns=60, low_power_wake_ns=7_300_000, prefix_cycles=1):
        if not 2600 <= reset_ns <= 2680 or not 26030 <= disable_ns <= 26110:
            raise ValueError('recognition delay outside TI range')
        if not 0 <= wake_ns <= 60 or not 5_300_000 <= low_power_wake_ns <= 7_300_000:
            raise ValueError('wake delay outside TI range')
        if prefix_cycles < 1:
            raise ValueError('initialization requires data-on')
        self.reset_ns = Fraction(reset_ns)
        self.disable_ns = Fraction(disable_ns)
        self.wake_ns = Fraction(wake_ns)
        self.low_power_wake_ns = Fraction(low_power_wake_ns)
        self.prefix_cycles = prefix_cycles
        self.now = Fraction(0)
        self.lps = False
        self.low_since = Fraction(0)
        self.state = 'disabled'
        self.clock_running = False
        self.clock_at = None
        self.init_cycle = 0
        self.reset_epoch = 0
        self.has_operated = False

    def hardware_reset(self, now_ns):
        now = Fraction(now_ns)
        if now < self.now:
            raise ValueError('time cannot run backwards')
        self.now = self.low_since = now
        self.lps = False
        self.state = 'disabled'
        self.clock_running = False
        self.clock_at = None
        self.init_cycle = 0
        self.has_operated = False
        self.reset_epoch += 1

    @property
    def operational(self):
        return self.state == 'normal'

    def update(self, now_ns, *, lps, ports_active=True):
        now = Fraction(now_ns)
        if now < self.now:
            raise ValueError('time cannot run backwards')
        # Process elapsed time under the previous LPS value first.
        if not self.lps:
            elapsed = now - self.low_since
            if self.state not in ('reset', 'disabled') and elapsed >= self.reset_ns:
                self.state = 'reset'
                self.reset_epoch += 1
            if elapsed >= self.disable_ns:
                self.state = 'disabled'
                self.clock_running = False
                self.clock_at = None
        if self.clock_at is not None and now >= self.clock_at:
            self.clock_running = True
            self.clock_at = None
        if bool(lps) != self.lps:
            if lps and self.state in ('reset', 'disabled'):
                # TRESTORE is measured after reset recognition. Hardware boot
                # starts disabled, so the restore requirement is not imposed.
                if self.has_operated and now - self.low_since - self.reset_ns < 15_000:
                    raise ValueError('LPS reasserted before minimum TRESTORE')
                if not self.clock_running:
                    delay = self.wake_ns if ports_active else self.low_power_wake_ns
                    self.clock_at = now + delay
                    self.clock_running = delay == 0
                self.state = 'initializing'
                self.init_cycle = 0
            elif not lps:
                self.low_since = now
            self.lps = bool(lps)
        self.now = now

    def sample_sclk(self):
        """Return forced CTL/D or None when normal protocol owns the pins.

        Invoke on full SYSCLK cycles only, after update at that timestamp. Clock
        phase, low half-cycle on restart, and oscillator edges are caller-owned.
        """
        if not self.clock_running:
            raise ValueError('SYSCLK sample while clock stopped')
        if self.state == 'initializing':
            self.init_cycle += 1
            if self.init_cycle <= 7:
                return 0, 0
            if self.init_cycle <= 7 + self.prefix_cycles:
                return 2, 255
            self.state = 'normal'
            self.has_operated = True
            return 0, 0
        if self.state in ('reset', 'disabled'):
            return 0, 0
        return None


class LinkOn:
    """C/LKON wake latch, TI terminal table p7 and description p4.

    Phase starts high at activation as a declared model convention; silicon
    activation phase is not specified. Uses elapsed time even if SYSCLK is off.
    """
    def __init__(self, *, sysclk_hz=49_152_000):
        if sysclk_hz <= 0:
            raise ValueError('clock frequency must be positive')
        self.period_ns = Fraction(8_000_000_000, sysclk_hz)
        self.active = False
        self.start_ns = Fraction(0)
        self.now = Fraction(0)

    def update(self, now_ns, *, link_active, register5, addressed_packet=False,
               bus_reset=False, hardware_reset=False):
        now = Fraction(now_ns)
        if now < self.now or not 0 <= register5 <= 255:
            raise ValueError('invalid time or interrupt register')
        self.now = now
        if hardware_reset:
            self.active = False
            return None  # strap input, high impedance during hardware reset
        interrupt = bool(register5 & 4 or (register5 & 0x80 and register5 & 0x38))
        was_active = self.active
        if link_active:
            self.active = False
        elif bus_reset:
            self.active = interrupt
        elif interrupt or addressed_packet:
            self.active = True
        if self.active and not was_active:
            self.start_ns = now
        if not self.active:
            return 0
        return int((now - self.start_ns) % self.period_ns < self.period_ns / 2)
