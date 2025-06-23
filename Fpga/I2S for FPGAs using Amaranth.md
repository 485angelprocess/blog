# I2S for FPGAs using Amaranth

I2S (Inter-intergrated Circuit Sound) is a serial standard for sending and receiving PCM audio between digital circuit components. The normal use case is to send audio data to a line-level DAC or amplifier, or to receive audio data from an ADC. I am working on an audio processor which uses a PCM5102 as a DAC output, and a PCM1863 as an ADC. I am using an FPGA as a flexible audio processor.

For this project I am using [amaranth-lang](amaranth-lang.org) which is a python based framework for developing HDL. It allows faster development, and setting up test frameworks easily. There is also quite a lot of work put in to aim amaranth at developing flexible and reusable modules.

To start I am using two streams of data. Each stream has a data port, and a valid and ready port. A stream is valid if data can be pushed out, and ready flags that the sink device can receive that data. In amaranth this can be written as a `Signature`

```python
class AudioStream(wiring.Signature):
    def __init__(self, shape):
        super().__init__({
            "tdata": Out(shape),
            "tvalid": Out(1),
            "tready": In(1)
        })
```

Amaranth now provides a stream class, but a custom one with a "t" prefix helps let Vivado abstract the stream as an AXIS stream. This makes block diagrams cleaner.

Using the stream signature as a port a basic i2s initializator looks like this:

```python
class I2sOut(wiring.Component):
    def __init__(self, shape, period = 10, depth = 16, mono = True, ws_switch = 1):
        self.period = period # Default period of SCK
        self.depth = depth # Width of audio data sent out
        self.shape = shape # Shape of stream data, stream data below width is ignored
        self.mono = mono # If set to mono, left channel is sent out to both i2s channels, right stream is ignored
        self.ws_switch = ws_switch # On which bit to switch WS, 0 is I2S, 1 is left-aligned

        super().__init__({
            "left": In(AudioStream(shape)),
            "right": In(AudioStream(shape)),
            "sck": Out(1), # Data clock
            "bck": Out(1), # PLL clock
            "ws": Out(1),  # Word select (left/right)
            "sd": Out(1)   # Data out
        })
```

Now for implementation. To start we need a BCK clock out.
