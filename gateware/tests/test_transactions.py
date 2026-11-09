import unittest
from sim.bus import Bus
from sim.devices import BeBoB, Dice, CSR, DICE
from sim.transactions import Client, Peer, decode


class TransactionTest(unittest.TestCase):
    def test_remote_rom_read_cmp_and_dice_owner_over_bus(self):
        bus = Bus([(0,1),(0,2)],nodes=3,root=0,gap_count=5)
        bebob,dice = BeBoB(),Dice()
        Peer(bus,1,bebob)
        Peer(bus,2,dice)
        client = Client(bus,0)
        bus.reset()
        bus.run()
        client.submit(0xffc0 | bus.ids[1],CSR+0x400,tcode=5,length=len(bebob.rom))
        bus.run()
        self.assertEqual(client.completed[-1][1:],(0,bebob.rom))
        old = bebob.read(CSR+0x984)
        new = (int.from_bytes(old,'big') | (1 << 24) | (3 << 16)).to_bytes(4,'big')
        client.submit(0xffc0 | bus.ids[1],CSR+0x984,tcode=9,data=old+new,extended=2)
        bus.run()
        self.assertEqual(client.completed[-1][1:],(0,old))
        owner = 0xffc2ffffe0001000
        old_owner = dice.owner.to_bytes(8,'big')
        client.submit(0xffc0 | bus.ids[2],DICE+0x100,tcode=9,
                      data=old_owner+owner.to_bytes(8,'big'),extended=2)
        bus.run()
        self.assertEqual(dice.owner,owner)
        frames = [v for _,k,v in bus.trace if k == 'transmit' and len(v.data)>1]
        for frame in frames:
            decode(frame.data)  # all wire header/data CRCs checked independently

    def test_reset_aborts_outstanding_once(self):
        bus = Bus([(0,1)],nodes=2)
        client = Client(bus,0)
        bus.reset()
        bus.run()
        client.submit(0xffc0 | bus.ids[1],CSR+0x400)
        bus.reset()
        bus.run()
        self.assertEqual(len(client.completed),1)
        self.assertEqual(client.completed[0][1],'stale_generation')
