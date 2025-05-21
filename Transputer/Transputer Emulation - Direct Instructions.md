# Transputer Emulation - Direct Instructions

This is a first part of working through a transputer emulator. I'm specifically aiming for the INMOS T800, which is the floating point model. The transputer architecture draws from RISC and parallel processing notions. Compared to work I've done on contemporary Intel CPUs, the design principles are a lot clearer and less mired in legacy decissions. The primary features of the T800 are a 32-bit word-size, stack-based register storage and quick interrupts. Much of the information here is pulled from: https://www.transputer.net/iset/pdf/transbook.pdf

The register stack consists of three registers labeled A, B and C. The stack can be pushed, which moves B into C, A into B and a new value is placed in A. The original contents of C is discarded. The stack can also be read and modified. In rust, I can create a general use struct which supports these operations:

```rust
pub const STACK_SIZE: usize = 3;

pub struct Stack{
    reg: Rc<RefCell<[i32; STACK_SIZE]>>
}

impl Stack{
    pub fn new() -> Self{
        Self{
            reg: Rc::new(RefCell::new([0; STACK_SIZE]))
        }
    }
    pub fn push(&mut self, value: i32){
        // Push values up and insert new value
        let mut c = self.reg.borrow_mut();
        for i in (1..STACK_SIZE).rev(){
            // C <= B, B <= A
            c[i] = c[i - 1];
        }
        // A = value
        c[0] = value;
    }
    pub fn get(&self, index: usize) -> i32{
        self.reg.borrow()[index].clone()
    }

    pub fn set(&self, index: usize, value: i32){
        self.reg.borrow_mut()[index] = value;
    }
}
```

I'm using for the `Rc<RefCell<>>` wrapper on the registers, which is to allow shared state between different processes. An interrupt process will use the same register space (which means that the state must be restored exiting the interrupt).

The processor also has to interface with memory. The memory struct has to provide methods for reading and writing, while having a shared state. At some point I may have to add some bus ordering, but the general structure is:

```rust
pub struct Mem{
    contents: Shared Container
}

impl Clone for Mem{
    fn clone(&self) -> Self {
        Self{
            // Pointer to the same underlying contents
            contents: self.contents.clone()
        }
    }
}

impl Mem{
    pub fn new() -> Self{
        Self{
            contents: New Shared container
        }
    }

    pub fn write(&mut self, address: i32, value: i32){
        // write value to address
    }

    pub fn read(&self, address: i32) -> i32{
        // return value at address
    }
}
```

For my current setup I am using a HashMap to have a lookup table of valid addresses. I will likely move this to a vec which dynamically grows with the stack size (well INMOS calls it a workspace). Or it can be allocated all at once for a given instance of the emulator. As long as it can provide read, write and clone methods it is arbitary.

Now I can run processes. The transputer has 15 direct instructions and then 16 "indirect" instructions. Direct instructions are the most common instructions that INMOS observed, and are given priority with a shorter instruction length. Indirect instructions are prefixed with 0xF and are a wider variety of lesser used instructions. I am implementing the indirect instructions later, so I'm going to look at the direct ones first. Each direct instruction consists of a 4 bit prefix and a 4 bit operand.

| Opcode | Mnemonic | Description             | Operation                                                                                                                                                      |
| ------ | -------- | ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0x0X   | j        | jump                    | Adds operand to the program pointer. This also deprioritzes the current processes, allowing other processses to run.                                           |
| 0x1X   | ldlp     | load local pointer      | Push the value of the workspace pointer (stack pointer) + 4*operand into the register stack.                                                                   |
| 0x2X   | pfix     | prefix                  | Set the lower 4 bits of the operand register to the operand, and then shift the operand register up 4 bits. Allows the operand register to have larger values. |
| 0x3X   | ldnl     | load non-local          | Loads a value from memory pointed by A + 4*operand                                                                                                             |
| 0x4X   | ldc      | load constant           | Pushes the value in the operand register into the register stack                                                                                               |
| 0x5X   | ldnlp    | local non-local pointer | Sets the value of A to A+4*operand                                                                                                                             |
| 0x6X   | nfix     | negative prefix         | Sets the lower 4 bits of the operand register to the operand, then inverts the register, then shifts up by 4                                                   |
| 0x7X   | ldl      | load local              | Loads a value at stack pointer + 4*operand from memory. Pushes that value into the register stack.                                                             |
| 0x8X   | adc      | add constant            | Adds the contents of register A to the operand register                                                                                                        |
| 0x9X   | call     | call                    | Stores the contents of the register stack and the program counter into stack memory, and then jumps to a location of PC+operand                                |
| 0xAX   | cj       | conditional jump        | If the value of register A is 0, then jump to an offset set by the operand register                                                                            |
| 0xBX   | ajw      | adjust workspace        | Allocates (decrements) or unallocates (increments) the stack                                                                                                   |
| 0xCX   | eqc      | equals constant         | If A == Operand, push 1 into the register stack, otherwise push 0                                                                                              |
| 0xDX   | stl      | store local             | Write the value of register A into the address set by the stack pointer + 4*operand                                                                            |
| 0xEX   | stnl     | store non-local         | Write the value of register B into the address set by register A+4*operand                                                                                     |
| 0xFX   | opr      | indirect instruction    | Additional operations                                                                                                                                          |

I'm not going to go through every one of these, but I want to highlight a few examples. I'll start with a simple instruction, `ldc`, this pushes the operand register into the register stack. I start with a test case.

```rust
#[test]
fn load_constant(){
    let mut p = Proc::new(Mem::new());
    p.run(DirectOp::LDC, 5);
    assert!(p.peek(0) == 5); // 5 has been pushed into stack
    p.run(DirectOp::LDC, 10);
    assert!(p.peek(0) == 10); // 10 has been pushed into stack
    assert!(p.peek(1) == 5); // register B now has the previous value of A
}
```

The `peek` method is a debug method I added to the processor to check the value of the registers.

I can set up my processor with registers and and flags.

```rust
pub struct Proc{
    // Registers
    stack: Stack, // Register stack
    operand: i32, // operand register
    workspace: i32, // stack pointer
    // Flags
    error: bool,
    idle : bool, // can another process run
    // Shared ram
    mem: Mem
}
```

The load constant method is then:

```rust
fn ldc(&mut self, value: i32){
    // Set the lower 4 bits of the operand register to the operand
    self.operand = mask4(self.operand) + value;

    // push value onto register stack
    self.stack.push(self.operand);

    // Clear the operand register
    self.operand = 0;
}
```

This is not so bad. The `adc` instruction requires a few more steps. The direct way of writing an add instruction is this:

```rust
fn adc(&mut self, value: i32){

    self.operand = mask4(self.operand) + value;

    // Add register a to the operand register
    let result = self.stack.get(0) + self.operand;
    
    // Set register A to the result
    self.stack.set(0, result);

    // Clear operand register
    self.operand = 0;
}
```

This will function for most cases, however the overflow case has to be handled. For standard rust adds, the program will panic with an overflow error. This means my emulator will crash. What I want to happen is the processor continues unabated, it just sets its own internal error flag. So I have to use the rust methods `checked_add` and `wrapping_add`. `checked_add` returns `None` if the value overflows, and `wrapping_add` ignores overflows and just discards the carry bit when adding. The `adc` instruction now looks like this:

```rust
fn adc(&mut self, value: RTYPE){
    self.operand = mask4(self.operand) + value;

    let a = self.stack.get(0);

    // Add while checking for overflow
    if let Some(result) = a.checked_add(self.operand){
        // Add did not overflow
        self.stack.set(0, result);
    }
    else{
        // Wrap and add, and set error flag
        self.stack.set(0, a.wrapping_add(self.operand));
        self.error = true;
    }

    self.operand = 0;
}
```

This now handles normal addition, and error flags.

Finally I want to show the call instruction, because it's got a few steps. First it stores the register contents into the memory stack and then the program counter. Then it offsets the program counter.

```rust
fn call(&mut self, value: RTYPE){
    // Pushes C, B, A and instruction pointer to workspace
    self.mem.write(self.workspace, self.stack.get(2));
    self.mem.write(self.workspace - 4, self.stack.get(1));
    self.mem.write(self.workspace - 8, self.stack.get(0));
    self.mem.write(self.workspace - 12, self.pc);

    // update stack pointer
    self.workspace = self.workspace - 12;

    // Jumps to relative location
    self.operand = mask4(self.operand) + value;
    self.pc = self.pc + self.operand;
    self.operand = 0;
}
```

This operates on both the program counter and workspace pointer register. This is used to call subroutines, and the register state can be recalled from the location in stack memory. In assembly using this would look something like this.

```
# Main
ldc 4 # Set A to constant value
stl 0 # place contents of A into stack
call decrement # Save state (4 words) and jump to decrement subroutine

# Assembler symbolic expressions
parameter = 5
locals = 0

decrement: # Symbolic label
ajw -locals # Allocate space for local variables (none here)
ldl parameter # Load parameter that is 1 above the saved state

adc -1 # Subtract one from the loaded parameter
stl parameter # Save parameter back to memory

ajw locals # Deallocate space for local variables
ret # Indirect return function state
```

Because the saved state takes 4 words, the subroutine can use arguments starting at 5 below the local workspace pointer. I'm going to go through the indirect instructions later, but wanted to get started making things happen. I have tests for most of the basic instructions.
