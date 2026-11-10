import unittest
from sim.bus import Bus


class BusTest(unittest.TestCase):
    def test_four_node_reset_selfid_delivery_and_epoch(self):
        bus = Bus([(0,1),(1,2),(1,3)], nodes=4, root=1)
        bus.reset()
        bus.run()
        self.assertTrue(bus.ready)
        for node in range(4):
            ids = [int.from_bytes(p[:4], 'big') >> 24 & 63
                   for _, kind, p in bus.received[node] if kind == 'selfid']
            self.assertEqual(ids, [0,1,2,3])
        bus.request(0, b'old')
        bus.run(bus.now + 1)
        bus.reset()
        bus.run()
        self.assertFalse(any(kind == 'packet' for events in bus.received for _,kind,_ in events))

    def test_fairness_order_and_propagation(self):
        bus = Bus([(0,1),(1,2)], nodes=3, root=1, gap_count=5)
        bus.reset()
        bus.run()
        for n in range(3):
            bus.request(n, bytes([n]))
        self.assertFalse(bus.request(0,b'duplicate'))
        bus.run()
        frames = [value for _, kind, value in bus.trace if kind == 'transmit']
        self.assertEqual([f.source for f in frames], [1,0,2])
        for left,right in zip(frames,frames[1:]):
            self.assertLess(left.end_ns,right.start_ns)
        bus.request(1,b'next')
        bus.run()
        self.assertTrue(any(kind == 'fairness_reset' for _,kind,_ in bus.trace))
        self.assertTrue(all(frame.epoch == bus.epoch for frame in frames))

    def test_streamed_reservation_ownership_cancel_and_reset(self):
        bus=Bus([(0,1)],nodes=2,root=0,gap_count=5);bus.reset();bus.run();grants=[]
        self.assertTrue(bus.reserve(0,granted=grants.append));bus.run(bus.now+10000)
        self.assertEqual(len(grants),1);token=grants[0]
        self.assertTrue(bus.request(1,b'peer',kind='iso'))
        bus.run(bus.now+1000);self.assertFalse(any(k=='transmit' for _,k,_ in bus.trace))
        completed=bus.now;self.assertTrue(bus.complete_reservation(token,b'native'))
        bus.run();frames=[f for _,k,f in bus.trace if k=='transmit']
        self.assertEqual([f.source for f in frames],[0,1]);self.assertEqual(frames[0].end_ns,completed)
        self.assertGreater(frames[1].start_ns,completed)
        self.assertFalse(bus.complete_reservation(token,b'duplicate'))
        self.assertTrue(bus.reserve(0,granted=grants.append));self.assertTrue(bus.cancel_reservation(0));bus.run()
        self.assertEqual(len(grants),1)
        self.assertTrue(bus.reserve(0,granted=grants.append));bus.run(bus.now+10000)
        old=grants[-1];bus.reset();bus.run();self.assertFalse(bus.complete_reservation(old,b'stale'))
