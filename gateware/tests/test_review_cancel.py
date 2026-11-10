import unittest
from amaranth.sim import Simulator
from fw2usb.transaction_link import TransactionLink
from sim.transactions import request
from sim.devices import CSR
from sim.phy import receive_samples
from sim.transmit import TransmitPhy
class Review(unittest.TestCase):
 def test_busy_request_must_not_get_pending_ack(self):
  d=TransactionLink();s=Simulator(d);s.add_clock(1/49152000)
  async def b(c):
   async def rx(label):
    for ctl,data in receive_samples(request(0xffc0,0xffc1,label,CSR+0x400),speed=2):
     c.set(d.link.phy.ctl_in,ctl);c.set(d.link.phy.data_in,data);await c.tick()
    await c.tick().repeat(4)
   async def ack():
    self.assertTrue(c.get(d.link.phy.pending))
    p=TransmitPhy();p.grant(2);c.set(d.link.phy.ctl_in,3);p.tick();await c.tick()
    c.set(d.link.phy.ctl_in,0);p.tick();await c.tick()
    for _ in range(20):
     p.tick(c.get(d.link.phy.ctl_out) if c.get(d.link.phy.oe) else None,c.get(d.link.phy.data_out));await c.tick()
     if c.get(d.link.phy.tx.done):break
    return p.completed[0].payload
   await rx(1);self.assertEqual(await ack(),b'\x2d')
   await c.tick().repeat(30);self.assertTrue(c.get(d.responder.busy))
   self.assertTrue(c.get(d.link.phy.pending))
   for ctl,data in receive_samples(null=True):
    c.set(d.link.phy.ctl_in,ctl);c.set(d.link.phy.data_in,data);await c.tick()
   await c.tick().repeat(100)
   self.assertTrue(c.get(d.responder.tx_valid))
   self.assertTrue(c.get(d.link.phy.pending),'cancelled priority response is never re-requested')
  s.add_testbench(b);s.run()
