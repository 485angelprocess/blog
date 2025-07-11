# RISC-V Implementation using Amaranth HDL

This project is located on my github here: [GitHub - 485angelprocess/embellish: FPGA based modules for video synthesis using CPU softcores](https://github.com/485angelprocess/embellish)

I was thinking about getting my video synthesis work back up, and as I've been experimenting with CPUs I wanted to try to put together some firmware that could run code. I've been working on both a gameboy architecture and a transputer architecture, but both would eventually run into the issue that it would be annoying to code for them. A Z800 type CPU would have some compiler support, but it would be still be using less supported toolchains. For this project, I want to have low-level access, but also make it as easy to develop ideas as possible. So I went with Risc, because there are compilers and assemblers I could use to ideally write in C or even other languages.

For this implementation I started with the base instructions of the RV32I. This is a nicely small range of instructions which are all straightforward to implement. Such a relief from the other processors I've worked on recently. The instruction set is decently documented, I used [RV32I, RV64I Instructions &mdash; riscv-isa-pages documentation](https://msyksphinz-self.github.io/riscv-isadoc/html/rvi.html) and https://www.vicilogic.com/static/ext/RISCV/RV32I_BaseInstructionSet.pdf as references. Mostly because they had all the information I needed in an easy format while working on my laptop.

## RISC-V Implementation

I started with defining the ins and outs of my processor. I haven't made too many decisions about the external architecture, but to start I have three buses. The program bus loads in 32-bit instructions, although addressing is on the byte level. There were a few ways to abstract/not abstract this, but it's a fine starting point. Then there is a bus for storing/loading data. RISC CPUs should only be interacting with data/registers through the store and load instructions. I left this bus with an 8-bit width, which avoids having to define some type of strobe/data-width parameter on the bus. This does mean it'll always take at least 4 clock cycles to read/write a full word. That may become an issue at some point, but it is not the hardest to fix.

Next I started going through the implementation. There are only a few opcodes that need to be defined, with most having several function codes. Each instruction has one of several formats usually labeled something like U, B, I, S, J or R. This defines how the data is representing in each instruction. To make it easy to work with I defined an amaranth layout which uses a union to label the different representations.

```python
risc_instruction_layout = data.UnionLayout({
    "op": 7,
    "r": data.StructLayout({
        "op": 7,
        "rd": 5,
        "f_lower": 3,
        "rs1": 5,
        "rs2": 5,
        "f_upper":  7
    }),
    "i": data.StructLayout({
        "op": 7,
        "rd": 5,
        "f" : 3,
        "rs": 5,
        "imm":signed(12) 
    }),
    "u": data.StructLayout({
        "op":  7,
        "rd":  5,
        "imm": signed(20)
    }),
    "s": data.StructLayout({
        "op": 7,
        "imm_lower": 5,
        "f": 3,
        "rs1": 5,
        "rs2": 5,
        "imm_upper": 7
    }),
    "j": data.StructLayout({
        "op": 7,
        "rd": 5,
        "offset": signed(20)
    }),
    "b": data.StructLayout({
        "op": 7,
        "offset_lower": 5,
        "f": 3,
        "rs1": 5,
        "rs2": 5,
        "offset_upper": 7
    })
})
```

Some of these values need some further mapping such as the jump and branch offsets, but that's handled with some signals in the body.

As I'm not immediately optimizing for speed, I set my processor up as a state machine. When an instruction is fetched, the opcode is matched. A few instructions such as `LUI` or `AUIPC` are executed immediately. Most others go to a state based on the family of instructions. There the function is checked and each instruction is matched. Integer arithmetic takes always one additional cycle. Memory access will block until all transactions finish.

None of the instructions had any great difficulties in implementation. The minimal wishbone implementation works very nicely with memory access. I did make a quick test for sanity, although when I go back to fix timing or optimize, I will write some more.

```python
class TestRiscCore(unittest.TestCase):
    def test_set_reg_to_value(self):
        prog = list()
        
        prog.append(InstructionBuilder.andi(0, 0, 0)) # Clear register (and with 0)
        prog.append(InstructionBuilder.addi(11, 0, 0)) # add constand to register
        
        prog.append(InstructionBuilder.andi(0, 1, 1)) # Clear register 0
        prog.append(InstructionBuilder.addi(13, 1, 1)) # add constant
        
        # Store word at register 1 (13) with value from register 0 (11)
        prog.append(InstructionBuilder.storeword(0, 0, 1))
        
        prog = [p.value() for p in prog]
        
        dut, core, prog = core_with_program(prog)
        
        async def mem_process(ctx):
            assert await receive(ctx, core.bus) == (13, 11, 1)
            assert await receive(ctx, core.bus) == (14, 0, 1)
            assert await receive(ctx, core.bus) == (15, 0, 1)
            assert await receive(ctx, core.bus) == (16, 0, 1)
                
        sim = Simulator(dut)
        sim.add_clock(1e-8)
        sim.add_testbench(mem_process)
        
        with sim.write_vcd("bench/risc_set_reg.vcd"):
            sim.run()
```

The main thing I was looking for in the test is having the assembly easy to write. I may integrate some assembler if my tests get a little more elaborate. This test also enforces a one byte data bus, which I would ideally have more flexible.

## Additional infrastructure

In order to get things running well, I need to write the components around the CPU. For this project I am trying to keep each module simple, and to keep any special use module very small and reliant on common building blocks. I added a wishbone interfaced bram module, a wishbone switch and two small utilities which map address-mapped register to the wishbone `dest` signal and vice versa. The switch core uses a round robin to check if any of the input buses have started a cycle.

```python
class BusSwitch(wiring.Component):
    def __init__(self, ports, dest_shape, addr = 16, data = 32, num_inputs = 2):
        self.n = len(ports)
        
        self.num_inputs = num_inputs
        
        p = dict()
        for i in range(len(ports)):
            p["p_{:02X}".format(i)] = Out(Bus(ports[i].addr, ports[i].data))
        
        c = dict()
        for i in range(num_inputs):
            c["c_{:02X}".format(i)] = In(Bus(addr, data, dest_shape))
        
        super().__init__(c | p)
        
    def elaborate(self, platform):
        m = Module()
        
        select = Signal(range(self.num_inputs))
        
        consume = [getattr(self, "c_{:02X}".format(i)) for i in range(self.num_inputs)]
        
        for i in range(len(consume)):
            c = consume[i]
            with m.If(select == i):
                with m.If(~c.cyc):
                    # Check other input
                    with m.If(select == len(consume) - 1):
                        m.d.sync += select.eq(0)
                    with m.Else():
                        m.d.sync += select.eq(select + 1)
                with m.Switch(c.dest):
                    # Connect
                    for i in range(self.n):
                        with m.Case(i):
                            p = getattr(self, "p_{:02X}".format(i))
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

Later I may add some buffers to the switch to increase throughput, but those can be made as a separate module. Additionally I wrote a small naive cache for program instructions. I am choosing to use a common data and program memory for now. Since they should be byte addressable, I wanted some glue to make my program bus easy. The cache loads in bytes from the expected address. It continues to read instructions until it is full. If the program bus requests the instruction cache, it is immediately delivered, otherwise the cache has to reset and reload from the requested address. If the CPU was only doing memory transactions, this wouldn't save much, if any clock cycles unless the CPU idles. But since I expect the CPU to be doing many stores and loads from register devices, there should be some idling which will make the cache useful. At worst, it's very small and abstracts instructions to make the CPU easier to logically program.

```python
class InstructionCache(wiring.Component):
    def __init__(self):
        super().__init__({
            "proc": In(Bus(32, 32)),
            "mem": Out(Bus(32, 8))
        })
        
    def elaborate(self, platform):
        m = Module()
        
        cache_width = 4
        
        # Cache data as circular buffers
        cache_address = Array([Signal(32, name = "a{}".format(i)) for i in range(cache_width)])
        
        cache_ready = Array([Signal(name = "r{}".format(i)) for i in range(cache_width)])
        
        cache = Array([Signal(32, name = "c{}".format(i)) for i in range(cache_width)])
        
        read_pointer = Signal(range(cache_width))
        write_pointer = Signal(range(cache_width))
        
        address = Signal(32)
        
        byte_counter = Signal(2, init = 0)
        
        m.d.comb += self.proc.r_data.eq(cache[read_pointer])
        m.d.comb += self.mem.addr.eq(address + byte_counter)
        
        with m.FSM() as fsm:
            with m.State("Reset"):
                # Clear cache
                m.d.sync += read_pointer.eq(0)
                m.d.sync += write_pointer.eq(0)
                # Indicate first address we're loading
                m.d.sync += cache_address[0].eq(address)
                
                for i in range(cache_width):
                    m.d.sync += cache_ready[i].eq(0)
                m.next = "Load"
            with m.State("Load"):
                # Load words into cache
                with m.If(~cache_ready[write_pointer]):
                    m.d.sync += cache_address[write_pointer].eq(address)
                    m.d.comb += self.mem.stb.eq(1)
                    m.d.comb += self.mem.cyc.eq(1)
                    with m.If(self.mem.ack):
                        m.d.sync += cache[write_pointer].eq(
                                                (cache[write_pointer] >> 8) + 
                                                (self.mem.r_data << 24))
                        with m.If(byte_counter == 3):
                            # Finished reading word
                            m.d.sync += byte_counter.eq(0)
                            m.d.sync += write_pointer.eq(write_pointer + 1)
                            m.d.sync += cache_ready[write_pointer].eq(1)
                            m.d.sync += address.eq(address + 4) # Go to next address
                        with m.Else():
                            # Next byte of word
                            m.d.sync += byte_counter.eq(byte_counter + 1)
                
                with m.If(self.proc.stb & self.proc.cyc & self.proc.ack):
                    m.d.sync += read_pointer.eq(read_pointer + 1) # Next value
                    m.d.sync += cache_ready[read_pointer].eq(0) # Clear ready flag
                
                with m.If(self.proc.stb & self.proc.cyc):
                    with m.If(cache_address[read_pointer] == self.proc.addr):
                        # Wait for program to be loaded
                        m.d.comb += self.proc.ack.eq(cache_ready[read_pointer])
                    with m.Else():
                        # Cache miss, set new address and clear cache
                        m.d.sync += address.eq(self.proc.addr)
                        m.next = "Reset"
        
        return m
```

It's implemented as a circular buffer, with two pointers keeping track of the write and read locations. The buffer size can be changed without adjusting the code here.

## Visualization

I wrote a small tk based visualizer to show bus use and some other helpful things. I found it quite helpful for identifying logical errors by running a simple infinite loop. I started to add a framebuffer to show minimal visual effects, but I started to getting odd behavior. I assume the issue is coming from the simulation being larger than Amaranth normally expects, as each part seems to be working ok. For now I'll leave it, and get some more robust tests on modules. I'd like to start adding vector modules which can draw lines from getting two points, and eventually doing rasterization. Before that I want to get something on a physical FPGA, which will force me to check timing and footprint as well.
