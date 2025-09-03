# Some Gameboy CPU Notes

This is going to be a more thinking out loud post. I have been working on the CPU for an FPGA emulator. Gameboy has 245 opcodes (+255 additional operations), which are the result of a few iterations of 8-bit CISC CPUs. So the design reasons for the instructions are fairly obfuscated. Each instruction consists of an opcode, which usually implies at least one register. Then the instruction can have 0-2 arguments, and may require additional cycles to finish operation. 

The processor has 8 8-bit register, which can also be used as 4 16-bit registers. There are also 2 additional 16-bit registers the program counter (PC) and the stack pointer (SP).

The core processor has to read a byte from the program counter, and then load in additional arguments. When all arguments are ready the processor can do an operation. These operations can be setting a register to a value, writing to memory, reading from memory or writing to the ALU bus. The ALU (arithmetic logic unit) contains the logic for things like adding, subtracting and multiplication.

Some example instructions:

| Instruction       | OpCode | Arguments            | Actions                                                                                                                                                                                 | Bus            |
| ----------------- | ------ | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------- |
| LD B, n           | 0x06   | 1 - 8 bit immediate  | Put 8-bit immediate value into register B.                                                                                                                                              |                |
| LD A, (HL)        | 0x7E   | 0                    | Load value from memory at address HL (the address formed by using the H and L register as a 16 bit number) into register A                                                              | Data Read      |
| LD (HL), C        | 0x71   | 0                    | Write the value of register C to memory at address HL                                                                                                                                   | Data Write     |
| LD A, (nn)        | 0xFA   | 2 - 16 bit immediate | Load value from memory at address nn into register A                                                                                                                                    | Data Read      |
| LD (\$FF00 +C), A | 0xE2   | 0                    | Load value from register A into memory at address 0xFF00 + the value of register C, into register A                                                                                     | Data Write     |
| PUSH AF           | 0xF5   | 0                    | Push the 16-bit contents of register A and register F onto the point in memory set by the stack pointer. This decrements the stack pointer twice (Increasing the stack size by 2 bytes) | Data write     |
| POP AF            | 0xF1   | 0                    | Pop the stack into the contents of register A and register F. This increments the stack pointer twice (decreasing the stack size by 2 bytes)                                            | Data Read      |
| Add A, B          | 0x80   | 0                    | The ALU adds registers A and B, the contents is stored in register A. Sets flags Z if A+B==0, and carry flags.                                                                          | ALU            |
| Add A, (HL)       | 0x86   | 0                    | The ALU address register A to the value stored at address HL, sets flags                                                                                                                | ALU, Data Read |

That's a few of them. So there's a variety of operations, with different arguments and bus transactions. I would like to be able to write the processor to functionally run code, to have testable functionality and to be able to run at an arbitary clock rate. I also want it to be easy to add and edit instructions, because it'll be easy to make mistakes.

Because I'm using amaranth, which is based on python, I'm trying to leverate objects to make this easier. It's definitely not there, I would like there to be a clearer separation of abstraction, but there's some things I like about it.

First I created a base class that provides instruction info, and amaranth expressions that can do things like start a bus transaction, and then wait for the bus transaction to finish, then do an operation.

```python
class InstructionBase(object):
    # Provide info about arguments, idle cycles
    def arg_length(self):
        ...
    def cycle_length(self):
        ...

    # Run operation
    def loaded(self, ctx):
        # Returns amaranth expression that evaluates to true
        # if the command is fully loaded
        ...
    
    def on_load(self, ctx):
        # Returns amaranth expression that is done combinatorally
        # When command is loaded
        ...

    def requires(self, ctx):
        # Returns amaranth expression that evaluates to true
        # if the operation can be ran
        ...

    def operate(self, ctx):
        # Returns amaranth expression that is done synchronously
        # When requirements are met
        ...
```

`ctx` is a object which provides the processors state info. It includes registers, the arg counter and the bus access.

For a hardcoded example, say I wanted to to run `LD A,(HL)`. This means when the processor receives opcode `0x7E`, the instruction should start read transaction with the bus address set to the value of HL. When the read instruction finishes, the value of A should be set to the bus's read value. 

```python
class Load_A_HL(InstructionBase):
    def arg_length(self):
        return 0 # Only the opcode is needed
    
    def cycle_length(self):
        return 1 # This instruction takes 2 system clock pulses to run

    def loaded(self, ctx):
        # Is true if all arguments were loaded
        return ctx.arg_counter() >= self.arg_length())

    def on_load(self, ctx):
        # if all instructions are loaded,
        # then enable bus read
        return [
            ctx.mem.addr.eq(ctx.get_wide("HL"),
            ctx.mem.r_en.eq(1)
        ]

    def requires(self, ctx):
        # Is true if bus has finished reading
        return ctx.mem.r_ready

    def operate(self, ctx):
        # Set register A to result
        return ctx.get_reg("A").eq(ctx.mem.r_data)

```

Now the processor can have a setup which checks for the opcode, and has functions on given conditions. This is meant to be have a generic interface for instructions.

```python
iset = # Lookup table of opcode: InstructionBase object
ctx = # Object to access processor state

arg_length = Signal(range(2)) # How many args we expect
cycle_length = Signal(range(16)) # How many clock cycles this instruction takes

opcode = Signal(8) # Loaded in from program bus

with m.Switch(opcode):
    for o in iset:
        # For each instruction
        with m.Case(o):
            # Assign signals
            m.d.comb += arg_length.eq(iset[o].arg_length())
            m.d.comb += cycle_length.eq(iset[o].cycle_length())
            
            # If loaded, do something
            with m.If(iset[o].loaded(ctx)):
                m.d.comb += iset[o].on_load(ctx)

            # If everything is ready, do something
            with m.If(iset[o].requires(ctx)):
                m.d.sync += iset[o].operate(ctx)
```

This is somewhat comprehensible, and it means that the instruction set can be defined as dictionary lookup containing objects. 


