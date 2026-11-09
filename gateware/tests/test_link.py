import subprocess
import unittest
from amaranth.sim import Simulator
from fw2usb.link import Crc32, CycleTimer, SelfIdCapture


class LinkTest(unittest.TestCase):
    def test_crc_rust_shared_golden_vectors(self):
        result = subprocess.run(['cargo', 'run', '--quiet', '-p', 'fw-1394', '--example', 'crc_vectors'],
                                check=True, capture_output=True, text=True)
        vectors = [line.split() for line in result.stdout.splitlines()]
        dut = Crc32()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            for data, expected in vectors:
                ctx.set(dut.clear, 1)
                await ctx.tick()
                ctx.set(dut.clear, 0)
                for byte in bytes.fromhex(data) if data != '-' else b'':
                    ctx.set(dut.valid, 1)
                    ctx.set(dut.byte, byte)
                    await ctx.tick()
                ctx.set(dut.valid, 0)
                self.assertEqual(ctx.get(dut.value), int(expected, 16))

        sim.add_testbench(bench)
        sim.run()

    def test_cycle_rollover_root_and_backpressure(self):
        dut = CycleTimer()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            ctx.set(dut.root, 1)
            ctx.set(dut.enable, 1)
            ctx.set(dut.load_value, (127 << 25) | (7999 << 12) | 3071)
            ctx.set(dut.load, 1)
            await ctx.tick()
            ctx.set(dut.load, 0)
            await ctx.tick().repeat(2)
            self.assertEqual(ctx.get(dut.value), 0)
            self.assertTrue(ctx.get(dut.cycle_start_valid))
            await ctx.tick().repeat(6144)
            self.assertEqual(ctx.get(dut.value), 1 << 12)
            self.assertEqual(ctx.get(dut.missed), 1)
            ctx.set(dut.cycle_start_ready, 1)
            await ctx.tick()
            self.assertFalse(ctx.get(dut.cycle_start_valid))
            ctx.set(dut.root, 0)
            await ctx.tick().repeat(6144)
            self.assertFalse(ctx.get(dut.cycle_start_valid))

        sim.add_testbench(bench)
        sim.run()

    def test_selfid_literal_inverse_and_corruption(self):
        dut = SelfIdCapture()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            for damaged in (False, True):
                ctx.set(dut.start, 1)
                await ctx.tick()
                ctx.set(dut.start, 0)
                for byte in bytes.fromhex('814308a0 7ebcf75f' if not damaged else '814308a0 7ebcf75e'):
                    ctx.set(dut.valid, 1)
                    ctx.set(dut.byte, byte)
                    await ctx.tick()
                ctx.set(dut.valid, 0)
                ctx.set(dut.end, 1)
                await ctx.tick()
                ctx.set(dut.end, 0)
                self.assertEqual(ctx.get(dut.accept), not damaged)
                self.assertEqual(ctx.get(dut.error), damaged)
                if not damaged:
                    self.assertEqual(ctx.get(dut.physical_id), 1)

        sim.add_testbench(bench)
        sim.run()
