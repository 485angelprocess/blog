# Risc V Emulation

I'm interested in experimenting with some RISC-V assembly. To that end, I wanted to start making a workflow to run RISC-V in QEMU. I found two helpful blog posts [RISC-V from scratch 2: Hardware layouts, linker scripts, and C runtimes](https://twilco.github.io/riscv-from-scratch/2019/04/27/riscv-from-scratch-2.html#finding-our-stack), and [Hello, RISC-V and QEMU](https://mth.st/blog/riscv-qemu/) to help guide me.

To start I got distracted making my terminal cuter with https://ohmyz.sh/ and messing around with fonts. Then I started setting up my ubuntu machine. Running and debugging RISC-V requires QEMU and GDB server. The QEMU package is installed with

```bash
# apt-get install qemu-system-riscv64
```

This can run a few different machines found with `$ qemu-system-riscv64 -machine help`. Then I installed compiler tools using the [riscv-gnu-toolchain](https://github.com/riscv-collab/riscv-gnu-toolchain). To summarize, clone the repository, install dependencies, configure and make.

Next I wanted a minimal working program to check that things we're running. After my first hello world didn't produce anything, I looked at [this example](https://github.com/noteed/riscv-hello-c), which is intended to make assembly easier to build off. With no immediate luck I looked at this one [riscv-hello-asm](https://github.com/noteed/riscv-hello-asm/tree/main). A few posts mentioned that the stack memory location is not always linked correctly. So when I ran a qemu instance such as:

```bash
$ qemu-system-riscv64 -nographic -machine sifive_u -bios none -kernel hello
```

The program I was trying to run was placed at some irrelevant location, and there was nothing for QEMU to work on.

To find out where the device I'm running on places the stack, I dump the devicetree blob from QEMU.

```bash
$ qemu-system-riscv64 -machine sifive_u -machine dumpdtb=riscv-sifive.dtb
```

This creates a dtb file. This isn't immediately parseable, so I need use `dtc` (installed on ubuntu using `apt-get install device-tree-compiler`) There's a lot of information in the file, but since I'm interested in the location of the memory I can find using `grep` (+ 3 lines).

```bash
$ grep memory riscv-sifive.dts -A 3
memory@80000000 {
   device_type = "memory";
   reg = <0x00 0x80000000 0x00 0x8000000>;
};
```

So our memory is at 0x80000000. In the riscv asm example the linker handles this.

In `hello.ld`:

```c
OUTPUT_ARCH( "riscv" )
OUTPUT_FORMAT("elf64-littleriscv")
ENTRY( _start )
SECTIONS
{
  /* text: test code section */
  . = 0x80000000;
  .text : { *(.text) }
  /* data: Initialized data segment */
  .gnu_build_id : { *(.note.gnu.build-id) }
  .data : { *(.data) }
  .rodata : { *(.rodata) }
  .sdata : { *(.sdata) }
  .debug : { *(.debug) }
  . += 0x8000;
  stack_top = .;

  /* End of uninitalized data segment */
  _end = .;
}
```

This is still a little mysterious to me (having not done any real C in about 10 years). But it does work on QEMU.

The actual assembly is from [riscv-hello-asm]([GitHub - noteed/riscv-hello-asm: Bare metal RISC-V assembly hello world](https://github.com/noteed/riscv-hello-asm/tree/main)).

```c
.align 2
.include "cfg.inc"
.equ UART_REG_TXFIFO,   0

.section .text
.globl _start

_start:
        csrr  t0, mhartid             # read hardware thread id (`hart` stands for `hardware thread`)
        bnez  t0, halt                # run only on the first hardware thread (hartid == 0), halt all the other threads

        la    sp, stack_top           # setup stack pointer

        la    a0, msg                 # load address of `msg` to a0 argument register
        jal   puts                    # jump to `puts` subroutine, return address is stored in ra regster

halt:   j     halt                    # enter the infinite loop

puts:                                 # `puts` subroutine writes null-terminated string to UART (serial communication port)
                                      # input: a0 register specifies the starting address of a null-terminated string
                                      # clobbers: t0, t1, t2 temporary registers

        li    t0, UART_BASE           # t0 = UART_BASE
1:      lbu   t1, (a0)                # t1 = load unsigned byte from memory address specified by a0 register
        beqz  t1, 3f                  # break the loop, if loaded byte was null

                                      # wait until UART is ready
2:      lw    t2, UART_REG_TXFIFO(t0) # t2 = uart[UART_REG_TXFIFO]
        bltz  t2, 2b                  # t2 becomes positive once UART is ready for transmission
        sw    t1, UART_REG_TXFIFO(t0) # send byte, uart[UART_REG_TXFIFO] = t1

        addi  a0, a0, 1               # increment a0 address by 1 byte
        j     1b

3:      ret

.section .rodata
msg:
     .string "Hello.\n"
```

Linking:

```bash
$ riscv64-unknown-linux-gnu-gcc -march=rv64g -mabi=lp64 -static -mcmodel=medany \
  -fvisibility=hidden -nostdlib -nostartfiles -Tsifive_u/hello.ld -Isifive_u \
  hello.s -o hello
```

And running:

```bash
$ qemu-system-riscv64 -nographic -machine sifive_u -bios none -kernel hello
hello
```

Yay!  It's something! I'm going to come back to this in a bit, but at least I can get a little progress.
