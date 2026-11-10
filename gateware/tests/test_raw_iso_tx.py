import unittest
from amaranth.sim import Simulator
from fw2usb.raw_iso_tx import RawIsoTransmitter
from sim.transactions import crc

class RawIsoTxTest(unittest.TestCase):
    def test_opaque_empty_padding_backpressure_and_metadata_latch(self):
        d=RawIsoTransmitter();sim=Simulator(d);sim.add_clock(1/49_152_000)
        async def bench(ctx):
            for payload in [b'',b'abcde',bytes(range(255))]:
                ctx.set(d.length,len(payload));ctx.set(d.channel,63);ctx.set(d.tag,2);ctx.set(d.sy,7);ctx.set(d.start,1);await ctx.tick();ctx.set(d.start,0)
                ctx.set(d.channel,0);ctx.set(d.tag,0);ctx.set(d.sy,0)
                out=bytearray()
                for tick in range(2000):
                    i=ctx.get(d.data_index);ctx.set(d.data_byte,payload[i] if i<len(payload) else 0)
                    ready=tick%7 not in [1,2];ctx.set(d.ready,ready);last=False
                    if ctx.get(d.valid) and ready:out.append(ctx.get(d.byte));last=ctx.get(d.last)
                    await ctx.tick()
                    if last:break
                else:self.fail('TX stalled')
                header=((len(payload)<<16)|(2<<14)|(63<<8)|0xa7).to_bytes(4,'big')
                expected=header+crc(header).to_bytes(4,'big')
                if payload:
                    padded=payload+bytes((-len(payload))%4);expected+=padded+crc(padded).to_bytes(4,'big')
                self.assertEqual(bytes(out),expected);self.assertFalse(ctx.get(d.busy))
                await ctx.tick().repeat(2)
            ctx.set(d.length,4097);ctx.set(d.start,1);await ctx.tick();ctx.set(d.start,0)
            self.assertTrue(ctx.get(d.error));self.assertTrue(ctx.get(d.done));self.assertFalse(ctx.get(d.valid));self.assertFalse(ctx.get(d.busy))
        sim.add_testbench(bench);sim.run()

    def test_cycle_deadline_wrap_and_reserved_budget(self):
        from fw2usb.raw_iso_tx import IsoTxWindow
        d=IsoTxWindow();sim=Simulator(d)
        async def bench(ctx):
            ctx.set(d.length,256);ctx.set(d.speed,0)
            ctx.set(d.now,(127<<25)|(7999<<12));ctx.set(d.target,0)
            self.assertTrue(ctx.get(d.future));self.assertFalse(ctx.get(d.late))
            ctx.set(d.now,0);self.assertTrue(ctx.get(d.open))
            ctx.set(d.now,3000);self.assertTrue(ctx.get(d.late));self.assertFalse(ctx.get(d.open))
            ctx.set(d.now,1<<12);self.assertTrue(ctx.get(d.late))
            for target in [1,8000<<12]:ctx.set(d.target,target);self.assertFalse(ctx.get(d.valid))
            ctx.set(d.target,0);ctx.set(d.speed,3);self.assertFalse(ctx.get(d.valid))
        sim.add_testbench(bench);sim.run()

    def test_shared_rust_iso_vectors(self):
        import subprocess
        result=subprocess.run(['cargo','run','--quiet','-p','fw-1394','--example','packet_vectors'],check=True,capture_output=True,text=True)
        packets=[bytes.fromhex(s) for s in result.stdout.splitlines()[:-1]]
        d=RawIsoTransmitter();sim=Simulator(d);sim.add_clock(1/49_152_000)
        async def bench(ctx):
            for packet in packets:
                length=int.from_bytes(packet[:2],'big');payload=packet[8:8+length]
                ctx.set(d.length,length);ctx.set(d.channel,3);ctx.set(d.tag,1);ctx.set(d.sy,0);ctx.set(d.start,1);await ctx.tick();ctx.set(d.start,0)
                wire=bytearray()
                for tick in range(600):
                    index=ctx.get(d.data_index);ctx.set(d.data_byte,payload[index] if index<len(payload) else 0)
                    ready=tick%5!=1;ctx.set(d.ready,ready);last=False
                    if ready and ctx.get(d.valid):wire.append(ctx.get(d.byte));last=ctx.get(d.last)
                    await ctx.tick()
                    if last:break
                self.assertEqual(bytes(wire),packet)
                await ctx.tick().repeat(2)
        sim.add_testbench(bench);sim.run()
