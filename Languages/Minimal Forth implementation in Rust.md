# Minimal Forth implementation in Rust

I have been looking at forth a bit and wanted to start putting together some implementations of it. The language is structured so that a minimal implementation is very quick to do. My overall goal is to make a non-portable RISC-V implementation, with a built-in editor, but for now I am doing a portable version with no editor. I used [zforth](https://github.com/zevv/zForth) as a main reference, also looking at gforth and colorForth as references.

A core to forth is an extensible dictionary of words, so I want to start setting up a rust struct to handle the state of the program, with the ability to run primitives, and do stack operations. To get things up and running I wanted to try to keep things as simple as possible. The data stack is a `Vec`. I map the dictionary words using a HashMap, this is close to the zforth implementation, but I'm trying to use some more idiomatic rust as well. The first pass at the core struct is:

```rust
type  BaseType = i32;

pub struct Context{
    data_stack: Vec<BaseType>,
    dict: HashMap<String, usize>,
    prim: HashMap<usize, PRIM>
}
```

Pop and push operate on the stack:

```rust
fn pop(&mut self) -> BaseType{
    self.data_stack.pop().unwrap()
}

fn push(&mut self, v: BaseType){
    self.data_stack.push();
}
```

For now I'm populating the primitive dictionary at runtime. Literals and syscalls have specific rules for parsing, so I'm treating somewhat separately. This sets up a map from  an op number/address to a enum for the primitives. Later, I will add functionality for op numbers above the primitives for custom words. For now I just want to see a basic program running, so I'm only doing a few words:

```rust
pub fn setup(&mut self){
    self.lit = self.add_implicit(PRIM::LIT);
    self.sys = self.add_implicit(PRIM::SYS);

    self.add_prim("dup", PRIM::DUP);
    self.add_prim("*", PRIM::MUL);
}
```

My parser is starting as this. I am going to tidy this up later, but it gets the op number and an optional argument. I see reasons to treat the argument as an `Option` or a mutable reference, which I'll decide on later.

```rust
fn get_op(&mut self, msg: &String) -> (usize, i32){

    if msg.starts_with("."){
        // System call/special functions
        if let Some(result) = msg.bytes().nth(1){
            // system call with specifier
            // These aren't implemented yet,
            // But ." is literal string
            // and .s displays the entire stack as examples
            return (self.sys, result.try_into().unwrap());
        }
        else{
            // system call no argument
            return (self.sys, 0);
        }
    }
    if self.dict.contains_key(msg){
        // in dictionary of words
        return (self.dict[msg], 0);
    }
    // assume it is literal
    (self.lit, msg.parse().unwrap())
}
```

With the op number I can direct my interpreter to run a primitive or a custom word.

```rust
pub fn parse(&mut self, msg: &String){

    // get address of word with argument
    let (op, v) = self.get_op(msg);

    if self.prim.contains_key(&op){
        self.do_prim(self.prim[&op], v);
    }
    else{
        todo!("Custom words not implemented yet.");
    }
}
```

Primitives are treated as a switch. Each primitive is intended to be very simple to implement.

```rust
pub fn do_prim(&mut self, p: PRIM, v: BaseType){
    match p{
        PRIM::LIT => self.push(v),
        PRIM::SYS => self.sys_call(v),
        PRIM::DUP => {
            // Duplicate the top of the stack
            let v = self.pop();
            self.push(v);
            self.push(v);
        },
        PRIM::MUL => {
            // Multiply the top 2 numbers on the stack
            let a = self.pop();
            let b = self.pop();
            self.push(a * b);
        },
        _ => todo!("Not implemented {:?}", p)
    }
}
```

With this setup, I can get my first extremely scoped program up. The program is:

```forth
5 dup * .
```

This puts 5 on the stack, duplicates it, and the multiples, giving the square of 5. The `.` word pops the stack and prints the top value.

The main function for my demo looks like:

```rust
fn main() {
    let mut ctx = Context::new();

    ctx.setup();

    let program = "5 dup * .";

    // go through program
    for p in program.split(" "){

        //println!("{}, {}", p.to_string(), p.len());
        ctx.parse(&p.to_string());
    }
}
```

This runs, printing out 25.

## Testing

Next I started going through and adding tests for the basic functionality I was looking for. I am going to add some more coverage later, but wanted to highlight some of the basic tests. `dup` is a core stack operation for forth. To start, it should panic when there is nothing in the stack:

```rust
#[test]
#[should_panic]
fn dup_requires_argument(){
    let mut ctx = Context::new();
    run_program("dup .", &mut ctx);
}
```

Next it should function, by duplicating the top of the stack:

```rust
#[test]
fn dup(){
    let mut ctx = Context::new();
    run_program("5 dup . .", &mut ctx);
    assert!(ctx.sys_buffer.pop().unwrap() == 5);
    assert!(ctx.sys_buffer.pop().unwrap() == 5);
}
```

For now I just added an object to hold anything that gets sent to the `.` command. I am not entirely happy with it. Ideally I'll think I'll have system calls handled by a separate struct, so that the core can be more test-friendly. This is a consequence of working off a C program which was intended to small and complete, without any testing focus.

I am adding several of these types of tests for other primitives. The other major functionality is working with new words. First I wanted to cover some of the basic error cases.

```rust
#[test]
#[should_panic]
fn undefined_word(){
    let mut ctx = Context::new();
    run_program("newword", &mut ctx);
}
```

Just throwing a new word should panic. Defining a new word with no body should also panic:

```rust
#[test]
#[should_panic]
fn new_word_no_body(){
    let mut ctx = Context::new();
    
    run_program(": square ;", &mut ctx);
}
```

Next I used the zforth example definition as a basic test:

```rust
#[test]
fn new_word(){
    let mut ctx = Context::new();
    
    // new word
    run_program(": square dup * ;", &mut ctx);
    
    // run program with new word
    run_program("5 square .", &mut ctx);
    
    assert!(ctx.sys_buffer.pop().unwrap() == 25);
}
```

## Basic demo

I added most of the base words and can add new words. I put a quick egui editor, and threw some syntax highlighting on. The project can be found here: [GitHub - 485angelprocess/bbforth: small forth interpreter implemented in rust](https://github.com/485angelprocess/bbforth)

![forth editor](../Resources/forth_editor.png)

Overall I'm happy with progress, it's really nice thinking about forth works internally, and the decisions that make it simple and flexible to implement from a language perspective. Next I want to finish adding primitives, which will mean doing some memory access and return stack operations. I also want to improve the editor. I might make it more of a terminal prompt, but at least want to make it easy to read and self document well.
