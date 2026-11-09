"""Synthetic BeBoB/DICE protocol fixtures; no vendor ROM/capture imported.

Wire facts: IEEE1394 CSR/IRM and IEC61883 PCR/FCP; DICE register offsets from
pinned dice-interface.h (facts only, independently authored state machines).
ROM GUID/revision, channel counts and clock-lock latency are explicit fixtures.
Unsupported controls reject; these are not universal product emulators.
"""
import struct

CSR = 0xfffff0000000
DICE = 0xffffe0000000


class DeviceError(Exception):
    def __init__(self, rcode):
        self.rcode = rcode


def crc16(data):
    state = 0
    for byte in data:
        for bit in range(7, -1, -1):
            feedback = ((state >> 15) ^ (byte >> bit)) & 1
            state = ((state << 1) & 0xffff) ^ (0x1021 if feedback else 0)
    return state


def rom(vendor, model, guid):
    info = struct.pack('>IIII', 0x31333934, 0x20ff9002, guid >> 32, guid & 0xffffffff)
    entries = struct.pack('>II', 0x03000000 | vendor, 0x17000000 | model)
    return struct.pack('>I', 0x04040000 | crc16(info)) + info + struct.pack('>I', 0x20000 | crc16(entries)) + entries


class Remote:
    def __init__(self, *, vendor, model, guid):
        self.rom = rom(vendor, model, guid)
        self.generation = 0
        self.reset()

    def reset(self):
        self.generation += 1
        self.registers = {CSR+0x21c: 63, CSR+0x220: 4915, CSR+0x224: 0xffffffff, CSR+0x228: 0xffffffff}

    def check(self, generation):
        if generation != self.generation:
            raise DeviceError('stale_generation')

    def read(self, address, length=4):
        if address % 4 or length % 4 or length <= 0:
            raise DeviceError(7)
        if CSR+0x400 <= address and address+length <= CSR+0x400+len(self.rom):
            return self.rom[address-CSR-0x400:address-CSR-0x400+length]
        try:
            return b''.join(self.registers[a].to_bytes(4, 'big') for a in range(address,address+length,4))
        except KeyError:
            raise DeviceError(7) from None

    def write(self, address, data):
        raise DeviceError(7)

    def compare_swap(self, address, compare, swap, *, generation):
        self.check(generation)
        if len(compare) != 4 or len(swap) != 4 or address not in self.registers:
            raise DeviceError(6)
        old = self.read(address)
        if old == compare:
            self.registers[address] = int.from_bytes(swap, 'big')
        return old


class BeBoB(Remote):
    def __init__(self, *, channels=2, guid=0x00130e0000000001):
        self.channels = channels
        self.fcp_responses = []
        super().__init__(vendor=0x00130e, model=6, guid=guid)

    def reset(self):
        super().reset()
        self.registers.update({CSR+0x900: 0xbfffff01, CSR+0x980: 0x80ffff01,
                               CSR+0x904: 0x80000000 | self.channels*8,
                               CSR+0x984: 0x80000000 | self.channels*8})
        self.fcp_responses.clear()
        self.primed = False

    @property
    def streaming(self):
        return self.primed and all((self.registers[CSR+a] >> 24) & 63 for a in (0x904,0x984))

    def compare_swap(self, address, compare, swap, *, generation):
        if address in (CSR+0x904, CSR+0x984):
            old = super().compare_swap(address, compare, swap, generation=generation)
            if address == CSR+0x984 and old == compare:
                self.primed = bool((int.from_bytes(swap,'big') >> 24) & 63)
            return old
        return super().compare_swap(address,compare,swap,generation=generation)

    def write(self, address, data):
        if address == CSR+0xb00 and 3 <= len(data) <= 512:
            # Unknown AV/C opcodes explicitly NOT_IMPLEMENTED. Actual model-
            # specific format/mixer replies require independently sourced fixtures.
            self.fcp_responses.append(bytes([8])+data[1:])
            return
        raise DeviceError(7)


class Dice(Remote):
    def __init__(self, *, channels=2, guid=0x00130e0000000002):
        self.channels = channels
        self.notifications = []
        super().__init__(vendor=0x00130e, model=0xde, guid=guid)

    def reset(self):
        super().reset()
        self.owner = 0xffff000000000000
        self.enabled = False
        self.clock_locked = True
        self.clock = 0x020c
        self.notifications.clear()
        self.registers.update({DICE:0x40,DICE+4:0x40,DICE+8:0xc0,DICE+12:0x48,
                               DICE+16:0x140,DICE+20:0x48,DICE+24:0,DICE+28:0,
                               DICE+32:0,DICE+36:0,
                               DICE+0x14c:self.clock,DICE+0x150:0,DICE+0x154:0x201,
                               DICE+0x15c:48000,DICE+0x300:1,DICE+0x304:0x48,
                               DICE+0x308:0xffffffff,DICE+0x30c:self.channels,DICE+0x310:0,
                               DICE+0x314:2,DICE+0x500:1,DICE+0x504:0x48,
                               DICE+0x508:0xffffffff,DICE+0x50c:self.channels,DICE+0x510:0})

    def read(self, address, length=4):
        if address == DICE+0x100 and length == 8:
            return self.owner.to_bytes(8,'big')
        return super().read(address,length)

    def compare_swap(self,address,compare,swap,*,generation):
        self.check(generation)
        if address == DICE+0x100 and len(compare) == len(swap) == 8:
            old = self.owner.to_bytes(8,'big')
            if old == compare:
                self.owner = int.from_bytes(swap,'big')
            return old
        return super().compare_swap(address,compare,swap,generation=generation)

    def write(self,address,data):
        if len(data) != 4 or self.owner == 0xffff000000000000:
            raise DeviceError(4)
        value = int.from_bytes(data,'big')
        if address == DICE+0x14c:
            if value not in (0x010c,0x020c):
                raise DeviceError(6)
            self.clock = value
            self.clock_locked = False
            self.registers[address] = value
        elif address in (DICE+0x308,DICE+0x508):
            if value > 63 and value != 0xffffffff:
                raise DeviceError(6)
            self.registers[address] = value
        elif address == DICE+0x314:
            if value > 2:
                raise DeviceError(6)
            self.registers[address] = value
        elif address == DICE+0x150:
            if value and (not self.clock_locked or self.registers[DICE+0x308] > 63):
                raise DeviceError(4)
            self.enabled = bool(value)
            self.registers[address] = int(self.enabled)
        else:
            raise DeviceError(7)

    def clock_settled(self):
        self.clock_locked = True
        self.registers[DICE+0x154] = (self.clock & 0xff00) | 1
        self.registers[DICE+0x15c] = 44100 if self.clock == 0x010c else 48000
        self.notifications.append((self.owner,0x20))
