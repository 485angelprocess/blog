# work girl processor notes

As I've been working on the processor, I've been trying to improve the setup for how I add commands, and how the processor works. I've tried a few different iterations. A crucial step was adding a verification step for every instruction. With every instruction I add, I write a verification check. For instance all load instructions are checked with (pseudo code)

```
assert dest.from_state(result) == source.from_state(initial)
```

Where each data type has a method for getting its own value from a processor state. The processor state is a simulator object I used, which holds register and memory information. As an example for a immediate value the `from_state` method returns a constant, and a register value returns the contents of that register. The goal is quickly check behavior for the variety of commands. In this approach I have also been abstracting the possible data types. The ones that have come up are a short register, wide register, short immediate, and a wide immediate. There is also the case of a read pointer, which I wrote as a wrapper data type.  For each instruction, I also provide a map of the registers and memory addresses that it effects. This allows me to auto generate test cases for verification. The steps for verification of a command are:

- Initialize the processor state. Registers and memory are at some random state.

- For this instruction, get the list of registers it uses/alters, as well as the addresses in memory it changes.

- Set the impacted registers to helpful initial values. Currently I have it set to check each combination of 0, 1, and 255, which catches several common errors, although is not exhaustive.
  
  - If needed, change these initial values to prevent known error states. For example the `push` command will have undefined behavior if the stack pointer is less than 2.

- Cache the initial processor state

- Load the opcode and arguments into the processor. For immediate arguments, I also use a set of helpful values. Then wait for a `noop` to be ran so that the instruction is guaranteed to be finished.
  
  - I check to make sure all instructions finish within a reasonable number of clock cycles, although I am not checking for exact cycle accuracy here.

- Save the resulting processor state.

- Check that all values that were not impacted remain the same.

- Check the verification test for this instruction.

I set a script which can run this for all defined instructions, or for a specific op code. I will likely improve this going forward, but it's been very helpful when there is a wide number of instructions that I have been refactoring. I am also adding proper unit-tests for code, and eventually will write a script which compares my system's performance to a known well working emulator.

The current structure of my processor is set up as a finite state machine which has three set states.

- Load: Loads byte from program memory, when byte has been loaded, go to Check

- Check: Checks if all arguments for a given instruction have been loaded. If not, load another byte, otherwise goes to the first state for the op code. That first state can be running the operation, or if the operation needs to read, goes to the read state.

- Read: Reads data from memory and then runs operation for the current op code.

For each type of instruction I create a label and a hardware description. As I work on it I am trying to cover as many instructions as possible with as few cases. For instructions that are used to write a value into memory i.e. `0x74`: `LD (HL), L` the description method is:

```
def describe(self, m, ctx, a, b, counter):
    # Write to memory
    m.d.comb += ctx["bus"].addr.eq(a)
    m.d.comb += ctx["bus"].w.data.eq(b)
    m.d.comb += ctx["bus"].w.enable.eq(1)
    m.d.comb += ctx["bus"].stb.eq(1)
    m.d.comb += ctx["bus"].cycle.eq(1)
    
    # Finish
    with m.If(ctx["bus"].ack):
        m.next = "load"
```

I use a `ctx` object which contains several processor state signals, and two values labeled `a` and `b`. These are values which are loaded in the Load or Read states and hold the usable value for a data type. This would be the contents of the register, or the value read from memory. This description just writes to the memory bus. When the write is done, it returns to the load case. Because `a` and `b` are handled in an earlier stage, I can write this description without any special knowledge of which registers are being used.

This is the best suited case for my current framework. Other instructions require some knowledge about which register is being written to, or need to modify specific registers. This isn't a huge deal, for now it just requires that cases are duplicated for different cases. Since each instruction is fairly small, this is just a space consideration (more special cases means more LUTs being used). Each instruction is fairly small, and at most there are 8 duplicate instructions, one for each register. Because I have a verification setup, I intend to improve code coverage and then loop back to making these more efficient. I only need to identify which have the largest footprint, and then make a common unit which prevents the need for special cases.
