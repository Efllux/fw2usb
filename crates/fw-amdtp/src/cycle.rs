//! IEEE 1394 cycle time arithmetic.
//!
//! The cycle timer runs at 24.576 MHz: 3072 ticks per 125 µs cycle, 8000 cycles per second.
//! CYCLE_TIME register layout: seconds(7) | cycle(13) | offset(12).

pub const TICKS_PER_CYCLE: u32 = 3072;
pub const CYCLES_PER_SECOND: u32 = 8000;
pub const TICKS_PER_SECOND: u32 = TICKS_PER_CYCLE * CYCLES_PER_SECOND; // 24_576_000

/// Cycles in one full 128 s cycle-timer period.
const CYCLES_PER_WRAP: u32 = 128 * CYCLES_PER_SECOND;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CycleTime {
    pub seconds: u8, // 0..128
    pub cycle: u16,  // 0..8000
    pub offset: u16, // 0..3072
}

impl CycleTime {
    pub fn from_register(r: u32) -> CycleTime {
        CycleTime {
            seconds: (r >> 25) as u8,
            cycle: ((r >> 12) & 0x1FFF) as u16,
            offset: (r & 0xFFF) as u16,
        }
    }

    pub fn to_register(self) -> u32 {
        ((self.seconds as u32 & 0x7F) << 25) | ((self.cycle as u32) << 12) | self.offset as u32
    }

    /// Total ticks modulo 128 s.
    pub fn ticks(self) -> u32 {
        (self.seconds as u32 * CYCLES_PER_SECOND + self.cycle as u32) * TICKS_PER_CYCLE
            + self.offset as u32
    }

    pub fn from_ticks(t: u32) -> CycleTime {
        let t = t % (128 * TICKS_PER_SECOND);
        let cycles = t / TICKS_PER_CYCLE;
        CycleTime {
            seconds: (cycles / CYCLES_PER_SECOND) as u8,
            cycle: (cycles % CYCLES_PER_SECOND) as u16,
            offset: (t % TICKS_PER_CYCLE) as u16,
        }
    }

    /// 16-bit SYT field: low 4 bits of the cycle count + 12-bit offset.
    pub fn syt(self) -> u16 {
        ((self.cycle & 0xF) << 12) | self.offset
    }
}

/// Resolve a 16-bit SYT against a nearby reference time (the cycle the packet arrived in).
/// SYT only carries cycle mod 16, so pick the absolute time closest to `reference`,
/// preferring the future (SYT is a presentation time, normally a few cycles ahead).
pub fn resolve_syt(syt: u16, reference: CycleTime) -> CycleTime {
    let syt_cycle = (syt >> 12) as u32;
    let offset = (syt & 0xFFF) as u32;
    let ref_cycles = reference.ticks() / TICKS_PER_CYCLE;
    let mut delta = ((syt_cycle + 16 - (ref_cycles & 0xF)) & 0xF) as i32; // 0..15 ahead
    if delta > 12 {
        // More than 12 cycles "ahead" is really a few cycles in the past.
        delta -= 16;
    }
    // The cycle timer wraps every 128 s = 1_024_000 cycles, which is not a power of two,
    // so the arithmetic must be done modulo that period, not modulo 2^32.
    let cycles = (ref_cycles as i32 + delta).rem_euclid(CYCLES_PER_WRAP as i32) as u32;
    CycleTime::from_ticks(cycles * TICKS_PER_CYCLE + offset)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn register_roundtrip() {
        let c = CycleTime {
            seconds: 100,
            cycle: 7999,
            offset: 3071,
        };
        assert_eq!(CycleTime::from_register(c.to_register()), c);
        assert_eq!(CycleTime::from_ticks(c.ticks()), c);
    }

    #[test]
    fn syt_resolution() {
        let now = CycleTime {
            seconds: 1,
            cycle: 30,
            offset: 100,
        };
        // 3 cycles ahead
        let t = CycleTime {
            seconds: 1,
            cycle: 33,
            offset: 2000,
        };
        assert_eq!(resolve_syt(t.syt(), now), t);
        // 1 cycle behind
        let t = CycleTime {
            seconds: 1,
            cycle: 29,
            offset: 5,
        };
        assert_eq!(resolve_syt(t.syt(), now), t);
        // across a second boundary
        let now = CycleTime {
            seconds: 1,
            cycle: 7998,
            offset: 0,
        };
        let t = CycleTime {
            seconds: 2,
            cycle: 2,
            offset: 7,
        };
        assert_eq!(resolve_syt(t.syt(), now), t);
    }

    #[test]
    fn syt_resolution_across_128s_wrap() {
        // Reference just after the wrap, SYT from just before it.
        let now = CycleTime {
            seconds: 0,
            cycle: 1,
            offset: 0,
        };
        let t = CycleTime {
            seconds: 127,
            cycle: 7999,
            offset: 5,
        };
        assert_eq!(resolve_syt(t.syt(), now), t);
        // Reference just before the wrap, SYT from just after it.
        let now = CycleTime {
            seconds: 127,
            cycle: 7999,
            offset: 0,
        };
        let t = CycleTime {
            seconds: 0,
            cycle: 2,
            offset: 7,
        };
        assert_eq!(resolve_syt(t.syt(), now), t);
    }
}
