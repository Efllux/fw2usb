import unittest
from amaranth.sim import Simulator
from fw2usb.smoke import Heartbeat


class SmokeTest(unittest.TestCase):
    def test_counter_wrap_and_led(self):
        dut = Heartbeat(bits=3)
        sim = Simulator(dut)
        sim.add_clock(1 / 25_000_000)

        async def bench(ctx):
            for n in range(25):
                self.assertEqual(ctx.get(dut.counter), n % 8)
                self.assertEqual(ctx.get(dut.led), (n % 8) >> 2)
                await ctx.tick()

        sim.add_testbench(bench)
        sim.run()

