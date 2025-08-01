# I2C Driver in Amaranth HDL

I needed to write a I2C driver to control an audio chip. I tried to make a somewhat simple driver, by breaking it down into three components. Still a bit frustrated because I feel like it can be simplified more, but it's at least functioning.

## I2C Overview

I2C is inter-intergtated circuit, it's a serial protocol for interfacing different ICs. It uses a clock line and a bidirectional data line. In most cases data is shifted on the falling edge, and read on the rising edge. There are a stop and start condition.

- The start condition is done by shifting the data from high to low while keeping the clock constant.

- The stop condition is done by shifting the data from low to high while keeping the clock constant.

After sending the start, one byte of data is written or read at a time, after each byte, the slave device should send a ACK if it's a valid address. 

## Implementation

To start, I decided the controller should be interfaced with a Wishbone-style bus, using a few registers. I used Xilinx's UART IP as a framework for interfacing with a serial bus. I started with defining the necessary registers:

| Register    | Function                                                                                                                                                                                      |
| ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ENABLE      | Writing 1 will enable transactions to start. Data should be buffered prior to enabling, unless there is some guarantee that the data bus is faster than the serial bus.                       |
| WRITE_DATA  | Write one word to data buffer. If we are just reading this just needs be some value. (Write-only)                                                                                             |
| WRITE_START | Volatile flag, indicates that the data is the start of frame. I guess I could make this implicit, but leaving it explicit gives me some flexbility for future designs.                        |
| DATA_EN     | Set to 1 if the next byte of data is written to the slave, set to 0 if the driver should read instead.                                                                                        |
| WRITE_LEN   | Number of bytes in the write buffer (Read-only)                                                                                                                                               |
| READ_DATA   | Response buffer. If the data was written, this will have a copy of the write data, otherwise this is the response from the slave. Read from this will pop from the response data. (Read-only) |
| READ_LEN    | Number of bytes in the response buffer (Read-only)                                                                                                                                            |
| READ_ACK    | Gives the ACK bit from the top of the response buffer. If ACK is 0, the slave responded. (Read-only)                                                                                          |
| PERIOD      | Set the period of the driver.                                                                                                                                                                 |

Essentially there are two buffers, one for sending data and then one for getting the response. Each byte of the transaction is marked as read or write by the top-level device. I had some frustrations with Vivado's IP, but it was the over-flexibility of the IP which made it difficult to use and setup. Hopefully I won't suffer the same scope creep.

Next I defined the output. SDA needs to be bidirectional, so needs three signals (ok, actually it could use two since SDA only needs to be pulled low, but it made it a little harder to debug). `sda_out`, `sda_en`, and `sda_in`  are used for data and `scl` is just an output clock.

With the input and outputs, I can write a test to design off of.

```python
def test_write(self):
    dut = I2CTop()
    
    response = I2CResponse(
        I2CWord(10),
        I2CWord(11),
        I2CWord(12),
        I2CWord(13)
    )
    
    async def bus_process(ctx):
        await Bus.sim_write(ctx, dut.bus, 8, 10) # Period
        await Bus.sim_write(ctx, dut.bus, 3, 1) # Write
        await Bus.sim_write(ctx, dut.bus, 2, 1) # Start flag
        await Bus.sim_write(ctx, dut.bus, 1, 10) # Write data
        await Bus.sim_write(ctx, dut.bus, 1, 11)
        await Bus.sim_write(ctx, dut.bus, 1, 12)
        await Bus.sim_write(ctx, dut.bus, 1, 13)
        assert await Bus.sim_read(ctx, dut.bus, 4) == 4
        await Bus.sim_write(ctx, dut.bus, 0, 1) # Enable
        
        # Wait for buffer to fill
        while await Bus.sim_read(ctx, dut.bus, 6) < 4:
            await ctx.tick()
        await Bus.sim_write(ctx, dut.bus, 0, 0) #Disable
            
        # Received 4 responses
        assert await Bus.sim_read(ctx, dut.bus, 7) == 0 # ACK
        assert await Bus.sim_read(ctx, dut.bus, 5) == 10
        assert await Bus.sim_read(ctx, dut.bus, 7) == 0 # ACK
        assert await Bus.sim_read(ctx, dut.bus, 5) == 11
        assert await Bus.sim_read(ctx, dut.bus, 7) == 0 # ACK
        assert await Bus.sim_read(ctx, dut.bus, 5) == 12
        assert await Bus.sim_read(ctx, dut.bus, 7) == 0 # ACK
        assert await Bus.sim_read(ctx, dut.bus, 5) == 13
        
    async def i2c_process(ctx):
        while not response.last():
            sda = ctx.get(dut.sda)
            scl = ctx.get(dut.scl)
            sda_en = ctx.get(dut.sda_en)
            response.get(ctx, sda, sda_en, scl, dut.sda_in)
            await ctx.tick()
            
    sim = Simulator(dut)
    sim.add_clock(1e-8)
    sim.add_testbench(bus_process)
    sim.add_testbench(i2c_process)
    
    with sim.write_vcd("bench/serial_test.vcd"):
        sim.run_until(1000 * 1e-8)
```

This sets up the driver and then writes 4 bytes out. The device should give me the same bytes back out, with an `ACK` flag on each byte. I may add further tests later if I run into problems, but this is a good start.

For the inner implementation, I split the functions into three parts. The output section works on a bit level, sending out/in each bit. There's a few cases the output section handles:

| Clock En | Data En | Function                               |
| -------- | ------- | -------------------------------------- |
| 0        | 1       | Use for sending start/stop conditions. |
| 1        | 1       | Write bits out to I2C device           |
| 1        | 0       | Read bits from I2C device              |

Data is written as a stream, which shifts in new data/parameters with clock timing. Data is read from this module with a single clock pulse, since there's no way to apply backpressure on the I2C bus (except for on a logical level). 

The actual model is mostly a counter which sends data based on the period, with some extra logic for these different cases:

```python
class I2COut(wiring.Component):
    """
    Drive serial lines
    """
    def __init__(self, max_period = 1024):
        self.max_period = max_period
    
        super().__init__({
            # Input
            "clk_en": In(1),
            "dat_en": In(1),
            "data": In(1),
            "ready": Out(1),
            "valid": In(1),
            "period": In(range(max_period)),
            # Data
            "read_data": Out(1),
            "read_valid": Out(1),
            #I2C interface
            "sda": Out(1),
            "sda_en": Out(1),
            "sda_in": In(1),
            "scl": Out(1)
        })
        
    def elaborate(self, platform):
        m = Module()
        
        counter = Signal(range(self.max_period))
        half_period = Signal(range(self.max_period))
        
        clk_en = Signal()
        dat_en = Signal()
        
        # Rising edge
        with m.If(clk_en):
            m.d.comb += self.scl.eq(counter < half_period)
        with m.Else():
        # clock disabled
            m.d.comb += self.scl.eq(1)
            
        # Read data from line
        m.d.comb += self.read_valid.eq((clk_en) & (counter == half_period - 2))
        m.d.comb += self.read_data.eq(self.sda_in)
            
        data = Signal()
            
        # send data out
        with m.If(dat_en):
            m.d.comb += self.sda_en.eq(1)
            m.d.comb += self.sda.eq(data)
        with m.Else():
            m.d.comb += self.sda.eq(1)
            m.d.comb += self.sda_en.eq(0)
        
        with m.FSM():
            with m.State("Idle"):
                m.d.comb += self.ready.eq(1)
                with m.If(self.valid):
                    
                    m.d.sync += clk_en.eq(self.clk_en)
                    m.d.sync += dat_en.eq(self.dat_en)
                    
                    m.d.sync += counter.eq(self.period)
                    m.d.sync += half_period.eq(self.period >> 1)
                    m.d.sync += data.eq(self.data) # get data
                    m.next = "Send"
                with m.Else():
                    # Disable clock and data if no signal immediately available
                    m.d.sync += clk_en.eq(0)
                    m.d.sync += dat_en.eq(0)
            with m.State("Send"):
                m.d.sync += counter.eq(counter - 1)
                with m.If(counter == 1):
                    m.next = "Idle"
        
        return m
```

The middle module handles the buffer and going from bytes to finer level I2C bits. It also handles sending start and stop conditions, as well as reading bits from the output side into bytes. Inputs and outputs are handled as two streams. The transmit buffer stream is composed of the data, a flag indicating if it is a write, and a flag indicating if it's the start of transaction. The response buffer stream includes the read data and the ack flag.

With the middleware, the bus level module is fairly straightforward, just reading and writing from registers. Separating out this middleware will also be helpful for modifying my driver for different bus interfaces.

```python
class I2CController(wiring.Component):
    """
    Bus controlled unit
    """
    def __init__(self):
        super().__init__({
            "bus": In(Bus(4, 32)),
            
            # Control signals
            "ctl_period": In(32),
            "wlen": In(32),
            "rlen": In(32),
            "enable": Out(1),
            
            # write /read from buffers
            "write_data": Out(8),
            "start": Out(1),
            "dat_en": Out(1),
            "write_valid": Out(1),
            "write_ready": In(1),
            
            "read_data": In(8),
            "read_ack": In(1),
            "read_valid": In(1),
            "read_ready": Out(1)
        })
        
    def elaborate(self, platform):
        m = Module()
        
        period = Signal(12, init = 100)
        
        m.d.comb += self.ctl_period.eq(period)
        
        with m.If(self.bus.cyc & self.bus.stb):
            with m.If(self.bus.w_en):
                # Write to bus
                with m.If(self.bus.addr == I2CRegister.WRITE_DATA):
                    m.d.comb += self.write_valid.eq(1)
                    m.d.comb += self.bus.ack.eq(1) # Prevent lock, could wait for fifo but that's less likely case i think
                    # Could put error flag for case where fifo is full
                with m.Else():
                    m.d.comb += self.bus.ack.eq(1)
                
                with m.Switch(self.bus.addr):
                    with m.Case(I2CRegister.ENABLE):
                        # Enable/disable driver
                        m.d.sync += self.enable.eq(self.bus.w_data)
                    with m.Case(I2CRegister.WRITE_DATA):
                        # Write data, loads to fifo
                        m.d.comb += self.write_data.eq(self.bus.w_data)
                        m.d.sync += self.start.eq(0) # Clear start flag
                    with m.Case(I2CRegister.WRITE_START):
                        # Write start flag
                        m.d.sync += self.start.eq(self.bus.w_data)
                    with m.Case(I2CRegister.PERIOD):
                        # Set I2C period
                        m.d.sync += period.eq(self.bus.w_data)
                    with m.Case(I2CRegister.DATA_EN):
                        m.d.sync += self.dat_en.eq(self.bus.w_data)
                    with m.Default():
                        pass
            with m.Else():
                # Read
                with m.If(self.bus.addr == I2CRegister.READ_DATA):
                    # Read from buffer
                    m.d.comb += self.read_ready.eq(1)
                    m.d.comb += self.bus.ack.eq(self.read_valid)
                with m.Else():
                    m.d.comb += self.bus.ack.eq(1)
                    
        # Read data
        with m.Switch(self.bus.addr):
            with m.Case(I2CRegister.ENABLE):
                m.d.comb += self.bus.r_data.eq(self.enable)
            with m.Case(I2CRegister.WRITE_DATA):
                pass
            with m.Case(I2CRegister.WRITE_START):
                m.d.comb += self.bus.r_data.eq(self.start)
            with m.Case(I2CRegister.WRITE_LEN):
                m.d.comb += self.bus.r_data.eq(self.wlen)
            with m.Case(I2CRegister.READ_DATA):
                # Does more than this
                m.d.comb += self.bus.r_data.eq(self.read_data)
            with m.Case(I2CRegister.READ_ACK):
                m.d.comb += self.bus.r_data.eq(self.read_ack)
            with m.Case(I2CRegister.READ_LEN):
                m.d.comb += self.bus.r_data.eq(self.rlen)
            with m.Case(I2CRegister.DATA_EN):
                m.d.comb += self.bus.r_data.eq(self.dat_en)
            with m.Case(I2CRegister.PERIOD):
                m.d.comb += self.bus.r_data.eq(period)
        
        return m
```

After wrapping my modules into a top-level module, I could pass my test and could also read and write from my on-board chip. Next I'm figuring out the right combination of registers to get audio out correctly from it, but that's for another time. 


