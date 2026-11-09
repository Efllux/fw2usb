import unittest
from amaranth.sim import Simulator
from fw2usb.status import StatusReceiver
from sim.phy import StatusSource


class StatusTest(unittest.TestCase):
    def test_literal_status_and_all_interrupt_positions(self):
        # flags 1011, address 0110, data 10100101, explicit MSB-first D0/D1.
        pairs = [2, 3, 1, 2, 2, 2, 1, 1]
        dut = StatusReceiver()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            for length in range(1, 9):
                ctx.set(dut.ctl, 0)
                await ctx.tick()
                for index, pair in enumerate(pairs[:length]):
                    ctx.set(dut.ctl, 1)
                    ctx.set(dut.pair, pair)
                    await ctx.tick()
                    self.assertEqual(ctx.get(dut.flags_valid), index in (0, 1))
                    self.assertEqual(ctx.get(dut.register_valid), index == 7)
                    self.assertEqual(ctx.get(dut.flags_mask),
                                     (0b1100, 0b0011)[index] if index < 2 else 0)
                    if index == 0:
                        self.assertEqual(ctx.get(dut.flags) & 0b1100, 0b1000)
                    if index == 1:
                        self.assertEqual(ctx.get(dut.flags), 0b1011)
                    if index == 7:
                        self.assertEqual(ctx.get(dut.address), 6)
                        self.assertEqual(ctx.get(dut.data), 0xa5)
                ctx.set(dut.ctl, 2)  # RX preempts even without intervening idle
                await ctx.tick()
                self.assertEqual(ctx.get(dut.flags_valid), 0)
                self.assertEqual(ctx.get(dut.register_valid), 0)
            # Back-to-back short statuses separated by one idle sample.
            for flags in range(16):
                ctx.set(dut.ctl, 0)
                await ctx.tick()
                for pair in (flags >> 2, flags & 3):
                    ctx.set(dut.ctl, 1)
                    ctx.set(dut.pair, pair)
                    await ctx.tick()
                self.assertEqual(ctx.get(dut.flags), flags)
                self.assertEqual(ctx.get(dut.flags_valid), 1)
                self.assertEqual(ctx.get(dut.register_valid), 0)

        sim.add_testbench(bench)
        sim.run()

    def test_register_retry_reset_persistence_and_idle(self):
        for cut in range(1, 8):
            p = StatusSource()
            p.flags = 0xb
            p.request_read(6, 0xa5)
            for _ in range(cut):
                self.assertEqual(p.tick()[0], 1)
            p.tick(receiving=True)
            p.request_read(9, 0xff)  # ignored while original read pending
            p.bus_reset()
            self.assertEqual(p.tick(), (0, 0))  # post-RX idle
            result = [p.tick() for _ in range(8)]
            self.assertEqual([pair for _, pair in result[2:]], [1, 2, 2, 2, 1, 1])
            self.assertIsNone(p.read_pending)
            p.flags = 1
            self.assertEqual(p.tick(), (0, 0))  # mandatory idle before new status
            self.assertEqual(p.tick(), (1, 0))
            self.assertEqual(p.tick(), (1, 1))
            self.assertEqual(p.tick(), (0, 0))

    def test_delivered_flags_not_retried(self):
        p = StatusSource()
        p.flags = 0xf
        self.assertEqual(p.tick(), (1, 3))
        p.tick(receiving=True)
        self.assertEqual(p.tick(), (0, 0))
        self.assertEqual(p.tick(), (1, 0))
        self.assertEqual(p.tick(), (1, 3))
        self.assertEqual(p.tick(), (0, 0))
        self.assertEqual(p.tick(), (0, 0))

    def test_new_flags_during_active_snapshot_are_retained(self):
        p = StatusSource()
        p.flags = 0b1000
        self.assertEqual(p.tick(), (1, 2))
        p.flags |= 0b0001  # arrives after snapshot, before second pair
        self.assertEqual(p.tick(), (1, 0))
        self.assertEqual(p.flags, 1)
        self.assertEqual(p.tick(), (0, 0))
        self.assertEqual(p.tick(), (1, 0))
        self.assertEqual(p.tick(), (1, 1))
        self.assertEqual(p.flags, 0)
