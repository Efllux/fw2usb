import unittest
from amaranth.sim import Simulator
from fw2usb.lreq import LreqSerializer
from sim.phy import LreqDecoder, RequestKind


class LreqTest(unittest.TestCase):
    def test_all_types_wire_order_and_model(self):
        dut = LreqSerializer()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            # Independently written literal pin vectors, not encoder round trips.
            vectors = [
                (0, 0, 0, 0, 0, '10000000', 0),
                (1, 2, 0, 0, 0, '10010100', 2),
                (2, 4, 0, 0, 0, '10101000', 4),
                (3, 1, 0, 0, 0, '10110010', 1),
                (4, 0, 10, 0, 0, '110010100', 10),
                (5, 0, 3, 165, 0, '11010011101001010', 0x3a5),
                (6, 0, 0, 0, 1, '111010', 1),
            ]
            for kind, speed, address, data, accel, expected, payload in vectors:
                model = LreqDecoder()
                ctx.set(dut.kind, kind)
                ctx.set(dut.speed, speed)
                ctx.set(dut.address, address)
                ctx.set(dut.data, data)
                ctx.set(dut.accel, accel)
                self.assertEqual(ctx.get(dut.ready), 1)
                ctx.set(dut.valid, 1)
                await ctx.tick()
                ctx.set(dut.valid, 0)
                # Changing inputs while busy cannot alter the captured request.
                ctx.set(dut.data, 0)
                observed, decoded = '', []
                for _ in expected:
                    self.assertEqual(ctx.get(dut.ready), 0)
                    bit = ctx.get(dut.lreq)
                    observed += str(bit)
                    r = model.sample(bit)
                    if r is not None:
                        decoded.append(r)
                    await ctx.tick()
                self.assertEqual(observed, expected)
                self.assertEqual(len(decoded), 1)
                self.assertEqual(decoded[0].kind, kind)
                self.assertEqual(decoded[0].payload, payload)
                self.assertEqual(ctx.get(dut.lreq), 0)
                self.assertEqual(ctx.get(dut.ready), 1)
                await ctx.tick()
            ctx.set(dut.kind, 7)
            ctx.set(dut.valid, 1)
            await ctx.tick()
            self.assertEqual(ctx.get(dut.ready), 0)
            self.assertEqual(ctx.get(dut.lreq), 0)

        sim.add_testbench(bench)
        sim.run()

    def test_pending_rules_and_loss(self):
        p = LreqDecoder()

        def send(bits, receiving=False):
            result = None
            for b in bits:
                result = p.sample(int(b), receiving=receiving) or result
            return result

        send('10110100')  # fair S200
        self.assertEqual(p.pending_bus.kind, RequestKind.FAIR)
        send('10011000')  # iso ignored while another bus request pending
        self.assertEqual(p.pending_bus.kind, RequestKind.FAIR)
        p.sample(0, receiving=True)
        self.assertIsNone(p.pending_bus)
        send('10101000', receiving=True)  # priority in RX ignored
        self.assertIsNone(p.pending_bus)
        send('10011000')
        p.sample(0, receiving=True)
        self.assertEqual(p.pending_bus.kind, RequestKind.ISOCHRONOUS)
        p.bus_reset()
        self.assertIsNone(p.pending_bus)
        send('111000')
        self.assertFalse(p.acceleration_enabled)
        send('10010100')
        self.assertTrue(p.acceleration_enabled)
        self.assertEqual(p.grant().payload, 2)
        self.assertIsNone(p.pending_bus)

    def test_short_bus_form_and_invalid_speed(self):
        for speed in range(8):
            p = LreqDecoder()
            bits = '1000' + format(speed, '03b') + '0'
            result = None
            for bit in bits:
                result = p.sample(int(bit)) or result
            self.assertEqual(result.payload, speed)
            self.assertEqual(result.null_packet, speed not in (0, 2, 4))
