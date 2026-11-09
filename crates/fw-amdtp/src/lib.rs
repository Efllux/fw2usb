//! IEC 61883-1 / -6 packet model for FireWire audio (AMDTP over CIP, AM824 samples).
//!
//! This crate is the reference model for the bridge: the FPGA link layer and the
//! microcontroller firmware must produce/consume exactly these bytes. It is `no_std`
//! and allocation-free so it can run on the bridge MCU unchanged.
//!
//! Byte order on the wire is big-endian quadlets.
#![no_std]

pub mod am824;
pub mod cip;
pub mod cycle;
pub mod stream;

pub use cip::{CipHeader, Sfc};
pub use cycle::CycleTime;
