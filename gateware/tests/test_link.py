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

    def test_ack_checks_and_policy(self):
        from fw2usb.link import AckReceiver
        dut = AckReceiver()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            ctx.set(dut.valid, 1)
            for byte in range(256):
                ctx.set(dut.byte, byte)
                await ctx.tick()
                good = ((byte >> 4) ^ (byte & 15)) == 15
                self.assertEqual(ctx.get(dut.accept), good)
                self.assertEqual(ctx.get(dut.error), not good)

        sim.add_testbench(bench)
        sim.run()

    def test_cycle_start_packet_and_root_gating(self):
        from fw2usb.cycle_master import CycleMaster
        dut = CycleMaster()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            ctx.set(dut.timer.root, 1)
            ctx.set(dut.timer.enable, 1)
            ctx.set(dut.timer.load, 1)
            ctx.set(dut.timer.load_value, 3071)
            await ctx.tick()
            ctx.set(dut.timer.load, 0)
            await ctx.tick().repeat(2)
            self.assertFalse(ctx.get(dut.request))
            await ctx.tick().repeat(34)
            self.assertTrue(ctx.get(dut.request))
            timestamp = ctx.get(dut.timer.value)
            ctx.set(dut.grant, 1)
            await ctx.tick()
            ctx.set(dut.grant, 0)
            ctx.set(dut.ready, 1)
            got = bytearray()
            for _ in range(20):
                last = False
                if ctx.get(dut.valid):
                    got.append(ctx.get(dut.byte))
                    last = ctx.get(dut.last)
                await ctx.tick()
                if last:
                    break
            self.assertEqual(got[:8], bytes.fromhex('ffff008f ffc0ffff'))
            self.assertEqual(got[8:12], bytes.fromhex('f0000200'))
            self.assertEqual(got[12:16], timestamp.to_bytes(4, 'big'))
            # Independent polynomial-division check, not an RTL roundtrip.
            dividend = int.from_bytes(got[:16], 'big') << 32
            dividend ^= 0xffffffff << (16 * 8)
            polynomial = (1 << 32) | 0x04c11db7
            for bit in range(dividend.bit_length()-1, 31, -1):
                if dividend & (1 << bit):
                    dividend ^= polynomial << (bit-32)
            self.assertEqual(got[16:], (dividend ^ 0xffffffff).to_bytes(4, 'big'))

        sim.add_testbench(bench)
        sim.run()
