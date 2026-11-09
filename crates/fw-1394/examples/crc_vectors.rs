fn main() {
    for n in 0..=256 {
        let data: Vec<u8> = (0..n).map(|i| ((i * 73 + n * 19) & 255) as u8).collect();
        let hex: String = data.iter().map(|b| format!("{b:02x}")).collect();
        println!(
            "{} {:08x}",
            if hex.is_empty() { "-" } else { &hex },
            fw_1394::crc32(&data)
        );
    }
}
