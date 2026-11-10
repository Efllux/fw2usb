"""Native lease -> scheduled LREQ -> actual PHY pins, including lost deadlines."""
import struct
import unittest
from amaranth.sim import Simulator
from fw2usb.raw_worker import RawWorker
from sim.bus import Bus
from sim.phy import LreqDecoder,receive_samples
from sim.transmit import TransmitPhy
from sim.transactions import crc
from test_raw_worker import frame
from test_cycle_follower import cycle_packet

class RawTxWorkerTest(unittest.TestCase):
    def test_scheduled_wire_and_abort_boundaries(self):
        d=RawWorker();s=Simulator(d);s.add_clock(1/49_152_000)
        b=Bus([(0,1)],nodes=2,root=1);b.reset();b.run()
        inputs=[];outputs=[];wire=[];policy={'grant':True};decoder=LreqDecoder()
        async def monitor(c):
            current=bytearray();c.set(d.out_ready,1)
            while True:
                _,_,valid,byte,last=await c.tick().sample(d.out_valid,d.out_byte,d.out_last)
                if valid:
                    current.append(byte)
                    if last:outputs.append(bytes(current));current.clear()
        async def phy(c):
            active=None;elapsed=0;next_cycle=6144
            while True:
                if elapsed>=next_cycle and c.get(d.ready) and not inputs and active is None:
                    from test_cycle_follower import packed
                    inputs.extend(receive_samples(cycle_packet(packed(elapsed//2)),speed=0));next_cycle=elapsed+6144
                if c.get(d.epoch_reset):decoder.bus_reset();active=None
                ctl,data=inputs.pop(0) if inputs and active is None else (0,0)
                decoder.sample(c.get(d.link.phy.lreq),receiving=ctl==2)
                if active is None and not inputs and ctl==0 and decoder.pending_bus is not None and policy['grant']:
                    req=decoder.grant();active=TransmitPhy();active.grant(req.payload>>1)
                if active is not None:
                    driven=active.phy_ctl;ctl=driven if driven is not None else c.get(d.link.phy.ctl_out)
                    active.tick(c.get(d.link.phy.ctl_out) if c.get(d.link.phy.oe) else None,c.get(d.link.phy.data_out))
                    if active.state=='idle':wire.extend(x.payload for x in active.completed);active=None
                c.set(d.link.phy.ctl_in,ctl);c.set(d.link.phy.data_in,data);await c.tick();elapsed+=1
        async def bench(c):
            cookie=0
            async def reset():
                c.set(d.epoch_reset,1);await c.tick();c.set(d.epoch_reset,0)
                for _,kind,value in b.received[0]:
                    if kind=='selfid':inputs.extend(receive_samples(value,speed=0))
                inputs.extend([(1,0)]*8+[(0,0)]*2)
                for _ in range(400):
                    await c.tick()
                    if c.get(d.ready):break
                else:self.fail('topology timeout')
                inputs.extend(receive_samples(cycle_packet(c.get(d.link.cycle.timer.value)+100),speed=0))
                for _ in range(400):
                    await c.tick()
                    if c.get(d.clock_ready):return
                self.fail('topology timeout')
            async def send(op,payload=b'',*,wait=True):
                nonlocal cookie
                cookie+=1;ident=cookie
                for byte in frame(op,ident,c.get(d.generation),payload):
                    c.set(d.command.valid,1);c.set(d.command.byte,byte)
                    while not c.get(d.command.ready):await c.tick()
                    await c.tick()
                c.set(d.command.valid,0)
                if not wait:return
                for _ in range(25000):
                    await c.tick()
                    for r in outputs:
                        if r[5]==1 and int.from_bytes(r[8:12],'little')==ident:return r
                self.fail('TX command timeout')
            def status(r):return int.from_bytes(r[16:20],'little')
            def target(cycles=1):
                now=c.get(d.link.cycle.timer.value);n=((now>>25)*8000+((now>>12)&8191)+cycles)%1024000
                return ((n//8000)<<25)|((n%8000)<<12)
            def record(data,cycle,*,generation=None,channel=3):
                return struct.pack('<IIIIQIBBBB',c.get(d.iso_handle),c.get(d.generation) if generation is None else generation,0,cycle,0,len(data),channel,2,7,0)+data
            await reset()
            for speed,data in [(0,b''),(1,b'abcde'),(2,bytes(range(256)))]:
                created=await send(0x200,bytes([1,3,speed,0])+struct.pack('<II',256,1))
                self.assertEqual(status(created),0);self.assertEqual(created[36:40],bytes(4));self.assertFalse(c.get(d.iso_armed))
                credit=await send(0x204,struct.pack('<III',c.get(d.iso_handle),1,512));self.assertEqual(status(credit),1)
                before=len(wire);r=await send(0x201,record(data,target()))
                self.assertEqual(status(r),0)
                header=((len(data)<<16)|(2<<14)|(3<<8)|0xa7).to_bytes(4,'big');expected=header+crc(header).to_bytes(4,'big')
                if data:
                    padded=data+bytes((-len(data))%4);expected+=padded+crc(padded).to_bytes(4,'big')
                self.assertEqual(wire[before:],[expected])
                self.assertEqual(status(await send(0x201,record(data,target(),generation=1))),4)
                self.assertEqual(status(await send(0x201,record(data,target(),channel=4))),1)
                self.assertEqual(status(await send(0x201,record(data,((target()>>12)-2)<<12))),6)
                await send(0x202,struct.pack('<I',c.get(d.iso_handle)))
            # A withheld ISO grant expires. Recovery owns LREQ and a late grant
            # must produce no old payload, even if another command is submitted.
            await send(0x200,bytes([1,3,2,0])+struct.pack('<II',256,1))
            policy['grant']=False;before=len(wire)
            r=await send(0x201,record(b'never-on-wire',target()))
            self.assertEqual(status(r),6);self.assertTrue(c.get(d.recovery.active))
            policy['grant']=True;await c.tick().repeat(100)
            self.assertFalse(any(wire[before:]))
            await reset();self.assertFalse(c.get(d.recovery.active))
            # Aborting USB while an ISO bus request is pending cannot re-use its
            # retained decoder payload, and must trigger real recovery.
            await send(0x200,bytes([1,3,2,0])+struct.pack('<II',256,1))
            policy['grant']=False;before=len(wire)
            await send(0x201,record(b'aborted',target()),wait=False)
            for _ in range(15000):
                await c.tick()
                if c.get(d.link.phy.pending):break
            else:self.fail('no pending ISO request')
            c.set(d.session_reset,1);await c.tick();c.set(d.session_reset,0);await c.tick()
            self.assertTrue(c.get(d.recovery.active));self.assertFalse(c.get(d.iso_enabled))
            policy['grant']=True;await c.tick().repeat(100)
            self.assertFalse(any(wire[before:]))
            await reset();self.assertFalse(c.get(d.recovery.active))
        s.add_testbench(monitor,background=True);s.add_testbench(phy,background=True);s.add_testbench(bench);s.run()
