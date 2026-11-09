//! Data-strobe (DS) line code.
//!
//! Data is sent as NRZ on one pair; the strobe on the other pair toggles whenever the data
//! line does *not* change. Exactly one of the two lines changes every bit period, so the
//! receiver recovers the bit clock as `data XOR strobe` (which toggles every bit).
//! In 1394 cable signalling, strobe is driven on TPA and data on TPB.

/// Line levels for one bit period.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DsSymbol {
    pub data: bool,
    pub strobe: bool,
}

#[derive(Clone, Debug)]
pub struct DsEncoder {
    prev: DsSymbol,
}

impl DsEncoder {
    /// Both lines start low (idle state before a packet is modelled as 0/0).
    pub const fn new() -> Self {
        DsEncoder {
            prev: DsSymbol {
                data: false,
                strobe: false,
            },
        }
    }

    pub fn encode(&mut self, bit: bool) -> DsSymbol {
        let strobe = if bit == self.prev.data {
            !self.prev.strobe
        } else {
            self.prev.strobe
        };
        self.prev = DsSymbol { data: bit, strobe };
        self.prev
    }
}

impl Default for DsEncoder {
    fn default() -> Self {
        Self::new()
    }
}

/// Decoder working on oversampled line levels (as an FPGA would sample them).
///
/// A new bit is emitted each time the recovered clock `data ^ strobe` changes; the bit value
/// is the data level at that moment. This is the "no PLL" DS receiver approach.
#[derive(Clone, Debug)]
pub struct DsDecoder {
    prev_clk: bool,
}

impl DsDecoder {
    pub const fn new() -> Self {
        DsDecoder { prev_clk: false }
    }

    /// Feed one sample of both lines; returns `Some(bit)` when a bit boundary is detected.
    pub fn sample(&mut self, data: bool, strobe: bool) -> Option<bool> {
        let clk = data ^ strobe;
        let edge = clk != self.prev_clk;
        self.prev_clk = clk;
        edge.then_some(data)
    }
}

impl Default for DsDecoder {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn bits(seed: u32, n: usize) -> impl Iterator<Item = bool> {
        let mut x = seed;
        (0..n).map(move |_| {
            x ^= x << 13;
            x ^= x >> 17;
            x ^= x << 5;
            x & 1 == 1
        })
    }

    #[test]
    fn exactly_one_line_changes_per_bit() {
        let mut e = DsEncoder::new();
        let mut prev = DsSymbol {
            data: false,
            strobe: false,
        };
        for b in bits(1, 10_000) {
            let s = e.encode(b);
            let changes = (s.data != prev.data) as u8 + (s.strobe != prev.strobe) as u8;
            assert_eq!(changes, 1);
            prev = s;
        }
    }

    #[test]
    fn roundtrip_with_oversampling() {
        // 4× oversampling, like sampling S100 (98.304 Mb/s) with a ~400 MHz DDR capture.
        let mut e = DsEncoder::new();
        let mut d = DsDecoder::new();
        let input: [bool; 4096] = {
            let mut a = [false; 4096];
            for (i, b) in bits(7, 4096).enumerate() {
                a[i] = b;
            }
            a
        };
        let mut out = 0usize;
        for &b in input.iter() {
            let s = e.encode(b);
            for _ in 0..4 {
                if let Some(rx) = d.sample(s.data, s.strobe) {
                    assert_eq!(rx, input[out]);
                    out += 1;
                }
            }
        }
        assert_eq!(out, input.len());
    }
}
