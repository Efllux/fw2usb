import struct
import unittest
from amaranth import ClockDomain,Elaboratable,Module
from amaranth.sim import Simulator
from fw2usb.tunnel import FrameEncoder,FrameDecoder


class TunnelTest(unittest.TestCase):
    def test_encode_decode_backpressure_and_fail_closed(self):
        class Harness(Elaboratable):
            def __init__(self):self.enc=FrameEncoder();self.dec=FrameDecoder()
            def elaborate(self,p):
                m=Module();m.submodules.enc=self.enc;m.submodules.dec=self.dec;return m
        dut=Harness();sim=Simulator(dut);sim.add_clock(1/60_000_000)
        async def bench(ctx):
            data=bytes(range(255));ctx.set(dut.enc.kind,0);ctx.set(dut.enc.opcode,0x100)
            ctx.set(dut.enc.id,7);ctx.set(dut.enc.generation,3);ctx.set(dut.enc.length,len(data))
            ctx.set(dut.enc.start,1);await ctx.tick();ctx.set(dut.enc.start,0)
            result=bytearray();index=0
            for tick in range(1000):
                ctx.set(dut.enc.out_ready,tick%7!=1);ctx.set(dut.enc.valid,index<len(data));ctx.set(dut.enc.byte,data[min(index,254)])
                if ctx.get(dut.enc.ready) and index<len(data):index+=1
                last=False
                if ctx.get(dut.enc.out_valid) and ctx.get(dut.enc.out_ready):result.append(ctx.get(dut.enc.out_byte));last=ctx.get(dut.enc.out_last)
                await ctx.tick()
                if last:break
            self.assertEqual(result,struct.pack('<4sBBHIIII',b'FW2R',0,0,0x100,7,255,0,3)+data)
            for byte in result:
                ctx.set(dut.dec.valid,1);ctx.set(dut.dec.byte,byte)
                while not ctx.get(dut.dec.ready):await ctx.tick()
                await ctx.tick()
            ctx.set(dut.dec.valid,0);await ctx.tick().repeat(2)
            self.assertTrue(ctx.get(dut.dec.command_valid));self.assertEqual(ctx.get(dut.dec.id),7)
            for i,value in enumerate(data):ctx.set(dut.dec.read_index,i);self.assertEqual(ctx.get(dut.dec.read_data),value)
            ctx.set(dut.dec.command_ready,1);await ctx.tick();ctx.set(dut.dec.command_ready,0)
            bad=bytearray(result[:24]);bad[0]=0
            for byte in bad:ctx.set(dut.dec.valid,1);ctx.set(dut.dec.byte,byte);await ctx.tick()
            ctx.set(dut.dec.valid,0);await ctx.tick().repeat(2)
            self.assertTrue(ctx.get(dut.dec.halted));self.assertFalse(ctx.get(dut.dec.ready))
        sim.add_testbench(bench);sim.run()
