import unittest
from amaranth.sim import Simulator
from fw2usb.link_layer import LinkLayer
from sim.phy import LreqDecoder, receive_samples
from sim.transmit import TransmitPhy
from sim.bus import Bus
from sim.devices import BeBoB, CSR
from sim.transactions import Client, Peer


class LinkLayerTest(unittest.TestCase):
    def test_bus_selfid_and_rom_reply_through_phy_pins(self):
        bus = Bus([(0,1)],nodes=2,root=0)
        peer = BeBoB()
        Peer(bus,1,peer)
        client = Client(bus,0)
        bus.reset()
        bus.run()
        client.submit(0xffc0 | bus.ids[1],CSR+0x400,tcode=5,length=len(peer.rom))
        bus.run()
        sid_packets = [v for _,k,v in bus.received[0] if k == 'selfid']
        replies = [v.data for _,k,v in bus.received[0] if k == 'packet' and len(v.data)>1]
        dut = LinkLayer()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            accepted = []
            for sid in sid_packets:
                ctx.set(dut.selfid_phase,1)
                for ctl,data in list(receive_samples(sid,speed=0))+[(0,0)]*3:
                    ctx.set(dut.phy.ctl_in,ctl)
                    ctx.set(dut.phy.data_in,data)
                    await ctx.tick()
                    if ctx.get(dut.selfid.accept):
                        accepted.append(ctx.get(dut.selfid.physical_id))
            self.assertEqual(accepted,[0,1])
            ctx.set(dut.selfid_phase,0)
            good = 0
            for reply in replies:
                for ctl,data in list(receive_samples(reply,speed=2))+[(0,0)]*3:
                    ctx.set(dut.phy.ctl_in,ctl)
                    ctx.set(dut.phy.data_in,data)
                    await ctx.tick()
                    good += ctx.get(dut.packet.good)
            self.assertEqual(good,len(replies))

        sim.add_testbench(bench)
        sim.run()

    def test_cycle_master_automatic_request_and_phy_wire_tx(self):
        dut = LinkLayer()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            ctx.set(dut.cycle.timer.root,1)
            ctx.set(dut.cycle.timer.enable,1)
            ctx.set(dut.timer_load,1)
            ctx.set(dut.timer_value,3071)
            await ctx.tick()
            ctx.set(dut.timer_load,0)
            decoder = LreqDecoder()
            for _ in range(70):
                decoder.sample(ctx.get(dut.phy.lreq))
                await ctx.tick()
                if decoder.pending_bus is not None:
                    break
            else:
                self.fail('cycle request never serialized')
            self.assertEqual(int(decoder.pending_bus.kind),2)
            self.assertEqual(decoder.pending_bus.payload,0)
            phy = TransmitPhy()
            phy.grant(0)
            ctx.set(dut.phy.ctl_in,3)
            phy.tick()
            await ctx.tick()
            ctx.set(dut.phy.ctl_in,0)
            phy.tick()
            await ctx.tick()
            for _ in range(120):
                phy.tick(ctx.get(dut.phy.ctl_out) if ctx.get(dut.phy.oe) else None,
                         ctx.get(dut.phy.data_out))
                await ctx.tick()
                if ctx.get(dut.phy.tx.done):
                    break
            else:
                self.fail('cycle packet never finished')
            self.assertEqual(len(phy.completed),1)
            self.assertEqual(len(phy.completed[0].payload),20)
            self.assertEqual(phy.completed[0].payload[:4],bytes.fromhex('ffff008f'))

        sim.add_testbench(bench)
        sim.run()

    def test_speculative_immediate_ack_and_bad_header_cancellation(self):
        from sim.transactions import request
        for corrupt in (False,True):
            dut = LinkLayer()
            sim = Simulator(dut)
            sim.add_clock(1 / 49_152_000)

            async def bench(ctx):
                wire = bytearray(request(0xffc0,0xffc1,1,CSR+0x400))
                if corrupt:
                    wire[-1] ^= 1
                decoder = LreqDecoder()
                samples = list(receive_samples(wire,speed=2))
                seen = None
                for index,(ctl,data) in enumerate(samples):
                    ctx.set(dut.phy.ctl_in,ctl)
                    ctx.set(dut.phy.data_in,data)
                    decoder.sample(ctx.get(dut.phy.lreq),receiving=ctl == 2)
                    await ctx.tick()
                    if decoder.pending_bus is not None and seen is None:
                        seen = index
                for _ in range(0):
                    ctx.set(dut.phy.ctl_in,0)
                    decoder.sample(ctx.get(dut.phy.lreq))
                    await ctx.tick()
                self.assertIsNotNone(seen)
                self.assertLess(seen,len(samples)-1)
                self.assertEqual(int(decoder.pending_bus.kind),0)
                phy = TransmitPhy()
                phy.grant(2)
                ctx.set(dut.phy.ctl_in,3)
                phy.tick()
                await ctx.tick()
                ctx.set(dut.phy.ctl_in,0)
                phy.tick()
                await ctx.tick()
                for _ in range(10):
                    phy.tick(ctx.get(dut.phy.ctl_out) if ctx.get(dut.phy.oe) else None,
                             ctx.get(dut.phy.data_out))
                    await ctx.tick()
                    if ctx.get(dut.phy.tx.done):
                        break
                self.assertEqual(phy.completed[0].payload,b'' if corrupt else b'\x2d')

            sim.add_testbench(bench)
            sim.run()
