import unittest
from amaranth.sim import Simulator
from fw2usb.lreq import LreqSerializer
from sim.phy import RegisterPhy
from sim.registers import PhyRegisters


class RegisterTest(unittest.TestCase):
    def test_defaults_masks_pages_and_unknown_revision(self):
        p = PhyRegisters(contender=True, power_class=3, cps=True)
        self.assertEqual([p.read(a) for a in range(8)],
                         [1, 0x3f, 0xe2, 0x40, 0xc3, 0x10, 0, 0])
        for a in (0, 2, 3, 6):
            before = p.read(a)
            p.write(a, 255)
            self.assertEqual(p.read(a), before)
        p.write(4, 255)
        self.assertEqual(p.read(4), 0xc7)
        p.write(7, 0x3f)
        self.assertEqual(p.read(7), 0x2f)
        self.assertEqual([p.read(a) for a in range(8, 14)], [1, 0, 8, 0, 0x28, 0x42])
        with self.assertRaises(ValueError):
            p.read(14)
        for page in range(2, 7):
            p.write(7, page << 5)
            for a in range(8, 16):
                p.write(a, 255)
                self.assertEqual(p.read(a), 0)
        for port in range(2, 16):
            p.write(7, port)
            for a in range(8, 16):
                self.assertEqual(p.read(a), 0)

    def test_bus_reset_gap_counter_and_w1c(self):
        p = PhyRegisters(cps=True)
        p.write(1, 0xc5)
        p.write(5, 0xc3)
        p.self_id_complete(12, root=True)
        p.bus_reset()
        self.assertEqual(p.read(1), 0x85)
        self.assertFalse(p.physical_id_valid)
        self.assertEqual(p.read(0) & 3, 1)
        self.assertEqual(p.read(5), 0x93)
        p.bus_reset()
        self.assertEqual(p.read(1), 0xbf)
        p.write(1, 7)
        p.bus_reset()
        self.assertEqual(p.read(1), 7)
        p.set_cps(False)
        p.write(5, 0)
        self.assertEqual(p.read(5), 0x10)
        p.write(5, 0x10)
        self.assertEqual(p.read(5), 0)
        p.set_cps(True)
        p.set_cps(False)
        self.assertEqual(p.read(5), 0x10)

    def test_port_isolation_fault_and_software_reset(self):
        p = PhyRegisters(revision=0x1234)
        p.write(9, 0x10)
        p.write(8, 1)
        self.assertEqual(p.read(5) & 4, 4)
        p.write(7, 1)
        self.assertEqual(p.read(8), 0xf8)
        self.assertEqual(p.read(9), 0)
        p.ports[1][1] |= 8  # explicit external fault event
        p.write(9, 0)
        self.assertEqual(p.read(9), 8)
        p.write(9, 8)
        self.assertEqual(p.read(9), 0)
        p.write(7, 0x20)
        self.assertEqual([p.read(14), p.read(15)], [0x12, 0x34])
        p.write(7, 0xe0)
        p.write(8, 0x81)
        p.bus_reset()
        self.assertEqual(p.read(8), 0x81)
        p.write(14, 0x80)
        self.assertEqual(p.read(7), 0)
        p.write(7, 0xe0)
        self.assertEqual(p.read(8), 2)
        self.assertEqual(p.read(14), 0)

    def test_literal_requests_and_interrupted_read(self):
        p = RegisterPhy()
        # WRITE register7=0x20; READ registerA => vendor OUI high byte 08.
        for b in '11010111001000000':
            p.tick(int(b), receiving=True)
        self.assertEqual(p.registers.read(7), 0x20)
        for b in '110010100':
            first = p.tick(int(b), receiving=True)
        self.assertEqual(first[0], 2)
        p.tick(receiving=True)
        p.bus_reset()
        p.registers.write(7, 0)  # snapshot survives page change and reset
        pairs = [p.tick() for _ in range(8)]
        self.assertEqual([v for _, v in pairs], [0, 2, 2, 2, 0, 0, 2, 0])
        self.assertEqual(p.tick(), (0, 0))

    def test_rtl_serializer_to_register_model(self):
        dut = LreqSerializer()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)
        p = RegisterPhy()

        async def bench(ctx):
            for kind, address, data in [(5, 4, 0x47), (4, 4, 0)]:
                ctx.set(dut.kind, kind)
                ctx.set(dut.address, address)
                ctx.set(dut.data, data)
                ctx.set(dut.valid, 1)
                await ctx.tick()
                ctx.set(dut.valid, 0)
                for _ in range(17 if kind == 5 else 9):
                    p.tick(ctx.get(dut.lreq), receiving=True)
                    await ctx.tick()
            self.assertEqual(p.registers.read(4), 0x47)
            self.assertEqual([p.tick()[1] for _ in range(8)], [0, 0, 1, 0, 1, 0, 1, 3])

        sim.add_testbench(bench)
        sim.run()
