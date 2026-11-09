//! Bit-level reference model of an IEEE 1394a cable PHY, for the fw2usb soft-PHY research.
//!
//! Scope so far: the parts we are confident about and can test without hardware.
//! - [`ds`]: data-strobe encoding/decoding (the packet-transmission line code)
//! - [`line`]: arbitration line-state resolution (1 / 0 / Z with two drivers on one pair)
//! - [`selfid`]: self-ID packet #0 format
//!
//! Arbitration signal tables and the PHY state machines are still to be transcribed from
//! IEEE 1394-1995 §4 / 1394a-2000 (see docs/SOFT-PHY.md).
#![no_std]

pub mod ds;
pub mod line;
pub mod selfid;
