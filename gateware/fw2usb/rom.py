"""Synthetic development config-ROM construction; IEEE1212 CRC16."""
import struct

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

