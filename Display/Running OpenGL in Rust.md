# Running OpenGL in Rust - Creating a Window

I have an ongoing video synthesizer project. As part of it I want to make an abstraction layer to OpenGL which can provide interfaces to play with user facing interfaces. The goal is to play around with hardware control, scripting, and guis to get a device that is usable for live video synthesis at shows.

I have used hardware synthesizers like LZX's vidiot, which are nice but expensive and in low supply. I also use software like Resolume Arena and TouchDesigner. Both are ok, but lack the a level of depth and don't have the same user feedback.

Anyway, to start on the software side I need some wrapper around OpenGL that can provide a flexible interface. 

## Fermium

There are many ways to get a window open with an OpenGL context, right now I am using [fermium](https://docs.rs/fermium/latest/fermium/). Fermium itself is a wrapper of the SDL 2 C Library which provides cross-platform support for low-level window commands. Including OpenGL! So after adding fermium to a rust project (`cargo add fermium`), I can intialize a video window.

These are the imports for this setup.

```rust
use fermium::{error::*, events::*, video::*, *};
use fermium::hints::*;
use hints::{SDL_SetHint, SDL_HINT_RENDER_VSYNC};
```

Then I initialize the window, and set the OpenGL hints. Because this is all C bindings, it has to be in an unsafe bracket. All of the OpenGL commands are going to be unsafe, as we're working with binded APIs.

```rust
unsafe{
    SDL_Init(SDL_INIT_VIDEO);
    assert_eq!(0, SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3));
    assert_eq!(0, SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION, 3));
    assert_eq!(0, SDL_GL_SetAttribute(
            SDL_GL_CONTEXT_PROFILE_MASK,
            SDL_GL_CONTEXT_PROFILE_CORE.0 as _
        )
}
```

This sets the OpenGL version to 3.3. The asserts make sure the function returns correctly. Trying to set the attributes to an invalid value or if there are OS features missing will cause the program to crash.

Here I can set the vsync flag. This flag forces the window to refresh at the same rate as the display driver. Usually this fixes the frame rate at 60Hz (sometimes 72Hz or 144Hz). Without vsync the frame rate can be arbitarily high, which might be helpful for somethings, but also will mean the program is doing extra work that won't be displayed.

```rust
SDL_SetHint(SDL_HINT_RENDER_VSYNC.as_ptr() as *const i8, "1".as_ptr() as *const i8);
```

This function also hints at the type of casting I have to do work with the older-style C bindings.

Now I can create the actual window. This is opening as a windowed display, eventually I will make this dynamic to run fullscreen or on a specified display.

```rust
let win = SDL_CreateWindow(
            b"fermium demo\0".as_ptr().cast(),
            50,
            50,
            800,
            600,
            (SDL_WINDOW_SHOWN | SDL_WINDOW_OPENGL).0 as _,
        );
```

Then I can load the OpenGL bindings. This process gives us the available functions for the version we are using.

```rust
let ctx = SDL_GL_CreateContext(win);
let fns = GlFns::load_from(
            &|char_ptr| SDL_GL_GetProcAddress(c_char_ptr.cast()))
            .unwrap()
```

The window process loop checks for events and refreshes the display.

```rust
unsafe{
    let mut event = SDL_Event::default();
    
    loop {

        if SDL_WaitEventTimeout(&mut event, 10) == 1{
            // Window events
            match event.type_{
            SDL_QUIT => {
            println!("SDL_QUIT");
            return;
            },
            SDL_KEYDOWN => {
            println!("SDL_KEYDOWN {:?}", event.key);
            },
            _ => () // other event, game pad stuff etc 
            }
        }


        {
            // Run gl code
        }

        // Swap buffers
        SDL_GL_SwapWindow(self.win);
    }
}
```

## gl33

[gl33](https://docs.rs/gl33/latest/gl33/) is a crate which provides binding for the OpenGL 3.3 core. Some fuctionality is missing that was added in newer versions of OpenGL, but it works well enough.

For a simple example I can set the background color. I can set the color that the framebuffer is cleared to with:

```rust
unsafe{
    gl.ClearColor(r, g, b);
}
```

`gl` is the function bindings, and `r, g, b` are f32 floats ranging from 0.0 to 1.0. Then at the beginning of a frame I can clear the screen to the set color using:

```rust
unsafe{
    gl.Clear(GL_COLOR_BUFFER_BIT)
}
```

`GL_COLOR_BUFFER_BIT` is provided in `gl33::gl_enumerations::*` . With the window open and OpenGL appering to run ok, the next step is loading shaders and displaying 3D objects. The infrastructure for loading and compiling shaders is a little involved, so I'll leave that for another post.
