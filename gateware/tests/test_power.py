import unittest
from fractions import Fraction
from sim.power import InterfacePower


class PowerTest(unittest.TestCase):
    def boot(self, p, *, ports_active=True):
        p.update(0, lps=True, ports_active=ports_active)
        delay = p.wake_ns if ports_active else p.low_power_wake_ns
        p.update(delay, lps=True, ports_active=ports_active)
        self.assertTrue(p.clock_running)
        self.assertEqual([p.sample_sclk() for _ in range(9)],
                         [(0, 0)] * 7 + [(2, 255), (0, 0)])
        self.assertTrue(p.operational)
        return delay

    def test_boot_and_low_power_corners(self):
        for delay in (5_300_000, 7_300_000):
            p = InterfacePower(low_power_wake_ns=delay)
            self.boot(p, ports_active=False)
        p = InterfacePower()
        p.update(0, lps=True)
        p.update(59, lps=True)
        self.assertFalse(p.clock_running)
        with self.assertRaises(ValueError):
            p.sample_sclk()
        p.update(60, lps=True)
        self.assertTrue(p.clock_running)

    def test_reset_disable_restore_and_independent_time(self):
        for reset, disable in ((2600, 26030), (2680, 26110)):
            p = InterfacePower(reset_ns=reset, disable_ns=disable)
            self.boot(p)
            p.update(1000, lps=False)
            p.update(1000 + reset - 1, lps=False)
            self.assertTrue(p.operational)
            p.update(1000 + reset, lps=False)
            self.assertEqual(p.state, 'reset')
            self.assertEqual(p.sample_sclk(), (0, 0))
            self.assertEqual(p.reset_epoch, 1)
            p.update(1000 + disable, lps=False)
            self.assertFalse(p.clock_running)
            p.update(100_000, lps=True)
            p.update(100_060, lps=True)
            self.assertTrue(p.clock_running)
            self.assertEqual([p.sample_sclk() for _ in range(9)],
                             [(0, 0)] * 7 + [(2, 255), (0, 0)])

    def test_short_deassertion_does_not_reset(self):
        p = InterfacePower()
        self.boot(p)
        p.update(1000, lps=False)
        p.update(3500, lps=True)
        self.assertTrue(p.operational)
        self.assertEqual(p.reset_epoch, 0)
        # Rational timestamps preserve sub-nanosecond phase differences.
        p.update(Fraction(7001, 2), lps=True)
        with self.assertRaises(ValueError):
            p.update(3500, lps=True)

    def test_interface_reset_flushes_reads_but_preserves_registers(self):
        from sim.phy import PoweredRegisterPhy
        p = PoweredRegisterPhy()
        p.update(0, lps=True)
        p.update(60, lps=True)
        for _ in range(9):
            p.sample_sclk(1)  # ignored during initialization
        self.assertEqual(p.phy.requests.bits, [])
        p.phy.registers.write(4, 0xc5)
        for bit in '110001000':  # read register4; RX blocks status
            p.sample_sclk(int(bit), receiving=True)
        self.assertIsNotNone(p.phy.status.read_pending)
        p.bus_reset()
        self.assertIsNotNone(p.phy.status.read_pending)
        p.update(1000, lps=False)
        p.update(3680, lps=False)
        self.assertIsNone(p.phy.status.read_pending)
        self.assertEqual(p.phy.registers.read(4), 0xc5)
        p.bus_reset()
        self.assertEqual(p.phy.status.flags, 0)
        self.assertEqual(p.sample_sclk(1), (0, 0))
        p.update(20_000, lps=True)
        for _ in range(9):
            p.sample_sclk(1)
        self.assertEqual(p.phy.requests.bits, [])
        self.assertEqual(p.sample_sclk(), (0, 0))
