"""Synthetic development config-ROM construction; IEEE1212 CRC16."""
import struct

def crc16(data):
    state = 0
    for byte in data:
        for bit in range(7, -1, -1):
            feedback = ((state >> 15) ^ (byte >> bit)) & 1
            state = ((state << 1) & 0xffff) ^ (0x1021 if feedback else 0)
    return state


# Bus_Info_Block quadlet 2 (IEEE 1394-2008 8.3.2.5.4; IEEE 1212 bus-dependent info).
# irmc  [31]    1: this design hosts IRM CSRs (CsrBank: BUS_MANAGER_ID, BANDWIDTH/CHANNELS_AVAILABLE).
# cmc   [30]    1: acts as cycle master (CycleMaster).
# isc   [29]    1: isochronous capable (AMDTP rx/tx).
# bmc   [28]    0: no bus manager is implemented.   pmc [27] 0: no power management capability.
# cyc_clk_acc [23:16] 100 ppm, the accuracy a cycle-master-capable node must meet; the field is
#               meaningful because cmc=1. [verify] against the board oscillator and the exact field encoding.
# max_rec [15:12] 7: max async payload 2**(7+1)=256 B, matching TransactionResponder's 64-quadlet
#               capacity (below the S100 512 B limit, so valid at every speed). [verify] encoding.
# max_ROM [9:8] 1: block reads of up to 64 B (the 32 B ROM fits); 0 would mean quadlet reads only.
#               [verify] the max_ROM code table (1394a).
# generation [7:4] 0: the ROM is static. [verify] 1394a semantics.
# link_spd [2:0] 2: S400 (0=S100, 1=S200, 2=S400), matching the link's S100-S400 async support.
BUS_OPTIONS = (1<<31)|(1<<30)|(1<<29)|(100<<16)|(7<<12)|(1<<8)|(0<<4)|2


def rom(vendor, model, guid):
    info = struct.pack('>IIII', 0x31333934, BUS_OPTIONS, guid >> 32, guid & 0xffffffff)
    entries = struct.pack('>II', 0x03000000 | vendor, 0x17000000 | model)
    return struct.pack('>I', 0x04040000 | crc16(info)) + info + struct.pack('>I', 0x20000 | crc16(entries)) + entries

