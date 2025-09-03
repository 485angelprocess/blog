# Starting with Forth

I somehow gotten into reading about Forth, a programming language first developed by Charles Moore in 1970. There are quite a lot variations of Forth which have been developed. Part of Forth was an editing environment built specifically around it. At some point Moore was also interested in making it a standalone OS or OS-less program and environment. I checked out two versions, Gforth, and SwiftForth. I am interested in looking into ColorForth, which is Moore's ongoing project, although the implementations for that are hardware specific. Gforth is an open source implementation, while SwiftForth is a more profressional proprietary implementation.

The installation instructions for Gforth are here: https://gforth.org/. Using the tarball mirror:

```bash
$ wget https://www.complang.tuwien.ac.at/forth/gforth/Snapshots/current/gforth.tar.xz
$ tar xvfJ gforth.tar.xz
$ cd gforth-*
$ ./install-deps.sh
$ ./configure
$ make
$ sudo make install
```

Starting with a simple hello world. First I can invoke the Gforth environment with `gforth`. Then hello world is `." hello, world"`, Forth is whitespace sensitive, so the leading space of hello is required. Note that `."` is a word, which waits for the end of the word with a special delimiter `"`, which is why `."hello world"` fails, because the interpreter tries to read `."hello` as the first word.

Next I can start working with the stack. One of the things that interested me in Forth is it designed much less abstractly with regards to how computers process information than later languages. It's nice to see some snapshots of how that abstraction has developed over time within programming language methodology. Any number that is typed is put on the stack, and the stack is displayed with `.s` or the the top of the stack with `.` . Words consume their stack, which is much closer to what is happening at the assembly level, where arguments are placed in the arguments proceeding the call of a routine or function.

Forth has arithmetic words, `+`, `-`, `*`, `/` and `mod`. They act on the top two stack items. `2 2 +` will result in 4 being at the top of the stack. `/mod` produced two result, the result and the remainder of the integer division. There is also the `negate` word which flips the sign of the top of the stack.

Stack manipulation is done with several words. `drop` removes the top of the stack. `dup` duplicates the top. `over` duplicates the bottom of the stack into the top.  `swap` switches the first and second values in the stack, and `rot` rotates the top three stack matrices.

Colon definitions can be used to create procedures and functions.

```forth
: squared ( n -- n^2 )
    dup * ;
```

`( n -- n^2 )` is a comment. This definition creates a new word which will act on the stack. There is some additional discussion of definitions versus macros on this page [Colon Definitions (Gforth Manual)](https://net2o.de/gforth/Colon-Definitions.html). A defined word can be used as any other word. The do

That's some of the basics, it was pretty easy to get running, next I want to look into the debugging options. Initially I'm getting slightly confused on how to use them, so it'll be another day.
