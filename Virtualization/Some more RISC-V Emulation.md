# Some more RISC-V Emulation

I am still looking into understanding risc-v a bit more, this will be a little scattershot. First I was looking at understanding [noteed/riscv-hello](https://github.com/noteed/riscv-hello-c/tree/master). This uses just a few features of the [libfemto](https://github.com/michaeljclark/riscv-probe/tree/master/libfemto/std) So this starts by creating a minimal UART driver. The header file just defines one function, and runs in C.

This is `stdio.h`

```cpp
#pragma once

#ifdef __cplusplus
extern "C" {
#endif

int putchar(int);

#ifdef __cplusplus
}
#endif
```

Then they build the the driver by setting the address of UART in memory (in this case `0x10013000`). If waits for the uart register to be available. and then writes the char to the register location.

```c
// See LICENSE for license details.

#include <stdio.h>

enum {
    /* UART Registers */
    UART_REG_TXFIFO = 0,
};

static volatile int *uart = (int *)(void *)0x10013000;

int putchar(int ch)
{
    while (uart[UART_REG_TXFIFO] < 0);
    return uart[UART_REG_TXFIFO] = ch & 0xff;
}
```

Next there is a small wrapper function, which actually calls main.

```c
void main();

void libfemto_start_main(){
    main();
}
```

The actual main function creates a char array and pushes it out one character at a time, and then loops forever.

```c
#include <stdio.h>

void main(){
    const char *s = "Hello\n";
    while (*s) putchar(*s++);
    while(1);
}
```

There are two more files. One is the C runtime file which jumps to the main of the actual program. The default one that gcc pulls is not correct so we have to override it.

```c
# See LICENSE for license details.

.section .text.init,"ax",@progbits
.globl _start

_start:
    j       main
```

Then define the memory layout of the program. 

```c
MEMORY
{
  ram   (wxa!ri) : ORIGIN = 0x80000000, LENGTH = 128M
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

I found a good breakdown of the linker file at [Mastering the GNU linker script - AllThingsEmbedded](https://allthingsembedded.com/post/2020-04-11-mastering-the-gnu-linker-script/).The `MEMORY` section sets the ram origin to the boot location. Then it sets the Program Headers(`PHDRS`), these descrive how the program should be loaded into memory. Some more info on that section [here](https://ftp.gnu.org/old-gnu/Manuals/ld-2.9.1/html_node/ld_23.html). Then it describes the sections of memory in `SECTION` . There are 4 sections used here.

- `.text` section that contains the code. This is loaded at the text program directory location.

- `.rodata` contains read only data. This is overlapping the `.text` section, the code shouldn't be modifying itself.

- `.data` contains initilalized global and static variables, which in this case should just be the UART register address.

- `.bss` these are unitialized global and static variables. In most cases these will be initialized to zero, but not always in embedded systems.
