import unittest
from amaranth.sim import Simulator
from fw2usb.transmit import TransmitAdapter
from sim.transmit import TransmitPhy


class TransmitRtlTest(unittest.TestCase):
    def test_widths_packets_and_underrun(self):
        dut = TransmitAdapter()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            for speed in range(3):
                for truncated, empty in ((False, False), (True, False), (True, True)):
                    p = TransmitPhy()
                    p.grant(speed)
                    ctx.set(dut.speed, speed)
                    ctx.set(dut.grant, 1)
                    self.assertEqual(ctx.get(dut.oe), 0)
                    self.assertEqual(p.tick(), 3)
                    await ctx.tick()
                    ctx.set(dut.grant, 0)
                    self.assertEqual(ctx.get(dut.oe), 0)
                    self.assertEqual(p.tick(), 0)
                    await ctx.tick()
                    payload = b'' if empty else bytes(range(256))
                    offset = 0
                    errors = 0
                    for _ in range(1100):
                        ctx.set(dut.valid, offset < len(payload))
                        ctx.set(dut.byte, (payload[min(offset, 255)] if payload else 0))
                        ctx.set(dut.last, offset == 255 and not truncated)
                        ready = ctx.get(dut.ready)
                        p.tick(ctx.get(dut.ctl) if ctx.get(dut.oe) else None,
                               ctx.get(dut.data))
                        if ready:
                            offset += 1
                        await ctx.tick()
                        errors += ctx.get(dut.underrun)
                        if ctx.get(dut.done):
                            break
                    else:
                        self.fail('transmitter failed to terminate')
                    self.assertEqual(errors, int(truncated))
                    self.assertEqual(ctx.get(dut.oe), 0)
                    self.assertEqual(p.tick(), 0)  # reclaim idle
                    self.assertEqual(p.completed[0].payload, payload)
                    await ctx.tick()

        sim.add_testbench(bench)
        sim.run()
