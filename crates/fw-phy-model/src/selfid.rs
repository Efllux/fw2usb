//! Self-ID packet #0 (IEEE 1394-1995 §4.3.4.1, as amended by 1394a).
//!
//! ```text
//! 31 30 | 29..24 | 23 | 22 | 21..16 | 15..14 | 13..12 | 11 | 10..8 | 7..6 | 5..4 | 3..2 | 1 | 0
//!  1  0 | phy_ID |  0 |  L | gap_cnt|   sp   |  rsv   |  c |  pwr  |  p0  |  p1  |  p2  | i | m
//! ```
//! Sent as this quadlet followed by its bitwise inverse.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Speed {
    S100 = 0,
    S200 = 1,
    S400 = 2,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Port {
    NotPresent = 0b00,
    NotConnected = 0b01,
    Parent = 0b10,
    Child = 0b11,
}

impl Port {
    fn from_bits(b: u32) -> Port {
        match b & 3 {
            0 => Port::NotPresent,
            1 => Port::NotConnected,
            2 => Port::Parent,
            _ => Port::Child,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SelfId0 {
    pub phy_id: u8,
    /// Link active.
    pub link_active: bool,
    pub gap_count: u8,
    pub speed: Speed,
    /// Contender for isochronous resource manager.
    pub contender: bool,
    /// Power class (0 = no power needed/provided).
    pub power_class: u8,
    pub ports: [Port; 3],
    /// Initiated the bus reset.
    pub initiated_reset: bool,
    /// More self-ID packets follow (nodes with >3 ports).
    pub more: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SelfIdError {
    NotSelfId,
    NotPacketZero,
    BadInverse,
    BadSpeed,
}

impl SelfId0 {
    pub fn encode(&self) -> [u32; 2] {
        let q = (0b10 << 30)
            | ((self.phy_id as u32 & 0x3F) << 24)
            | ((self.link_active as u32) << 22)
            | ((self.gap_count as u32 & 0x3F) << 16)
            | ((self.speed as u32) << 14)
            | ((self.contender as u32) << 11)
            | ((self.power_class as u32 & 7) << 8)
            | ((self.ports[0] as u32) << 6)
            | ((self.ports[1] as u32) << 4)
            | ((self.ports[2] as u32) << 2)
            | ((self.initiated_reset as u32) << 1)
            | self.more as u32;
        [q, !q]
    }

    pub fn decode(q: [u32; 2]) -> Result<SelfId0, SelfIdError> {
        let [a, b] = q;
        if a >> 30 != 0b10 {
            return Err(SelfIdError::NotSelfId);
        }
        if b != !a {
            return Err(SelfIdError::BadInverse);
        }
        if (a >> 23) & 1 != 0 {
            return Err(SelfIdError::NotPacketZero);
        }
        let speed = match (a >> 14) & 3 {
            0 => Speed::S100,
            1 => Speed::S200,
            2 => Speed::S400,
            _ => return Err(SelfIdError::BadSpeed),
        };
        Ok(SelfId0 {
            phy_id: ((a >> 24) & 0x3F) as u8,
            link_active: (a >> 22) & 1 == 1,
            gap_count: ((a >> 16) & 0x3F) as u8,
            speed,
            contender: (a >> 11) & 1 == 1,
            power_class: ((a >> 8) & 7) as u8,
            ports: [
                Port::from_bits(a >> 6),
                Port::from_bits(a >> 4),
                Port::from_bits(a >> 2),
            ],
            initiated_reset: (a >> 1) & 1 == 1,
            more: a & 1 == 1,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn soft_phy_self_id() {
        // What the fw2usb soft PHY would announce: S100 only, one connected port,
        // link active, IRM contender, no bus power.
        let s = SelfId0 {
            phy_id: 1,
            link_active: true,
            gap_count: 0x3F,
            speed: Speed::S100,
            contender: true,
            power_class: 0,
            ports: [Port::Child, Port::NotPresent, Port::NotPresent],
            initiated_reset: false,
            more: false,
        };
        let q = s.encode();
        assert_eq!(q[0], 0x817F_08C0);
        assert_eq!(q[1], !0x817F_08C0);
        assert_eq!(SelfId0::decode(q).unwrap(), s);
    }

    #[test]
    fn rejects_corrupt_inverse() {
        assert_eq!(
            SelfId0::decode([0x817F_08C0, 0]),
            Err(SelfIdError::BadInverse)
        );
    }
}
