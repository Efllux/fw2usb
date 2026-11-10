fn main() {
    for n in 0..=32 {
        let data: Vec<u8> = (0..n).map(|i| (i * 17) as u8).collect();
        let mut out = [0u8; 128];
        let bytes = fw_1394::iso_packet(3, 1, 0, &data, &mut out).unwrap();
        println!(
            "{}",
            bytes.iter().map(|b| format!("{b:02x}")).collect::<String>()
        );
    }
    let mut out = [0u8; 128];
    let bytes = fw_1394::read_quadlet(0xffc1, 0xffc0, 3, 0xfffff0000400, &mut out).unwrap();
    println!(
        "{}",
        bytes.iter().map(|b| format!("{b:02x}")).collect::<String>()
    );
}
