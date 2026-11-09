//! Regenerate docs/SOFT-PHY.md capacity tables. Sources and caveats there.
use fw_amdtp::bandwidth::{minimum_speed, reservation, stream_payload};
fn main() {
    let rows: &[(&str, &[u32])] = &[
        ("BeBoB PRO10 48k", &[360, 360]),
        ("BeBoB PRO10 96k", &[712, 712]),
        ("BeBoB PRO26io 48k max", &[872, 872]),
        ("DICE PRO24 48k", &[552, 296]),
        ("DICE PRO40 48k 4-stream", &[360, 328, 424, 264]),
        ("DICE PRO40 TCD3070 48k", &[680, 680]),
        ("RME FF400 48k", &[576, 576]),
        ("RME FF800 48k", &[896, 896]),
        ("RME FF400 192k", &[1280, 1280]),
        ("RME FF800 192k", &[1536, 1536]),
        ("OXFW FireWave 6out 48k", &[200]),
        ("EFW AudioFire12 48k", &[424, 424]),
        ("MOTU 828mkII ADAT 48k", &[616, 616]),
        ("MOTU UltraLiteMk3 192k", &[1288, 1672]),
        ("Digi002/003 48k", &[616, 616]),
        ("TASCAM FW1884 48k", &[648, 584]),
    ];
    println!("| Profile | Peak data bytes | S100 units | S200 units | S400 units | Capacity minimum |\n|---|---|---:|---:|---:|---|");
    for (name, payloads) in rows {
        let units: [u32; 3] = core::array::from_fn(|s| {
            payloads
                .iter()
                .map(|&p| reservation(p, s as u8, 63).unwrap())
                .sum()
        });
        let speed = match minimum_speed(payloads, 63) {
            Some(0) => "S100",
            Some(1) => "S200",
            Some(2) => "S400",
            _ => "exceeds S400",
        };
        println!(
            "| {name} | {payloads:?} | {} | {} | {} | {speed} |",
            units[0], units[1], units[2]
        );
    }
    assert_eq!(stream_payload(0, 18 * 4, 8), Some(576));
}
