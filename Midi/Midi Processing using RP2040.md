# Basic USB MIDI on RP2040

This is the start of a project where the goal is to take midi values in from a controller (i.e. a midi keyboard) to use as pitch values for a drum controller, which then passes data thorugh to a computer running a synthesizer plugin. The goal is to have a working performance device suitable for live shows.

## Using the Arduino IDE

To start I have a Adafruit Feather RP2040 lying around and wanted to get it recognized as a midi device. With Arduino MIDI library this is pretty fast and painless.

```Cpp
#include <Adafruit_TinyUSB.h>
#include <MIDI.h>

// Create USB Midi instance
Adafruit_USBD_MIDI midi;
MIDI_CREATE_INSTANCE(Adafruit_USBD_MIDI, midi, MIDIusb);

void setup(){
    // Broadcast on all channels
    MIDIusb.begin(MIDI_CHANNEL_OMNI);
    // Turn off echo
    MIDIusb.turnThruOff();
}

void loop(){
    int pitch = 35;
    int velocity = 100;
    int channel = 1;
    // Send note on
    MIDIusb.sendNoteOn(pitch, velocity, channel);
    delay(200);
    // Send note off
    MIDIusb.sendNoteOff(pitch, velocity, channel);
    delay(1000);
}
```

This has to run through the USB stack `TinyUSB` which is under `Tools->USB Stack`. It is recognized on pure data which I'm using as a simple midi analyzer.

## Rust

I am interested in embedded rust development, so this seems like a well scoped project to look into some of the rust frameworks. There is a simple example using a pico to send midi messages here [Mads Kleldgaard's Pico Midi Controller](https://github.com/madskjeldgaard/rust-pico-midi-controller/tree/main)

First I cloned the [RP2040 template](https://github.com/rp-rs/rp2040-project-template), installed the tools listed. I added `usb-device` and `usbd-midi` and changed `.cargo/config.toml` to set the runner from `probe-rs` to `elf2uf2-rs -d` . The runner allows you to upload via the onboard usb port using the uf2 bootloader, instead of using a standalone debugger. This is faster for my purposes, but also means no onboard debugging. It also means having to press the boot and reset buttons in sequence on every upload, annoying but not bad for a small project.

Mads' example no longer works immediately since `usbd-midi` changed some basic class names. But setting up the USB class now looks like:

```rust
// Load usb bus
let usb_bus = UsbBusAllocator::new(UsbBus::new(
        pac.USBCTRL_REGS,
        pac.USBCTRL_DPRAM,
        clocks.usb_clock,
        true,
        &mut pac.RESETS,
    ));

// Setup midi device
// Create MIDI class with 1 input and 1 output jack
let mut midi = UsbMidiClass::new(&usb_bus, 1, 1).unwrap();

// USB device
let mut usb_dev = UsbDeviceBuilder::new(&usb_bus, UsbVidPid(0x16C0, 0x5E4))
        .device_class(0)
        .device_sub_class(0)
        .strings(&[StringDescriptors::default()
                .manufacturer("Angel Process")
                .product("MIDI Chord Drums")
                .serial_number("12345678")])
        .unwrap()
        .build();
```

And running the main loop looks like this:

```rust
let mut next_toggle = timer.get_counter().ticks() + 500_000;
let mut led_on = false;

let mut mnote = 0;

loop {
        // Poll the USB device and MIDI class
        if usb_dev.poll(&mut [&mut midi]) {
            // Handle MIDI events here
            info!("Handling midi events");
        }

        let now = timer.get_counter().ticks();
        if now >= next_toggle {
            next_toggle += 500_000; // Schedule next toggle in 500 ms
            let mut bytes = [0; 3];
            if led_on {
                // Note off
                info!("off!");
                led_pin.set_low().unwrap();

                // Send MIDI Note Off message for note 48 (C3)
                let channel = Channel::C1;
                let note = Note::from(mnote);
                let velocity = Value7::from(100);
                let note_off = MidiMessage::NoteOff(channel, note, velocity);

                if mnote == 11{
                 mnote = 0;   
                }
                else{
                    mnote += 1;
                }

                note_off.render_slice(&mut bytes);
            } else {
                // Note on
                info!("on!");
                led_pin.set_high().unwrap();

                // Send MIDI Note On message for note 48 (C3)
                let channel = Channel::C1;
                let note = Note::from(mnote);
                let velocity = Value7::from(100);
                let note_on = MidiMessage::NoteOn(channel, note, velocity);
                note_on.render_slice(&mut bytes);
            }

            let packet = UsbMidiEventPacket::try_from_payload_bytes(CableNumber::Cable0, &bytes).unwrap();
            let _result = midi.send_packet(packet);

            led_on = !led_on;
        }
    }
```

As Mads observed, putting a delay in the main loop throws a USB error. They observed this for Mac, but it seems to also hold true for Windows.

This functionally can send MIDI messages to a host computer, which is satisfying progress for me for now. Next is to parse midi in data from both the host computer and a separate device, as well as to read in sensor data to act as triggers.

# 
