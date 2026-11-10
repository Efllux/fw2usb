import struct
import unittest
from amaranth import ClockDomain,Elaboratable,Module
from amaranth.sim import Simulator
from fw2usb.uac2 import descriptors,AudioControl,AudioPacketBuffer


class AudioTest(unittest.TestCase):
    def test_descriptor_entities_and_alternates(self):
        data=bytes(descriptors().get_descriptor_bytes(2,0));pos=9;interface=None;alt=None;ends=[];entities=[];acbytes=0;actotal=0
        self.assertEqual(struct.unpack_from('<H',data,2)[0],len(data))
        while pos<len(data):
            n=data[pos];self.assertGreaterEqual(n,2);d=data[pos:pos+n];self.assertEqual(len(d),n)
            if d[1]==4:interface=d[2];alt=d[3]
            if d[1]==0x24 and interface==0:
                acbytes+=n
                if d[2]==1:actotal=int.from_bytes(d[6:8],'little')
                else:entities.append(d[3])
            if d[1]==5:ends.append((interface,alt,d[2],d[3],int.from_bytes(d[4:6],'little')))
            pos+=n
        self.assertEqual(pos,len(data));self.assertEqual(acbytes,actotal)
        self.assertEqual(entities,[1,10,11,12,13]);self.assertEqual(len(set(entities)),len(entities))
        self.assertEqual(ends,[(1,1,2,5,42),(1,1,0x83,17,4),(2,1,0x82,5,42),(3,0,1,2,512),(3,0,0x81,2,512)])

    def test_clock_control_and_alt_gate(self):
        class Harness(Elaboratable):
            def __init__(self):self.h=AudioControl()
            def elaborate(self,p):
                m=Module();m.domains+=ClockDomain('usb');m.submodules.h=self.h;return m
        dut=Harness();sim=Simulator(dut);sim.add_clock(1/60e6,domain='usb')
        async def bench(ctx):
            i=dut.h.interface;ctx.set(i.active_config,1)
            async def setup(typ,request,value,index,length,read=1):
                for sig,v in [(i.setup.type,typ),(i.setup.recipient,1),(i.setup.is_in_request,read),(i.setup.request,request),
                              (i.setup.value,value),(i.setup.index,index),(i.setup.length,length),(i.setup.received,1)]:ctx.set(sig,v)
                await ctx.tick('usb');ctx.set(i.setup.received,0)
            async def reply():
                ctx.set(i.data_requested,1);await ctx.tick('usb');ctx.set(i.data_requested,0);ctx.set(i.tx.ready,1);b=bytearray()
                for _ in range(20):
                    last=False
                    if ctx.get(i.tx.valid):b.append(ctx.get(i.tx.payload));last=ctx.get(i.tx.last)
                    await ctx.tick('usb')
                    if last:break
                ctx.set(i.handshakes_in.ack,1);await ctx.tick('usb');ctx.set(i.handshakes_in.ack,0)
                ctx.set(i.status_requested,1);await ctx.tick('usb');ctx.set(i.status_requested,0)
                return bytes(b)
            await setup(1,1,0x100,0x100,4);self.assertEqual(await reply(),struct.pack('<I',48000))
            await setup(1,2,0x100,0x100,14);self.assertEqual(await reply(),struct.pack('<HIII',1,48000,48000,0))
            await setup(1,1,0x200,0x100,1);self.assertEqual(await reply(),b'\0')
            await setup(0,11,1,1,0,0);ctx.set(i.status_requested,1);self.assertTrue(ctx.get(i.handshakes_out.stall));ctx.set(i.status_requested,0)
            ctx.set(dut.h.valid,1);await setup(0,11,1,1,0,0)
            ctx.set(i.status_requested,1);await ctx.tick('usb');ctx.set(i.status_requested,0)
            self.assertTrue(ctx.get(dut.h.play))
            await setup(0,10,0,1,1);self.assertEqual(await reply(),b'\1')
            ctx.set(dut.h.valid,0);await ctx.tick('usb');self.assertFalse(ctx.get(dut.h.play))
        sim.add_testbench(bench);sim.run()

    def test_packet_atomic_underflow(self):
        d=AudioPacketBuffer();sim=Simulator(d);sim.add_clock(1/60e6)
        async def bench(ctx):
            for b in range(6):ctx.set(d.valid,1);ctx.set(d.byte,b+1);await ctx.tick()
            ctx.set(d.valid,0);await ctx.tick().repeat(2)
            for length,expected in [(12,bytes(12)),(6,bytes(range(1,7)))]:
                ctx.set(d.length,length);ctx.set(d.start,1);await ctx.tick();ctx.set(d.start,0)
                out=bytearray()
                for k in range(length):ctx.set(d.out_ready,1);out.append(ctx.get(d.out_byte));await ctx.tick()
                ctx.set(d.out_ready,0);self.assertEqual(bytes(out),expected)
            self.assertEqual(ctx.get(d.underruns),1)
        sim.add_testbench(bench);sim.run()

    def test_profile_identity_and_discovered_slot_binding(self):
        from fw2usb.audio_profiles import PROFILES
        for p in PROFILES:
            args=dict(vendor=p.vendor,model=p.model,firmware='synthetic-revision1',rate=48000,
                      capture_pcm_positions=[0,2,3],playback_pcm_positions=[1,2])
            bound=p.bind(**args);self.assertEqual(bound['capture'],(0,2))
            for replacement in [dict(rate=96000),dict(firmware=''),dict(model=0),dict(capture_pcm_positions=[0])]:
                with self.assertRaises(ValueError):p.bind(**(args|replacement))
