"""Exact synthetic independent clocks with frequency offset and edge jitter.

Jitter entries are displacement from ideal edges (not extra accumulated drift).
This is a digital stimulus generator, not an oscillator/metastability model.
"""
from fractions import Fraction


class Clock:
    def __init__(self, frequency_hz, *, ppm=0, phase_ns=0, jitter_ns=(0,)):
        rate = Fraction(frequency_hz) * (1 + Fraction(ppm) / 1_000_000)
        if rate <= 0 or not jitter_ns:
            raise ValueError('invalid frequency or empty jitter pattern')
        self.period_ns = Fraction(1_000_000_000) / rate
        self.phase_ns = Fraction(phase_ns)
        self.jitter_ns = tuple(map(Fraction, jitter_ns))
        if max(self.jitter_ns) - min(self.jitter_ns) >= self.period_ns:
            raise ValueError('jitter can reverse edge order')
        self.index = 0

    def next_edge(self):
        n = self.index
        self.index += 1
        return self.phase_ns + n * self.period_ns + self.jitter_ns[n % len(self.jitter_ns)]

    async def drive(self, ctx, signal):
        """Amaranth background testbench; rising edges follow exact schedule.

        Half-cycle duty is synthetic. Float conversion occurs only at simulator
        delay boundary; exact arithmetic above avoids cumulative Python drift.
        """
        previous = Fraction(0)
        while True:
            rising = self.next_edge()
            if rising < previous:
                raise ValueError('edge before start or previous falling edge')
            await ctx.delay(float((rising - previous) / 1_000_000_000))
            ctx.set(signal, 1)
            falling = rising + self.period_ns / 2
            await ctx.delay(float(self.period_ns / 2 / 1_000_000_000))
            ctx.set(signal, 0)
            previous = falling
