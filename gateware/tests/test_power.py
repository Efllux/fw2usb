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
        p.phy.requests.acceleration_enabled = False
        p.update(1000, lps=False)
        p.update(3680, lps=False)
        self.assertFalse(p.phy.requests.acceleration_enabled)
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

    def test_linkon_all_interrupt_combinations_latch_and_wave(self):
        from sim.power import LinkOn
        for reg in range(256):
            p = LinkOn()
            expected = bool(reg & 4 or (reg & 0x80 and reg & 0x38))
            self.assertEqual(p.update(0, link_active=False, register5=reg), expected)
            self.assertEqual(p.update(1, link_active=True, register5=reg), 0)
        p = LinkOn()
        self.assertEqual(p.update(0, link_active=False, register5=0,
                                  addressed_packet=True), 1)
        self.assertEqual(p.update(p.period_ns / 2, link_active=False, register5=0), 0)
        self.assertEqual(p.update(p.period_ns, link_active=False, register5=0), 1)
        self.assertEqual(p.update(200, link_active=False, register5=0, bus_reset=True), 0)
        self.assertEqual(p.update(201, link_active=False, register5=4, bus_reset=True), 1)
        # Clearing interrupt alone does not clear a latched wake indication.
        self.assertEqual(p.update(202, link_active=False, register5=0), 1)
        self.assertIsNone(p.update(203, link_active=False, register5=0, hardware_reset=True))

    def test_software_reset_restarts_clock_and_clears_pending_read(self):
        from sim.phy import PoweredRegisterPhy
        p = PoweredRegisterPhy()
        p.update(0, lps=True)
        p.update(60, lps=True)
        for _ in range(9):
            p.sample_sclk()
        p.phy.registers.write(7, 0xe0)
        for bit in '110001000':
            p.sample_sclk(int(bit), receiving=True)
        self.assertIsNotNone(p.phy.status.read_pending)
        # WRITE page7:E = 80, SWR. Literal 1|101|1110|10000000|0.
        for bit in '11011110100000000':
            p.sample_sclk(int(bit), receiving=True)
        self.assertFalse(p.power.clock_running)
        self.assertEqual(p.power.state, 'initializing')
        self.assertIsNone(p.phy.status.read_pending)
        self.assertEqual(p.phy.registers.read(7), 0)
        p.update(120, lps=True)
        self.assertEqual([p.sample_sclk() for _ in range(9)],
                         [(0, 0)] * 7 + [(2, 255), (0, 0)])

    def test_linkon_register_power_composition(self):
        from sim.phy import PoweredRegisterPhy
        p = PoweredRegisterPhy()
        p.phy.registers.write(5, 0x80)  # RPIE enables reset-default CPSI wake
        self.assertEqual(p.linkon_pin(), 1)
        p.update(0, lps=True)
        p.update(60, lps=True)
        self.assertEqual(p.linkon_pin(), 0)
        p.phy.registers.write(4, 0)  # LCtrl inactive; PHY interface stays operational
        self.assertEqual(p.linkon_pin(), 1)
        p.phy.registers.write(5, 0x10)  # clear CPSI and RPIE; latch persists
        self.assertEqual(p.linkon_pin(), 1)
        p.bus_reset()
        self.assertEqual(p.linkon_pin(), 0)
