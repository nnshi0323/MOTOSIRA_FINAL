# MOTOSIRA — Wiring (Raspberry Pi 4)

**Always power off and unplug the Pi before touching GPIO pins.**
Pin numbers are PHYSICAL pin numbers. Pin 1 is the one nearest the microSD-card end of the
header, inner row (square solder pad under the board).

## INMP441 microphone (I2S, digital — no ADC needed)
| INMP441 pin | Pi physical pin | Pi signal | Note |
|---|---|---|---|
| VDD | **1** | 3.3 V | **Never 5 V** (pins 2/4) — it destroys the mic |
| GND | **6** | Ground | |
| SCK | **12** | GPIO18 (PCM_CLK) | bit clock |
| WS  | **35** | GPIO19 (PCM_FS) | word select |
| SD  | **38** | GPIO20 (PCM_DIN) | **data INTO the Pi. Not GPIO21/pin 40 (that is audio OUT) — the mic would record only zeros** |
| L/R | **9** (or 14, 20, 25) | Ground | selects the LEFT channel (the software reads left) |

Solder the header pins on the INMP441 board; wires pushed through unsoldered holes give silence or noise.

Driver: `dtparam=i2s=on` + `dtoverlay=googlevoicehat-soundcard` in `/boot/firmware/config.txt`
(done by `setup_pi.sh` / `sudo python3 tools/fix_boot_config.py`). The mic then appears as ALSA
card **sndrpigooglevoi**, 48 kHz, 2 channels, 32-bit — the software handles this format.

## Waveshare 3.5" RPi LCD (A) — shares the header, no conflict
The LCD uses pins 1–26 but NOT pin 12 electrically. Its signals: SPI (pins 19, 21, 23, 24, 26),
LCD_RS pin 18 (GPIO24), RST pin 22 (GPIO25), touch IRQ pin 11 (GPIO17), power 1/2/4, ground 6/9.
The LCD board physically covers pins 1–26, so use a **stacking/extension header** (or breadboard
T-cobbler) to reach pins 1, 6, 9 and 12 for the mic. Pins 35 and 38 are outside the LCD area.

## Optional Hall-effect RPM sensor (off by default)
Signal → pin **37 (GPIO26)**, VCC → 3.3 V, GND → ground. GPIO17 is taken by the LCD touch panel.
Enable with `MOTOSIRA_RPM_ENABLED=1` in `.env` (needs the `gpiozero` library on the Pi).
Without it the LCD/dashboard/report show "RPM: N/A (sensor not connected)" — never a made-up value.

## Verify
```bash
arecord -l                    # card "sndrpigooglevoi" must be listed
./run_pi.sh mictest           # 5 s recording with a level meter: tap the mic, the meter must move
./run_pi.sh check             # full check (says exactly which wire/setting is wrong)
```
| Symptom | Cause |
|---|---|
| no sndrpigooglevoi card | overlay missing → `sudo python3 tools/fix_boot_config.py`, reboot |
| card present, "returns only zeros" | SD not on pin 38, SCK/WS swapped, VDD not 3.3 V, or header not soldered |
| very quiet | L/R not grounded (mic on right channel), or mic far from the engine |
