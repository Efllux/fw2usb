import unittest
from sim.devices import BeBoB, Dice, DeviceError, CSR, DICE, crc16


class DeviceTest(unittest.TestCase):
    def test_rom_crc_and_cmp_generation(self):
        p = BeBoB()
        rom = p.read(CSR+0x400,32)
        self.assertEqual(int.from_bytes(rom[2:4],'big'),crc16(rom[4:20]))
        self.assertEqual(int.from_bytes(rom[22:24],'big'),crc16(rom[24:]))
        for address,channel in ((CSR+0x984,2),(CSR+0x904,3)):
            old = p.read(address)
            value = int.from_bytes(old,'big') | (1 << 24) | (channel << 16)
            self.assertEqual(p.compare_swap(address,old,value.to_bytes(4,'big'),generation=p.generation),old)
        self.assertTrue(p.streaming)
        generation = p.generation
        p.reset()
        self.assertFalse(p.streaming)
        with self.assertRaises(DeviceError):
            p.compare_swap(CSR+0x904,bytes(4),bytes(4),generation=generation)
        p.write(CSR+0xb00,bytes.fromhex('01ff30ff'))
        self.assertEqual(p.fcp_responses.pop(),bytes.fromhex('08ff30ff'))

    def test_dice_owner_clock_notifications_and_reset(self):
        p = Dice()
        with self.assertRaises(DeviceError):
            p.write(DICE+0x150,(1).to_bytes(4,'big'))
        owner = 0xffc0ffffe0001000
        empty = p.owner.to_bytes(8,'big')
        self.assertEqual(p.compare_swap(DICE+0x100,empty,owner.to_bytes(8,'big'),generation=p.generation),empty)
        p.write(DICE+0x14c,(0x010c).to_bytes(4,'big'))
        p.write(DICE+0x308,(3).to_bytes(4,'big'))
        with self.assertRaises(DeviceError):
            p.write(DICE+0x150,(1).to_bytes(4,'big'))
        p.clock_settled()
        self.assertEqual(p.notifications,[(owner,0x20)])
        p.write(DICE+0x150,(1).to_bytes(4,'big'))
        self.assertTrue(p.enabled)
        p.reset()
        self.assertFalse(p.enabled)
        self.assertEqual(p.owner,0xffff000000000000)
