//! Packet-zero topology reduction, IEEE1394a self-ID ordering (§4.4.3.3).
//! Extended self-ID packets are explicitly rejected until their ports are modeled.
use crate::Error;
use fw_phy_model::selfid::{Port, SelfId0};

#[derive(Debug, PartialEq, Eq)]
pub struct Topology<const N: usize> {
    pub parent: [Option<u8>; N],
    pub count: usize,
    pub root: u8,
}

impl<const N: usize> Topology<N> {
    pub fn from_self_ids(packets: &[[u32; 2]]) -> Result<Self, Error> {
        if packets.is_empty() || packets.len() > N || packets.len() > 63 {
            return Err(Error::Length);
        }
        let mut parent = [None; N];
        let mut stack = [0u8; N];
        let mut depth = 0usize;
        for (id, &packet) in packets.iter().enumerate() {
            let sid = SelfId0::decode(packet).map_err(|_| Error::Field)?;
            if sid.phy_id as usize != id || sid.more {
                return Err(Error::Field);
            }
            let parents = sid.ports.iter().filter(|p| **p == Port::Parent).count();
            if parents != usize::from(id + 1 < packets.len()) {
                return Err(Error::Field);
            }
            let children = sid.ports.iter().filter(|p| **p == Port::Child).count();
            if children > depth {
                return Err(Error::Field);
            }
            for _ in 0..children {
                depth -= 1;
                parent[stack[depth] as usize] = Some(id as u8);
            }
            stack[depth] = id as u8;
            depth += 1;
        }
        if depth != 1 {
            return Err(Error::Field);
        }
        Ok(Self {
            parent,
            count: packets.len(),
            root: stack[0],
        })
    }
}

/// Alpha PHY configuration quadlet and inverse, IEEE1394-2008 §16.3.2.3.
pub fn force_root_packet(root: u8, gap_count: Option<u8>) -> Result<[u32; 2], Error> {
    if root > 62 || gap_count.is_some_and(|g| g > 63) {
        return Err(Error::Field);
    }
    let q = ((root as u32) << 24)
        | 0x0080_0000
        | gap_count.map_or(0, |g| 0x0040_0000 | ((g as u32) << 16));
    Ok([q, !q])
}

#[cfg(test)]
mod tests {
    use super::*;
    use fw_phy_model::selfid::Speed;
    fn packet(id: u8, ports: [Port; 3]) -> [u32; 2] {
        SelfId0 {
            phy_id: id,
            ports,
            link_active: true,
            gap_count: 63,
            speed: Speed::S400,
            contender: true,
            power_class: 0,
            initiated_reset: false,
            more: false,
        }
        .encode()
    }
    #[test]
    fn branched_tree_and_invalid_orphans() {
        use Port::*;
        let packets = [
            packet(0, [Parent, NotPresent, NotPresent]),
            packet(1, [Parent, NotPresent, NotPresent]),
            packet(2, [Child, Child, NotPresent]),
        ];
        let t = Topology::<8>::from_self_ids(&packets).unwrap();
        assert_eq!(t.root, 2);
        assert_eq!(&t.parent[..3], &[Some(2), Some(2), None]);
        let bad = [
            packets[0],
            packet(1, [NotConnected, NotPresent, NotPresent]),
        ];
        assert_eq!(Topology::<8>::from_self_ids(&bad), Err(Error::Field));
        let force = force_root_packet(2, Some(63)).unwrap();
        assert_eq!(force, [0x02ff0000, 0xfd00ffff]);
    }
}
