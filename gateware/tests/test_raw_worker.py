import struct
import unittest
from amaranth.sim import Simulator
from fw2usb.raw_worker import RawWorker
from sim.bus import Bus
from sim.devices import BeBoB,CSR
from sim.transactions import Peer
from sim.phy import LreqDecoder,receive_samples
from sim.transmit import TransmitPhy


def frame(opcode,cookie,generation,payload=b''):
    return struct.pack('<4sBBHIIII',b'FW2R',0,0,opcode,cookie,len(payload),0,generation)+payload


class RawWorkerTest(unittest.TestCase):
    def test_live_wire_read_usb_frames_and_generation(self):
        bus=Bus([(0,1)],nodes=2,root=1,gap_count=5);device=BeBoB();Peer(bus,1,device);bus.reset();bus.run()
        queue=[]
        bus.listeners[0].append(lambda kind,value:queue.extend(receive_samples(value.data,speed=value.speed)) if kind=='packet' else None)
        dut=RawWorker();sim=Simulator(dut);sim.add_clock(1/49_152_000)
        output=[];wire_tx=[];pending_output=bytearray();decoder=LreqDecoder()
        async def monitor(ctx):
            ctx.set(dut.out_ready,1)
            while True:
                _,_,valid,byte,last=await ctx.tick().sample(dut.out_valid,dut.out_byte,dut.out_last)
                if valid:
                    pending_output.append(byte)
                    if last:output.append(bytes(pending_output));pending_output.clear()
        async def phy(ctx):
            active=None
            while True:
                if ctx.get(dut.epoch_reset):decoder.bus_reset();active=None
                if active is None and queue:
                    ctl,data=queue.pop(0);receiving=ctl==2
                else:ctl,data,receiving=0,0,False
                decoder.sample(ctx.get(dut.link.phy.lreq),receiving=receiving)
                if active is None and not queue and ctl==0 and decoder.pending_bus is not None:
                    request=decoder.grant();active=TransmitPhy();active.grant(request.payload>>1)
                if active is not None:
                    driven=active.phy_ctl
                    ctl=driven if driven is not None else ctx.get(dut.link.phy.ctl_out)
                    active.tick(ctx.get(dut.link.phy.ctl_out) if ctx.get(dut.link.phy.oe) else None,
                                ctx.get(dut.link.phy.data_out))
                    if active.state=='idle':
                        for transmission in active.completed:
                            wire_tx.append(transmission.payload)
                            if len(transmission.payload)>1:
                                self.assertTrue(bus.request(0,transmission.payload,speed=transmission.speed));bus.run()
                        active=None
                ctx.set(dut.link.phy.ctl_in,ctl);ctx.set(dut.link.phy.data_in,data)
                await ctx.tick()
        async def bench(ctx):
            ctx.set(dut.epoch_reset,1);await ctx.tick();ctx.set(dut.epoch_reset,0)
            for _,kind,value in bus.received[0]:
                if kind=='selfid':queue.extend(receive_samples(value,speed=0))
            queue.extend([(1,0)]*8+[(0,0)]*2) # unsolicited register0: id0, nonroot
            for _ in range(300):
                await ctx.tick()
                if ctx.get(dut.ready):break
            self.assertTrue(ctx.get(dut.ready));self.assertEqual(ctx.get(dut.local_node),0xffc0)
            self.assertEqual(ctx.get(dut.generation),2)
            async def send(opcode,cookie,payload=b'',generation=2):
                for byte in frame(opcode,cookie,generation,payload):
                    ctx.set(dut.command.valid,1);ctx.set(dut.command.byte,byte)
                    while not ctx.get(dut.command.ready):await ctx.tick()
                    await ctx.tick()
                ctx.set(dut.command.valid,0)
                for _ in range(2000):
                    await ctx.tick()
                    for reply in output:
                        if reply[5]==1 and int.from_bytes(reply[8:12],'little')==cookie:return reply
                self.fail('native command timeout')
            info=await send(3,1)
            self.assertEqual(int.from_bytes(info[12:16],'little'),8)
            self.assertEqual(info[24:28],struct.pack('<HH',0xffc0,0xffc1))
            payload=struct.pack('<HBBQHHII',0xffc1,4,2,CSR+0x400,0,0,4,200_000)
            reply=await send(0x100,2,payload)
            self.assertEqual(int.from_bytes(reply[16:20],'little'),0)
            self.assertEqual(reply[24:26],bytes([2,0]))
            self.assertEqual(reply[40:],device.rom[:4])
            self.assertTrue(any(len(p)>1 for p in wire_tx))
            create=bytes([0,3,2,0])+struct.pack('<II',512,64)
            reply=await send(0x200,3,create)
            self.assertEqual(reply[24:],struct.pack('<IIII',1,512,1,1));self.assertTrue(ctx.get(dut.iso_enabled))
            self.assertFalse(ctx.get(dut.iso_admit));self.assertEqual(ctx.get(dut.iso_packet_credits),0)
            credited=await send(0x204,30,struct.pack('<III',1,2,1000));self.assertEqual(int.from_bytes(credited[16:20],'little'),0)
            ctx.set(dut.iso_cost,300);self.assertTrue(ctx.get(dut.iso_admit))
            ctx.set(dut.iso_consume,1);await ctx.tick();ctx.set(dut.iso_consume,0)
            self.assertEqual(ctx.get(dut.iso_packet_credits),1);self.assertEqual(ctx.get(dut.iso_byte_credits),700)
            bad_credit=await send(0x204,31,struct.pack('<III',1,32,8192));self.assertEqual(int.from_bytes(bad_credit[16:20],'little'),1)
            self.assertEqual(ctx.get(dut.iso_byte_credits),700)
            ctx.set(dut.iso_cost,700);self.assertFalse(ctx.get(dut.iso_admit)) # exceeds negotiated512B+metadata
            ctx.set(dut.iso_cost,300);ctx.set(dut.iso_consume,1);await ctx.tick();ctx.set(dut.iso_consume,0)
            self.assertFalse(ctx.get(dut.iso_admit));self.assertEqual(ctx.get(dut.iso_packet_credits),0)
            bad_credit=await send(0x204,32,struct.pack('<III',9,1,100));self.assertEqual(int.from_bytes(bad_credit[16:20],'little'),1)
            stale=await send(0x100,4,payload,generation=1)
            self.assertEqual(int.from_bytes(stale[16:20],'little'),4)
            bad=await send(0x202,5,struct.pack('<I',9))
            self.assertEqual(int.from_bytes(bad[16:20],'little'),1);self.assertTrue(ctx.get(dut.iso_enabled))
            await send(0x202,6,struct.pack('<I',1));self.assertFalse(ctx.get(dut.iso_enabled))
            old=device.read(CSR+0x984);new=(int.from_bytes(old,'big')|(1<<24)|(2<<16)).to_bytes(4,'big')
            cas=struct.pack('<HBBQHHII',0xffc1,9,2,CSR+0x984,2,0,8,200_000)+old+new
            reply=await send(0x100,7,cas)
            self.assertEqual(reply[40:],old);self.assertEqual(device.read(CSR+0x984),new)
            block=struct.pack('<HBBQHHII',0xffc1,5,2,CSR+0x400,0,0,len(device.rom),200_000)
            reply=await send(0x100,8,block);self.assertEqual(reply[40:],device.rom)
            write=struct.pack('<HBBQHHII',0xffc1,0,2,CSR+0xb00,0,0,4,200_000)+bytes.fromhex('01ff30ff')
            reply=await send(0x100,9,write);self.assertEqual(reply[25],0)
            self.assertEqual(device.fcp_responses[-1],bytes.fromhex('08ff30ff'))
            timeout=struct.pack('<HBBQHHII',0xffc2,4,2,CSR+0x400,0,0,4,1)
            reply=await send(0x100,10,timeout);self.assertEqual(int.from_bytes(reply[16:20],'little'),6)
            ctx.set(dut.session_reset,1);await ctx.tick();ctx.set(dut.session_reset,0)
            info=await send(3,11);self.assertEqual(info[24:26],struct.pack('<H',0xffc0))
            ctx.set(dut.epoch_reset,1);await ctx.tick();ctx.set(dut.epoch_reset,0)
            for _ in range(60):await ctx.tick()
            self.assertFalse(ctx.get(dut.ready));self.assertEqual(ctx.get(dut.generation),3)
            self.assertTrue(any(f[5]==2 and int.from_bytes(f[6:8],'little')==0x8000 and int.from_bytes(f[20:24],'little')==3 for f in output))
        sim.add_testbench(monitor,background=True);sim.add_testbench(phy,background=True);sim.add_testbench(bench);sim.run()
