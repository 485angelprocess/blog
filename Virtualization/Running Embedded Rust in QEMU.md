# Running Embedded Rust in QEMU

I am interested in expanding my ability to write more stable and flexible embedded programs. As part of that, I am improving my knowledge of virtualization options. For rust applications a somewhat established approach is to use QEMU virtualization. QEMU is a very flexible virtualization platform, which I have used before for faster development of a raspberry pi application.

I am using [The Embedded Rust Book](https://docs.rust-embedded.org/book/start/qemu.html) as a reference.

To start with a cortex-m project, it is good to start with the templates. A new project can be pulled from them using `cargo generate`

```powershell
  cargo generate --git https://github.com/rust-embedded/cortex-m-quickstart
```

The initial `main.rs` is

```rust
#![no_std]
#![no_main]

use panic_halt as _;

use cortex_m_rt::entry;

#[entry]
fn main() -> ! {
    loop {
        // your code goes here
    }
}
```

This does not linke the `std` crate, but to the subset `core` crate. The `main` function is set explicitly as the entry point.

This code is fine, but it doesn't do anything. To get started let's add a debug print function, and a exit indicator for the debugger.

```rust
#![no_main]
#![no_std]

use panic_halt as _;

use cortex_m_rt::entry;
use cortex_m_semihosting::{debug, hprintln};

#[entry]
fn main() -> ! {
    hprintln!("Hello, world!").unwrap();

    // exit QEMU
    // NOTE do not run this on hardware; it can corrupt OpenOCD state
    debug::exit(debug::EXIT_SUCCESS);

    loop {}
}
```

`hprintln!` is a macro which is printed using semihosting to QEMU's host. This would also display in a debug session.

To output the binary, the package just has to be built.

```rust
cargo build
```

Then qemu can be run using

```bash
$ qemu-system-arm \
  -cpu cortex-m3 \
  -machine lm3s6965evb \
  -nographic \
  -semihosting-config enable=on,target=native \
  -kernel target/thumbv7m-none-eabi/debug/examples/cortex_demo
```

This outputs the debug message directly to console, and exits gracefully.
