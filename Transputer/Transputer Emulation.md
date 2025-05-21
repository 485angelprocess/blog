# Transputer Emulation

One of the architectures I'm interested in are transputers. They are an alternative and dead architecture from the 90s which use parallel mcus to run programs. Each MCU has a serial connection to adjacent MCUs.

![transputer_0.jpg](C:\Users\magen\Documents\Blog\Resources\transputer_0.jpg)

![transputer_2.png](C:\Users\magen\Documents\Blog\Resources\transputer_2.png)

I am interested in what can be learned from an alternative parallel architecture, how the language interacts with a different underlying hardware and the potential for modular computing.

Some websites I looked at, there's an overwhelming from a wide range of perspectives, so I haven't looked too closely at anything yet.

- https://www.transputer.net - variety of transputer documentation

- https://sites.google.com/site/transputeremulator/Home?authuser=0 - transputer emulator

- [Porting Small-C to transputer and developing my operating system](https://nanochess.org/bootstrapping_c_os_transputer.html) - transputer os

![transputer_1.jpg](C:\Users\magen\Documents\Blog\Resources\transputer_1.jpg)

To start with this investigation I want to try to get an emulator up and running. I both got jserver, which is an emulator which can run the T414/T400/T425/T800/T805 type transputers. I also got Oscar Toledo's basic emulator up. Oscar's installation instructions are here: [GitHub - nanochess/transputer: Transputer T805 emulator, assembler, Pascal compiler, operating system, and K&amp;R C compiler.](https://github.com/nanochess/transputer) The setup for this was very painless on my linux machine, fora revived project from the 90s, it went up immediately. It reminds me of being surprised at how easy it was to work on a DOS CNC machine. I want to return to looking at this, but I want to look a little at the Occam programming language, which is featured in the jserver emulator.

![transputer_emulator.png](C:\Users\magen\Documents\Blog\Resources\transputer_emulator.png)

For jserver, I followed the steps here: https://sites.google.com/site/transputeremulator/Home/jserver/installation-instructions?authuser=0. Getting hello world to work was fast. Then I set up the Occam toolset.

Occam is designed for transputers, so it also exposes some of the interesting points of them. Let's look at the `hello.occ` program.

```occam
#INCLUDE "hostio.inc" --  -- contains SP protocol
PROC hello (CHAN OF SP fs, ts )
  #USE "hostio.lib"
  SEQ
    so.write.string.nl    (fs, ts, "Hello world...")
    so.exit           (fs, ts, sps.success)
:
```

Looking at the [Introduction to the Programming Language Occam](https://www.eg.bucknell.edu/~cs366/occam.pdf), I can breakthis down a little bit. 

`#INCLUDE "hostio.inc"` gives us the serial protocols we need, especially those which can write to the output terminal.

A process (`PROC` ) is the basic element, processes can be, but aren't necessarily concurrent. Processes can only share date through a channel. This means there is no shared variables. 

![Screenshot 2025-03-31 112448.png](C:\Users\magen\Documents\Blog\Resources\Screenshot%202025-03-31%20112448.png)

The `CHAN` type defines a channel. In the main body of the process we use the `hostio.lib` to write to the serial channel.

Now I slightly more complicated program which computes the square roots.

While getting this running, I edited some of the scripts, essentially just making them use arguments to make building better. The make stage is from the mk.bat script, which is run using `mk.bat hello` or `mk.bat root`

```batch
imakef %1.btl /o %1.mak
```

This runs make to create btl and mak files. I also need the emulator description, and entry point defined. This is from the example hello file.

```
-- hardware description, omitting host connection

VAL k IS 1024 :
VAL m IS k * k :

NODE test.bed.p :  -- declare processor
ARC hostlink :
NETWORK example
  DO
    SET test.bed.p (type, memsize := "T414", 2 * m )
    CONNECT test.bed.p[link][0] TO HOST WITH hostlink
    
:

-- mapping
NODE application:
MAPPING
  DO
    MAP application ONTO test.bed.p
:

-- software description
#INCLUDE "hostio.inc"
#USE "hello.cah"
CONFIG
  CHAN OF SP fs, ts :
  PLACE fs, ts ON hostlink :
  PLACED PAR
    PROCESSOR application
      hello ( fs, ts )
:

```

Then the program is built using `build.bat`

```batch
REM Borland make
REM omake -f%1.mak
REM
REM WATCOM wmake
REM wmake -f %1.mak -ms
REM
REM Microsoft nmake
nmake -f %1.
```

This is just running `nmake` , everything else is a comment for older oses.

Some notes on getting occam to compile.

- All keywords are capitalized

- It is very whitespace-sensitive. Indentation seeems to be two spaces. Files need to end on a new-line.

This is a basic sequential program to calculate the square root.

```
#INCLUDE "hostio.inc" -- contains SP protocol
PROC msqrt (CHAN OF SP keyboard, screen)
  #USE "hostio.lib" -- IO library
  BYTE key,result:
  REAL32 A:
  SEQ
    so.write.string.nl(keyboard, screen, "Value Square Root")
    SEQ i = 1 FOR 10
      SEQ
        so.write.string(keyboard, screen, "i = ")
        so.write.int(keyboard, screen, i, 2)
        A := REAL32 ROUND i
        so.write.real32(keyboard, screen, SQRT(A), 4, 6)
        so.write.nl(keyboard, screen)
    so.exit(keyboard, screen, sps.success)
:

```

Running:

```
Booting root transputer...ok
Value Square Root
i =  1    1.000000
i =  2    1.414214
i =  3    1.732051
i =  4    2.000000
i =  5    2.236068
i =  6    2.449490
i =  7    2.645751
i =  8    2.828427
i =  9    3.000000
i = 10    3.162278
```

Not quite exploiting parallelism yet, but some progress and work into it.
