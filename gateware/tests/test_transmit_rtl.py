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
                    # Grant on the pins: the adapter sits behind the input
                    # flip-flops and cannot see it in this cycle.
                    self.assertEqual(ctx.get(dut.oe), 0)
                    self.assertEqual(p.tick(), 3)
                    await ctx.tick()
                    # The registered grant coincides with the PHY's turnaround
                    # idle. The adapter takes its first byte here, and its
                    # registered outputs reach the pins in the next cycle.
                    ctx.set(dut.grant, 1)
                    payload = b'' if empty else bytes(range(256))
                    offset = 0
                    errors = 0
                    for step in range(1100):
                        ctx.set(dut.valid, offset < len(payload))
                        ctx.set(dut.byte, (payload[min(offset, 255)] if payload else 0))
                        ctx.set(dut.last, offset == 255 and not truncated)
                        ready = ctx.get(dut.ready)
                        driven = p.tick(ctx.get(dut.ctl) if ctx.get(dut.oe) else None,
                                        ctx.get(dut.data))
                        if step == 0:
                            self.assertEqual(ctx.get(dut.oe), 0)
                            self.assertEqual(driven, 0)  # PHY turnaround idle
                        if ready:
                            offset += 1
                        await ctx.tick()
                        ctx.set(dut.grant, 0)
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
                self.assertEqual(p.tick(), 3)  # grant on the pins
                await ctx.tick()

                def supply():
                    ctx.set(dut.valid, 1)
                    ctx.set(dut.byte, 0xa5)
                    ctx.set(dut.last, 1)
                # Outputs are registered, so the byte must be offered one cycle
                # before the pin cycle that carries it: in the turnaround cycle
                # for no hold, otherwise while the last wanted hold is on the pins.
                ctx.set(dut.grant, 1)
                if wait == 0:
                    supply()
                self.assertEqual(ctx.get(dut.oe), 0)
                self.assertEqual(p.tick(), 0)  # PHY turnaround idle
                await ctx.tick()
                ctx.set(dut.grant, 0)
                for held in range(min(wait, 47)):
                    self.assertEqual(ctx.get(dut.oe), 1)
                    self.assertEqual(ctx.get(dut.ctl), 1)
                    if held == wait - 1:
                        supply()
                    p.tick(ctx.get(dut.ctl), ctx.get(dut.data))
                    await ctx.tick()
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

    def test_concatenated_speed_codes_and_illegal_downgrade(self):
        for speed in range(3):
            for config in range(8):
                multispeed, next_speed = config >= 4, config % 4
                dut = TransmitAdapter()
                sim = Simulator(dut)
                sim.add_clock(1 / 49_152_000)

                async def bench(ctx):
                    p = TransmitPhy()
                    p.grant(speed, multispeed=multispeed)
                    ctx.set(dut.speed, speed)
                    ctx.set(dut.multispeed, multispeed)
                    self.assertEqual(p.tick(), 3)  # grant on the pins
                    await ctx.tick()
                    # Registered grant during the PHY turnaround idle; the
                    # prebuffered byte is taken in this cycle.
                    ctx.set(dut.grant, 1)
                    ctx.set(dut.valid, 1)
                    ctx.set(dut.byte, 0xa5)
                    ctx.set(dut.last, 1)
                    ctx.set(dut.concatenate, 1)
                    ctx.set(dut.next_speed, next_speed)
                    self.assertEqual(ctx.get(dut.oe), 0)
                    self.assertEqual(p.tick(), 0)
                    await ctx.tick()
                    ctx.set(dut.grant, 0)
                    errors = 0
                    for _ in range(12):
                        p.tick(ctx.get(dut.ctl) if ctx.get(dut.oe) else None,
                               ctx.get(dut.data))
                        await ctx.tick()
                        errors += ctx.get(dut.config_error)
                        if ctx.get(dut.done):
                            break
                    else:
                        self.fail('concatenated termination failed')
                    invalid = multispeed and (next_speed == 3 or (speed > 0 and next_speed == 0))
                    self.assertEqual(errors, int(invalid))
                    self.assertEqual(p.completed[0].payload, b'\xa5')
                    self.assertEqual(p.completed[0].concatenate, not invalid)
                    self.assertEqual(p.completed[0].next_speed, speed if invalid or not multispeed else next_speed)
                    self.assertEqual(p.tick(), 0)

                sim.add_testbench(bench)
                sim.run()
