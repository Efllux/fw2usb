use fw2usb_cli::{client::Session, transport};
use std::{fs::File, io::Write};
use transport::{Replay, Transport, Usb};
type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
fn number(s: &str) -> Result<u64> {
    Ok(if let Some(h) = s.strip_prefix("0x") {
        u64::from_str_radix(h, 16)?
    } else {
        s.parse()?
    })
}
fn wav(path: &str, rate: u32, channels: u16, pcm: &[u8]) -> Result<()> {
    let len = u32::try_from(pcm.len())?;
    let block = channels.checked_mul(3).ok_or("channel overflow")?;
    let mut file = File::create(path)?;
    file.write_all(b"RIFF")?;
    file.write_all(&len.checked_add(36).ok_or("WAV too large")?.to_le_bytes())?;
    file.write_all(b"WAVEfmt ")?;
    file.write_all(&16u32.to_le_bytes())?;
    file.write_all(&1u16.to_le_bytes())?;
    file.write_all(&channels.to_le_bytes())?;
    file.write_all(&rate.to_le_bytes())?;
    file.write_all(
        &rate
            .checked_mul(block as u32)
            .ok_or("rate overflow")?
            .to_le_bytes(),
    )?;
    file.write_all(&block.to_le_bytes())?;
    file.write_all(&24u16.to_le_bytes())?;
    file.write_all(b"data")?;
    file.write_all(&len.to_le_bytes())?;
    file.write_all(pcm)?;
    Ok(())
}
fn run() -> Result<()> {
    let mut args: Vec<String> = std::env::args().skip(1).collect();
    let mut replay = None;
    let mut socket = None;
    let mut serial = None;
    let mut generation = 0u32;
    let mut explicit_generation = false;
    while args.first().is_some_and(|s| s.starts_with("--")) {
        if args.len() < 2 {
            return Err("option value missing".into());
        }
        let key = args.remove(0);
        let value = args.remove(0);
        match key.as_str() {
            "--replay" => replay = Some(value),
            "--socket" => socket = Some(value),
            "--serial" => serial = Some(value),
            "--generation" => {
                generation = value.parse()?;
                explicit_generation = true;
            }
            _ => return Err("unknown option".into()),
        }
    }
    let command = args.first().map(String::as_str).unwrap_or("list");
    if command == "list" {
        if let Some(path) = replay {
            Replay::open(&path)?;
            println!("fw2usb simulation transcript {path}");
            return Ok(());
        }
        return Usb::list();
    }
    if socket.is_some() && (replay.is_some() || serial.is_some()) {
        return Err("choose one transport".into());
    }
    let transport: Box<dyn Transport> = if let Some(path) = socket {
        #[cfg(unix)]
        {
            Box::new(fw2usb_cli::transport::Loopback::open(&path)?)
        }
        #[cfg(not(unix))]
        {
            return Err("Unix socket loopback requires Unix".into());
        }
    } else if let Some(path) = replay {
        Box::new(Replay::open(&path)?)
    } else {
        Box::new(Usb::open(serial.as_deref())?)
    };
    let mut session = Session::new(transport, generation);
    if !explicit_generation && command != "bus-info" {
        session.call(3, Vec::new())?;
        generation = session.generation;
    }
    let arg = |i: usize| args.get(i).map(String::as_str).ok_or("argument missing");
    match command {
        "bus-info"=>{let data=session.call(3,Vec::new())?;println!("generation={} bus-info={}",session.generation,data.iter().map(|b|format!("{b:02x}")).collect::<String>());},
        "self-id"=>{let data=session.call(4,Vec::new())?;if !data.len().is_multiple_of(8){return Err("malformed self-ID dump".into());}for pair in data.as_chunks::<8>().0{let a=u32::from_be_bytes(pair[..4].try_into()?);let b=u32::from_be_bytes(pair[4..].try_into()?);if a!=!b{return Err("bad self-ID inverse".into());}println!("{a:08x} {b:08x}");}},
        "read"=>{let data=session.read(u16::try_from(number(arg(1)?)?)?,number(arg(2)?)?,4)?;println!("0x{:08x}",u32::from_be_bytes(data.try_into().map_err(|_|"short quadlet")?));},
        "write"=>{session.submit(u16::try_from(number(arg(1)?)?)?,number(arg(2)?)?,0,&u32::try_from(number(arg(3)?)?)?.to_be_bytes(),4)?;},
        "cas"=>{
            let node=u16::try_from(number(arg(1)?)?)?;let address=number(arg(2)?)?;
            let compare=number(arg(3)?)?;let replacement=number(arg(4)?)?;
            let bits=args.get(5).map(|s|number(s)).transpose()?.unwrap_or(32);
            let (a,b)=match bits {32=>(u32::try_from(compare)?.to_be_bytes().to_vec(),u32::try_from(replacement)?.to_be_bytes().to_vec()),64=>(compare.to_be_bytes().to_vec(),replacement.to_be_bytes().to_vec()),_=>return Err("CAS width must be32 or64".into())};
            let old=session.compare_swap(node,address,&a,&b)?;println!("{}",old.iter().map(|b|format!("{b:02x}")).collect::<String>());
            if old!=a{return Err("compare mismatch".into());}
        },
        "config-rom"=>{
            let node=u16::try_from(number(arg(1)?)?)?;let header=session.read(node,0xfffff0000400,4)?;
            let initial=(header[0] as u32+2)*4;if initial>4096{return Err("ROM bound exceeded".into());}
            let prefix=session.read(node,0xfffff0000400,initial)?;
            let root=(header[0] as usize+1)*4;
            let entries=u16::from_be_bytes(prefix[root..root+2].try_into()?) as u32;
            let length=initial+entries*4;if length>4096{return Err("ROM bound exceeded".into());}
            let rom=session.read(node,0xfffff0000400,length)?;
            fw_1394::validate_root_rom(&rom).map_err(|_|"invalid config ROM CRC/bounds")?;
            if let Some(path)=args.get(2){std::fs::write(path,&rom)?;}else{println!("{}",rom.iter().map(|b|format!("{b:02x}")).collect::<String>());}
        },
        "iso-send"=>{
            let channel=u8::try_from(number(arg(1)?)?)?;let hex=arg(2)?;
            if !hex.is_ascii() || !hex.len().is_multiple_of(2) || hex.len()>512 {return Err("ISO payload must be hex, maximum256 bytes".into());}
            let data=(0..hex.len()).step_by(2).map(|i|u8::from_str_radix(&hex[i..i+2],16)).collect::<std::result::Result<Vec<_>,_>>()?;
            let lead=args.get(3).map(|s|number(s)).transpose()?.unwrap_or(8);
            if lead==0 || lead>8000 {return Err("lead must be1..8000 cycles".into());}
            let handle=session.iso_tx_create(channel,2,256)?;
            let result=(|| -> Result<()> {
                let (now,_)=session.clock_snapshot()?;
                let cycle=(((now>>25) as u64*8000+((now>>12)&8191) as u64+lead)%1_024_000) as u32;
                let target=((cycle/8000)<<25)|((cycle%8000)<<12);
                session.iso_send(handle,channel,1,0,target,&data)
            })();
            let cleanup=session.call(0x202,handle.to_le_bytes().to_vec());
            result?;cleanup?;
        },
        "record"=>{
            let channel=u8::try_from(number(arg(1)?)?)?;if channel>63{return Err("channel out of range".into());}
            let path=arg(2)?;let rate=u32::try_from(number(arg(3)?)?)?;let channels=u16::try_from(number(arg(4)?)?)?;
            if channels==0 || channels>32{return Err("invalid channel count".into());}
            let mut create=vec![0,channel,2,0];create.extend(4096u32.to_le_bytes());create.extend(64u32.to_le_bytes());
            let handle=session.call(0x200,create)?;if handle.len()<4{return Err("missing ISO handle".into());}
            let credits=handle.len()>=16 && u32::from_le_bytes(handle[12..16].try_into()?)&1!=0;
            let handle=u32::from_le_bytes(handle[..4].try_into()?);let recording=(|| -> Result<Vec<u8>> {
            if credits {session.iso_credit(handle,32,8192)?;}
            let mut returned_packets=0;let mut returned_bytes=0;
            let mut sequence=None;
            let mut parser=fw_amdtp::stream::PacketParser::new();let mut pcm=Vec::new();
            let max_packets=args.get(5).map(|s|number(s)).transpose()?.unwrap_or(8000);let mut packets=0;
            while packets<max_packets {
                let Some(frame)=session.transport.next()? else{break;};
                if frame.kind!=2{continue;}
                if frame.opcode==0x8000 || frame.opcode==0x203{return Err("reset/loss interrupted recording".into());}
                if frame.opcode!=0x201{continue;}
                let data=&frame.payload;if data.len()<32{return Err("short ISO record".into());}
                let get=|i|u32::from_le_bytes(data[i..i+4].try_into().unwrap());
                if get(0)!=handle{continue;}
                if frame.generation!=generation || get(4)!=generation || data[28]!=channel || data[31]&3!=3{return Err("invalid/stale ISO record".into());}
                let seq=get(8);if sequence.is_some_and(|last:u32|seq!=last.wrapping_add(1)){return Err("ISO sequence loss".into());}sequence=Some(seq);
                let length=get(24) as usize;if data.len()!=32+length{return Err("ISO length mismatch".into());}
                let payload=&data[32..];let cip=fw_amdtp::CipHeader::decode(payload).map_err(|_|"bad CIP")?;
                if cip.fmt!=0x10 || u16::from(cip.dbs)<channels || cip.dbs==0 || !(payload.len()-8).is_multiple_of(cip.dbs as usize*4){return Err("partial AMDTP frame".into());}
                if payload.len()>8 && cip.sfc().map(|s|s.rate())!=Some(rate){return Err("sample rate changed".into());}
                let mut expected_channel=0usize;
                let mut channel_error=false;
                let event=parser.parse(payload,&mut |_,ch,sample|{channel_error|=ch>=channels as usize;if ch<channels as usize{channel_error|=ch!=expected_channel;expected_channel=(expected_channel+1)%channels as usize;pcm.extend_from_slice(&sample.to_le_bytes()[..3]);}}).map_err(|_|"bad AMDTP")?;
                if channel_error || expected_channel!=0 || matches!(event,fw_amdtp::stream::RxEvent::Data{dbc_gap:true,..}){return Err("AMDTP discontinuity".into());}
                packets+=1;
                if credits {
                    returned_packets+=1;returned_bytes+=56+length as u32;
                    if returned_packets>=8 || returned_bytes>=4096 {
                        session.iso_credit(handle,returned_packets,returned_bytes)?;returned_packets=0;returned_bytes=0;
                    }
                }
            }
            Ok(pcm)
            })();
            let cleanup=session.call(0x202,handle.to_le_bytes().to_vec());
            let pcm=recording?;cleanup?;
            wav(path,rate,channels,&pcm)?;println!("recorded {} frames",pcm.len()/(channels as usize*3));
        },
        _=>return Err("commands: list, bus-info, self-id, config-rom NODE [FILE], read NODE ADDR, write NODE ADDR VALUE, record CHANNEL WAV RATE CHANNELS [PACKETS]".into()),
    }
    Ok(())
}
fn main() {
    if let Err(error) = run() {
        eprintln!("fw2usb: {error}");
        std::process::exit(1);
    }
}
