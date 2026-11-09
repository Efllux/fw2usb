use fw_amdtp::stream::PacketBuilder;
use fw_amdtp::{CycleTime, Sfc};
fn main() {
    for sfc in [Sfc::Hz44100, Sfc::Hz48000] {
        let mut builder = PacketBuilder::new(1, 2, 0, sfc);
        let mut sample_index = 0i32;
        for cycle in 0..64 {
            let mut pcm = Vec::new();
            let mut source = || {
                let mut frame = [0; 32];
                frame[0] = ((sample_index * 7919) & 0xffffff) - 0x800000;
                frame[1] = -frame[0] - 1;
                sample_index += 1;
                pcm.extend_from_slice(&frame[..2]);
                Some(frame)
            };
            let mut out = [0u8; 256];
            let (len, _) = builder.build(
                CycleTime {
                    seconds: 0,
                    cycle,
                    offset: 0,
                },
                &mut source,
                &mut out,
            );
            let samples = pcm
                .iter()
                .map(|s| format!("{:06x}", (*s as u32) & 0xffffff))
                .collect::<Vec<_>>()
                .join(",");
            println!(
                "{} {} {} {}",
                sfc.rate(),
                cycle,
                out[..len]
                    .iter()
                    .map(|b| format!("{b:02x}"))
                    .collect::<String>(),
                if samples.is_empty() { "-" } else { &samples }
            );
        }
    }
}
