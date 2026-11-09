import unittest
from amaranth.sim import Simulator
from fw2usb.phy_link import PhyLink
from sim.phy import LreqDecoder, receive_samples
from sim.transmit import TransmitPhy


class PhyLinkTest(unittest.TestCase):
    def test_request_grant_tx_rx_status_and_reset(self):
        dut = PhyLink()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            ctx.set(dut.request.kind, 3)
            ctx.set(dut.request.speed, 4)
            ctx.set(dut.request.valid, 1)
            await ctx.tick()
            ctx.set(dut.request.valid, 0)
            decoder = LreqDecoder()
            for _ in range(8):
                decoder.sample(ctx.get(dut.lreq))
                await ctx.tick()
            self.assertEqual(decoder.pending_bus.payload, 4)
            self.assertTrue(ctx.get(dut.pending))
            self.assertFalse(ctx.get(dut.request.ready))
            phy = TransmitPhy()
            phy.grant(2)
            ctx.set(dut.ctl_in, 3)
            phy.tick()
            await ctx.tick()
            ctx.set(dut.ctl_in, 0)
            phy.tick()
            await ctx.tick()
            ctx.set(dut.tx.valid, 1)
            ctx.set(dut.tx.byte, 0xa5)
            ctx.set(dut.tx.last, 1)
            # Echoing our output on shared CTL must not start our RX decoder.
            for _ in range(5):
                oe = ctx.get(dut.oe)
                ctl = ctx.get(dut.ctl_out)
                data = ctx.get(dut.data_out)
                ctx.set(dut.ctl_in, ctl if oe else 0)
                ctx.set(dut.data_in, data)
                phy.tick(ctl if oe else None, data)
                await ctx.tick()
                self.assertFalse(ctx.get(dut.rx.start))
                if ctx.get(dut.tx.done):
                    break
            self.assertEqual(phy.completed[0].payload, b'\xa5')
            ctx.set(dut.ctl_in, 0)
            await ctx.tick()
            got = []
            for ctl, data in receive_samples(b'\x12\xa5', speed=1):
                ctx.set(dut.ctl_in, ctl)
                ctx.set(dut.data_in, data)
                await ctx.tick()
                if ctx.get(dut.rx.valid):
                    got.append(ctx.get(dut.rx.byte))
            self.assertEqual(got, [0x12, 0xa5])
            for pair in (0, 0, 0, 2, 3, 2, 0, 2):
                ctx.set(dut.ctl_in, 1)
                ctx.set(dut.data_in, pair << 6)
                await ctx.tick()
            self.assertEqual(ctx.get(dut.status.data), 0xe2)
            self.assertTrue(ctx.get(dut.status.register_valid))
            ctx.set(dut.enable, 0)
            await ctx.tick()
            self.assertFalse(ctx.get(dut.oe))
            self.assertFalse(ctx.get(dut.pending))

        sim.add_testbench(bench)
        sim.run()
