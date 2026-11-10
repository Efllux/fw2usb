#!/usr/bin/env python3
"""Live Rust CLI Unix stream -> RTL USB CDC/worker/PHY -> peer models -> WAV.
USB bulk-byte port replaces LUNA tokens/electrical PHY. No control transcript
is used: all replies, CRCs and audio records are produced by the RTL under test.
"""
import argparse,hashlib,json,queue,socket,struct,subprocess,tempfile,threading,time,wave
from collections import deque
from fractions import Fraction
from pathlib import Path
from amaranth import ClockDomain,Elaboratable,Module,Signal
from amaranth.sim import Simulator
from fw2usb.usb_bridge import RawUsbBridge
from sim.bus import Bus
from sim.devices import BeBoB,Dice,CSR,DICE
from sim.phy import LreqDecoder,receive_samples
from sim.transmit import TransmitPhy
from sim.transactions import Peer,Client,crc
from fw2usb.transaction import rom_words
from sim.clocks import Clock

ROOT=Path(__file__).resolve().parents[2]


class BulkPort(Elaboratable):
    def __init__(self):
        self.clock=Signal();self.reset=Signal();self.reset_detected=Signal()
        self.out_byte=Signal(8);self.out_valid=Signal();self.out_ready=Signal()
        self.in_byte=Signal(8);self.in_valid=Signal();self.in_ready=Signal();self.in_last=Signal()
    def elaborate(self,p):return Module()


class Host:
    """OS IO stays on a worker thread; the Amaranth clock loop never blocks."""
    def __init__(self,path,args):
        self.incoming=queue.Queue();self.outgoing=queue.Queue();self.connected=threading.Event();self.stop=threading.Event();self.error=None
        self.server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);self.server.bind(str(path));self.server.listen(1)
        self.process=subprocess.Popen([str(ROOT/'target/debug/fw2usb-cli'),'--socket',str(path)]+args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        try:
            self.server.settimeout(5);connection,_=self.server.accept()
            with connection:
                connection.settimeout(.003);self.connected.set()
                while not self.stop.is_set():
                    while True:
                        try:connection.sendall(self.outgoing.get_nowait())
                        except queue.Empty:break
                    try:data=connection.recv(512)
                    except socket.timeout:continue
                    if not data:break
                    for b in data:self.incoming.put(b)
        except Exception as e:self.error=str(e)
    def close(self):
        self.stop.set();self.server.close();self.thread.join(timeout=1)
        if self.process.poll() is None:self.process.kill()
        return self.process.communicate(timeout=1)


def run(output,*,cycles=16,family='bebob',fault=None):
    output.mkdir(parents=True,exist_ok=True)
    subprocess.run(['cargo','build','--quiet','-p','fw2usb-cli'],cwd=ROOT,check=True)
    bus=Bus([(0,1),(0,2)],nodes=3,root=0,gap_count=5)
    device=BeBoB() if family=='bebob' else Dice()
    Peer(bus,1,device);Peer(bus,2,Dice() if family=='bebob' else BeBoB());remote_client=Client(bus,2);bus.reset();bus.run()
    cable=deque();wire_tx=[];records=[];commands=[];expected=bytearray();state={'host':None,'packets':0,'audio_cycle':0,'start':False,'active_command':None,'mixed_sent':False}
    bus.listeners[0].append(lambda kind,value:cable.extend(receive_samples(value.data,speed=value.speed)) if kind=='packet' else None)
    class Harness(Elaboratable):
        def __init__(self):
            self.sclk=ClockDomain('sync');self.port=BulkPort();self.bridge=RawUsbBridge(usb=self.port)
        def elaborate(self,p):
            m=Module();m.domains+=self.sclk;m.submodules.bridge=self.bridge;return m
    dut=Harness();worker=dut.bridge.worker;sim=Simulator(dut)
    sclk=Clock(49_152_000,ppm=80,phase_ns=1,jitter_ns=(0,Fraction(1,4),Fraction(-1,4)))
    usbclk=Clock(60_000_000,ppm=-50,phase_ns=7,jitter_ns=(0,Fraction(-1,5),Fraction(1,5)))
    async def sclk_driver(ctx):await sclk.drive(ctx,dut.sclk.clk)
    async def usb_driver(ctx):await usbclk.drive(ctx,dut.port.clock)
    async def usb_io(ctx):
        current=bytearray();pending=None;previous=None;settle=0;tick=0
        while True:
            host=state['host'];active=host is not None and host.connected.is_set()
            if active and host is not previous:previous=host;settle=64;pending=None;current.clear()
            ctx.set(dut.port.reset_detected,settle>48)
            if settle: settle-=1
            ready=active and not settle and tick%31 not in range(4,13)
            ctx.set(dut.port.in_ready,ready)
            if active and not settle and pending is None:
                try:pending=host.incoming.get_nowait()
                except queue.Empty:pass
            ctx.set(dut.port.out_valid,pending is not None and not settle)
            ctx.set(dut.port.out_byte,pending or 0)
            _,_,rx_ready,tx_valid,tx_byte,tx_last=await ctx.tick('usb').sample(dut.port.out_ready,dut.port.in_valid,dut.port.in_byte,dut.port.in_last)
            if pending is not None and not settle and rx_ready:pending=None
            if ready and tx_valid:
                current.append(tx_byte)
                if tx_last:
                    record=bytes(current);records.append(record);host.outgoing.put(record);current.clear()
            tick+=1
    bus_origin=bus.now
    async def phy(ctx):
        decoder=LreqDecoder();active=None;active_token=None;grants=deque();tick=0;next_audio=0
        while True:
            bus.run(until=bus_origin+tick*sclk.period_ns)
            if ctx.get(worker.epoch_reset):decoder.bus_reset();active=None;active_token=None;grants.clear()
            if (state['active_command']=='config-rom' and not state['mixed_sent'] and ctx.get(worker.command.command_valid) and ctx.get(worker.command.opcode)==0x100 and not remote_client.pending and 2 not in bus.pending):
                remote_client.submit(0xffc0|bus.ids[0],CSR+0x400)
                state['mixed_sent']=True
            if state['start'] and ctx.get(worker.iso_armed) and tick>=next_audio and state['packets']<cycles:
                payload=device.audio(state['audio_cycle'],ppm=20 if family=='bebob' else -180,jitter_ticks=(0,1,-1,2,-2))
                if payload is None:raise AssertionError('native stream start did not enable fixture')
                channel=3 if family=='bebob' else 4
                h=((len(payload)<<16)|(1<<14)|(channel<<8)|0xa0).to_bytes(4,'big')
                wire=bytearray(h+crc(h).to_bytes(4,'big')+payload+crc(payload).to_bytes(4,'big'))
                if fault=='crc' and state['packets']==2:wire[-1]^=1
                if not bus.request(1,bytes(wire),speed=2,kind='iso'):raise AssertionError('device ISO queue was not available')
                for word in range(8,len(payload),4):expected.extend((int.from_bytes(payload[word:word+4],'big')&0xffffff).to_bytes(3,'little'))
                state['packets']+=1;state['audio_cycle']+=1;next_audio=tick+6144
            if active is None and cable:ctl,data=cable.popleft();receiving=ctl==2
            else:ctl,data,receiving=0,0,False
            decoder.sample(ctx.get(worker.link.phy.lreq),receiving=receiving)
            if active is None:
                if decoder.pending_bus is None:
                    bus.cancel_reservation(0)
                    while grants:bus.complete_reservation(grants.popleft(),b'')
                elif 0 not in bus.pending and not grants and not (bus.reserved and bus.reserved.source==0):
                    pending=decoder.pending_bus
                    if not bus.reserve(0,kind=('immediate','iso','priority','fair')[int(pending.kind)],speed=pending.payload>>1,granted=grants.append):raise AssertionError('native PHY reservation rejected')
                if grants and not cable and ctl==0 and decoder.pending_bus is not None:
                    active_token=grants.popleft();request=decoder.grant();active=TransmitPhy();active.grant(request.payload>>1)
            if active is not None:
                driven=active.phy_ctl;ctl=driven if driven is not None else ctx.get(worker.link.phy.ctl_out)
                active.tick(ctx.get(worker.link.phy.ctl_out) if ctx.get(worker.link.phy.oe) else None,ctx.get(worker.link.phy.data_out))
                if active.state=='idle':
                    if len(active.completed)>1:raise AssertionError('native concatenation not modeled by this harness')
                    payload=active.completed[0].payload if active.completed else b''
                    if payload:wire_tx.append(payload)
                    if not bus.complete_reservation(active_token,payload):raise AssertionError('native reservation completion failed')
                    active=None;active_token=None
            ctx.set(worker.link.phy.ctl_in,ctl);ctx.set(worker.link.phy.data_in,data)
            await ctx.tick();tick+=1
    async def bench(ctx):
        ctx.set(worker.epoch_reset,1);ctx.set(worker.cycle_master_enable,1);await ctx.tick();ctx.set(worker.epoch_reset,0)
        for _,kind,value in bus.received[0]:
            if kind=='selfid':cable.extend(receive_samples(value,speed=0))
        status=(bus.ids[0]<<2)|2
        cable.extend((1,((status>>shift)&3)<<6) for shift in range(14,-1,-2));cable.extend([(0,0)]*2)
        for _ in range(1000):
            await ctx.tick()
            if ctx.get(worker.ready):break
        else:raise AssertionError('native topology did not become ready')
        if ctx.get(worker.local_node)!=(0xffc0|bus.ids[0]):raise AssertionError('local ID mismatch')
        local=0xffc0|bus.ids[0]
        async def remote_request(address,*,tcode=4,data=b'',length=4):
            while 2 in bus.pending:await ctx.tick()
            before=len(remote_client.completed);remote_client.submit(local,address,tcode=tcode,data=data,length=length,extended=2 if tcode==9 else 0)
            for _ in range(5000):
                await ctx.tick()
                if len(remote_client.completed)>before:break
            else:raise AssertionError('local RTL CSR service stalled')
            _,rcode,result=remote_client.completed[-1]
            if rcode!=0:raise AssertionError('local RTL CSR service failed: '+str((rcode,result,remote_client.completed,wire_tx[-3:])))
            return result
        local_rom=await remote_request(CSR+0x400)
        if local_rom!=rom_words()[0].to_bytes(4,'big'):raise AssertionError('local native ROM differs')
        old=await remote_request(CSR+0x220)
        if int.from_bytes(old,'big')!=4915:raise AssertionError('bad local IRM initial bandwidth')
        new=(4815).to_bytes(4,'big')
        if await remote_request(CSR+0x220,tcode=9,data=old+new,length=8)!=old:raise AssertionError('local IRM compare-swap failed')
        if await remote_request(CSR+0x220)!=new:raise AssertionError('local IRM reservation lost')
        node=str(0xffc0|bus.ids[1]);generation=ctx.get(worker.generation)
        with tempfile.TemporaryDirectory(prefix='fw2usb-native-',dir='/tmp') as temp:
            async def command(args,*,expect_failure=False):
                path=Path(temp)/'peer.sock';host=Host(path,args);state['host']=host;state['active_command']=args[0];deadline=time.monotonic()+(120 if args[0]=='record' else 30)
                try:
                    while host.process.poll() is None:
                        if time.monotonic()>deadline:raise AssertionError('CLI stalled: '+str(args)+' state='+str((state['packets'],ctx.get(worker.iso_enabled),ctx.get(worker.iso_armed),ctx.get(worker.iso_packet_credits),ctx.get(worker.iso_byte_credits),ctx.get(dut.bridge.audio.iso.losses),ctx.get(dut.bridge.audio.errors),len(records),len(cable))))
                        if host.error:raise AssertionError(host.error)
                        await ctx.tick().repeat(64)
                    out,err=host.close()
                    if bool(host.process.returncode)!=expect_failure:raise AssertionError(str(args)+' unexpected result: '+err.decode())
                    commands.append(dict(args=args,stdout=out.decode(),stderr=err.decode(),returncode=host.process.returncode))
                    return out.decode()
                finally:
                    host.close();state['host']=None;state['active_command']=None;path.unlink(missing_ok=True)
                    await ctx.tick().repeat(64)
            await command(['bus-info']);await command(['self-id'])
            rom=output/f'{family}.rom';await command(['config-rom',node,str(rom)])
            if rom.read_bytes()!=device.rom:raise AssertionError('native ROM read differs')
            if not state['mixed_sent'] or remote_client.pending or remote_client.completed[-1][1:]!=(0,rom_words()[0].to_bytes(4,'big')):raise AssertionError('concurrent local CSR/remote ROM transaction failed')
            tx_payload=bytes.fromhex('000200000002ffff4001020340fedcba')
            await command(['iso-send','7',tx_payload.hex(),'2'])
            tx_header=((len(tx_payload)<<16)|(1<<14)|(7<<8)|0xa0).to_bytes(4,'big')
            tx_expected=tx_header+crc(tx_header).to_bytes(4,'big')+tx_payload+crc(tx_payload).to_bytes(4,'big')
            if wire_tx.count(tx_expected)!=1:raise AssertionError('native CLI ISO TX missing/duplicated/corrupt')
            if ctx.get(worker.iso_enabled):raise AssertionError('CLI leaked TX lease')
            if family=='bebob':
                for offset in [0x904,0x984]:
                    old=int.from_bytes(device.read(CSR+offset),'big');new=old|(1<<24)|(3<<16)
                    await command(['cas',node,hex(CSR+offset),hex(old),hex(new)])
            else:
                owner=((0xffc0|bus.ids[0])<<48)|0xffffe0001000
                await command(['cas',node,hex(DICE+0x100),hex(device.owner),hex(owner),'64'])
                await command(['write',node,hex(DICE+0x14c),'0x020c']);device.clock_settled()
                await command(['write',node,hex(DICE+0x308),'4']);await command(['write',node,hex(DICE+0x150),'1'])
            state['start']=True;wav_path=output/f'{family}{"-bad-"+fault if fault else ""}.wav'
            wav_path.unlink(missing_ok=True)
            await command(['record','3' if family=='bebob' else '4',str(wav_path),'48000','2',str(cycles)],expect_failure=fault is not None)
            frames=0
            if fault:
                if wav_path.exists():raise AssertionError('invalid native stream published WAV')
                if 'reset/loss' not in commands[-1]['stderr']:raise AssertionError('fault was not reported as loss')
            else:
                with wave.open(str(wav_path),'rb') as wav:
                    actual=wav.readframes(wav.getnframes());frames=wav.getnframes()
                    if actual!=expected:raise AssertionError('native Rust WAV differs from source')
            if not fault and (ctx.get(dut.bridge.audio.iso.losses) or ctx.get(dut.bridge.audio.errors)):raise AssertionError('native audio loss/error')
            if ctx.get(worker.iso_enabled):raise AssertionError('CLI leaked ISO lease')
            cycle_starts=[tx for tx in wire_tx if len(tx)==20 and tx[:4]==bytes.fromhex('ffff008f')]
            if len(cycle_starts)<2:raise AssertionError('root did not send periodic cycle-start')
            for tx in cycle_starts:
                if crc(tx[:-4]).to_bytes(4,'big')!=tx[-4:] or tx[8:12]!=bytes.fromhex('f0000200'):raise AssertionError('bad native cycle-start')
            state['report']=dict(family=family,cycles=cycles,frames=frames,generation=generation,commands=commands,
                                 native_tx_packets=len(wire_tx),root_cycle_starts=len(cycle_starts),local_csr_service=True,concurrent_master_service=True,raw_iso_tx_exact=True,usb_records=len(records),wav_sha256=hashlib.sha256(wav_path.read_bytes()).hexdigest() if not fault else None,pcm_bit_exact=not fault,fault_rejected=bool(fault))
    for bench_,background in [(sclk_driver,True),(usb_driver,True),(usb_io,True),(phy,True),(bench,False)]:sim.add_testbench(bench_,background=background)
    sim.run();report=state['report'];report['scope']='actual RTL native worker/PHY/ISO/credit/CDC/mux and live Rust CLI Unix byte transport; event-level cable peers; LUNA USB tokens/electrical transport excluded'
    (output/f'{family}{"-bad-"+fault if fault else ""}-native-report.json').write_text(json.dumps(report,indent=2)+'\n')
    (output/f'{family}{"-bad-"+fault if fault else ""}-native.fw2r').write_bytes(b''.join(records))
    print(f'{family}: native commands + {report["frames"]} frames '+('fault rejected without WAV PASS' if fault else 'bit-exact WAV PASS'))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'gateware/build/native-cosim');p.add_argument('--cycles',type=int,default=16);p.add_argument('--family',choices=['bebob','dice'],default='bebob');p.add_argument('--fault',choices=['crc']);a=p.parse_args()
    if not 1<=a.cycles<=8000:p.error('cycles must be1..8000')
    run(a.output,cycles=a.cycles,family=a.family,fault=a.fault)
