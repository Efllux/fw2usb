import unittest
from amaranth.sim import Simulator
from fw2usb.recovery import PhyRecovery

class RecoveryTest(unittest.TestCase):
    def test_preserves_rhb_waits_for_real_reset_and_fails_closed(self):
        d=PhyRecovery(timeout_cycles=80);sim=Simulator(d);sim.add_clock(1/49_152_000)
        async def bench(ctx):
            for rhb in [0,1]:
                ctx.set(d.start,1);await ctx.tick();ctx.set(d.start,0)
                self.assertTrue(ctx.get(d.active));self.assertEqual(ctx.get(d.kind),4);self.assertEqual(ctx.get(d.address),1)
                ctx.set(d.ready,1);await ctx.tick();ctx.set(d.ready,0)
                ctx.set(d.register_valid,1);ctx.set(d.register_address,1);ctx.set(d.register_data,rhb<<7|5);await ctx.tick();ctx.set(d.register_valid,0)
                self.assertEqual(ctx.get(d.kind),5);self.assertEqual(ctx.get(d.data),0x7f|rhb<<7)
                ctx.set(d.ready,1);await ctx.tick();ctx.set(d.ready,0);await ctx.tick().repeat(5)
                self.assertTrue(ctx.get(d.active));ctx.set(d.bus_reset,1);await ctx.tick();ctx.set(d.bus_reset,0)
                self.assertFalse(ctx.get(d.active));self.assertFalse(ctx.get(d.failed))
            ctx.set(d.start,1);await ctx.tick();ctx.set(d.start,0);await ctx.tick().repeat(82)
            self.assertTrue(ctx.get(d.failed));self.assertFalse(ctx.get(d.valid));self.assertFalse(ctx.get(d.active))
        sim.add_testbench(bench);sim.run()
