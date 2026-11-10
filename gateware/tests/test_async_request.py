import unittest
from amaranth.sim import Simulator
from fw2usb.async_request import AsyncRequestEncoder
from sim.transactions import request


class AsyncRequestTest(unittest.TestCase):
    def test_request_types_against_independent_wire_model(self):
        dut=AsyncRequestEncoder();sim=Simulator(dut);sim.add_clock(1/49_152_000)
        async def bench(ctx):
            for tcode,data,length,extended in [(4,b'',4,0),(0,bytes.fromhex('12345678'),4,0),
                                               (5,b'',32,0),(1,bytes(range(17)),17,0),
                                               (9,bytes(range(16)),16,2)]:
                for sig,value in [(dut.destination,0xffc1),(dut.source,0xffc0),(dut.label,7),
                                  (dut.address,0xfffff0000400),(dut.tcode,tcode),(dut.length,length),
                                  (dut.extended,extended),(dut.quadlet,int.from_bytes(data[:4],'big'))]:ctx.set(sig,value)
                ctx.set(dut.start,1);await ctx.tick();ctx.set(dut.start,0)
                got=bytearray()
                for tick in range(150):
                    ctx.set(dut.ready,tick%7!=2)
                    index=ctx.get(dut.data_index);ctx.set(dut.data_byte,data[index] if index<len(data) else 0)
                    last=False
                    if ctx.get(dut.valid) and ctx.get(dut.ready):got.append(ctx.get(dut.byte));last=ctx.get(dut.last)
                    await ctx.tick()
                    if last:break
                expected=request(0xffc1,0xffc0,7,0xfffff0000400,tcode=tcode,data=data,length=length,extended=extended)
                self.assertEqual(got,expected)
        sim.add_testbench(bench);sim.run()
