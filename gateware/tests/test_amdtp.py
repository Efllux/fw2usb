import subprocess
import unittest
from amaranth.sim import Simulator
from fw2usb.amdtp import AmdtpReceiver, AmdtpTransmitter, SytEngine


def vectors():
    result = subprocess.run(['cargo','run','--quiet','-p','fw-amdtp','--example','amdtp_vectors'],check=True,capture_output=True,text=True)
    return [(int(r),int(c),bytes.fromhex(h),[] if p == '-' else [int(s,16) for s in p.split(',')])
            for r,c,h,p in (line.split() for line in result.stdout.splitlines())]


class AmdtpTest(unittest.TestCase):
    def test_rust_generated_pcm_and_cip_rx(self):
        dut = AmdtpReceiver()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)
        async def bench(ctx):
            for rate,cycle,payload,expected in vectors():
                ctx.set(dut.start,1)
                await ctx.tick()
                ctx.set(dut.start,0)
                got=[]
                for byte in payload:
                    ctx.set(dut.valid,1)
                    ctx.set(dut.byte,byte)
                    await ctx.tick()
                    if ctx.get(dut.sample_valid):
                        got.append(ctx.get(dut.sample))
                ctx.set(dut.valid,0)
                ctx.set(dut.end,1)
                await ctx.tick()
                ctx.set(dut.end,0)
                self.assertFalse(ctx.get(dut.error))
                self.assertEqual(got,expected)
                self.assertEqual(ctx.get(dut.syt),int.from_bytes(payload[6:8],'big'))
        sim.add_testbench(bench)
        sim.run()

    def test_tx_matches_shared_rust_payloads(self):
        dut=AmdtpTransmitter()
        sim=Simulator(dut)
        sim.add_clock(1/49_152_000)
        async def bench(ctx):
            for rate,cycle,payload,pcm in vectors():
                for signal,value in [(dut.sid,payload[0]),(dut.dbs,payload[1]),(dut.dbc,payload[3]),
                                     (dut.fdf,payload[5]),(dut.syt,int.from_bytes(payload[6:8],'big')),
                                     (dut.frames,len(pcm)//2)]:
                    ctx.set(signal,value)
                ctx.set(dut.start,1)
                await ctx.tick()
                ctx.set(dut.start,0)
                got=bytearray(); index=0
                for tick in range(500):
                    ctx.set(dut.ready,tick%5 != 2)
                    ctx.set(dut.sample_valid,index<len(pcm))
                    ctx.set(dut.sample,pcm[min(index,len(pcm)-1)] if pcm else 0)
                    if ctx.get(dut.sample_ready) and index<len(pcm):
                        index+=1
                    last=False
                    if ctx.get(dut.valid) and ctx.get(dut.ready):
                        got.append(ctx.get(dut.byte)); last=ctx.get(dut.last)
                    await ctx.tick()
                    if last:break
                self.assertEqual(bytes(got),payload)
        sim.add_testbench(bench); sim.run()

    def test_hardware_syt_scheduler_against_rust(self):
        all_vectors=vectors()
        for rate,code in [(44100,1),(48000,2)]:
            dut=SytEngine(rate=rate,code=code)
            sim=Simulator(dut); sim.add_clock(1/49_152_000)
            async def bench(ctx):
                for r,cycle,payload,pcm in all_vectors:
                    if r != rate:continue
                    ctx.set(dut.cycle,cycle); ctx.set(dut.advance,1)
                    await ctx.tick(); ctx.set(dut.advance,0)
                    self.assertEqual(ctx.get(dut.syt),int.from_bytes(payload[6:8],'big'))
                    self.assertEqual(ctx.get(dut.fdf),payload[5])
                    self.assertEqual(ctx.get(dut.frames),len(pcm)//2)
            sim.add_testbench(bench); sim.run()

    def test_iso_wire_tx_crc_commit_and_pcm_rx(self):
        from amaranth import Elaboratable, Module
        from fw2usb.iso import IsoAudioReceiver,IsoAudioTransmitter
        from sim.transactions import crc
        all_vectors=vectors()[:20]
        class Harness(Elaboratable):
            def __init__(self):self.tx=IsoAudioTransmitter();self.rx=IsoAudioReceiver()
            def elaborate(self,platform):
                m=Module();m.submodules.tx=self.tx;m.submodules.rx=self.rx;return m
        dut=Harness();sim=Simulator(dut);sim.add_clock(1/49_152_000)
        async def bench(ctx):
            ctx.set(dut.rx.channel,3)
            for rate,cycle,payload,pcm in all_vectors:
                codec=dut.tx.codec
                for signal,value in [(codec.sid,payload[0]),(codec.dbs,payload[1]),(codec.dbc,payload[3]),
                                     (codec.fdf,payload[5]),(codec.syt,int.from_bytes(payload[6:8],'big')),
                                     (codec.frames,len(pcm)//2),(dut.tx.channel,3)]:ctx.set(signal,value)
                ctx.set(dut.tx.start,1);await ctx.tick();ctx.set(dut.tx.start,0)
                got=bytearray();index=0
                for tick in range(500):
                    ctx.set(dut.tx.ready,1);ctx.set(codec.sample_valid,index<len(pcm))
                    ctx.set(codec.sample,pcm[min(index,len(pcm)-1)] if pcm else 0)
                    if ctx.get(codec.sample_ready) and index<len(pcm):index+=1
                    last=False
                    if ctx.get(dut.tx.valid):got.append(ctx.get(dut.tx.byte));last=ctx.get(dut.tx.last)
                    await ctx.tick()
                    if last:break
                header=((len(payload)<<16)|(1<<14)|(3<<8)|0xa0).to_bytes(4,'big')
                expected=header+crc(header).to_bytes(4,'big')+payload+crc(payload).to_bytes(4,'big')
                self.assertEqual(bytes(got),expected)
                for corrupt in (False,True):
                    wire=bytearray(got)
                    if corrupt:wire[-1]^=1
                    ctx.set(dut.rx.rx.start,1);await ctx.tick();ctx.set(dut.rx.rx.start,0)
                    samples=[];errors=0
                    for byte in wire:
                        ctx.set(dut.rx.rx.valid,1);ctx.set(dut.rx.rx.byte,byte);await ctx.tick()
                        self.assertFalse(ctx.get(dut.rx.sample_valid))
                    ctx.set(dut.rx.rx.valid,0);ctx.set(dut.rx.rx.end,1);await ctx.tick();ctx.set(dut.rx.rx.end,0)
                    for _ in range(400):
                        await ctx.tick();errors+=ctx.get(dut.rx.error)
                        if ctx.get(dut.rx.sample_valid):samples.append(ctx.get(dut.rx.sample))
                        if ctx.get(dut.rx.done) or (corrupt and errors):break
                    self.assertEqual(samples,[] if corrupt else pcm)
                    self.assertEqual(bool(errors),corrupt)
        sim.add_testbench(bench);sim.run()

    def test_independent_device_clock_matches_rust_and_drifts(self):
        from sim.audio import AudioClock
        def sampler(frame,channel):
            left=((frame*7919)&0xffffff)-0x800000
            return left if channel==0 else -left-1
        for rate in (44100,48000):
            clock=AudioClock(rate=rate,channels=2,sid=1,sampler=sampler)
            for r,cycle,payload,pcm in vectors():
                if r==rate:self.assertEqual(clock.next_cycle(cycle),payload)
        for ppm in (-100,100):
            clock=AudioClock(rate=48000,ppm=ppm,jitter_ticks=(0,1,-1,2,-2))
            for cycle in range(8000):clock.next_cycle(cycle)
            expected=48000*(1+ppm/1_000_000)
            self.assertLessEqual(abs(clock.frame-expected),8)
