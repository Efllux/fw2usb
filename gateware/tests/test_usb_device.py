import struct
import unittest
from amaranth import ClockDomain,Elaboratable,Module
from amaranth.sim import Simulator
from fw2usb.usb_device import GetCaps,descriptors


class UsbDeviceTest(unittest.TestCase):
    def test_descriptors_bulk_endpoints(self):
        collection=descriptors()
        device=bytes(collection.get_descriptor_bytes(1,0))
        config=bytes(collection.get_descriptor_bytes(2,0))
        self.assertEqual(struct.unpack_from('<HH',device,8),(0x1209,2))
        self.assertEqual(struct.unpack_from('<H',config,2)[0],len(config))
        offsets=[];index=0
        while index<len(config):
            length=config[index]
            self.assertGreater(length,0)
            if config[index+1]==5:offsets.append(config[index:index+length])
            index+=length
        self.assertEqual([d[2] for d in offsets],[1,0x81])
        self.assertTrue(all(int.from_bytes(d[4:6],'little')==512 for d in offsets))

    def test_get_caps_short_and_full_response(self):
        class Harness(Elaboratable):
            def __init__(self):self.handler=GetCaps(capabilities=7)
            def elaborate(self,p):
                m=Module();m.domains+=ClockDomain('usb');m.submodules.handler=self.handler;return m
        dut=Harness();sim=Simulator(dut);sim.add_clock(1/60_000_000,domain='usb')
        async def bench(ctx):
            i=dut.handler.interface
            for length in (7,16):
                for signal,value in [(i.setup.type,2),(i.setup.recipient,1),(i.setup.is_in_request,1),
                                     (i.setup.request,1),(i.setup.index,0),(i.setup.value,0),
                                     (i.setup.length,length),(i.setup.received,1)]:ctx.set(signal,value)
                await ctx.tick('usb');ctx.set(i.setup.received,0)
                ctx.set(i.data_requested,1);await ctx.tick('usb');ctx.set(i.data_requested,0)
                ctx.set(i.tx.ready,1);got=bytearray()
                for _ in range(20):
                    last=False
                    if ctx.get(i.tx.valid):got.append(ctx.get(i.tx.payload));last=ctx.get(i.tx.last)
                    await ctx.tick('usb')
                    if last:break
                self.assertEqual(bytes(got),struct.pack('<HHIQ',0,0,65536,7)[:length])
                ctx.set(i.handshakes_in.ack,1);await ctx.tick('usb');ctx.set(i.handshakes_in.ack,0)
                ctx.set(i.status_requested,1);self.assertTrue(ctx.get(i.handshakes_out.ack));await ctx.tick('usb');ctx.set(i.status_requested,0)
        sim.add_testbench(bench);sim.run()
