//! Bit-level reference model of an IEEE 1394a cable PHY, for the fw2usb soft-PHY research.
//!
//! Scope so far: the parts we are confident about and can test without hardware.
//! - [`ds`]: data-strobe encoding/decoding (the packet-transmission line code)
//! - [`line`]: arbitration line-state resolution (1 / 0 / Z with two drivers on one pair)
//! - [`selfid`]: self-ID packet #0 format
//!
//! [`arb`] adds sourced transmit/interpretation tables; [`two_node`] models
//! signal handshakes and timed opaque self-ID packets. See docs/SOFT-PHY.md
//! for scope: this is not a conformance-complete PHY.
#![no_std]

pub mod arb;
pub mod ds;
pub mod line;
pub mod selfid;
pub mod two_node;
