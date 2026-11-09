import unittest
from fractions import Fraction
from amaranth import ClockDomain, Elaboratable, Module
from amaranth.lib.fifo import AsyncFIFOBuffered
from amaranth.sim import Simulator
from sim.clocks import Clock


class FifoHarness(Elaboratable):
    """Research harness for the library FIFO, not yet a bridge packet FIFO."""
    def __init__(self):
        self.sclk = ClockDomain('sclk')
        self.usb = ClockDomain('usb')
        self.fifo = AsyncFIFOBuffered(width=16, depth=8, w_domain='sclk', r_domain='usb')

    def elaborate(self, platform):
        m = Module()
        m.domains += [self.sclk, self.usb]
        m.submodules.fifo = self.fifo
        return m


class ClockTest(unittest.TestCase):
    def test_exact_drift_and_jitter(self):
        p = Clock(49_152_000, ppm=100, phase_ns=3, jitter_ns=(0, 1, -1))
        expected_period = Fraction(1_000_000_000, 49_152_000) / Fraction(10001, 10000)
        edges = [p.next_edge() for _ in range(4)]
        self.assertEqual(edges, [3, 3 + expected_period + 1,
                                 3 + expected_period * 2 - 1, 3 + expected_period * 3])
        self.assertTrue(all(a < b for a, b in zip(edges, edges[1:])))
        with self.assertRaises(ValueError):
            Clock(1_000_000_000, jitter_ns=(-1, 1))

    def test_async_fifo_independent_drift_jitter_and_backpressure(self):
        for ppm in (-100, 100):
            dut = FifoHarness()
            sim = Simulator(dut)
            fifo = dut.fifo
            wclock = Clock(49_152_000, ppm=ppm, phase_ns=1,
                           jitter_ns=(0, Fraction(1, 4), Fraction(-1, 4)))
            rclock = Clock(60_000_000, ppm=-ppm, phase_ns=7,
                           jitter_ns=(0, Fraction(-1, 5), Fraction(1, 5)))

            async def write_clock(ctx):
                await wclock.drive(ctx, dut.sclk.clk)

            async def read_clock(ctx):
                await rclock.drive(ctx, dut.usb.clk)

            async def writer(ctx):
                value = 0
                while value < 1024:
                    ctx.set(fifo.w_en, 1)
                    ctx.set(fifo.w_data, value ^ 0xa55a)
                    _, _, ready = await ctx.tick('sclk').sample(fifo.w_rdy)
                    if ready:
                        value += 1
                ctx.set(fifo.w_en, 0)

            async def reader(ctx):
                value = 0
                cycles = 0
                full_seen = False
                while value < 1024 and cycles < 20_000:
                    # Long stalls fill FIFO; resumed consumption empties it.
                    enabled = cycles % 53 >= 23
                    ctx.set(fifo.r_en, enabled)
                    _, _, ready, data = await ctx.tick('usb').sample(fifo.r_rdy, fifo.r_data)
                    full_seen |= not ctx.get(fifo.w_rdy)
                    if ready and enabled:
                        self.assertEqual(data, value ^ 0xa55a)
                        value += 1
                    cycles += 1
                self.assertEqual(value, 1024)
                self.assertTrue(full_seen)

            sim.add_testbench(write_clock, background=True)
            sim.add_testbench(read_clock, background=True)
            sim.add_testbench(writer)
            sim.add_testbench(reader)
            sim.run()

    def test_fifo_coordinated_reset_discards_old_epoch(self):
        dut = FifoHarness()
        sim = Simulator(dut)
        fifo = dut.fifo
        wc = Clock(49_152_000, ppm=100, phase_ns=1)
        rc = Clock(60_000_000, ppm=-100, phase_ns=7)

        async def write_clock(ctx):
            await wc.drive(ctx, dut.sclk.clk)

        async def read_clock(ctx):
            await rc.drive(ctx, dut.usb.clk)

        async def bench(ctx):
            for value in range(4):
                ctx.set(fifo.w_en, 1)
                ctx.set(fifo.w_data, 0x1000 + value)
                while True:
                    _, _, ready = await ctx.tick('sclk').sample(fifo.w_rdy)
                    if ready:
                        break
            ctx.set(fifo.w_en, 0)
            for _ in range(6):
                await ctx.tick('usb')
            self.assertTrue(ctx.get(fifo.r_rdy))
            # Testbench coordinates both domains and quiesces all producers and
            # consumers. This is not a hardware epoch handshake implementation.
            ctx.set(dut.sclk.rst, 1)
            ctx.set(dut.usb.rst, 1)
            for _ in range(6):
                await ctx.tick('sclk')
            ctx.set(dut.sclk.rst, 0)
            ctx.set(dut.usb.rst, 0)
            for _ in range(8):
                await ctx.tick('usb')
            self.assertFalse(ctx.get(fifo.r_rdy))
            ctx.set(fifo.w_en, 1)
            ctx.set(fifo.w_data, 0x2000)
            while True:
                _, _, ready = await ctx.tick('sclk').sample(fifo.w_rdy)
                if ready:
                    break
            ctx.set(fifo.w_en, 0)
            for _ in range(12):
                _, _, ready, value = await ctx.tick('usb').sample(fifo.r_rdy, fifo.r_data)
                if ready:
                    self.assertEqual(value, 0x2000)
                    break
            else:
                self.fail('new epoch never reached reader')

        sim.add_testbench(write_clock, background=True)
        sim.add_testbench(read_clock, background=True)
        sim.add_testbench(bench)
        sim.run()
