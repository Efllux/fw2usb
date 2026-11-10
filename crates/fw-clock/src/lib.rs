//! Bounded SYT frequency recovery research model, no resampling.
//! Call once per timestamped SYT_INTERVAL boundary, with an extended sample index.
//! Bus/USB correlation must be measured independently; a nominal bus frequency
//! alone cannot distinguish bus-oscillator error from device-oscillator error.
#![no_std]

const MODULUS: u32 = 16 * 3072;

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Error {
    NoTimestamp,
    BadOffset,
    Discontinuity,
    Outlier,
    BadCorrelation,
}

pub struct Recovery {
    nominal: f64,
    rate: f64,
    previous: Option<(u32, u64)>,
    ticks: u64,
    samples: u64,
    windows: u32,
    age_us: u32,
}
impl Recovery {
    pub fn new(rate: u32) -> Self {
        assert!(matches!(
            rate,
            44100 | 48000 | 88200 | 96000 | 176400 | 192000
        ));
        Self {
            nominal: rate as f64,
            rate: rate as f64,
            previous: None,
            ticks: 0,
            samples: 0,
            windows: 0,
            age_us: 0,
        }
    }
    /// 4096 sample frames per window; first-order frequency LPF alpha=1/16.
    /// Input gap must be less than half the 2ms SYT wrap period. Reject outliers
    /// beyond 2000ppm; caller resets recovery after rate/generation changes.
    pub fn observe(
        &mut self,
        syt: u16,
        sample_index: u64,
        bus_hz_per_usb_second: f64,
    ) -> Result<bool, Error> {
        if syt == 0xffff {
            return Err(Error::NoTimestamp);
        }
        let offset = u32::from(syt & 0xfff);
        if offset >= 3072 {
            return Err(Error::BadOffset);
        }
        if !(24_000_000.0..25_000_000.0).contains(&bus_hz_per_usb_second) {
            return Err(Error::BadCorrelation);
        }
        self.age_us = 0;
        let time = u32::from(syt >> 12) * 3072 + offset;
        let old = self.previous.replace((time, sample_index));
        let Some((old_time, old_samples)) = old else {
            return Ok(false);
        };
        let delta = (time + MODULUS - old_time) % MODULUS;
        let ds = sample_index
            .checked_sub(old_samples)
            .ok_or(Error::Discontinuity)?;
        if delta == 0 || delta >= MODULUS / 2 || ds == 0 || ds > 128 {
            self.ticks = 0;
            self.samples = 0;
            return Err(Error::Discontinuity);
        }
        self.ticks += u64::from(delta);
        self.samples += ds;
        if self.samples < 4096 {
            return Ok(false);
        }
        let measured = self.samples as f64 * bus_hz_per_usb_second / self.ticks as f64;
        self.ticks = 0;
        self.samples = 0;
        if (measured / self.nominal - 1.0).abs() > 0.002 {
            return Err(Error::Outlier);
        }
        self.rate += (measured - self.rate) / 16.0;
        self.windows += 1;
        Ok(true)
    }
    /// Controller calls this on bus reset, rate change or500ms timestamp loss.
    /// It must also stop playback and invalidate USB Clock Validity.
    pub fn elapse(&mut self, microseconds: u32) {
        self.age_us = self.age_us.saturating_add(microseconds);
        if self.age_us >= 500_000 {
            self.invalidate();
        }
    }
    pub fn invalidate(&mut self) {
        self.previous = None;
        self.ticks = 0;
        self.samples = 0;
        self.windows = 0;
        self.rate = self.nominal;
    }
    pub fn rate(&self) -> f64 {
        self.rate
    }
    pub fn locked(&self) -> bool {
        self.windows >= 64
    }
    /// HS explicit feedback, unsigned16.16 samples per125us microframe.
    pub fn feedback(&self) -> u32 {
        (self.rate * 65536.0 / 8000.0 + 0.5) as u32
    }
    /// 32-bit phase accumulator increment, MCLK=256fs. Clock must exceed2*MCLK.
    pub fn mclk_increment(&self, clock_hz: u32) -> Option<u32> {
        if f64::from(clock_hz) <= self.rate * 512.0 {
            return None;
        }
        Some((self.rate * 256.0 * 4294967296.0 / f64::from(clock_hz) + 0.5) as u32)
    }
}

/// Ideal digital phase accumulator model. This validates numerical resolution,
/// not FPGA clock-tree jitter. Never use a fabric NCO output as a routed clock.
#[derive(Default)]
pub struct Nco {
    phase: u32,
}
impl Nco {
    pub fn advance(&mut self, increment: u32, clocks: u64) -> u64 {
        let sum = u128::from(self.phase) + u128::from(increment) * u128::from(clocks);
        self.phase = sum as u32;
        (sum >> 32) as u64
    }
    pub fn high(&self) -> bool {
        self.phase & 0x8000_0000 != 0
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn drift_jitter_wrap_and_usb_correlation() {
        for nominal in [44100, 48000, 96000, 192000] {
            for ppm in [-200.0, -100.0, 0.0, 100.0, 200.0] {
                // Independent bus oscillator +75ppm, USB -40ppm.
                let bus_hz = 24_576_000.0 * 1.000075;
                let usb_scale = 0.999960;
                let real = f64::from(nominal) * (1.0 + ppm / 1e6);
                let expected = real / usb_scale;
                let interval = if nominal <= 48000 {
                    8
                } else if nominal <= 96000 {
                    16
                } else {
                    32
                };
                let mut r = Recovery::new(nominal);
                for event in 0..100_000u64 {
                    let sample = event * interval;
                    let jitter = ((event * 17 % 19) as i64 - 9) as f64;
                    let tick = (sample as f64 * bus_hz / real + 1_000_000.0 + jitter) as u64
                        % u64::from(MODULUS);
                    let syt = (((tick / 3072) << 12) | (tick % 3072)) as u16;
                    r.observe(syt, sample, bus_hz / usb_scale).unwrap();
                }
                assert!(r.locked());
                assert!(
                    (r.rate() / expected - 1.0).abs() * 1e6 < 2.0,
                    "{} {}",
                    nominal,
                    r.rate()
                );
                assert!((f64::from(r.feedback()) * 8000.0 / 65536.0 - r.rate()).abs() < 0.062);
                let inc = r.mclk_increment(196_608_000).unwrap();
                assert!(
                    (f64::from(inc) * 196_608_000.0 / 4294967296.0 / 256.0 - r.rate()).abs()
                        < 0.001
                );
            }
        }
    }
    #[test]
    fn drift_step_fifo_bound_and_clock_loss() {
        let mut r = Recovery::new(48000);
        let mut time = 1_000_000.0;
        let mut consumed = 0.0f64;
        let mut produced = 0.0f64;
        for event in 0..100_000u64 {
            let real = 48000.0 * (1.0 + if event < 50_000 { -150.0 } else { 150.0 } / 1e6);
            let dt = 8.0 / real;
            time += dt * 24_576_000.0;
            produced += 8.0;
            consumed += r.rate() * dt;
            // Model starts centered in a1024-frame FIFO, no SRC/drop/duplication.
            assert!((produced - consumed).abs() < 64.0);
            let tick = (time as u64) % u64::from(MODULUS);
            r.observe(
                (((tick / 3072) << 12) | (tick % 3072)) as u16,
                event * 8,
                24_576_000.0,
            )
            .unwrap();
        }
        assert!((r.rate() / 48007.2 - 1.0).abs() < 2e-6);
        r.elapse(499_999);
        assert!(r.locked());
        r.elapse(1);
        assert!(!r.locked());
    }
    #[test]
    fn nco_phase_continuity_and_expiration() {
        let mut r = Recovery::new(48000);
        let inc = r.mclk_increment(196_608_000).unwrap();
        let mut nco = Nco::default();
        let a = nco.advance(inc, 98_304_001);
        let b = nco.advance(inc, 98_303_999);
        assert_eq!(a + b, 12_288_000);
        assert!(!nco.high());
        r.invalidate();
        assert!(!r.locked());
        assert_eq!(r.feedback(), 6 << 16);
    }
    #[test]
    fn invalid_discontinuous_and_rate_switch_reset() {
        let mut r = Recovery::new(48000);
        assert_eq!(r.observe(0xffff, 0, 24_576_000.0), Err(Error::NoTimestamp));
        assert_eq!(r.observe(0x0c00, 0, 24_576_000.0), Err(Error::BadOffset));
        assert_eq!(r.observe(0, 0, 0.0), Err(Error::BadCorrelation));
        r.observe(0, 0, 24_576_000.0).unwrap();
        assert_eq!(r.observe(0, 8, 24_576_000.0), Err(Error::Discontinuity));
        assert!(!r.locked());
        r = Recovery::new(44100);
        assert_eq!(r.feedback(), 361267);
        assert!(r.mclk_increment(10_000_000).is_none());
    }
}
