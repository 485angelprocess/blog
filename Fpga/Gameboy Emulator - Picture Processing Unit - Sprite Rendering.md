# Gameboy Emulator - Picture Processing Unit - Tiles

For the PPU I am not trying to match exact hardware, but create flexible modules that can match behavior, and later more exact timing behavior. I am interested in playing with some of the elements that I'll build with in different contexts, so I want to make sure they aren't tied exactly to gameboy architecture. I also have the luxury of a master faster base clock, and an fpga that has many times the power of the original gameboy.

As I get further along into making the emulator run, I will go back and adjust some features of each module to match memory mapping and sequencing.

## Memory

To start thinking about memory, I want to decide on a bus interface for the internal workings of my emulator. I have been doing projects using AXI4, mainly because it is preferred by Vivado. But to branch out, I am going to use a wishbone-like bus. [Wishbone](https://wishbone-interconnect.readthedocs.io/en/latest/) is an open-source interconnection specification. While there is a wishbone interface buried in the amaranth source, it is not documented, and I can make a quick wishbone signature to use as my base connection.

```python
class WritePort(wiring.Signature):
    def __init__(self, address_shape, data_shape):
        super().__init__({
            "data": Out(data_shape),
            "enable": Out(1)
        })

class ReadPort(wiring.Signature):
    def __init__(self, address_shape, data_shape):
        super().__init__({
            "data": In(data_shape)
        })

class Bus(wiring.Signature):
    def __init__(self, address_shape, data_shape, sel_width = 1, burst = False):

        ports = {
            "w": Out(WritePort(address_shape, data_shape)),
            "r": Out(ReadPort(address_shape, data_shape)),
            "addr": Out(address_shape),
            "sel": Out(sel_width),
            "err": In(1),
            "cycle": Out(1),
            "stb": Out(1),
            "ack": In(1)
        }

        if burst:
            ports = ports | {"cti": Out(3)}

        super().__init__(ports)
```

Having written several AXI interfaces recently, I've been mentally blocking out read and write ports. Wishbone shares signals which reduces the number of ports needed.

I am mostly interested in wishbone classic bus cycles [documented here](https://wishbone-interconnect.readthedocs.io/en/latest/03_classic.html). 

My board does not have external ram, so I am going to use amaranth's `memory` module. This is an abstract class which is implemented as LUT RAM or BRAM. This occasionally has some issues, but generally is a solid way to implement a small amount of ram. Documentation on what port configurations are more reliable is in the [amaranth documentation](https://amaranth-lang.org/docs/amaranth/v0.5.4/stdlib/memory.html#module-amaranth.lib.memory).

For simulating vram, I want to provide a bus interface for the amaranth memory.

```python
class WishboneRam(wiring.Component):
    def __init__(self, width, height = 1, address_shape = 16, write_shape = 32):
        self.width = width
        self.height = height
        self.write_shape = write_shape

        self.init = []

        address_space = self.address_space()

        ports = {"bus": In(signature.Bus(address_shape, write_shape, burst = False))}

        if has_stream:
            ports |= {"produce": Out(signature.VideoStream(stream_shape))}

        super().__init__(ports)

    def address_space(self):
        divide = int(math.log(self.write_shape) / math.log(2.0))
        return (self.width * self.height * 8) >> (divide - 1)

    def write_bus(self, m, write_port):
        """
        Write framebuffer from bus
        """
        m.d.comb += write_port.data.eq(self.bus.w.data)
        m.d.comb += write_port.addr.eq(self.bus.addr)

        strobe_last = Signal(name = "write_stb_last")
        m.d.sync += strobe_last.eq(self.bus.stb)

        with m.If(self.bus.w.enable):    
            m.d.comb += self.bus.ack.eq(write_port.en)
            m.d.comb += write_port.en.eq(self.bus.stb & self.bus.cycle & (strobe_last))

    def read_bus(self, m, read_port):
        """
        Read framebuffer from bus
        """
        m.d.comb += self.bus.r.data.eq(read_port.data)
        m.d.comb += read_port.addr.eq(self.bus.addr)

        read_valid = Signal()

        with m.If(~self.bus.w.enable):
            m.d.comb += self.bus.ack.eq(read_valid & self.bus.stb)
            m.d.sync += read_valid.eq(read_port.en)
            m.d.comb += read_port.en.eq(self.bus.stb & self.bus.cycle  & ~self.bus.ack)
            
    def elaborate(self, platform):
        m = Module()

        frame_size = self.width * self.height
        buffer = m.submodules.buffer = memory.Memory(shape = self.write_shape, depth = frame_size, init = self.init)

        self.write_bus(m, buffer.write_port(granularity = self.granularity))
        self.read_bus(m, buffer.read_port())

        return m
```

A read or write reliable takes one clock cycle. Data is written when the bus write_enable, strobe, and cycle output are set. Data is read to the bus when strobe and cycle output are set. The ack signal is set when the data has been written. Data written above the valid memory address will wrap, which has to be managed by the controller device.

To verify I wrote a few functions (scoped as static class), to help write and read from the bus.

```python
class BusTb(object):
    @staticmethod
    async def write_single(ctx, port, addr, data):
        ctx.set(port.w.data, data)
        ctx.set(port.addr, addr)
        ctx.set(port.w.enable, 1)
        ctx.set(port.stb, 1)
        ctx.set(port.cycle, 1)
        await ctx.tick().until(port.ack)
        ctx.set(port.stb, 0)
        ctx.set(port.w.enable, 0)
        ctx.set(port.cycle, 0)

    @staticmethod   
    async def read_single(ctx, port, addr):
        ctx.set(port.addr, addr)
        ctx.set(port.w.enable, 0)
        ctx.set(port.cycle, 1)
        ctx.set(port.stb, 1)
        data, = await ctx.tick().sample(port.r.data).until(port.ack)
        ctx.set(port.stb, 0)
        ctx.set(port.cycle, 0)
        return data
```

The testbench writes random addresses and data, and checks that reading the memory gives the last write to a given address.

```python
def tb_framebuffer():
    dut = Framebuffer(10, 10)

    addr = list()
    data = list()
    expect = dict()
    for i in range(20):
        addr.append(random.randrange(dut.address_space()))
        data.append(random.randrange(1 << 31))
        expect[addr[-1]] = data[-1]

    async def process(ctx):
        for i in range(len(addr)):
            await BusTb.write_single(ctx, dut.bus, addr[i], data[i])

        for key in expect:
            assert await BusTb.read_single(ctx, dut.bus, key) == expect[key]

    sim = Simulator(dut)
    sim.add_clock(1e-8)
    sim.add_testbench(process)

    with sim.write_vcd("bench/tb_framebuffer.vcd"):
        sim.run_until(500*1e-8)
```

## Cache

One of the reusable modules I want to make use of for this project, is simple caching. Specifically I want to use caches to abstract memory access from data access. Each module should believe it is accessing data that is formatted for the type of data it is accessing, without having to handle multiple reads, or receiving 2 or 4 elements at a time. Towards that end, I wanted to write a flexible cache module which reads from one size, and provides mapped data to the client module.

I am starting with a read only module, since the parts I am working on are only reading from memory. When I start getting into the cpu, I will update this to include writes.

The read cache has to achieve a few goals:

1. Easy instantiation for a given data shape to memory

2. Ability to cache N values (i.e. read an entire line when a member of the line is requested)

3. Should map address of data to an offset address of ram opaquely, i.e. the module only needs to considering data as logical blocks, (each data element has width 1). Additionally memory mapping can occur outside the cache.

4. Some delay is ok. Reads that are requesting data that has already been stored should be sent from cache, not initiate a new read from ram.

To allow flexible reading I started with an class which provides how to map from ram. I can overload this class for more complex mapping (which will come in handy when reading pixel data). For a basic map, I set the width of the data, and the number of reads to cache at a time.

```python
class CacheMap(object):
    """
    Map subset of ram to client
    """
    def __init__(self, width, n = 1):
        assert width in (1, 2, 4, 8, 16, 32)
        self._n = n
        self._width = width

    def num_reads(self):
        return self._n

    def width(self):
        return self._width

    def total(self):
        return self.width() * self.num_reads()

    def cache_shape(self):
        array_len = int(32 / self.width())
        shape = data.UnionLayout({
                    "w": data.ArrayLayout(32, self._n),
                    "r": data.ArrayLayout(self.width(), self._n * array_len)
                })
        return shape

    def cache_stride(self):
        w_stride = int(math.log(32 / (self.width())) / math.log(2.0))
        n_stride = int(math.log(self.num_reads()) / math.log(2.0))
        return w_stride + n_stride

    def write(self, m, cache, data, counter):
        m.d.sync += cache.w[counter].eq(data)

    def read(self, m, cache, data, offset):
        m.d.comb += data.eq(cache.r[offset])
```

This is slightly limited by forcing my ram bus to be 32 bits wide, but overgeneralizing it would be uneccessary.  One of the tricks that makes the module easier to write is using the UnionLayout. The union layout gives fields that all start from bit 0.

![](C:\Users\magen\AppData\Roaming\marktext\images\2025-03-12-14-45-36-image.png)

Since each submember of the union is an array it makes it easier to access the correct read and write location as if the data was just python container. It also means I can write to an array divided into one width, and the data will be readable as another width. This can be done several ways in all HDLs, but it's very refreshing to make it this painless.

Using a mapping object as a start point, I can write an amranth module that uses the object to wait for the client to request a read, load in the cache from the base point, and then provide the correct data elements to the client.

```python
class Cache(wiring.Component):
    """
    Cache for reading ram as  desired shape
    """
    def __init__(self, mapper):
        self.map = mapper
        self.width = mapper.width()
        super().__init__({
            "bus": Out(signature.Bus(16, 32)),
            "cache": In(signature.Bus(16, mapper.width()))
        })

    def elaborate(self, platform):
        m = Module()

        map_addr = Signal(16)
        cache = Signal(self.map.cache_shape())
        cache_base = Signal(16)

        base = Signal(16)
        offset = Signal(16)

        print("Cache total is {}".format(self.map.total()))
        print("Cache stride is {}".format(self.map.cache_stride()))

        # Base is the first address of the group
        m.d.comb += base.eq(self.cache.addr >> self.map.cache_stride())
        # Offset is what member of the cached value we are reading
        m.d.comb += offset.eq(self.cache.addr - (base << self.map.cache_stride()))

        load_counter = Signal(range(self.map.num_reads()))

        # Read from base adddress
        m.d.comb += self.bus.addr.eq((base * self.map.num_reads()) + load_counter)

        self.map.read(m, cache, self.cache.r.data, offset)

        cache_valid = Signal()

        with m.FSM():
            with m.State("Load"):
                # Load data into cache
                m.d.comb += self.bus.stb.eq(self.cache.stb)
                m.d.comb += self.bus.cycle.eq(self.cache.cycle)
                m.d.comb += self.bus.sel.eq(self.cache.sel)
                with m.If(self.bus.stb & self.bus.ack):
                    # Map data
                    self.map.write(m, cache, self.bus.r.data, counter = load_counter)
                    m.d.sync += cache_base.eq(base)
                    with m.If(load_counter == self.map.num_reads() - 1):
                        m.d.sync += load_counter.eq(0)
                        m.next = "Cached"
                    with m.Else():
                        m.d.sync += load_counter.eq(load_counter + 1)
            with m.State("Cached"):
                # Cache is valid
                with m.If(self.cache.stb & self.cache.cycle):
                    with m.If(base == cache_base):
                        m.d.comb += self.cache.ack.eq(1)
                    with m.Else():
                        # Need to load new cache value
                        m.next = "Load"

        return m
```

For my purposes it makes sense to always align the cache start point to a multiple of the cache's total width. This means that if the client requests address 123, and the width of the entire cache is 100, the cache loads in data that is represented in addresses 100-200. The might be some cases where it is more efficient to load from the nearest ram word, but I don't have to handle that right now.

The cache checks if it needs to reload by checking the base address. If a new read comes in which has a different base address, the module will stall the client until it loads in data. Once the data is stored in the local array, it can guarantee immediate reads, which is why the ack flag is combinatorally set to 1 if a read is active and the cache is valid.

This is a very naive cache system. I could employ parallel loading and reading, additional layers and predictive. My main goal, however, was to decouple logical data blocks from direct memory access.

## Loading background tiles

At a basic level, the gameboy stores the background as a set of 32x32 tile pointers. A portion of the tiles are rendered to the LCD screen. Each tile has pixel data which is pointed to in memory. Each horizontal line, the PPU loads 32 tile pointers and then loads their 2bpp pixel data to a line buffer. I can abstract that into two modules. The first waits for a start flag, and the loads the correct subset of tiles from memory. It produces a stream of pointers. Then a second module receives the stream and sets the color at each pixel.

I started with the module which loads tile pointers from ram. It provides a control bus slave to allow a controller to set registers. It has a bus master, which will be routed through a cache mapper and set to the correct location in ram. It also provides a stream of data to be connected to the line buffer.

```python
class TileGrid(wiring.Component):
    def __init__(self):
        super().__init__({
            "ctl": In(signature.Bus(4, 32)),
            "bus": Out(signature.Bus(16, 8)),
            "produce": Out(signature.DataStream(oam_layout()))
        })
```

The `oam_layout()` is the object attributes. It contains the tile number, the y and x pixel locations of a tile.

At the start of each line, the module reads N pointers from memory. I use a flag on the output stream to indicate this module has reached the end of the line. The bus logic has an active read when the downstream line buffer is ready to read data. As long as that downstream logic is synced to the horizontal refresh, and finishes nicely when it receives a last flag, I can ignore having to handle sync logic here.

```python
m.d.comb += self.produce.valid.eq(self.bus.ack)
m.d.comb += self.produce.last.eq(x == width - 1)

m.d.comb += self.bus.stb.eq(self.produce.ready)
m.d.comb += self.bus.cycle.eq(self.produce.ready)

with m.If(self.produce.ready & self.produce.valid):
    with m.If(self.produce.last):
        m.d.sync += x.eq(0)
    with m.Else():
        m.d.sync += x.eq(x + 1)
```

To figure out where I am loading the tiles from, I have to figure out what subset of the background I am reading. The gameboy uses a Wx and Wy register to set the top left sub-region of the 32x32 background. Wx and Wy are pixel level, so the top left tile is located at Wx/8, and Wy/8, or equivalently by shifting down by 3. The remainder is sent to the line buffer so it knows the pixel-level offset of a tile. Some pseudocode of the address calculation:

```python
wx # x offset
wy # y offset

# divide by 8 with no remainder
x_offset_tile = wx >> 3 
y_offset_tile = wy >> 3

# Address of current tile to load
x_addr_tile = x + x_offset_tile 
y_addr_tile = y + y_offset_tile 

# Address = x + (y * length) = x + (y * 32) = x + (y << 5)
addr = x_addr_tile + (y_addr_tile << 5)
```

The Wx and Wy registers are written via a control bus. I can pass the top left coordinates of the tile onto the stream of output data for the line buffer to parse. The output is the coordinates that are rendered. The coordinates are in pixels, although a detail is that the gameboy's origin is 16 pixels above and 8 bits left of the actual start of the display. This allows for parts of sprites to peek in on the top and left sides.

```python
x_remainder = wx & 0b111
y_remainder = wy & 0b111


pixel_x = (x << 3) + x_remainder
pixel_y = (y << 3) + y_remainder
```
