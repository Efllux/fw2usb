"""Independent TSB41AB2 register semantics, TI SLLS424G Tables 1–8.

This is a register model, not the cable state machine. External events are
explicit inputs; debounce, reset timing and LinkOn pulse generation are absent.
Unknown silicon revision bytes raise rather than invent a product identity.
"""


class PhyRegisters:
    def __init__(self, *, contender=False, power_class=0, cps=False,
                 revision=None):
        if not 0 <= power_class <= 7:
            raise ValueError('power class out of range')
        if revision is not None and not 0 <= revision <= 0xffff:
            raise ValueError('revision out of range')
        self.contender = bool(contender)
        self.power_class = power_class
        self.cps = bool(cps)
        self.revision = revision
        self.reset_epoch = 0
        self.hardware_reset()

    def hardware_reset(self):
        self.reset_epoch += 1
        self.base = [int(self.cps), 0x3f, 0xe2, 0x40,
                     0x80 | (self.contender << 6) | self.power_class,
                     0x10, 0, 0]
        # Disconnected ports report child, with undriven A/B line states Z.
        self.ports = [[0xf8, 0], [0xf8, 0]]
        self.vendor = 2
        self.resets_since_gap_write = 0
        self.physical_id_valid = False
        self.interrupt_sequence = 0

    def interrupt(self, mask):
        """Inject detected TI Table2 interrupt causes; no detector is implied."""
        if mask == 0 or mask & ~0x3c:
            raise ValueError('invalid interrupt mask')
        self.base[5] |= mask
        self.interrupt_sequence += 1

    @staticmethod
    def _address(address):
        if not 0 <= address <= 15:
            raise ValueError('register address out of range')

    def read(self, address):
        self._address(address)
        if address < 8:
            return self.base[address]
        page, port = self.base[7] >> 5, self.base[7] & 15
        if page == 0:
            return self.ports[port][address - 8] if port < 2 and address < 10 else 0
        if page == 1:
            if address >= 14 and self.revision is None:
                raise ValueError('product revision unspecified by datasheet')
            return [1, 0, 8, 0, 0x28, 0x42,
                    (self.revision or 0) >> 8, (self.revision or 0) & 255][address - 8]
        if page == 7 and address == 8:
            return self.vendor
        return 0

    def write(self, address, value):
        self._address(address)
        if not 0 <= value <= 255:
            raise ValueError('register data out of range')
        if address == 1:
            self.base[1] = value
            self.resets_since_gap_write = 0
        elif address == 4:
            self.base[4] = value & 0xc7
        elif address == 5:
            # Four event bits W1C, remaining bits ordinary writable controls.
            self.base[5] = (value & 0xc3) | (self.base[5] & ~value & 0x3c)
        elif address == 7:
            self.base[7] = value & 0xef
        elif address >= 8:
            page, port = self.base[7] >> 5, self.base[7] & 15
            if page == 0 and port < 2:
                if address == 8:
                    old = self.ports[port][0]
                    self.ports[port][0] = (old & 0xfe) | (value & 1)
                    if (old ^ value) & 1 and self.ports[port][1] & 0x10:
                        self.interrupt(4)
                elif address == 9:
                    old = self.ports[port][1]
                    self.ports[port][1] = (old & 0xe0) | (value & 0x10) | (old & ~value & 8)
                    if (old ^ self.ports[port][1]) & 8 and self.ports[port][1] & 0x10:
                        self.interrupt(4)
            elif page == 7:
                if address == 8:
                    if value & 3 == 3:
                        raise ValueError('illegal Link_Speed (test diagnostic)')
                    self.vendor = value & 0x83
                elif address == 14 and value & 0x80:
                    self.hardware_reset()

    def bus_reset(self):
        self.physical_id_valid = False
        self.base[0] &= 0xfd  # physical ID undefined; root clears
        self.base[1] &= 0xbf
        self.base[5] &= 0xbf
        self.resets_since_gap_write += 1
        if self.resets_since_gap_write >= 2:
            self.base[1] |= 0x3f

    def set_cps(self, present):
        if self.cps and not present:
            self.interrupt(0x10)
        self.cps = bool(present)
        self.base[0] = (self.base[0] & 0xfe) | int(self.cps)

    def self_id_complete(self, physical_id, *, root=False):
        if not 0 <= physical_id <= 63:
            raise ValueError('physical ID out of range')
        self.base[0] = (physical_id << 2) | (bool(root) << 1) | self.cps
        self.physical_id_valid = True
