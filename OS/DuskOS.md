# DuskOS

Dusk OS is a minimal Forth-based OS which is designed for minimal and undefined hardware. It is pitched as an early end of civilization project, although I don't know how much computing I'll be worrying about. It is interesting to me as a minimal OS project which is designed to run on minimal hardware. I wanted to look through the tour which can be found here: https://duskos.org/.

I built Dusk for Risc-V by cloing the git:

```bash
$ git clone https://git.sr.ht/\~vdupras/duskos
```

then building the Risc-V deployment:

```bash
$ cd duskos/deploy/riscv
$ make
$ make emul
```

I have previously setup Risc-V toolchains and qemu ([Risc V Emulation](https://annabelleadelai.de/riscv/Risc%20V%20Emulation.html)) so this was pretty painless. I'm unsure if the deployment requires the gcc toolchain, but I'm pretty sure it doesn't.

Anyway, running this boots into DuskOS giving the prompt:

```
Dusk OS
134KB used 15MB free ok
```

Dusk works by providing free memory, I can check my current address:

```
here .x
800a65dc ok
```

I can see that Dusk was bootstrapped into address 0x8000_0000, which is consistent with my previous work with bare-metal Risc-V on this machine.

I can write hex to my free memory:

```
$cafebabe here !
 ok
here @ .x
cafebabe ok
here dump
:800a65dc beba feca 0000 0000 0000 0000 0000 0000 ................
:800a65ec 0000 0000 0000 0000 0000 0000 0000 0000 ................
:800a65fc 0000 0000 0000 0000 0000 0000 0000 0000 ................
:800a660c 0000 0000 0000 0000 0000 0000 0000 0000 ................
:800a661c 0000 0000 0000 0000 0000 0000 0000 0000 ................
:800a662c 0000 0000 0000 0000 0000 0000 0000 0000 ................
:800a663c 0000 0000 0000 0000 0000 0000 0000 0000 ................
:800a664c 0000 0000 0000 0000 0000 0000 0000 0000 ................
 ok
```

Dusk mostly supports C. I can load the C word with `needs comp/c`. and then compile a word using C:

```
:c int add54(int n){return n+54;}
5 add54 .
59 ok
```

Errors in the C code are handled  with just an immediate error message:

```
:c int add54(int n){return n+54}
File: (none)
Line no: 1 token: }
wrong character ok
```

This is from missing the semicolon. Dusk features builtin assemblers. I haven't stumbled onto the word to get documentation yet, but I can load the assembler/dissassembler: `needs asm/riscv` and `needs asm/riscvd`.

Disassembling my add function:

```
' add54 dis
800ced6c addi   xRSP, xRSP, -4                    ffc10113
800ced70 sw     xRA, xRSP[0]                      00112023
800ced74 addi   xPSP, xPSP, -4                    ffc18193
800ced78 sw     xW, xPSP[0]                       0041a023
800ced7c lw     xW, xPSP[0]                       0001a203
800ced80 addi   x11, xZERO, 54 -> $00000036       03600593
800ced84 add    xW, xW, x11                       00b20233
800ced88 mv     xAcmp, xW                         00020e13
800ced8c mv     xBcmp, xZERO                      00000e93
800ced90 mv     x11, xPSP                         00018593
800ced94 addi   x11, x11, 4                       00458593
800ced98 mv     xAcmp, x11                        00058e13
800ced9c mv     xBcmp, xZERO                      00000e93
800ceda0 mv     xPSP, x11                         00058193
800ceda4 lw     xRA, xRSP[0]                      00012083
800ceda8 addi   xRSP, xRSP, 4                     00410113
 ok
```

It loads the top value of the stack into `xW`, loads 54 into `x11` and then pushes the result onto the stack.

I can also use the assembler to define new words:

```
code add53 53 i) +, exit,
 ok
' add53 dis
800d27b4 addi   x11, xZERO, 53 -> $00000035       03500593
800d27b8 add    xW, xW, x11                       00b20233
800d27bc mv     xAcmp, xW                         00020e13
800d27c0 mv     xBcmp, xZERO                      00000e93
800d27c4 ret                                      00008067
800d27c8 ???                                      00000000
800d27cc ???                                      00000000
800d27d0 ???                                      00000000
```

At this point I have to figure some graphics which are not running on my qemu setup. They seem interesting to play with. I some further ideas about run-time compiling which I want to play with implementing.
