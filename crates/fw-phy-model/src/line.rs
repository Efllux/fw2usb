//! Arbitration line states.
//!
//! During arbitration each end of a twisted pair either drives a differential "1", a "0",
//! or nothing ("Z"). What the pair carries is the combination of both drivers: if only one
//! drives, its value wins; if both drive the *same* value, that value; if they drive
//! *opposite* values the differential voltages cancel and the pair reads as Z. Each port
//! learns what the far end is sending by comparing the received state with what it drives
//! itself. The full meaning table (TX_REQUEST, PARENT_NOTIFY, …) is still to be transcribed
//! from the spec.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Arb {
    Zero,
    One,
    Z,
}

/// Resolve the state seen on a pair driven by both ends.
pub fn resolve(a: Arb, b: Arb) -> Arb {
    match (a, b) {
        (Arb::Z, x) | (x, Arb::Z) => x,
        (x, y) if x == y => x,
        _ => Arb::Z, // 1 + 0 cancel
    }
}

/// What the far end must be driving, given what we drive and what we receive.
/// Returns `None` when the observation is ambiguous (we drive 1 or 0 and read Z, which means
/// the far end drives the opposite value; we return that) or inconsistent.
pub fn infer_remote(ours: Arb, seen: Arb) -> Option<Arb> {
    match (ours, seen) {
        (Arb::Z, s) => Some(s),
        (o, Arb::Z) => Some(if o == Arb::One { Arb::Zero } else { Arb::One }),
        (o, s) if o == s => Some(Arb::Z), // could also be "same value"; Z is the conservative reading
        _ => None,
    }
}

/// Classify a differential voltage with a window comparator (two thresholds).
/// `threshold_mv` is the arbitration comparator threshold (spec value to be confirmed).
pub fn classify(diff_mv: i32, threshold_mv: i32) -> Arb {
    if diff_mv > threshold_mv {
        Arb::One
    } else if diff_mv < -threshold_mv {
        Arb::Zero
    } else {
        Arb::Z
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const ALL: [Arb; 3] = [Arb::Zero, Arb::One, Arb::Z];

    #[test]
    fn resolution_table() {
        assert_eq!(resolve(Arb::One, Arb::Zero), Arb::Z);
        assert_eq!(resolve(Arb::One, Arb::Z), Arb::One);
        assert_eq!(resolve(Arb::Zero, Arb::Zero), Arb::Zero);
        assert_eq!(resolve(Arb::Z, Arb::Z), Arb::Z);
        for a in ALL {
            for b in ALL {
                assert_eq!(resolve(a, b), resolve(b, a), "symmetric");
            }
        }
    }

    #[test]
    fn inference_is_consistent_with_resolution() {
        for ours in ALL {
            for remote in ALL {
                let seen = resolve(ours, remote);
                let guess = infer_remote(ours, seen).expect("never inconsistent for a real pair");
                assert_eq!(resolve(ours, guess), seen);
            }
        }
    }

    #[test]
    fn window_comparator() {
        assert_eq!(classify(250, 168), Arb::One);
        assert_eq!(classify(-250, 168), Arb::Zero);
        assert_eq!(classify(20, 168), Arb::Z);
    }
}
