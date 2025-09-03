# Rust Forth Emulator

I've been working on a minimal forth editor. I just did a rewrite of it after going through the [makelisp](https://github.com/shinh/makelisp) project, and reading through Charles Moore's book on his design. I got some better perspective on how to organize the project, as well as some better ways to  write idiomatic rust.

The project can be found at [GitHub - 485angelprocess/bbforth: small forth interpreter implemented in rust](https://github.com/485angelprocess/bbforth). The project is functional, although with a very small dictionary.

I wanted to write out some of the logical units of the project, and go through some of the ideas. I will be giving a talk about why Forth is important next month, and want to think through some of the ideas around it.

## Reader/User input

One of the ideas I got from Moore is that one of the cores of Forth is that it is a user interface. This is also mentioned in sapf's readme. Well, of course any programming language probably is a user interface, but thinking through that Forth is a way for a human to interface with low level hardware is an important start point. Algol-like languages are their own type of user interfaces, which often have more levels of obscuring how the things you write are altering the state of the actual CPU. Anyway, the first start for a Forth interpreter is getting user input in a way which is both easy from a human perspective and from a computer perspective.

I used the `rustyline` crate to handle user input. It provides a easy way to get terminal-interface features like history. From the terminal, I get an input string, which I separate into tokens. Tokens are put into several types, the base ones being immediates (ints, floats and strings) and words. What helps Forth work well is a minimal number of types, and making the data types reusable in different contexts. Data types are organized using an enum:

```rust
enum ForthVal{
    Null,
    Int(i64),
    Float(i64),
    Str(String),
    Sym(String), // words
    List(Vec<ForthVal>)
}
```

## Interpreter

With each input I get a series of `ForthVal`, which can be interpreted in series. Each of these values can read or write from some work context, which needs a stack at minimum. The interpreter should provide some printable reply, I have this as a vector of `ForthVal` which is written to with each line, and then printed. Each `ForthVal` type is printable with a simple call.

```rust
struct WorkspaceContext{
    stack: Vec<ForthVal>,
    reply: Vec<ForthVal>
}
```

Any immediate types are placed on the stack, and then words can pop from the stack as needed. Eventually, I want to add features for argument and variable support to the context, but that should be fairly straightforward to add.

Next I need some basic words, from which more complex words can be compiled. I used a separate enum:

```rust
enum ForthRoutine{
    Prim(Box<dyn Fn(&mut WorkspaceContext) -> ForthVal),
    Compiled(Vec<ForthVal>)
}
```

Primitives are stored as a pointer to a trait which implements a function which modifies the workspace and returns data. Compiled programs are stored as a vector of ForthVals, which can be run as needed. 

One detail of implementation which I'm still unsure about, is the dictionary is stored as two containers. One maps Strings to an id, another maps an id to a `ForthRoutine`, this allows me to store words as an id, and still have a reference to a callable function. This is storing the function as an id in the dictionary. Going through another feature, I stored a pointer to the `ForthRoutine`. For primitives, this is a pointer to the function pointer. This approach will require additional management, as modifying user-defined words will have to keep the same references. This is doable, and essentially how the id system works. Regardless, primitives can be set at start up, and user defined words can  be defined during startup. My goal is to make this programming language flexible to the underlying target. The reader, interpreter and writer are manipulating data, and then words can be defined to do direct data manipulation or create code for other targets.

This is enough basic setup to do basic Forth operations. Defining words is a matter of connecting a string to a function pointer.

```rust
/// Insert new definition
pub fn insert(&mut self, s: &str, f: ForthFn) -> usize{
    let id = self.lookup.len();
    self.lookup.insert(s.to_string(), id);
    self.library.insert(id, 
        ForthRoutine::Prim(
            Box::new(f)
        )
    );
    id
}

/// Declare primitive functions
pub fn setup(&mut self){
    // Stack operations
    self.insert(
        "dup",
        dup
    );
    self.insert(
        "clear",
        |ws| {
            ws.stack.clear();
            ForthVal::Null
        }
    );

    self.insert_box("+", math::binary_op(|a, b|{b+a}));
}
```

This gives an idea of the setup. `dup` is a static function which duplicates the top of the stack. `clear` clears the stack. `+` adds the top two values on the static. I do some wrappers on arithmetic to handle multiple types. Now with I can do basic calculation:

```Forth
> 5 3 + .
8
```

Next I added a state machine to define words. I may change the syntax later, but for now `:` changes the state so that the next symbol is a new word. Following values are added to a vector, when the `;` symbol is reached, the word and compiled function is added to the dictionary.

```Forth
> : square dup * ;
> 5 square .
25
```

## Additional Features

### Lists

One of the features I wanted to add are lists, which I got from sapf and Joy. Here, a list is more than one word which can be operated on. A simple case is adding multiple values.

```Forth
> [1 2] 3 + .
[4 5]
```

This involves changing the reader module to parse `[` as a start of list, which then values are appending to. For now I use my arithmetic wrapper to specially handle the various cases of number vs lists. I think there are some more elegant ways to handle values, but I'll get there soon.

## Generators

Generators or lazy lists are an interesting feature of sapf, and somewhat required to do audio or video work. Unless everything is loaded as wavetables, using a bunch of memory, most synthesis just requires calculating the next sample as needed. They may come from common wavetables, but don't need to be stored as lists. My implementation runs generators as a structure/form:

```rust
pub struct GeneratorUnit{
    pub env: GenEnv,
    pub gen: Rc<dyn Generator>,
    pub trace: Vec<ForthVal>
}
```

I am trying to design with the idea that these will be running in separate threads. Each generator has a environment, which has the relevant stack values, and defined/named arguments. Right now a generator has to have one object which implements the trait:

```rust
pub trait Generator{
    fn num_args(&self) -> usize;
    fn next(&self, env: &GenEnv) -> ForthVal;
}
```

This defines the number of values consumed from the stack, and a function which gets the next value from the generator. The trace is my current method of doing additional functions on the generator. I can define a generator that gets the natural numbers:

```forth
> natural
[0 1 2 3 4 5 ...]
```

I can then do functions on the natural numbers:

```forth
> 5 natural + .
[5 6 7 8 9 10 ...]
```

I believe I can make generators a little more elegant and efficient, but this should be enough to do audio manipulation using a Forth-style language. Well, once I get the audio buffer working. I am seeing a way to use this which also uses my ideas on modular synthesis, where I can create units/forms/components which are sending audio and control signals. I want to experiment with some windowing interface ideas. I have been playing a bit with sapf, but want some more traditional multi channel editing that works better with how I work as a musician.
