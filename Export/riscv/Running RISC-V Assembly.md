# Running RISC-V Assembly

This is going to be a short introduction into getting assembly to run on my RISC-V emulation, going towards a RISC-V forth interpreter. My aim is to get basic assembly running, and be able to run a debugger on it well.

I started with looking at Ola's [post](https://theintobooks.wordpress.com/2019/12/28/hello-world-on-risc-v-with-qemu/) on a hello world in assembly. Their hello world looks like this:

```asm
.global _start

_start:

    lui t0, 0x10010

    andi t1, t1, 0
    addi t1, t1, 72
    sw t1, 0(t0)

    andi t1, t1, 0
    addi t1, t1, 101
    sw t1, 0(t0)

    andi t1, t1, 0
    addi t1, t1, 108
    sw t1, 0(t0)

    andi t1, t1, 0
    addi t1, t1, 108
    sw t1, 0(t0)

    andi t1, t1, 0
    addi t1, t1, 111
    sw t1, 0(t0)

    andi t1, t1, 0
    addi t1, t1, 10
    sw t1, 0(t0)

finish:
    beq t1, t1, finish
```

Each character load clears the `t0` register using `andi` (and immediate) and places the next character in using `addi` (add immediate). They load the UART address in as 0x10010 (check their post for explanation of that address), although I also have seen it looking through a small risc-v standard library. Each character is placed in the UART register, which will print it out on the QEMU prompt using the `sw` (store word) command.

The linker and makefile needed slight modifications. I simply changed the makefile for RISC-V 64:

```makefile
hello: hello.o link.lds
        riscv64-unknown-elf-ld -T link.lds -o hello hello.o

hello.o: hello.s
        riscv64-unknown-elf-as -o hello.o hello.s

clean:
        rm hello hello.o
```

For the linker, I have OpenSBI act as the bootloader. It jumps to address `0x8020_0000` once SBI finishes.

```c
OUTPUT_ARCH( "riscv" )

ENTRY( _start )

MEMORY
{
  ram   (wxa!ri) : ORIGIN = 0x80200000, LENGTH = 128M
}

PHDRS
{
  text PT_LOAD;
  data PT_LOAD;
  bss PT_LOAD;
}

SECTIONS
{
  .text : {
    PROVIDE(_text_start = .);
    *(.text.init) *(.text .text.*)
    PROVIDE(_text_end = .);
  } >ram AT>ram :text

  .rodata : {
    PROVIDE(_rodata_start = .);
    *(.rodata .rodata.*)
    PROVIDE(_rodata_end = .);
  } >ram AT>ram :text

  .data : {
    . = ALIGN(4096);
    PROVIDE(_data_start = .);
    *(.sdata .sdata.*) *(.data .data.*)
    PROVIDE(_data_end = .);
  } >ram AT>ram :data

  .bss :{
    PROVIDE(_bss_start = .);
    *(.sbss .sbss.*) *(.bss .bss.*)
    PROVIDE(_bss_end = .);
  } >ram AT>ram :bss

  PROVIDE(_memory_start = ORIGIN(ram));
  PROVIDE(_memory_end = ORIGIN(ram) + LENGTH(ram));
}
```

Now I can assemble code using `make`, and run in qemu using the command:

```bash
$ qemu-system-riscv64 -machine sifive_u -nographic -kernel hello
```

This prints the SBI preamble and then prints "Hello". Great!
