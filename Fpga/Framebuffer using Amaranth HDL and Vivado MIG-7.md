# Framebuffer using Amaranth HDL and Vivado MIG-7

Framebuffers are commonly needed for any type of video processing. A framebuffer is simply a collection of pixel data (i.e. a frame of video) which can be read as a stream and written to asynchronously. Framebuffers are useful whenever the incoming data is not already rasterized, or pixels are not ordered line by line, or when the data in is not constantly refreshing every pixel. This occurs if during video decoding, which is generally not rasterized, and on most frames only some pixels are written to.

Vivado's MIG-7 is a memory controller for DDR3 Ram, on hardware with ram it simplifies a large number of processes. It allows for direct memory access using an AXI-4 protocol. The main process is to make a module that can abstract interface to make frame management easy, and to have the desired input and output interface. For this example, I'm going to make a wishbone interface for direct reading and writing and a stream output interface using the AXIS protocol. I also want my module to have a control bus, also using wishbone to select frame size and frame selection.

## Interfaces

I start by defining the signatures that will be used. All the interfaces use the amaranth imports:

```python
from amaranth.lib import wiring
from amaranth.lib.wiring import In, Out
```

AXI4 is defined by arm, this is a minimal master interface. Addresses and data have their own handshakes, and the bus must finish a response transaction after a write has finished. The `len` parameter gives the downstream component information about how many transactions there will be. The `size` component gives information about how wide each transaction is. AXI4 has some redundancy built in, which allows for some flexibility, but I've found that there's often some issues with mismatching implementations. But, it's what AMD/Xilinx decided to build into Vivado blocks, so it has to get used. Here is a AXI4 master interface in amaranth:

```python
class Axi4(wiring.Signature):
    def __init__(self, addr_shape, data_shape):
        super().__init__({
            # Write address
            "awaddr": Out(addr_shape),
            "awvalid": Out(1),
            "awready": In(1),
            "awlen": Out(8),
            "awsize": Out(3),

            # Write data
            "wdata": Out(data_shape),
            "wlast": Out(1),
            "wstrb": Out(4),
            "wvalid": Out(1),
            "wready": In(1),

            # Read address
            "araddr": Out(addr_shape),
            "arlen": Out(8),
            "arsize": Out(3),
            "arvalid": Out(1),
            "arready": In(1),

            # Read data
            "rdata": In(data_shape),
            "rlast": In(1),
            "rvalid": In(1),
            "rready": Out(1),

            # Response
            "bresp": In(2),
            "bvalid": In(1),
            "bready": Out(1)
        })
```

AXIS is a related standard which is used for data streams. At some point in the video processing pipeline, I will want video in rasterized order as a stream. Here I'm taking it from the framebuffer. An AXIS stream carries data, with a valid flag and a ready flag for backflow control. Additionally the `last` and `user` signal are used to indicate hsync and vsync.

```python
class Axis(wiring.Signature):
    def __init__(self, data_shape, user_shape = 1):
        super().__init__({
            "tdata": Out(data_shape),
            "tvalid": Out(1),
            "tready": In(1),
            "tuser": Out(user_shape),
            "tlast": In(1)
        })
```

While there is a built-in amaranth interface for streams, I want to explicitly use the same naming conventions as Vivado, as it simplifies integrating into their block system.

Finally wishbone is a open source framework for bus ports, this is a simple implementation for single reads and writes. This is not setting up for high throughput direct reads/writes, but I can add to it later. I mostly know that I am setting up projects which use this port structure for its simplicity to implement. For a higher throughput system, building in capability for bursts will improve ram performance.

```python
class Wishbone(wiring.Signature):
    def __init__(self, addr_shape, data_shape):
        super().__init__({
            "addr": Out(addr_shape),

            "stb": Out(1),
            "cyc": Out(1),
            "ack": In(1),

            "w_data": Out(data_shape),
            "w_enable": Out(1),

            "r_data": In(data_shape)
        })
```

Now that I have my interfaces setup, most of the work is connecting things together, and getting some tests up and running.

## Testing

To run tests, I want to set up some helpful functions to make tests easy to write and to understand. I have made a earlier post about writing this type of function for single wishbone single transactions. I am going to reuse those functions, and add some for the AXI interfaces. For AXI4, I want to be able to simulate write functions using the Amaranth simulation framework. This looks like this:

```python
async def axi_write(ctx, port, addr, size, length, data):

    # Writes address first and then writes data
    # This misses case of simultaneous address and data write

    # Write address
    ctx.set(port.awvalid, 1)
    ctx.set(port.awaddr, addr)
    ctx.set(port.awsize, size)
    ctx.set(port.awlen, length)

    await ctx.tick().until(port.awready)

    # Finish write address
    ctx.set(port.awvalid, 0)

    # Start write data
    ctx.set(port.wvalid, 1)

    for i in range(len(data)):
        ctx.set(port.wdata, data[i])
        ctx.set(port.wlast, i == len(data) - 1) # Last flag
        await ctx.tick().until(port.wready)

    # End write data
    ctx.set(port.wvalid, 0)

    # Response
    ctx.set(port.bready, 1)

    await ctx.tick().until(port.bvalid)

    # Valid response
    assert ctx.get(port.bresp) == 0

    return
```

This writes the address, then writes a number of values, and then checks the response.  A thing that should also be checked is changing the delay between transactions, especially the case where the address and data transactions are started simultaneously, and when there is a delay greater than 1 clock cycle.

An AXI read is similar:

```python
async def axi_read(ctx, port, addr, size, length):
    # Write read address
    ctx.set(port.arvalid, 1)
    ctx.set(port.araddr, addr)
    ctx.set(port.arsize, size)
    ctx.set(port.arlen, length)

    await ctx.tick().until(port.arready)

    # Finish read address
    ctx.set(port.arvalid, 0)

    data = list()

    # Read data
    while True:
        ctx.set(port.rready, 1)
        d, last = await ctx.tick().sample(port.rdata, port.rlast).until(port.rvalid)
        data.append(d)
        if last:
            ctx.set(port.rready, 0)
            return data
```

For the AXIS stream, I only need to read the result. This just means setting the ready flag and waiting for valid data.

```python
async def axis_read(ctx, port):
    ctx.set(port.tready, 1)
    await ctx.tick().until(port.tvalid)
    data = ctx.get(port.tdata)
    user = ctx.get(port.tuser)
    last = ctx.get(port.tlast)
    ctx.set(port.tready, 0)
    return data, user, last
```

Finally, some wishbone utilities:

```python
async def wishbone_write(ctx, port, addr, data):
    ctx.set(port.stb, 1)
    ctx.set(port.cyc, 1)
    ctx.set(port.addr, addr)
    ctx.set(port.w_data, data)
    ctx.set(port.w_enable, 1)

    await ctx.tick().until(port.ack)

    ctx.set(port.stb, 0)
    ctx.set(port.cyc, 0)
    ctx.set(port.w_enable, 0)

async def wishbone_read(ctx, port, addr):
    ctx.set(port.stb, 1)
    ctx.set(port.cyc, 1)
    ctx.set(port.addr, addr)
    ctx.set(port.w_enable, 0)
    
    data, = await ctx.tick().sample(port.r_data).until(port.ack)
    
    ctx.set(port.stb, 0)
    ctx.set(port.cyc, 0)
    
    return data
```

What I started with is making a mock mig device to test against. There is also the AXI verification tool in Vivado, which I'll be using later. But for now, it's easier to stay within amaranth, while working on functional components. I wrote some sanity tests to make sure my ram device works as expected. These are very simple, but it's a headache to check back if the mock device works when doing later tests.

```python
class TestMockMem(unittest.TestCase):
    """
    Sanity tests for my fake memory device
    """
    def dut(self):
        return MockRam()

    def test_short(self):
        dut = self.dut()

        async def process(ctx):
            await axi_write(ctx, dut.axi, addr = 0, size = 0, length = 0, data = [10])
            assert await axi_read(ctx, dut.axi, addr = 0, size = 0, length = 0) == [10]

            await axi_write(ctx, dut.axi, addr = 1, size = 0, length = 0, data = [11])
            assert await axi_read(ctx, dut.axi, addr = 1, size = 0, length = 0) == [11]

            await axi_write(ctx, dut.axi, addr = 2, size = 0, length = 0, data = [13])
            assert await axi_read(ctx, dut.axi, addr = 0, size = 0, length = 0) == [10]
            assert await axi_read(ctx, dut.axi, addr = 2, size = 0, length = 0) == [13]

        sim = Simulator(dut)
        sim.add_clock(1e-8)
        sim.add_testbench(process)

        with sim.write_vcd("bench/test_mock_mem_short.vcd") as vcd:
            sim.run()

    def test_long(self):
        dut = self.dut()

        async def process(ctx):
            await axi_write(ctx, dut.axi, addr = 0, size = 2, length = 1, data = [
                0xAABBCCDD, 0xEEFF0011
            ])
            result = await axi_read(ctx, dut.axi, addr = 0, size = 2, length = 1)
            #print("Result = {}".format(" ".join(["0x{:08X}".format(r) for r in result])))
            assert result == [0xAABBCCDD, 0xEEFF0011]

            await axi_write(ctx, dut.axi, addr = 8, size = 2, length = 1, data = [
                0xBBAAEEFF, 0x33221155
            ])

            result = await axi_read(ctx, dut.axi, addr = 0, size = 2, length = 3)
            assert result == [0xAABBCCDD, 0xEEFF0011, 0xBBAAEEFF, 0x33221155]

        sim = Simulator(dut)
        sim.add_clock(1e-8)
        sim.add_testbench(process)

        with sim.write_vcd("bench/test_mock_mem_long.vcd") as vcd:
            sim.run()
```

Handling the size and length constraints for AXI always makes modules a little goofy looking, but as long as I have a reference for functioning, I can always go back and make improvements.
