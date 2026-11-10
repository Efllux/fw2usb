"""Reset/self-ID/ROM/CMP/device audio -> RTL PHY/ISO/CDC/FW2R -> Rust CLI WAV.

USB is modeled at bulk byte-stream boundary; LUNA's physical core is separately
synthesized/tested. Control transcript operations execute on behavioral bus peers.
No captured data, firmware binary or physical hardware is required.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import wave
from amaranth import ClockDomain, Elaboratable, Module
from amaranth.sim import Simulator
from fw2usb.link_layer import LinkLayer
from fw2usb.raw_iso_bridge import RawIsoBridge
from fw2usb.tunnel import FrameEncoder
from sim.bus import Bus
from sim.devices import BeBoB,Dice,CSR,DICE
from sim.transactions import Client,Peer,crc,decode
from sim.phy import receive_samples
from sim.clocks import Clock
from fractions import Fraction

ROOT=Path(__file__).resolve().parents[2]


def usb_frame(kind,opcode,cookie,generation,payload):
    return struct.pack('<4sBBHIIII',b'FW2R',0,kind,opcode,cookie,len(payload),0,generation)+payload


def submit_payload(node,address,length):
    return struct.pack('<HBBQHHII',node,4 if length==4 else 5,2,address,0,0,length,200_000)


def run(output,cycles):
    output.mkdir(parents=True,exist_ok=True)
    subprocess.run(['cargo','build','--quiet','-p','fw2usb-cli'],cwd=ROOT,check=True)
    cli=ROOT/'target/debug/fw2usb-cli'
    reports=[]
    for family in ('bebob','dice'):
        bus=Bus([(0,1),(0,2)],nodes=3,root=0,gap_count=5)
        bebob,dice=BeBoB(),Dice();device=bebob if family=='bebob' else dice;peer_node=1 if family=='bebob' else 2
        Peer(bus,1,bebob);Peer(bus,2,dice);client=Client(bus,0)
        bus.reset();bus.run();generation=bus.epoch;node=0xffc0|bus.ids[peer_node]
        transcript=bytearray();cookie=0
        def exchange(opcode,payload,response):
            nonlocal cookie
            cookie+=1
            transcript.extend(usb_frame(0,opcode,cookie,generation,payload))
            transcript.extend(usb_frame(1,0x101 if opcode==0x100 else opcode,cookie,generation,response))
        exchange(3,b'',struct.pack('<HHHH',client.node_id,0xffc0|bus.ids[0],3,0))
        sids=b''.join(value for _,kind,value in bus.received[0] if kind=='selfid')
        exchange(4,b'',sids)
        for length in (4,24,len(device.rom)):
            client.submit(node,CSR+0x400,tcode=4 if length==4 else 5,length=length);bus.run()
            _,rcode,data=client.completed[-1]
            if rcode!=0:raise AssertionError('ROM read failed')
            exchange(0x100,submit_payload(node,CSR+0x400,length),struct.pack('<BBHIQ',2,rcode,0,len(data),0)+data)
        # Connection/control operations are actual async wire transactions on the
        # model bus, rather than directly setting a streaming boolean.
        if family=='bebob':
            for address,channel in ((CSR+0x984,2),(CSR+0x904,3)):
                old=device.read(address);new=(int.from_bytes(old,'big')|(1<<24)|(channel<<16)).to_bytes(4,'big')
                client.submit(node,address,tcode=9,data=old+new,extended=2);bus.run()
                if client.completed[-1][1]!=0:raise AssertionError('CMP connect failed')
            channel=3
        else:
            owner=((client.node_id<<48)|0xffffe0001000).to_bytes(8,'big')
            client.submit(node,DICE+0x100,tcode=9,data=device.owner.to_bytes(8,'big')+owner,extended=2);bus.run()
            for address,value in ((DICE+0x14c,0x020c),(DICE+0x308,4)):
                client.submit(node,address,tcode=0,data=value.to_bytes(4,'big'));bus.run()
                if client.completed[-1][1]!=0:raise AssertionError('DICE setup failed')
            device.clock_settled()
            client.submit(node,DICE+0x150,tcode=0,data=(1).to_bytes(4,'big'));bus.run();channel=4
        create=bytes([0,channel,2,0])+struct.pack('<II',4096,64)
        exchange(0x200,create,struct.pack('<IIII',1,4096,1,1))
        exchange(0x204,struct.pack('<III',1,32,8192),b'')
        exchange(0x202,struct.pack('<I',1),b'')
        wire_replies=[frame.data for _,kind,frame in bus.received[0] if kind=='packet' and len(frame.data)>1]
        class Harness(Elaboratable):
            def __init__(self):
                self.sclk=ClockDomain('sync');self.usb=ClockDomain('usb')
                self.link=LinkLayer();self.bridge=RawIsoBridge();self.encoder=FrameEncoder()
            def elaborate(self,platform):
                m=Module();m.domains+=[self.sclk,self.usb];m.submodules.link=self.link;m.submodules.bridge=self.bridge;m.submodules.encoder=self.encoder
                m.d.comb += [self.bridge.iso.rx.start.eq(self.link.phy.rx.start & ~self.link.selfid_phase),
                             self.bridge.iso.rx.valid.eq(self.link.phy.rx.valid & ~self.link.selfid_phase),
                             self.bridge.iso.rx.byte.eq(self.link.phy.rx.byte),self.bridge.iso.rx.end.eq(self.link.phy.rx.end & ~self.link.selfid_phase),
                             self.bridge.iso.rx.phy_error.eq(self.link.phy.rx.error)]
                return m
        dut=Harness();sim=Simulator(dut)
        sclk=Clock(49_152_000,ppm=80,phase_ns=1,jitter_ns=(0,Fraction(1,4),Fraction(-1,4)))
        usbclk=Clock(60_000_000,ppm=-50,phase_ns=7,jitter_ns=(0,Fraction(-1,5),Fraction(1,5)))
        async def sclk_driver(ctx):await sclk.drive(ctx,dut.sclk.clk)
        async def usb_driver(ctx):await usbclk.drive(ctx,dut.usb.clk)
        records=[];rtl_pcm=[];expected_pcm=bytearray();current=bytearray();selfid_ids=[];good_replies=0
        async def usb_consumer(ctx):
            tick=0
            while True:
                enabled=tick%31 not in range(4,13)
                ctx.set(dut.bridge.bulk_ready,enabled)
                _,_,valid,byte,last=await ctx.tick('usb').sample(dut.bridge.bulk_valid,dut.bridge.bulk_byte,dut.bridge.bulk_last)
                if enabled and valid:
                    current.append(byte)
                    if last:records.append(bytes(current));current.clear()
                tick+=1
        async def bench(ctx):
            nonlocal good_replies
            ctx.set(dut.bridge.generation,generation);ctx.set(dut.bridge.iso.channel,channel)
            async def pins(packet,*,sid=False):
                nonlocal good_replies
                ctx.set(dut.link.selfid_phase,sid)
                for ctl,data in list(receive_samples(packet,speed=0 if sid else 2))+[(0,0)]*4:
                    ctx.set(dut.link.phy.ctl_in,ctl);ctx.set(dut.link.phy.data_in,data);await ctx.tick()
                    if ctx.get(dut.link.selfid.accept):selfid_ids.append(ctx.get(dut.link.selfid.physical_id))
                    if ctx.get(dut.link.packet.good):good_replies+=1
                    if ctx.get(dut.bridge.iso.sample_valid):rtl_pcm.append(ctx.get(dut.bridge.iso.sample))
            for index in range(0,len(sids),8):await pins(sids[index:index+8],sid=True)
            if selfid_ids!=[0,1,2]:raise AssertionError('RTL self-ID capture mismatch')
            for response in wire_replies:await pins(response)
            first_cycle=int(bus.now//125_000)+1
            for n in range(cycles):
                cycle=first_cycle+n
                payload=device.audio(cycle,ppm=100 if family=='bebob' else -100,jitter_ticks=(0,1,-1,2,-2))
                if payload is None:raise AssertionError('device not connected')
                for word in range(8,len(payload),4):expected_pcm.extend((int.from_bytes(payload[word:word+4],'big')&0xffffff).to_bytes(3,'little'))
                header=((len(payload)<<16)|(1<<14)|(channel<<8)|0xa0).to_bytes(4,'big')
                wire=header+crc(header).to_bytes(4,'big')+payload+crc(payload).to_bytes(4,'big')
                ctx.set(dut.bridge.cycle_time,((cycle//8000&127)<<25)|((cycle%8000)<<12));ctx.set(dut.bridge.ticks,cycle*3072)
                before=len(records)
                await pins(wire)
                for _ in range(1200):
                    await ctx.tick()
                    if ctx.get(dut.bridge.iso.sample_valid):rtl_pcm.append(ctx.get(dut.bridge.iso.sample))
                    if ctx.get(dut.bridge.iso.error) or ctx.get(dut.bridge.iso.losses):raise AssertionError('RTL ISO error/loss')
                    if len(records)>before:break
                else:raise AssertionError('CDC/USB record stalled')
                record=records[-1]
                if record[24+32:]!=payload:raise AssertionError('verified RAM payload altered across CDC')
            # Exercise generic frame encoder with a real ROM completion record.
            encoder=dut.encoder;example=bytes(device.rom)
            for signal,value in [(encoder.kind,1),(encoder.opcode,0x101),(encoder.id,99),(encoder.generation,generation),(encoder.length,len(example))]:ctx.set(signal,value)
            ctx.set(encoder.start,1);await ctx.tick();ctx.set(encoder.start,0);encoded=bytearray();index=0
            for _ in range(200):
                ctx.set(encoder.out_ready,1);ctx.set(encoder.valid,index<len(example));ctx.set(encoder.byte,example[min(index,len(example)-1)])
                if ctx.get(encoder.ready) and index<len(example):index+=1
                last=False
                if ctx.get(encoder.out_valid):encoded.append(ctx.get(encoder.out_byte));last=ctx.get(encoder.out_last)
                await ctx.tick()
                if last:break
            if encoded!=usb_frame(1,0x101,99,generation,example):raise AssertionError('RTL generic tunnel framing mismatch')
        sim.add_testbench(sclk_driver,background=True);sim.add_testbench(usb_driver,background=True);sim.add_testbench(usb_consumer,background=True);sim.add_testbench(bench);sim.run()
        if len(rtl_pcm)*3!=len(expected_pcm):raise AssertionError('RTL PCM count mismatch')
        actual_pcm=b''.join(sample.to_bytes(3,'little') for sample in rtl_pcm)
        if actual_pcm!=expected_pcm:raise AssertionError('RTL PCM differs from source')
        returned_packets=returned_bytes=0
        for record in records:
            returned_packets+=1;returned_bytes+=len(record)
            if returned_packets>=8 or returned_bytes>=4096:
                exchange(0x204,struct.pack('<III',1,returned_packets,returned_bytes),b'')
                returned_packets=returned_bytes=0
        transcript.extend(b''.join(records));fixture=output/f'{family}.fw2r';fixture.write_bytes(transcript)
        prefix=[str(cli),'--replay',str(fixture),'--generation',str(generation)]
        for command in (['list'],['bus-info'],['self-id']):subprocess.run(prefix+command,cwd=ROOT,check=True,capture_output=True)
        rom_path=output/f'{family}.rom';subprocess.run(prefix+['config-rom',str(node),str(rom_path)],cwd=ROOT,check=True,capture_output=True)
        if rom_path.read_bytes()!=device.rom:raise AssertionError('CLI ROM differs')
        wav_path=output/f'{family}.wav';result=subprocess.run(prefix+['record',str(channel),str(wav_path),'48000','2',str(cycles)],cwd=ROOT,check=True,capture_output=True,text=True)
        with wave.open(str(wav_path),'rb') as wav:
            actual=wav.readframes(wav.getnframes());frames=wav.getnframes()
            if wav.getsampwidth()!=3 or wav.getnchannels()!=2 or wav.getframerate()!=48000 or actual!=expected_pcm:raise AssertionError('CLI WAV is not bit exact')
        negative_checks=[]
        if len(records)>1:
            for failure in ('sequence','generation'):
                damaged=bytearray(records[1])
                at=24+(8 if failure=='sequence' else 4)
                damaged[at:at+4]=(999).to_bytes(4,'little')
                broken=output/f'{family}-bad-{failure}.fw2r'
                base=bytes(transcript[:-sum(map(len,records))])
                broken.write_bytes(base+records[0]+bytes(damaged)+b''.join(records[2:]))
                bad_wav=output/f'{family}-bad-{failure}.wav'
                bad_wav.unlink(missing_ok=True)
                negative=subprocess.run([str(cli),'--replay',str(broken),'--generation',str(generation),'record',str(channel),str(bad_wav),'48000','2',str(cycles)],cwd=ROOT,capture_output=True,text=True)
                if negative.returncode==0 or bad_wav.exists():raise AssertionError('invalid stream published WAV')
                negative_checks.append(failure)
        reports.append({'negative_checks':negative_checks,'family':family,'cycles':cycles,'frames':frames,'generation':generation,'rtl_packet_accepts':good_replies,
                        'wav_sha256':hashlib.sha256(wav_path.read_bytes()).hexdigest(),'pcm_bit_exact':True,'transcript':str(fixture),'wav':str(wav_path)})
        print(f'{family}: {frames} frames, bit-exact WAV PASS')
    report={'scope':'behavioral control/cable model; RTL PHY RX, CRC, AM824, synchronous RAM, async CDC and FW2R bulk framing; Rust CLI replay. USB electrical/token waveform and board timing not covered.', 'results':reports}
    (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=ROOT/'gateware/build/cosim');parser.add_argument('--cycles',type=int,default=64)
    args=parser.parse_args()
    if not 1<=args.cycles<=8000:parser.error('cycles must be1..8000')
    run(args.output,args.cycles)
