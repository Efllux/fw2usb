//! Event-level, one-port/two-node S100 initialization simulation.
//! Based on 1394a-2000 §4.4.3 figures 4-22..24. Not a complete cable PHY:
//! packets are timed opaque events, ports are already connected/debounced,
//! and no suspend/repeater/normal arbitration implementation is implied.
use crate::arb::{decode, receive, Pairs, Received, Signal};
use crate::selfid::{Port, SelfId0, Speed};

pub const STEP_NS: u32 = 10;
pub const RESET_NS: u32 = 166_660;
pub const RESET_WAIT_NS: u32 = 170;
pub const FORCE_ROOT_NS: u32 = 100_000;
pub const CONFIG_TIMEOUT_NS: u32 = 166_800;
pub const CONTEND_FAST_NS: u32 = 810;
pub const CONTEND_SLOW_NS: u32 = 1_630;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State {
    Reset,
    ResetWait,
    TreeStart,
    ChildHandshake,
    ParentHandshake,
    RootContention,
    SelfStart,
    SelfGrant,
    SelfReceive,
    SpeedCapabilities,
    SelfPrefix,
    SelfData,
    SelfEnd,
    IdentDone,
    Idle,
    Fault,
}
#[derive(Clone, Copy, Debug)]
pub struct Node {
    pub state: State,
    pub force_root: bool,
    pub root: bool,
    pub phy_id: Option<u8>,
    pub gap_count: u8,
    pub initiated_reset: bool,
    age: u32,
    child: bool,
    child_identified: bool,
    received_ids: u8,
    rng: u32,
    contend_ns: u32,
}
impl Node {
    pub const fn new(force_root: bool, seed: u32) -> Self {
        Self {
            state: State::Reset,
            force_root,
            root: false,
            phy_id: None,
            gap_count: 63,
            initiated_reset: true,
            age: 0,
            child: false,
            child_identified: false,
            received_ids: 0,
            rng: seed,
            contend_ns: CONTEND_FAST_NS,
        }
    }
    pub fn reset(&mut self) {
        *self = Self::new(self.force_root, self.rng);
    }
    fn enter(&mut self, state: State) {
        self.state = state;
        self.age = 0;
    }
    pub fn output(&self) -> Pairs {
        use State::*;
        match self.state {
            Reset => Signal::BusReset,
            ParentHandshake => Signal::ParentNotify,
            ChildHandshake => Signal::ChildNotify,
            SelfGrant => Signal::SelfIdGrant,
            SelfPrefix | SelfData => Signal::DataPrefix,
            SelfEnd => Signal::DataEnd,
            IdentDone => Signal::IdentDone,
            _ => Signal::Idle,
        }
        .tx()
    }
    pub fn self_id(&self) -> Option<[u32; 2]> {
        Some(
            SelfId0 {
                phy_id: self.phy_id?,
                link_active: true,
                gap_count: self.gap_count,
                speed: Speed::S100,
                contender: true,
                power_class: 0,
                ports: [
                    if self.root { Port::Child } else { Port::Parent },
                    Port::NotPresent,
                    Port::NotPresent,
                ],
                initiated_reset: self.initiated_reset,
                more: false,
            }
            .encode(),
        )
    }
    fn step(&mut self, peer: Pairs, packet: Option<[u32; 2]>) {
        use State::*;
        let rx = decode(receive(self.output(), peer));
        if rx == Received::BusReset && !matches!(self.state, Reset | ResetWait) {
            self.reset();
            self.initiated_reset = false;
            return;
        }
        self.age += STEP_NS;
        if let Some(q) = packet {
            if SelfId0::decode(q).is_err() {
                self.enter(Fault);
                return;
            }
            self.received_ids += 1;
        }
        match self.state {
            Reset if self.age >= RESET_NS => self.enter(ResetWait),
            ResetWait if self.age >= RESET_WAIT_NS && rx == Received::Idle => self.enter(TreeStart),
            TreeStart => {
                if rx == Received::ParentNotifyOrRequestCancel {
                    self.child = true;
                    self.root = true;
                    self.enter(ChildHandshake);
                } else if !self.force_root || self.age >= FORCE_ROOT_NS {
                    self.enter(ParentHandshake);
                }
            }
            ChildHandshake if rx == Received::ChildHandshakeOrDisableNotify => {
                self.enter(SelfStart)
            }
            ParentHandshake => match rx {
                Received::ParentHandshakeOrDataEnd => self.enter(SelfStart),
                Received::RootContentionOrGrantOrSuspend => {
                    // Deterministic LCG, test-injectable seed; hardware needs independent entropy.
                    self.rng = self.rng.wrapping_mul(1_664_525).wrapping_add(1_013_904_223);
                    self.contend_ns = if self.rng & 0x8000_0000 == 0 {
                        CONTEND_FAST_NS
                    } else {
                        CONTEND_SLOW_NS
                    };
                    self.enter(RootContention);
                }
                _ => {}
            },
            RootContention if self.age > self.contend_ns => {
                if rx == Received::ParentNotifyOrRequestCancel {
                    self.child = true;
                    self.root = true;
                    self.enter(ChildHandshake);
                } else if rx == Received::Idle {
                    self.enter(ParentHandshake);
                }
            }
            SelfStart if self.root || rx == Received::SelfIdGrantOrRequest => {
                if self.child && !self.child_identified {
                    self.enter(SelfGrant);
                } else {
                    self.phy_id = Some(self.received_ids);
                    self.enter(SelfPrefix);
                }
            }
            SelfGrant if rx == Received::DataPrefix => self.enter(SelfReceive),
            SelfReceive => {
                if rx == Received::IdentDone {
                    self.child_identified = true;
                    self.enter(SpeedCapabilities);
                } else if rx == Received::Idle && !self.child {
                    self.enter(Idle);
                }
            }
            SpeedCapabilities if self.age >= 110 => self.enter(SelfStart),
            SelfPrefix if self.age >= 180 => self.enter(SelfData),
            SelfData if self.age >= 660 => self.enter(SelfEnd), // ceil(64 / 98.304 MHz) to step
            SelfEnd if self.age >= 250 => self.enter(if self.root { Idle } else { IdentDone }),
            IdentDone if rx == Received::DataPrefix => self.enter(SelfReceive),
            _ => {}
        }
        if self.age >= 300_000 && !matches!(self.state, Idle | Reset | ResetWait) {
            self.enter(Fault);
        }
    }
}

/// Both nodes sample the same previous instant (no ordering advantage).
pub struct Bus {
    pub nodes: [Node; 2],
    pub time_ns: u64,
    pub self_ids: [Option<[u32; 2]>; 2],
    pub self_id_count: usize,
    last_data: [bool; 2],
}
impl Bus {
    pub const fn new(bridge_force_root: bool, peer_force_root: bool) -> Self {
        Self {
            nodes: [
                Node::new(bridge_force_root, 1),
                Node::new(peer_force_root, 0x8000_0000),
            ],
            time_ns: 0,
            self_ids: [None; 2],
            self_id_count: 0,
            last_data: [false; 2],
        }
    }
    pub fn step(&mut self) {
        let outputs = [self.nodes[0].output(), self.nodes[1].output()];
        let mut packets = [None; 2];
        for (i, packet) in packets.iter_mut().enumerate() {
            let data = self.nodes[i].state == State::SelfData;
            if data && !self.last_data[i] {
                *packet = self.nodes[i].self_id();
                if self.self_id_count < 2 {
                    self.self_ids[self.self_id_count] = *packet;
                    self.self_id_count += 1;
                }
            }
            self.last_data[i] = data;
        }
        self.nodes[0].step(outputs[1], packets[1]);
        self.nodes[1].step(outputs[0], packets[0]);
        self.time_ns += STEP_NS as u64;
    }
    pub fn reset(&mut self) {
        for node in &mut self.nodes {
            node.reset();
        }
        self.self_ids = [None; 2];
        self.self_id_count = 0;
        self.last_data = [false; 2];
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn finish(bus: &mut Bus) {
        for _ in 0..100_000 {
            bus.step();
            if bus.nodes.iter().all(|n| n.state == State::Idle) {
                return;
            }
            assert!(
                bus.nodes.iter().all(|n| n.state != State::Fault),
                "{:?}",
                bus.nodes
            );
        }
        panic!("initialization stalled: {:?}", bus.nodes);
    }
    #[test]
    fn reset_tree_sid_idle_bridge_is_root() {
        let mut b = Bus::new(true, false);
        finish(&mut b);
        assert!(b.nodes[0].root);
        assert!(!b.nodes[1].root);
        assert_eq!(b.nodes[0].phy_id, Some(1));
        assert_eq!(b.nodes[1].phy_id, Some(0));
        assert!(b.time_ns > RESET_NS as u64);
        let child = SelfId0::decode(b.self_ids[0].unwrap()).unwrap();
        let root = SelfId0::decode(b.self_ids[1].unwrap()).unwrap();
        assert_eq!((child.phy_id, root.phy_id), (0, 1));
        assert_eq!(child.ports[0], Port::Parent);
        assert_eq!(root.ports[0], Port::Child);
        b.reset();
        finish(&mut b);
        assert_eq!(b.self_id_count, 2);
    }
    #[test]
    fn independent_contention_choices_converge() {
        let mut b = Bus::new(false, false);
        let mut contention = false;
        for _ in 0..100_000 {
            b.step();
            contention |= b.nodes.iter().any(|n| n.state == State::RootContention);
            if b.nodes.iter().all(|n| n.state == State::Idle) {
                break;
            }
        }
        assert!(contention);
        finish(&mut b);
        assert_ne!(b.nodes[0].root, b.nodes[1].root);
    }
    #[test]
    fn only_remote_force_root_does_not_guarantee_bridge_root() {
        let mut b = Bus::new(false, true);
        finish(&mut b);
        assert!(b.nodes[1].root);
    }
    #[test]
    fn new_reset_interrupts_tree() {
        let mut b = Bus::new(true, false);
        while b.nodes[1].state != State::ParentHandshake {
            b.step();
        }
        b.nodes[1].reset();
        b.step();
        assert_eq!(b.nodes[0].state, State::Reset);
        finish(&mut b);
    }
}
