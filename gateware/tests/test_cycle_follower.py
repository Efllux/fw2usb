import unittest
from amaranth.sim import Simulator
from fw2usb.link_layer import LinkLayer
from sim.phy import receive_samples
from sim.transactions import crc

PERIOD=128*8000*3072

def packed(t):
    t%=PERIOD
    return ((t//(8000*3072))<<25)|(((t//3072)%8000)<<12)|(t%3072)

def ticks(v):return (v>>25)*8000*3072+((v>>12)&8191)*3072+(v&4095)

def cycle_packet(time,source=0xffc1):
    h=bytes.fromhex('ffff008f')+((source<<16)|0xffff).to_bytes(4,'big')+bytes.fromhex('f0000200')+time.to_bytes(4,'big')
    return h+crc(h).to_bytes(4,'big')

class CycleFollowerTest(unittest.TestCase):
    def test_crc_root_gating_monotonic_forward_backward_and_wrap(self):
        d=LinkLayer();s=Simulator(d);s.add_clock(1/49_152_000)
        async def bench(c):
            c.set(d.follow_cycles,1);c.set(d.root_node,0xffc1)
            async def receive(wire,speed=2):
                previous=ticks(c.get(d.cycle.timer.value))
                for ctl,data in list(receive_samples(wire,speed=speed))+[(0,0)]*5:
                    c.set(d.phy.ctl_in,ctl);c.set(d.phy.data_in,data);await c.tick()
                    now=ticks(c.get(d.cycle.timer.value))
                    self.assertLess((now-previous)%PERIOD,PERIOD//2,'cycle time went backward')
                    previous=now
            await receive(cycle_packet(packed(500*3072+100)))
            self.assertEqual(c.get(d.follower.updates),1)
            now=ticks(c.get(d.cycle.timer.value));self.assertGreaterEqual(now,500*3072+100)
            self.assertLess(now,500*3072+150)
            # A master behind our clock causes a bounded pause, not a backward write.
            await receive(cycle_packet(packed(now-100)),speed=0)
            debt=c.get(d.follower.debt);self.assertGreater(debt,50);self.assertLess(debt,150)
            frozen=c.get(d.cycle.timer.value);await c.tick().repeat(debt*2-2)
            self.assertEqual(c.get(d.cycle.timer.value),frozen)
            await c.tick().repeat(8);self.assertNotEqual(c.get(d.cycle.timer.value),frozen)
            updates=c.get(d.follower.updates)
            bad=bytearray(cycle_packet(packed(now+1000)));bad[-1]^=1
            await receive(bad);await receive(cycle_packet(packed(now+1000),source=0xffc2))
            await receive(cycle_packet(8000<<12));await receive(cycle_packet(4095))
            self.assertEqual(c.get(d.follower.updates),updates)
            c.set(d.follow_cycles,0)
            await receive(cycle_packet(packed(now+1000)))
            self.assertEqual(c.get(d.follower.updates),updates)
            # Reset/role changes clear synchronization debt without resetting time.
            c.set(d.follow_cycles,1);await receive(cycle_packet(packed(ticks(c.get(d.cycle.timer.value))-100)))
            self.assertTrue(c.get(d.follower.pause));before=c.get(d.cycle.timer.value)
            c.set(d.phy.bus_reset,1);await c.tick();c.set(d.phy.bus_reset,0)
            self.assertEqual(c.get(d.follower.debt),0);self.assertGreaterEqual(c.get(d.cycle.timer.value),before)
            c.set(d.timer_load,1);c.set(d.timer_value,packed(PERIOD-100));await c.tick();c.set(d.timer_load,0)
            await receive(cycle_packet(packed(20)))
            self.assertEqual(c.get(d.follower.updates),1)
            self.assertLess(ticks(c.get(d.cycle.timer.value)),100)
            self.assertTrue(c.get(d.follower.synced));await c.tick().repeat(12290)
            self.assertFalse(c.get(d.follower.synced));self.assertFalse(c.get(d.follower.pause))
        s.add_testbench(bench);s.run()

    def test_independent_master_drift_and_receive_jitter(self):
        for ppm in [-200,200]:
            d=LinkLayer();s=Simulator(d);s.add_clock(1/49_152_000)
            async def bench(c):
                c.set(d.follow_cycles,1);c.set(d.root_node,0xffc1);elapsed=0;previous=0
                async def step(ctl=0,data=0):
                    nonlocal elapsed,previous
                    c.set(d.phy.ctl_in,ctl);c.set(d.phy.data_in,data);await c.tick();elapsed+=1
                    now=ticks(c.get(d.cycle.timer.value))
                    self.assertLess((now-previous)%PERIOD,PERIOD//2);previous=now
                def master():return 10*3072+(elapsed*(1_000_000+ppm))//2_000_000
                for i in range(16):
                    # Packet departure/arrival jitter is explicit; no exact cable
                    # phase claim follows from these bounded synthetic delays.
                    timestamp=packed(master())
                    for _ in range(i%3):await step()
                    for ctl,data in list(receive_samples(cycle_packet(timestamp),speed=i%3))+[(0,0)]*5:await step(ctl,data)
                    self.assertLessEqual(abs(master()-ticks(c.get(d.cycle.timer.value))),5)
                    for _ in range(6144):await step()
                self.assertEqual(c.get(d.follower.updates),16)
            s.add_testbench(bench);s.run()

    def test_csr_cycle_write_and_bus_reset_preserve_time(self):
        from fw2usb.transaction_link import TransactionLink
        from sim.transactions import request
        from sim.devices import CSR
        d=TransactionLink();s=Simulator(d);s.add_clock(1/49_152_000)
        async def bench(c):
            c.set(d.link.cycle.node_id,0xffc0)
            async def write(value):
                wire=request(0xffc0,0xffc1,4,CSR+0x200,tcode=0,data=value.to_bytes(4,'big'))
                for ctl,data in list(receive_samples(wire,speed=2))+[(0,0)]*40:
                    c.set(d.link.phy.ctl_in,ctl);c.set(d.link.phy.data_in,data);await c.tick()
            target=packed(3*8000*3072+100)
            await write(target)
            now=ticks(c.get(d.link.cycle.timer.value))
            self.assertGreaterEqual(now,ticks(target));self.assertLess(now,ticks(target)+40)
            c.set(d.link.phy.bus_reset,1);await c.tick();c.set(d.link.phy.bus_reset,0)
            await c.tick().repeat(10);self.assertGreaterEqual(ticks(c.get(d.link.cycle.timer.value)),now)
            before=ticks(c.get(d.link.cycle.timer.value))
            await write(8000<<12)
            after=ticks(c.get(d.link.cycle.timer.value))
            self.assertGreaterEqual(after,before);self.assertLess(after-before,100)
            self.assertEqual(c.get(d.responder.csr.rcode),6)
        s.add_testbench(bench);s.run()
