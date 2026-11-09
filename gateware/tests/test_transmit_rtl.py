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

    def test_initial_hold_limit_and_timeout(self):
        for wait in (0, 1, 47, 48):
            dut = TransmitAdapter()
            sim = Simulator(dut)
            sim.add_clock(1 / 49_152_000)

            async def bench(ctx):
                p = TransmitPhy()
                p.grant(2)
                ctx.set(dut.speed, 2)
                ctx.set(dut.allow_hold, 1)
                ctx.set(dut.grant, 1)
                p.tick()
                await ctx.tick()
                ctx.set(dut.grant, 0)
                p.tick()
                await ctx.tick()
                for _ in range(min(wait, 47)):
                    self.assertEqual(ctx.get(dut.ctl), 1)
                    p.tick(ctx.get(dut.ctl), ctx.get(dut.data))
                    await ctx.tick()
                if wait <= 47:
                    ctx.set(dut.valid, 1)
                    ctx.set(dut.byte, 0xa5)
                    ctx.set(dut.last, 1)
                errors = 0
                for _ in range(8):
                    p.tick(ctx.get(dut.ctl) if ctx.get(dut.oe) else None,
                           ctx.get(dut.data))
                    await ctx.tick()
                    errors += ctx.get(dut.underrun)
                    if ctx.get(dut.done):
                        break
                else:
                    self.fail('hold timeout failed to terminate')
                self.assertEqual(errors, int(wait > 47))
                self.assertEqual(p.completed[0].payload, b'\xa5' if wait <= 47 else b'')
                self.assertEqual(p.tick(), 0)

            sim.add_testbench(bench)
            sim.run()
