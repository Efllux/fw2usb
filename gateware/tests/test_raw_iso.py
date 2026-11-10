import struct
import unittest
from amaranth import ClockDomain,Elaboratable,Module,Signal,ResetInserter
from amaranth.sim import Simulator
from fw2usb.raw_iso_bridge import RawIsoBridge
from sim.transactions import crc


class RawIsoTest(unittest.TestCase):
    def test_opaque_payload_tag_sy_empty_and_lease_snapshot(self):
        class Harness(Elaboratable):
            def __init__(self):
                self.bridge=RawIsoBridge(opaque=True,cdc=False);self.reset=Signal()
            def elaborate(self,p):
                m=Module();m.submodules.bridge=ResetInserter(self.reset)(self.bridge);return m
        dut=Harness();sim=Simulator(dut);sim.add_clock(1/49_152_000)
        async def bench(ctx):
            d=dut.bridge
            for attempt,payload in enumerate((b'partial',b'',b'\x12\x34\x56\x78\x9a')):
                ctx.set(d.generation,2);ctx.set(d.handle,7);ctx.set(d.cycle_time,0x12345000);ctx.set(d.ticks,99)
                ctx.set(d.iso.channel,3);ctx.set(d.bulk_ready,0)
                header=((len(payload)<<16)|(3<<8)|0xa7).to_bytes(4,'big')
                wire=header+crc(header).to_bytes(4,'big')
                if payload:
                    padded=payload+bytes((-len(payload))%4);wire+=padded+crc(padded).to_bytes(4,'big')
                ctx.set(d.iso.rx.start,1);await ctx.tick();ctx.set(d.iso.rx.start,0)
                # A new lease arriving before replay must not relabel old data.
                ctx.set(d.handle,8);ctx.set(d.generation,3);ctx.set(d.cycle_time,0x999);ctx.set(d.ticks,1000)
                for byte in wire:ctx.set(d.iso.rx.valid,1);ctx.set(d.iso.rx.byte,byte);await ctx.tick()
                ctx.set(d.iso.rx.valid,0);ctx.set(d.iso.rx.end,1);await ctx.tick();ctx.set(d.iso.rx.end,0)
                result=bytearray()
                for tick in range(300):
                    ready=tick%7 not in (1,2);ctx.set(d.bulk_ready,ready);last=False
                    if ctx.get(d.bulk_valid) and ready:result.append(ctx.get(d.bulk_byte));last=ctx.get(d.bulk_last)
                    await ctx.tick()
                    if last or (attempt==0 and len(result)==9):break
                if attempt==0:
                    # Reset a stalled frame after its first bytes have escaped.
                    # The next lease must begin with FW2R, never the old tail.
                    ctx.set(dut.reset,1);await ctx.tick();ctx.set(dut.reset,0)
                    await ctx.tick().repeat(4)
                    continue
                self.assertEqual(result[:4],b'FW2R');self.assertEqual(int.from_bytes(result[20:24],'little'),2)
                self.assertEqual(int.from_bytes(result[24:28],'little'),7)
                self.assertEqual(int.from_bytes(result[36:40],'little'),0x12345000)
                self.assertEqual(int.from_bytes(result[40:48],'little'),99)
                self.assertEqual(result[52:56],bytes([3,0,7,3]))
                self.assertEqual(result[56:],payload)
                await ctx.tick().repeat(4)
        sim.add_testbench(bench);sim.run()
