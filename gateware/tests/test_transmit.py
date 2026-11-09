import unittest
from sim.transmit import TransmitPhy, Transmission


class TransmitTest(unittest.TestCase):
    def start(self, speed=0, multispeed=False):
        p = TransmitPhy()
        p.grant(speed, multispeed=multispeed)
        self.assertEqual(p.tick(), 3)
        self.assertEqual(p.tick(), 0)
        self.assertIsNone(p.phy_ctl)
        return p

    def finish(self, p, ctl=0, data=0):
        p.tick(ctl, data)
        p.tick(0)
        self.assertEqual(p.tick(), 0)
        self.assertEqual(p.state, 'idle')

    def test_literal_data_all_widths_and_turnaround(self):
        # Literal A5 vectors independent of any serializer/formatter.
        for speed, values in [(0, [0x80, 0x80, 0x40, 0x40]),
                              (1, [0xa0, 0x50]), (2, [0xa5])]:
            for hold in (0, 1, 47):
                p = self.start(speed)
                p.tick(0)  # optional initial idle
                for _ in range(hold):
                    p.tick(1)
                for v in values:
                    p.tick(2, v)
                self.finish(p)
                self.assertEqual(p.completed, [Transmission(b'\xa5', speed, False, speed)])

    def test_cancel_and_null(self):
        for hold in (0, 1, 47):
            p = self.start()
            p.tick(0)
            for _ in range(hold):
                p.tick(1)
            self.finish(p)
            self.assertEqual(p.completed[0].payload, b'')

    def test_concatenation_and_multispeed(self):
        p = self.start(2, True)
        p.tick(2, 0xa5)
        self.finish(p, 1, 0x40)
        self.assertEqual(p.completed, [Transmission(b'\xa5', 2, True, 1)])
        # Next grant deliberately external: no invented packet separation.
        p.grant(1)
        p.tick()
        p.tick()
        p.tick(2, 0x50)
        p.tick(2, 0xa0)
        self.finish(p)
        self.assertEqual(p.completed[1].payload, b'\x5a')
        p = self.start(2, True)
        p.tick(2, 0)
        with self.assertRaises(ValueError):
            p.tick(1, 0)  # forbidden faster->S100

    def test_hold_overrun_partial_data_collision_and_reset(self):
        p = TransmitPhy()
        p.grant(0)
        with self.assertRaises(ValueError):
            p.tick(0)
        p = self.start()
        for _ in range(47):
            p.tick(1)
        with self.assertRaises(ValueError):
            p.tick(1)
        p = self.start()
        p.tick(2, 0x80)
        with self.assertRaises(ValueError):
            p.tick(0)
        p.bus_reset()
        self.assertEqual(p.state, 'idle')
        self.assertEqual(p.completed, [])
        self.assertEqual(p.aborted, [b''])
        p = self.start(2)
        p.tick(2, 0xa5)
        p.tick(0)
        with self.assertRaises(ValueError):
            p.tick(2)
        p.tick(0)
        with self.assertRaises(ValueError):
            p.tick(0)  # PHY reclaim idle owns bus
