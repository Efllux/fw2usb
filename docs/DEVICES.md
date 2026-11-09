# Devices

Devices we want to support, and who can test them. **Add yours via a "Device report" issue or a PR.**

Legend: 🎯 target · 🧪 in progress · ✅ works · ❓ unknown

| Device | Chipset / protocol | Prior open-source support | Testers | fw2usb |
|---|---|---|---|---|
| Focusrite Saffire PRO 10 I/O | BeBoB | Linux `snd-bebob`, FFADO | — | 🎯 |
| Focusrite Saffire PRO 26 I/O | BeBoB | Linux `snd-bebob`, FFADO | — | 🎯 |
| Focusrite Saffire Pro 24 / 24 DSP / 40 | DICE (TCD22xx) | Linux `snd-dice`, ASFireWire (macOS) | — | 🎯 |
| Focusrite Liquid Saffire 56 | DICE | Linux `snd-dice`, snd-firewire-ctl-services | — | ❓ |
| M-Audio FireWire 410 / 1814 | BeBoB | Linux `snd-bebob` | — | ❓ |
| RME Fireface 400 / 800 | RME proprietary | Linux `snd-fireface` | — | ❓ |
| MOTU 828 / UltraLite family | MOTU proprietary | Linux `snd-firewire-motu` | — | ❓ |
| DV camcorders | AV/C + IEC 61883-2 | dvgrab, libiec61883 | — | later |
| SBP-2 hard drives | SBP-2 | Linux `firewire-sbp2` | — | later |

References: [Linux FireWire subsystem](https://ieee1394.docs.kernel.org/en/latest/about.html),
[FFADO](https://www.ffado.org/), [snd-firewire-ctl-services](https://github.com/alsa-project/snd-firewire-ctl-services),
[ASFireWire](https://www.asfw.net/hardware/).
