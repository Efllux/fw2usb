//! Arbitration encoding: IEEE 1394-1995 §4.3.3 tables 4-25..28;
//! publicly cross-checked against EP1094638A2 tables 3..5, pp.3..4.
//! 1394a-2000 §4.3.3 adds disable/suspend. See docs/SOFT-PHY.md.
use crate::line::{resolve, Arb};
use Arb::{One as I, Zero as O, Z};

/// Local cable coordinates; the cable crosses A to B without changing polarity.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Pairs(pub Arb, pub Arb);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Signal {
    Idle,
    Request,
    Grant,
    ParentNotify,
    ChildNotify,
    IdentDone,
    SelfIdGrant,
    DataPrefix,
    DataEnd,
    BusReset,
    DisableNotify,
    Suspend,
}
impl Signal {
    pub const fn tx(self) -> Pairs {
        match self {
            Self::Idle => Pairs(Z, Z),
            Self::Request | Self::Grant | Self::SelfIdGrant => Pairs(Z, O),
            Self::ParentNotify => Pairs(O, Z),
            Self::ChildNotify | Self::IdentDone => Pairs(I, Z),
            Self::DataPrefix => Pairs(O, I),
            Self::DataEnd => Pairs(I, O),
            Self::BusReset => Pairs(I, I),
            Self::DisableNotify => Pairs(Z, I),
            Self::Suspend => Pairs(O, O),
        }
    }
}

/// Interpreted arbitration is NOT an inference of the remote driver.
/// EP1094638A2 table 3: own transmitted 1 dominates cancellation; own 0
/// and comparator 0 is interpreted 0 (remote may be 0 OR Z).
pub fn interpret(ours: Arb, comparator: Arb) -> Option<Arb> {
    match (ours, comparator) {
        (Z, s) => Some(s),
        (O, Z) | (I, Z) | (I, I) => Some(I),
        (O, O) => Some(O),
        _ => None,
    }
}
/// Ideal settled observation. Does not model propagation, thresholds or mismatches.
pub fn receive(ours: Pairs, peer: Pairs) -> Pairs {
    Pairs(
        interpret(ours.0, resolve(ours.0, peer.1)).unwrap(),
        interpret(ours.1, resolve(ours.1, peer.0)).unwrap(),
    )
}

/// Names deliberately retain aliases: context (tree/SID/arbitration) is necessary.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Received {
    Idle,
    ParentNotifyOrRequestCancel,
    IdentDone,
    SelfIdGrantOrRequest,
    RootContentionOrGrantOrSuspend,
    ParentHandshakeOrDataEnd,
    ChildHandshakeOrDisableNotify,
    DataPrefix,
    BusReset,
}
pub const fn decode(p: Pairs) -> Received {
    match p {
        Pairs(Z, Z) => Received::Idle,
        Pairs(Z, O) => Received::ParentNotifyOrRequestCancel,
        Pairs(Z, I) => Received::IdentDone,
        Pairs(O, Z) => Received::SelfIdGrantOrRequest,
        Pairs(O, O) => Received::RootContentionOrGrantOrSuspend,
        Pairs(O, I) => Received::ParentHandshakeOrDataEnd,
        Pairs(I, Z) => Received::ChildHandshakeOrDisableNotify,
        Pairs(I, O) => Received::DataPrefix,
        Pairs(I, I) => Received::BusReset,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn all_combinations_and_dominance() {
        for ours in [O, I, Z] {
            for peer in [O, I, Z] {
                let got = interpret(ours, resolve(ours, peer)).unwrap();
                let expected = if ours == I || peer == I {
                    I
                } else if ours == O || peer == O {
                    O
                } else {
                    Z
                };
                assert_eq!(got, expected);
            }
        }
        assert_eq!(interpret(O, I), None);
        assert_eq!(interpret(I, O), None);
    }
    #[test]
    fn tree_and_grant_handshakes() {
        use Signal::*;
        assert_eq!(receive(ParentNotify.tx(), ParentNotify.tx()), Pairs(O, O));
        assert_eq!(receive(ParentNotify.tx(), ChildNotify.tx()), Pairs(O, I));
        assert_eq!(receive(ChildNotify.tx(), Idle.tx()), Pairs(I, Z));
        assert_eq!(receive(Request.tx(), Grant.tx()), Pairs(O, O));
        assert_eq!(receive(Idle.tx(), SelfIdGrant.tx()), Pairs(O, Z));
        for ours in [
            Idle,
            Request,
            Grant,
            ParentNotify,
            ChildNotify,
            DataPrefix,
            DataEnd,
            Suspend,
        ] {
            assert_eq!(receive(ours.tx(), BusReset.tx()), Pairs(I, I));
        }
    }
    #[test]
    fn all_signal_codes() {
        let signals = [
            Signal::Idle,
            Signal::Request,
            Signal::Grant,
            Signal::ParentNotify,
            Signal::ChildNotify,
            Signal::IdentDone,
            Signal::SelfIdGrant,
            Signal::DataPrefix,
            Signal::DataEnd,
            Signal::BusReset,
            Signal::DisableNotify,
            Signal::Suspend,
        ];
        let codes = [
            Pairs(Z, Z),
            Pairs(Z, O),
            Pairs(Z, O),
            Pairs(O, Z),
            Pairs(I, Z),
            Pairs(I, Z),
            Pairs(Z, O),
            Pairs(O, I),
            Pairs(I, O),
            Pairs(I, I),
            Pairs(Z, I),
            Pairs(O, O),
        ];
        for (s, p) in signals.into_iter().zip(codes) {
            assert_eq!(s.tx(), p);
        }
    }
}
