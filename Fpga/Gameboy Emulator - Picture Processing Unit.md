# Gameboy Emulator - Picture Processing Unit - Display Output

The PPU is the rendering end of the gameboy/gameboy color. It uses  16KB of VRAM (8KB on the original gameboy) to render to a 160x144 pixel LCD.  The unit manages visual data, and renders backgrounds, window and sprites to the screen.

## VGA Output

To start with this emulation, I want to be able to see the output. Since the FPGA board I'm using has an build in VGA output port, I'd like to be able to render the LCD panel to a VGA monitor. The gameboy LCD refreshes at 59.7275 frames per second, so I should be able to get away with a 60hz standard.

To start I made a basic class to contain timing information:

```python
class VideoRegion(object):
    def __init__(self, active, front_porch, sync, back_porch):
        self.active = active
        self.front_porch = front_porch
        self.sync = sync
        self.back_porch = back_porch

    def total(self):
        return self.active + self.front_porch + self.sync + self.back_porch
```

Then I created an amaranth module which can will keep track of which part of the video we're on. This module can be reused for horizontal and vertical timing. For horizontal timing the pixel clock is used as the input, for the vertical timing the horizontal overflow pulse is used.

```python
class VideoState(enum.Enum):
    """
    Represents section of video
    """
    ACTIVE  = 0 # Video is currently sending
    FP      = 1 # Front porch
    SYNC    = 2 # Sync section
    BP      = 3 # Back porch

class VideoCounter(wiring.Component):
    """
    Horizontal or vertical video counter
    """
    def __init__(self, region):
        self.region = region
        super().__init__({
            "clk_en": In(1), # Pixel clock or horizontal clock
            "state": Out(VideoState),
            "ovf": Out(1)
        })

    def elaborate(self, platform):
        m = Module()

        counter = Signal(range(self.region.total()))
        ovf = Signal()

        m.d.comb += ovf.eq(counter == self.region.total() - 1)
        m.d.comb += self.ovf.eq(ovf & self.clk_en)


        # Map video section
        with m.If(counter < self.region.back_porch):
            m.d.comb += self.state.eq(VideoState.BP)
        with m.Elif(counter < self.region.back_porch + self.region.active):
            m.d.comb += self.state.eq(VideoState.ACTIVE)
        with m.Elif(counter < self.region.back_porch + self.region.active + self.region.sync):
            m.d.comb += self.state.eq(VideoState.FP)
        with m.Else():
            m.d.comb += self.state.eq(VideoState.SYNC)

        with m.If(self.clk_en):
            with m.If(self.ovf):
                m.d.sync += counter.eq(0)
            with m.Else():
                m.d.sync += counter.eq(counter + 1)

        return m
```

With the region out of the way, I just need a way to stream in data and make sure it aligns with video being sent out. I start with a signature and pixel container:

```python
from amaranth.lib import wiring, data
from amaranth.lib.wiring import In, Out

def pixel_shape(width):
    return data.StructLayout({
        "r": width,
        "g": width,
        "b": width
    })

class Stream(wiring.Signature):
    def __init__(self, shape):
        super.__init__({
            "data": Out(shape),
            "valid": Out(1),
            "ready": In(1),
            "vsync": Out(1)
        })
```

I start with driver module. It takes a stream of pixels in, and outputs the vga data and sync signals. The polarity flag is used since some resolutions expect a normally on sync, others a normally off sync. Most monitors don't seem to use this polarity anymore, but it's good to have consistent. The pixel division allows us to set the pixel clock as a ratio of the input clock. For example an 800x600 resolution at 60Hz has a 40MHz clock, so we can use a synthesized clock of 120MHz and divide by 3.

```python
class Polarity(object):
    POS = 0
    NEG = 1

class VgaDriver(wiring.Component):
    def __init__(self, pix_divide, 
                        hregion, 
                        vregion,
                        polarity = Polarity.POS
                        shape = signature.PixelLayout()):
        self.hregion = hregion
        self.vregion = vregion
        self.pix_divide = pix_divide
        self.polarity = polarity

        super.__init__({
            "consume": In(Stream(shape)),
            "data": Out(12),
            "hsync": Out(1),
            "vsync": Out(1)
        })
```

The pixel clock division is done using a simple counter.

```python
# Pixel clock divider
pix_counter = Signal(range(self.pix_divide))
pix_clk = Signal()

m.d.comb += pix_clk.eq(pix_counter == 0)

with m.If(pix_counter == self.pix_divide - 1):
    m.d.sync += pix_counter.eq(0)
with m.Else():
    m.d.sync += pix_counter.eq(pix_counter + 1)
```

Then we can connect to our video region counters:

```python
# Horizontal region
hcounter = m.submodules.hcounter = VideoCounter(self.hregion)

m.d.comb += hcounter.clk_en.eq(pix_clk)

# Vertical region
vcounter = m.submodules.vcounter = VideoCounter(self.vregion)

m.d.comb += vcounter.clk_en.eq(hcounter.ovf)
```

Since I want my video output to be aligned with the monitor refresh. To do this I block reading in from the stream if I receive a vsync, and only resume when I entered the sync region on the VGA side.

```python
input_enable = Signal()
video_active = Signal()

m.d.comb += video_active.eq(
                (hcounter.state == VideoState.ACTIVE) &
                (vcounter.state == VideoState.ACTIVE))

with m.If(input_enable & video_active):
    m.d.comb += self.consume.ready.eq(pix_clk)

# Stop sending at end of frame
with m.If(self.consume.ready & self.consume.valid & self.consume.vsync):
    m.d.sync += input_enable.eq(0)

# Reached end of output frame, data can be send when pixels are active
with m.If(vcounter.state == VideoState.SYNC):
    m.d.sync += input_enable.eq(1)

with m.If(video_active & input_enable):
    # Top 4 bits of each pixel
    m.d.comb += self.data[0:4].eq(self.consume.data.r[-4:])
    m.d.comb += self.data[4:8].eq(self.consume.data.g[-4:])
    m.d.comb += self.data[8:12].eq(self.consume.data.b[-4:])
with m.Else():
    m.d.comb += self.data.eq(0)
```

For certain VGA formats, some monitors will check the polarity of the hsync and vsync signals. 

```python
if self.polarity == Polarity.POS:
    m.d.comb += self.hsync.eq(hcounter.state == VideoState.SYNC)
    m.d.comb += self.vsync.eq(vcounter.state == VideoState.SYNC)
else:
    m.d.comb += self.hsync.eq(hcounter.state != VideoState.SYNC)
    m.d.comb += self.vsync.eq(vcounter.state != VideoState.SYNC)
```

I can convert this amaranth module to a vga module.

```python
vga = VgaDriver(3, VideoRegion(800, 40, 128, 88), VideoRegion(600, 1, 4, 23))
with open("build/vga_driver.v", "w") as f:
    v = verilog.convert(vga, name = "vga_driver_svga")
    f.write(v)
print("Wrote vga module")
```

I try to write display drivers with an easy way to set timing configurations. If I was doing a more general purpose display, I would add a bus interface to set registers to change the timing in run-time.

## Rendering LCD

Since the gameboy's native LCD panel is much smaller than the 800x600 resolution, I am going add some borders and upsample the incoming stream. These become easy when using a nice stream format.

### Vertical upsample

First I upsample each incoming pixel 4 times we end up with a 640x576 resolution. Upsampling vertically requires storing the incoming video stream for one line. When a line is finished, the buffer is used as the video source N times.

```python
class UpsampleVertical(wiring.Component):
    def __init__(self, divide = 4, width = 160, shape = signature.PixelLayout()):
        self.divide = divide # Multiplies the height of incoming stream
        self.width = width # Width of incoming stream
        self.shape = shape # Shape of incoming stream data
        super().__init__({
            "consume": In(signature.VideoStream(shape)),
            "produce": Out(signature.VideoStream(shape))
        })

    def elaborate(self, platform):
        m = Module()

        sync_flag = Signal()

        # Caches a line of pixels
        line_buffer = m.submodules.buffer = memory.Memory(shape = self.shape, depth = self.width, init = [])

        # Write to cache
        write_port = line_buffer.write_port()
        # Read from cache
        read_port = line_buffer.read_port(domain = "comb")

        addr = Signal(range(self.width))
        addr_last = Signal()

        m.d.comb += addr_last.eq(addr == self.width - 1)

        line_counter = Signal(range(self.divide))
        active = Signal()

        m.d.comb += active.eq(line_counter == 0)

        with m.If(self.consume.valid & self.consume.ready):
            # Capture vsync flag
            with m.If(self.consume.vsync):
                m.d.sync += sync_flag.eq(1)

        # Only send vsync flag on last line of upsample
        m.d.comb += self.produce.vsync.eq(sync_flag & (line_counter == self.divide - 1) & (addr_last))

        with m.If(self.produce.valid & self.produce.ready):
            with m.If(self.produce.vsync):
                m.d.sync += sync_flag.eq(0)
            with m.If(addr_last):
                m.d.sync += addr.eq(0)
                with m.If(line_counter == self.divide - 1):
                    m.d.sync += line_counter.eq(0)
                with m.Else():
                    m.d.sync += line_counter.eq(line_counter + 1)
            with m.Else():
                m.d.sync += addr.eq(addr + 1)

        with m.If(active):
            m.d.comb += [
                self.produce.data.eq(self.consume.data),
                self.produce.valid.eq(self.consume.valid),
                self.consume.ready.eq(self.produce.ready)
            ]

            # Write to buffer
            m.d.comb += write_port.en.eq(self.produce.valid & self.produce.ready)
            m.d.comb += write_port.data.eq(self.produce.data)
            m.d.comb += write_port.addr.eq(addr)
        with m.Else():
            m.d.comb += read_port.addr.eq(addr)
            m.d.comb += self.produce.valid.eq(1)
            m.d.comb += self.produce.data.eq(read_port.data)

        return m
```

To confirm behavior, I use two helper functions to read and write from the streams in the amaranth simulator:

```python
async def stream_put(ctx, stream, data, vsync):
    ctx.set(stream.data, data)
    ctx.set(stream.vsync, vsync)
    ctx.set(stream.valid, 1)
    await ctx.tick().until(stream.ready)
    ctx.set(stream.valid, 0)


async def stream_get(ctx, stream, expect, vsync):
    ctx.set(stream.ready, 1)
    data, vs = await ctx.tick().sample(stream.data, stream.vsync).until(stream.valid)
    assert expect == data
    assert vs == vsync
    ctx.set(stream.ready, 0)
```

With that I can make sure that for each line in I get the same line back 4 times.

```python
def tb_vertical_resample():
    dut = UpsampleVertical(4, 4, shape = unsigned(16))

    async def write_process(ctx):
        for i in range(10):
            for j in range(4):
                await stream_put(ctx, dut.consume, j, 0)

    async def read_process(ctx):
        for i in range(100):
            for j in range(16):
                await stream_get(ctx, dut.produce, j % 4, 0)

    sim = Simulator(dut)
    sim.add_clock(1e-8)
    sim.add_testbench(write_process)
    sim.add_testbench(read_process)

    with sim.write_vcd("bench/tb_upsample_vertical.vcd"):
        sim.run_until(100*1e-8)
```

Although not the most intense testing, it gives me a baseline of operation. This module could be made a bit simpler by having the incoming stream provide an hsync flag. This would allow the module to not have to internally track pixel position. If I start to have problems with the wider display pipeline, I can return and check finer cases.

### Horizontal upsample

The horizontal upsample is a similar process, but instead of needing to cache an entire line I only need to cache one instance of the stream data, as well as the vsync flag.

```python
class UpsampleHorizontal(wiring.Component):
    def __init__(self, divide, shape = signature.PixelLayout()):
        self.divide = divide
        self.shape = shape
        super().__init__({
            "consume": In(signature.VideoStream(shape)),
            "produce": Out(signature.VideoStream(shape))
        })

    def elaborate(self, platform):
        m = Module()

        sync_reg = Signal()
        data_reg = Signal(self.shape)

        counter = Signal(range(self.divide))

        # Copy data to registers
        with m.If(self.consume.valid & self.consume.ready):
            m.d.sync += data_reg.eq(self.consume.data)
            m.d.sync += sync_reg.eq(self.consume.vsync)

        # Keep track of how many copies of data we have sent
        with m.If(self.produce.valid & self.produce.ready):
            with m.If(counter == self.divide - 1):
                m.d.sync += counter.eq(0)
            with m.Else():
                m.d.sync += counter.eq(counter + 1)

        with m.If(counter == 0):
            # Data from stream
            m.d.comb += self.produce.data.eq(self.consume.data)
            m.d.comb += self.produce.valid.eq(self.consume.valid)
            m.d.comb += self.consume.ready.eq(self.produce.ready)
        with m.Else():
            # From registers
            m.d.comb += self.produce.data.eq(data_reg)
            m.d.comb += self.produce.valid.eq(1)
            m.d.comb += self.consume.ready.eq(0) # Explicit block incoming stream

        # Sync flag on last sampled value
        with m.If(counter == self.divide - 1):
            m.d.comb += self.produce.vsync.eq(sync_reg)

        return m
```

 Verifying behavior is similar to vertical upsampling:

```python
def tb_horizontal_resample():
    dut = UpsampleHorizontal(4, shape = unsigned(16))

    async def write_process(ctx):
        for i in range(10):
            for j in range(4):
                await stream_put(ctx, dut.consume, j, 0)

    async def read_process(ctx):
        for i in range(100):
            for j in range(16):
                await stream_get(ctx, dut.produce, math.floor(j / 4), 0)

    sim = Simulator(dut)
    sim.add_clock(1e-8)
    sim.add_testbench(write_process)
    sim.add_testbench(read_process)

    with sim.write_vcd("bench/tb_upsample_horizontal.vcd"):
        sim.run_until(100*1e-8)
```

### Border

The gameboy LCD does not evenly fit into my 800x600 display, so I also want to add padding so the graphics are centered on the screen. I can insert fill pixels at the start and end of each line, and each frame.

The vertical border inserts 12 pixels at the start and end of each line. When I have time to loop back to this, I can make this bit more efficient by sharing a counter with the upsampler, and inserting 3 pixels before upsampling. But for now, this is functional.

```python
class VerticalBorder(wiring.Component):
    def __init__(self, margin = 12, width = 800, fill = {"r": 0, "g": 0x6, "b": 0x6}, shape = signature.PixelLayout()):
        self.margin = margin
        self.width = width
        self.fill = Const(fill, shape)

        super().__init__({
            "consume": In(signature.VideoStream(shape)),
            "produce": Out(signature.VideoStream(shape))
        })

    def elaborate(self, platform):
        m = Module()

        fill_pixels = 2 * self.margin * self.width
        sync_location = self.margin * self.width

        active = Signal()
        pix_counter = Signal(range(fill_pixels))

        m.d.comb += self.produce.vsync.eq(pix_counter == sync_location - 1)

        # When we receive a vsync, start border
        with m.If(self.consume.valid & self.consume.ready):
            with m.If(self.consume.vsync):
                m.d.sync += active.eq(0)
                m.d.sync += pix_counter.eq(0)

        # Active
        with m.If(active):
            # Pass stream through (don't pass vsync)
            m.d.comb += [
                self.produce.valid.eq(self.consume.valid),
                self.consume.ready.eq(self.produce.ready),
                self.produce.data.eq(self.consume.data)
            ]
        with m.Else():
            # Fill border
            m.d.comb += self.produce.data.eq(self.fill)
            m.d.comb += self.produce.valid.eq(1)

            with m.If(self.produce.valid & self.produce.ready):
                # How many pixels have been filled
                with m.If(pix_counter == fill_pixels - 1):
                    m.d.sync += active.eq(1)
                    m.d.sync += pix_counter.eq(0)
                with m.Else():
                    m.d.sync += pix_counter.eq(pix_counter + 1)

        return m
```

The horizontal border inserts blank pixels at the start and end of the frame.

```python
class HorizontalBorder(wiring.Component):
    def __init__(self, margin = 80, width = 800, fill = {"r": 0, "g": 0x0, "b": 0x6}, shape = signature.PixelLayout()):
        self.margin = margin
        self.width = width
        self.fill = Const(fill, shape)

        super().__init__({
            "consume": In(signature.VideoStream(shape)),
            "produce": Out(signature.VideoStream(shape))
        })

    def elaborate(self, platform):
        m = Module()

        sync_reg = Signal()
        counter = Signal(range(self.width))

        active = Signal()

        active_start = self.margin
        active_end = self.width - self.margin

        with m.If((counter >= active_start) & (counter < active_end)):
            m.d.comb += active.eq(1)

        counter_last = Signal()

        m.d.comb += counter_last.eq(counter == self.width - 1)

        m.d.comb += self.produce.vsync.eq(sync_reg & counter_last)

        with m.If(self.produce.valid & self.produce.ready):
            with m.If(self.produce.vsync):
                m.d.sync += sync_reg.eq(0)
            with m.If(counter_last):
                m.d.sync += counter.eq(0)
            with m.Else():
                m.d.sync += counter.eq(counter + 1)

        with m.If(self.consume.valid & self.consume.ready & self.consume.vsync):
            m.d.sync += sync_reg.eq(1)

        with m.If(active):
            m.d.comb += [
                self.produce.data.eq(self.consume.data),
                self.produce.valid.eq(self.consume.valid),
                self.consume.ready.eq(self.produce.ready)
            ]
        with m.Else():
            m.d.comb += self.produce.valid.eq(1)
            m.d.comb += self.produce.data.eq(self.fill)

        return m
```

Here I use the vsync flag coming in to start filling, and produce the vsync when I'm halfway through the border fill. This means that half the fill will be at the bottom of the screen, and then align to the top after the vsync flag is sent.

Both of these modules have to keep track of when to send the vsync flag, because I need it to align to the end of display.

## Putting it together

I made a wrapper which connects together this display pipeline. A 160x144 video stream goes in, and a 800x600 stream comes out.

```python
class Resize(wiring.Component):
    def __init__(self, upsample, border, shape = signature.PixelLayout()):
        self.upsample = upsample
        self.border = border
        super().__init__({
            "consume": In(signature.VideoStream(shape)),
            "produce": Out(signature.VideoStream(shape))
        })

    def elaborate(self, platform):
        m = Module()

        m.submodules.upsample = self.upsample
        m.submodules.border = self.border

        wiring.connect(m, wiring.flipped(self.consume), self.upsample.consume)
        wiring.connect(m, self.upsample.produce, self.border.consume)
        wiring.connect(m, wiring.flipped(self.produce), self.border.produce)

        return m
```

I also wrote a module which sets a framebuffer and repeatedly streams out data. After converting my amaranth modules to verilog, I place them in the vivado block diagram.

![Screenshot 2025-03-12 133928.png](C:\Users\magen\Documents\Blog\Resources\gameboy\Screenshot%202025-03-12%20133928.png)

This displayed correctly on my VGA monitor, which is a satisfying step. With a way to check output, I am going to move onto making the components of the picture-processing unit.
