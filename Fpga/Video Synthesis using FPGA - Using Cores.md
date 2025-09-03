# Video Synthesis using FPGA - Using Cores

I am returning to my video synthesizer project. My overall goal is to have a performance capable hardware which can do dynamic video synthesis which can carry interest for 5 hour shows, without being too hefty or unwieldy. My largest inspiration is playing with LZX Vidiot at a show, which is an analog synthesizer. I would love to put together some modular hardware when I get a chance, but right now I'm doing computer stuff until I figure out some things in my studio (mostly figuring a better chair so that doing small circuitry doesn't kill my back).

Anyway, I have been working on a variety of CPU emulators and it made me think of a layout for a potentially interesting way to do some video synthesis. The goal is to have multiple parallel small cores which are running small programs operating and passing through video. This video can arrive at an framebuffer and then be displayed. I am also interested in adding some feedback and more complex bus networks, but that's to be experimented with.

For this first iteration I wanted to start by designing a small CPU module. The CPU has two ports, one to receive data, and the other to send.

Each CPU has a small data and program memory. I am mostly trying to follow a RISC/MIPS-like architecture, although not super closely right now. At some point I'd like to be able to compile/assemble using a somewhat normal toolchain. My current idea is to use a `sys` instruction to handle sending/looping.  Each module should be taking one piece of data (probably a pixel in most cases) and then sending data to the next module. Once sent, the module should wait for the next data to be written.

## Infrastructure

To set myself up for success, I started with some needed infrastructure. I defined my wishbone signature, stream signature. Then I made a small memory module using Amaranth HDL's build in memory. This module is just acting as a wrapper to have it be readable and writeable from a wishbone bus:

```python
class Memory(wiring.Component):
    """
    Memory device for local core memory
    """
    def __init__(self, shape, depth):
        self.shape = shape
        self.depth = depth
        
        super().__init__({
            "bus": In(Bus(range(depth), shape))
        })
        
    def elaborate(self, platform):
        m = Module()
        
        mem = m.submodules.mem = memory.Memory(shape = self.shape, depth = self.depth, init = [])
        
        read_port = mem.read_port()
        write_port = mem.write_port()
        
        # Access memory
        with m.If(self.bus.w_en):
            m.d.comb += write_port.en.eq(self.bus.stb & self.bus.cyc)
        
        m.d.comb += read_port.en.eq((~self.bus.w_en) & self.bus.stb & self.bus.cyc)
            
        # Address
        m.d.comb += write_port.addr.eq(self.bus.addr)
        m.d.comb += read_port.addr.eq(self.bus.addr)
        
        # Ack signal
        with m.If(self.bus.ack):
            m.d.sync += self.bus.ack.eq(0)
        with m.Else():
            m.d.sync += self.bus.ack.eq(write_port.en | read_port.en)
        
        m.d.comb += self.bus.r_data.eq(read_port.data)
        
        m.d.comb += write_port.data.eq(self.bus.w_data)
        
        return m
```

Next I wrote a switch. I am still expanding this switch as a wrapper, for now I just wrote quick switch that can do 2 to N busses. The switch uses the `dest` signal to route busses, and polls the two inputs just using round-robin.

```python
class BusSwitch(wiring.Component):
    def __init__(self, ports, dest_shape, addr = 16, data = 32):
        self.n = len(ports)
        
        p = dict()
        for i in range(len(ports)):
            p["p_{:02X}".format(i)] = Out(Bus(ports[i].addr, ports[i].data))
        
        super().__init__({
            "c_00": In(Bus(addr, data, dest_shape)),
            "c_01": In(Bus(addr, data, dest_shape)),
        } | p)
        
    def elaborate(self, platform):
        m = Module()
        
        select = Signal()
        
        with m.If(select == 0):
            with m.If(~self.c_00.cyc):
                # Check other input
                m.d.sync += select.eq(1)
            with m.Switch(self.c_00.dest):
                # Connect
                for i in range(self.n):
                    with m.Case(i):
                        p = getattr(self, "p_{:02X}".format(i))
                        c = self.c_00
                        m.d.comb += [
                            p.stb.eq(c.stb),
                            p.cyc.eq(c.cyc),
                            c.ack.eq(p.ack),
                            p.addr.eq(c.addr),
                            p.w_en.eq(c.w_en),
                            p.w_data.eq(c.w_data),
                            c.r_data.eq(p.r_data)
                        ]
                        
        with m.If(select == 1):
            with m.If(~self.c_01.cyc):
                # Check other input
                m.d.sync += select.eq(0)
            with m.Switch(self.c_01.dest):
                # Connect
                for i in range(self.n):
                    with m.Case(i):
                        p = getattr(self, "p_{:02X}".format(i))
                        c = self.c_01
                        m.d.comb += [
                            p.stb.eq(c.stb),
                            p.cyc.eq(c.cyc),
                            c.ack.eq(p.ack),
                            p.addr.eq(c.addr),
                            p.w_en.eq(c.w_en),
                            p.w_data.eq(c.w_data),
                            c.r_data.eq(p.r_data)
                        ]
        
        return m
```

Not the cleanest right now, but it is functional. 

## CPU design

I am starting by figuring out how I want to interface with this. So I want to think about what the programs look like. A good basic shape is a vertical bar:

```asm
# START
.START
LOADI r2, 1 # incrementer
LOADI r3, 128 # Half frame
LOADI r4, 255 # Full frame
LOADI r5, 0 # off color
LOADI r6, 255 # on color

LOADI r1, 0 # Y

# Outer loop
.OUTER
LOADI r0, 0 # reset X
# Inner loop
.INNER
ADD r0, r0, r2
BLE r0, r3, 4

# if r0 > r3
SEND 0 2 # Send r0 and r1 to next module
SEND 5 1 # Send intensity
# if r0 <= r3
ADD r0, r0, r2 # increment X
BE  r0, r4, .NEXT # or whatever frame width is

J .INNER
.NEXT
ADD r1, r1, r2
BE r1, r4, .OUTER
J .START
```


