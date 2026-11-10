import unittest
from amaranth.sim import Simulator
from fw2usb.transaction import CsrBank, RomReader
from sim.bus import Bus
from sim.devices import BeBoB, CSR
from sim.transactions import Peer, decode


class TransactionRtlTest(unittest.TestCase):
    def test_csr_atomic_cas_backpressure_and_reset(self):
        dut = CsrBank()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            ctx.set(dut.valid,1)
            ctx.set(dut.address,CSR+0x220)
            ctx.set(dut.compare_swap,1)
            ctx.set(dut.compare,4915)
            ctx.set(dut.data,4900)
            await ctx.tick()
            self.assertEqual(ctx.get(dut.response_data),4915)
            self.assertFalse(ctx.get(dut.ready))
            await ctx.tick().repeat(3)
            ctx.set(dut.response_ready,1)
            await ctx.tick()
            # Second CAS with old compare fails and returns current value.
            self.assertEqual(ctx.get(dut.response_data),4900)
            ctx.set(dut.valid,0)
            ctx.set(dut.bus_reset,1)
            await ctx.tick()
            ctx.set(dut.bus_reset,0)
            ctx.set(dut.valid,1)
            ctx.set(dut.compare_swap,0)
            await ctx.tick()
            self.assertEqual(ctx.get(dut.response_data),4915)
            ctx.set(dut.address,CSR+0x400)
            ctx.set(dut.write,1)
            await ctx.tick()
            self.assertEqual(ctx.get(dut.rcode),6)
            ctx.set(dut.address,CSR+3)
            await ctx.tick()
            self.assertEqual(ctx.get(dut.rcode),7)

        sim.add_testbench(bench)
        sim.run()

    def test_hardware_remote_rom_reader_over_bus(self):
        bus = Bus([(0,1)],nodes=2,root=0,gap_count=5)
        device = BeBoB()
        Peer(bus,1,device)
        bus.reset()
        bus.run()
        local = 0xffc0 | bus.ids[0]
        remote = 0xffc0 | bus.ids[1]
        dut = RomReader(timeout_cycles=1000)
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            ctx.set(dut.local_node,local)
            ctx.set(dut.remote_node,remote)
            ctx.set(dut.start,1)
            await ctx.tick()
            ctx.set(dut.start,0)
            ctx.set(dut.tx_ready,1)
            packet = bytearray()
            completed = False
            for _ in range(1000):
                last = False
                if ctx.get(dut.tx_valid):
                    packet.append(ctx.get(dut.tx_byte))
                    last = ctx.get(dut.tx_last)
                await ctx.tick()
                if last:
                    decoded = decode(packet)
                    self.assertEqual(decoded['source'],local)
                    self.assertTrue(bus.request(0,packet))
                    bus.run()
                    replies = [f for _,k,f in bus.received[0] if k == 'packet' and len(f.data)>1]
                    response = decode(replies[-1].data)
                    ctx.set(dut.response_source,response['source'])
                    ctx.set(dut.response_label,response['label'])
                    ctx.set(dut.response_data,response['quadlet'])
                    ctx.set(dut.response_rcode,response['rcode'])
                    ctx.set(dut.response_valid,1)
                    await ctx.tick()
                    ctx.set(dut.response_valid,0)
                    packet.clear()
                if ctx.get(dut.done):
                    completed = True
                    break
                self.assertFalse(ctx.get(dut.error))
            self.assertTrue(completed)
            self.assertEqual(ctx.get(dut.length),len(device.rom)//4)
            result = bytearray()
            for index in range(ctx.get(dut.length)):
                ctx.set(dut.read_index,index)
                result += ctx.get(dut.read_data).to_bytes(4,'big')
            self.assertEqual(bytes(result),device.rom)

        sim.add_testbench(bench)
        sim.run()

    def test_wire_responder_rom_block_and_irm_cas(self):
        from fw2usb.responder import TransactionResponder
        from sim.transactions import request
        dut = TransactionResponder()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            cases = [(request(0xffc0,0xffc1,1,CSR+0x400,tcode=5,length=32),7),
                     (request(0xffc0,0xffc1,2,CSR+0x220,tcode=9,
                              data=(4915).to_bytes(4,'big')+(4900).to_bytes(4,'big'),extended=2),11),
                     (request(0xffc0,0xffc1,3,CSR+0x220),6)]
            for wire,expected_type in cases:
                ctx.set(dut.rx.start,1)
                await ctx.tick()
                ctx.set(dut.rx.start,0)
                for byte in wire:
                    ctx.set(dut.rx.valid,1)
                    ctx.set(dut.rx.byte,byte)
                    await ctx.tick()
                ctx.set(dut.rx.valid,0)
                ctx.set(dut.rx.end,1)
                await ctx.tick()
                ctx.set(dut.rx.end,0)
                ctx.set(dut.tx_ready,1)
                output = bytearray()
                for _ in range(500):
                    last = False
                    if ctx.get(dut.tx_valid):
                        output.append(ctx.get(dut.tx_byte))
                        last = ctx.get(dut.tx_last)
                    await ctx.tick()
                    if last:
                        break
                else:
                    self.fail('responder stalled')
                response = decode(output)
                self.assertEqual(response['tcode'],expected_type)
                self.assertEqual(response['rcode'],0)
                if expected_type == 7:
                    self.assertEqual(len(response['data']),32)
                    self.assertEqual(response['data'][4:8],b'1394')
                elif expected_type == 11:
                    self.assertEqual(response['data'],(4915).to_bytes(4,'big'))
                else:
                    self.assertEqual(response['quadlet'],4900)

        sim.add_testbench(bench)
        sim.run()

    def test_phy_pins_to_csr_rom_and_wire_response(self):
        from fw2usb.transaction_link import TransactionLink
        from sim.phy import LreqDecoder, receive_samples
        from sim.transactions import request
        from sim.transmit import TransmitPhy
        dut = TransactionLink()
        sim = Simulator(dut)
        sim.add_clock(1 / 49_152_000)

        async def bench(ctx):
            wire = request(0xffc0,0xffc1,7,CSR+0x400)
            decoder = LreqDecoder()
            for ctl,data in receive_samples(wire,speed=2):
                ctx.set(dut.link.phy.ctl_in,ctl)
                ctx.set(dut.link.phy.data_in,data)
                decoder.sample(ctx.get(dut.link.phy.lreq),receiving=ctl == 2)
                await ctx.tick()
            active = None
            frames = []
            for _ in range(400):
                decoder.sample(ctx.get(dut.link.phy.lreq))
                if active is None and decoder.pending_bus is not None:
                    req = decoder.grant()
                    active = TransmitPhy()
                    active.grant(req.payload >> 1)
                ctl = active.phy_ctl if active else 0
                ctx.set(dut.link.phy.ctl_in,ctl if ctl is not None else ctx.get(dut.link.phy.ctl_out))
                if active:
                    active.tick(ctx.get(dut.link.phy.ctl_out) if ctx.get(dut.link.phy.oe) else None,
                                ctx.get(dut.link.phy.data_out))
                    if active.state == 'idle':
                        frames.extend(active.completed)
                        active = None
                await ctx.tick()
                if len(frames) == 2:
                    break
            self.assertEqual(frames[0].payload,b'\x2d')
            response = decode(frames[1].payload)
            self.assertEqual(response['tcode'],6)
            self.assertEqual(response['label'],7)
            self.assertEqual(response['rcode'],0)
            self.assertEqual(response['quadlet'],dut.responder.csr.rom[0])

        sim.add_testbench(bench)
        sim.run()
