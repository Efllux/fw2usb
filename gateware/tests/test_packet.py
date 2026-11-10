import subprocess
import unittest
from amaranth.sim import Simulator
from fw2usb.packet import PacketReceiver


class PacketTest(unittest.TestCase):
    def test_rust_wire_vectors_crc_and_length_errors(self):
        result = subprocess.run(['cargo', 'run', '--quiet', '-p', 'fw-1394', '--example', 'packet_vectors'],
                                check=True, capture_output=True, text=True)
        packets = [bytes.fromhex(line) for line in result.stdout.splitlines()]
        dut = PacketReceiver()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            for packet in packets:
                cases = [(packet, True), (packet[:-1], False)]
                damaged = bytearray(packet)
                damaged[4] ^= 1
                cases.append((damaged, False))
                if len(packet) > 12 and packet[3] >> 4 == 10:
                    damaged = bytearray(packet)
                    damaged[8] ^= 1
                    cases.append((damaged, False))
                for data, good in cases:
                    ctx.set(dut.start, 1)
                    await ctx.tick()
                    ctx.set(dut.start, 0)
                    for byte in data:
                        ctx.set(dut.valid, 1)
                        ctx.set(dut.byte, byte)
                        await ctx.tick()
                    ctx.set(dut.valid, 0)
                    ctx.set(dut.end, 1)
                    await ctx.tick()
                    ctx.set(dut.end, 0)
                    self.assertEqual(ctx.get(dut.good), good, bytes(data).hex())
                    self.assertEqual(ctx.get(dut.bad), not good)

        sim.add_testbench(bench)
        sim.run()

    def test_tx_matches_rust_wire_with_backpressure(self):
        from fw2usb.packet import PacketTransmitter
        result = subprocess.run(['cargo', 'run', '--quiet', '-p', 'fw-1394', '--example', 'packet_vectors'],
                                check=True, capture_output=True, text=True)
        packets = [bytes.fromhex(line) for line in result.stdout.splitlines()]
        dut = PacketTransmitter()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            for packet in packets:
                iso = packet[3] >> 4 == 10
                hlen = 4 if iso else 12
                length = int.from_bytes(packet[:2], 'big') if iso else 0
                source = packet[:hlen] + packet[hlen+4:hlen+4+length]
                ctx.set(dut.start, 1)
                ctx.set(dut.has_data, length > 0)
                await ctx.tick()
                ctx.set(dut.start, 0)
                got = bytearray()
                index = 0
                for cycle in range(400):
                    ctx.set(dut.valid, index < len(source))
                    ctx.set(dut.byte, source[min(index, len(source)-1)])
                    ctx.set(dut.header_last, index == hlen-1)
                    ctx.set(dut.data_last, index == len(source)-1)
                    ctx.set(dut.out_ready, cycle % 7 not in (1, 2))
                    if ctx.get(dut.ready) and index < len(source):
                        index += 1
                    last = False
                    if ctx.get(dut.out_valid) and ctx.get(dut.out_ready):
                        got.append(ctx.get(dut.out_byte))
                        last = ctx.get(dut.out_last)
                    await ctx.tick()
                    if last:
                        break
                else:
                    self.fail('TX did not finish')
                self.assertEqual(bytes(got), packet)

        sim.add_testbench(bench)
        sim.run()
