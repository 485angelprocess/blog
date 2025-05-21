## Verifying Wishbone bus behavior using Amaranth - Single Read/Write

As part of a design for another project, I am using a wishbone "bus" (wishbone is a methodology for bus design, not technically a bus standard).

To start I setup a signature for the wishbone interface. I personally like having my read and write port written as `port.w.data` and `port.r.data` which is why the ports are separate. Wishbone shares other values such as address, stb, and cycle between and write.

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
            "cycle": Out(1),
            "stb": Out(1),
            "ack": In(1)
        }

        if burst:
            ports = ports | {"cti": Out(3)}

        super().__init__(ports)
```

Since wishbone offers a few optional signals, those are left as options to add. As I build more elaborate modules, I am going to add some more ports.

## Test functions

With that done, I want to create a few functions to make writing tests for wishbone interfaces easy. For a client interface, I want to be able to write data to an address, and then read data from an address

The write function is written to slot nicely into Amaranth's testbench framework. The `ctx` object provides useful methods for working with the simulator. `port` is the port under test (usually the top level wishbone interface for the DUT). 

```python
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
```

The `until` method of `TickTrigger` (returned by `ctx.tick()`) is a really helpful method. The `TickTrigger` [documentation](https://amaranth-lang.org/docs/amaranth/v0.5.4/simulator.html#amaranth.sim.TickTrigger) is helpful for writing concise testbenches. Coming from SystemVerilog, it allows an easy flexible framework for writing tests.

The read function is similar, but I use the `sample` method to receive data.

```python
async def read_single(ctx, port, addr, expect):
    ctx.set(port.addr, addr)
    ctx.set(port.w.enable, 0)
    ctx.set(port.cycle, 1)
    ctx.set(port.stb, 1)
    data, = await ctx.tick().sample(port.r.data).until(port.ack)
    assert data == expect
    ctx.set(port.stb, 0)
    ctx.set(port.cycle, 0)
```

For now I have the assert in the scope of the function. Some flexibility can be added by returning it instead. For unit tests I find that a simple assert is enough information, since I can then refer to the waveform, which stops right at the error condition. Some more information can be provided using a python unittest framework.

After working on some projects for a bit, I also added a poll function. This is helpful when I want to wait for some register to be ready before checking other values.

```python
async def poll(ctx, port, addr, until):
    counter = 0
    while await read_single(ctx, port, addr) != until:
        counter += 1
    return counter
```

 This function waits for a bus read to return a value `until`.

To do a testbench, I can use these functions to check my module's functionality:

```python
class Device(wiring.Component):
    bus: Bus(32, 32)

    def elaborate(self, platform):
        m = Module()

        # Do work here

        return m  

dut = Module()
dut.submodules.device = device = Device()

async def wb_testbench(ctx):
    # Write data to component at address 10
    await write_single(ctx, device.bus, 10, 2)
    # Read data from address 10
    assert await read_single(ctx, device.bus, 10) == 2
    # Wait for some register at address 11 to be set
    await poll(ctx, device.bus, 11)
    # Check another register at address 15
    assert await read_single(ctx, device.bus, 15) == 10

sim = Simulator(dut)
sim.add_clock(1e-8)
sim.add_testbench(wb_testbench)

with sim.write_vcd("bench.vcd"):
    sim.run()
```

This doesnt check for wishbone features and expected failures, but is a fast way to check for functionality. When developing a bus based module system, it greatly speeds up development time to have a flexible testing framework.

# 
