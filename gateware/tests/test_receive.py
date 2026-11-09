import unittest
from amaranth.sim import Simulator
from fw2usb.receive import ReceiveAdapter
from sim.phy import receive_samples


class ReceiveTest(unittest.TestCase):
    def test_all_widths_null_invalid_and_truncated(self):
        dut = ReceiveAdapter()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            async def run(samples):
                output, starts, ends, errors = [], 0, 0, 0
                for ctl, data in samples:
                    ctx.set(dut.ctl, ctl)
                    ctx.set(dut.data, data)
                    await ctx.tick()
                    if ctx.get(dut.valid):
                        output.append(ctx.get(dut.byte))
                    starts += ctx.get(dut.start)
                    ends += ctx.get(dut.end)
                    errors += ctx.get(dut.error)
                return bytes(output), starts, ends, errors

            # Independent literal pin example: S100 A5 -> 10,10,01,01.
            self.assertEqual(await run([(2, 255), (2, 0), (2, 128), (2, 128),
                                        (2, 64), (2, 64), (0, 0)]), (b'\xa5', 1, 1, 0))
            for speed in range(3):
                payload = bytes(range(256))
                self.assertEqual(await run(receive_samples(payload, speed=speed,
                                                           prefix_cycles=3)),
                                 (payload, 1, 1, 0))
            self.assertEqual(await run(receive_samples(null=True)), (b'', 0, 1, 0))
            self.assertEqual(await run([(2, 255), (2, 0x60), (2, 0x11), (0, 0)]),
                             (b'', 0, 1, 1))
            self.assertEqual(await run([(2, 255), (2, 0), (2, 0x80), (0, 0)]),
                             (b'', 1, 1, 1))
            # X fields ignored (S100 lower six bits, S200 lower nibble).
            self.assertEqual(await run([(2, 255), (2, 0x3f), (0, 0)]), (b'', 1, 1, 0))
            self.assertEqual(await run([(2, 255), (2, 0x4f), (0, 0)]), (b'', 1, 1, 0))

        sim.add_testbench(bench)
        sim.run()
