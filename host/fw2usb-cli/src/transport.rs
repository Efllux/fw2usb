use crate::wire::Frame;
use nusb::{
    descriptors::TransferType,
    transfer::{Bulk, ControlIn, ControlType, Direction, In, Out, Recipient},
    MaybeFuture,
};
use std::{
    collections::{HashSet, VecDeque},
    fs::File,
    io::{self, Write},
    time::Duration,
};

pub trait Transport {
    fn exchange(&mut self, request: Frame) -> Result<Frame, Box<dyn std::error::Error>>;
    fn next(&mut self) -> Result<Option<Frame>, Box<dyn std::error::Error>>;
}
pub struct Replay {
    frames: Vec<Frame>,
    cursor: usize,
    used: HashSet<u32>,
}
impl Replay {
    pub fn open(path: &str) -> Result<Self, Box<dyn std::error::Error>> {
        let mut file = File::open(path)?;
        let mut frames = Vec::new();
        while let Some(f) = Frame::read(&mut file)? {
            frames.push(f);
        }
        Ok(Self {
            frames,
            cursor: 0,
            used: HashSet::new(),
        })
    }
}
impl Transport for Replay {
    fn exchange(&mut self, request: Frame) -> Result<Frame, Box<dyn std::error::Error>> {
        let query = self
            .frames
            .iter()
            .find(|f| {
                f.kind == 0
                    && f.opcode == request.opcode
                    && f.payload == request.payload
                    && f.generation == request.generation
                    && !self.used.contains(&f.id)
            })
            .ok_or("request absent from simulation transcript")?;
        let mut response = self
            .frames
            .iter()
            .find(|f| f.kind == 1 && f.id == query.id)
            .ok_or("transcript response missing")?
            .clone();
        self.used.insert(query.id);
        response.id = request.id;
        Ok(response)
    }
    fn next(&mut self) -> Result<Option<Frame>, Box<dyn std::error::Error>> {
        while self.cursor < self.frames.len() {
            let f = self.frames[self.cursor].clone();
            self.cursor += 1;
            if f.kind == 2 {
                return Ok(Some(f));
            }
        }
        Ok(None)
    }
}
pub struct Usb {
    events: VecDeque<Frame>,
    reader: nusb::io::EndpointRead<Bulk>,
    writer: nusb::io::EndpointWrite<Bulk>,
}
impl Usb {
    pub fn list() -> Result<(), Box<dyn std::error::Error>> {
        for d in nusb::list_devices().wait()? {
            if d.vendor_id() == 0x1209 && matches!(d.product_id(), 1 | 2) {
                println!(
                    "{:04x}:{:04x} {} {:?}",
                    d.vendor_id(),
                    d.product_id(),
                    d.product_string().unwrap_or(""),
                    d.serial_number()
                );
            }
        }
        Ok(())
    }
    pub fn open(serial: Option<&str>) -> Result<Self, Box<dyn std::error::Error>> {
        let matches: Vec<_> = nusb::list_devices()
            .wait()?
            .filter(|d| {
                d.vendor_id() == 0x1209
                    && matches!(d.product_id(), 1 | 2)
                    && serial.is_none_or(|s| d.serial_number() == Some(s))
            })
            .collect();
        if matches.len() != 1 {
            return Err("select exactly one adapter with --serial".into());
        }
        let device = matches[0].open().wait()?;
        let config = device.active_configuration()?;
        let descriptor = config
            .interfaces()
            .map(|i| i.first_alt_setting())
            .find(|i| i.class() == 255 && i.subclass() == 2 && i.protocol() == 1)
            .ok_or("vendor interface missing")?;
        let input = descriptor
            .endpoints()
            .find(|e| e.transfer_type() == TransferType::Bulk && e.direction() == Direction::In)
            .ok_or("bulk IN missing")?
            .address();
        let output = descriptor
            .endpoints()
            .find(|e| e.transfer_type() == TransferType::Bulk && e.direction() == Direction::Out)
            .ok_or("bulk OUT missing")?
            .address();
        let interface = device
            .claim_interface(descriptor.interface_number())
            .wait()?;
        let caps = interface
            .control_in(
                ControlIn {
                    control_type: ControlType::Vendor,
                    recipient: Recipient::Interface,
                    request: 1,
                    value: 0,
                    index: descriptor.interface_number() as u16,
                    length: 16,
                },
                Duration::from_secs(1),
            )
            .wait()?;
        if caps.len() != 16 || caps[..2] != [0, 0] {
            return Err("unsupported protocol capabilities".into());
        }
        Ok(Self {
            events: VecDeque::new(),
            reader: interface
                .endpoint::<Bulk, In>(input)?
                .reader(4096)
                .with_read_timeout(Duration::from_secs(2)),
            writer: interface.endpoint::<Bulk, Out>(output)?.writer(4096),
        })
    }
}
impl Transport for Usb {
    fn exchange(&mut self, request: Frame) -> Result<Frame, Box<dyn std::error::Error>> {
        request.write(&mut self.writer)?;
        self.writer.flush()?;
        loop {
            let response = Frame::read(&mut self.reader)?.ok_or("USB stream ended")?;
            if response.kind == 1 && response.id == request.id {
                return Ok(response);
            }
            if response.kind == 2 && response.opcode == 0x8000 {
                return Err("bus reset during request".into());
            }
            if response.kind == 2 {
                if self.events.len() >= 64 {
                    return Err(
                        io::Error::new(io::ErrorKind::OutOfMemory, "event queue overflow").into(),
                    );
                }
                self.events.push_back(response);
            }
        }
    }
    fn next(&mut self) -> Result<Option<Frame>, Box<dyn std::error::Error>> {
        if let Some(frame) = self.events.pop_front() {
            return Ok(Some(frame));
        }
        Ok(Frame::read(&mut self.reader)?)
    }
}
