# LED Control

Here I am trying to go through and write some things I've learned working in displays for several years. In this process, I'm also trying to refine my thoughts about what works and doesn't for differently scoped projects.

## Addressable LEDs

Addressable LEDs are common in many displays and light sculptures, they enable a fast way to create dynamic effects, and to configure color, brightness and animations after being installed. There are few common configurations that are used. They are differentiated by a few features.

- Voltage - Most LED componenents run at 5V or 12V. 5V LED components are best for smaller arrangements, and have the advantage of having the same voltage as common low-cost microcontrollers. (i.e. Arduinos). 12V LED components are best for larger arrangements. The total amperage will be less for the same output, which means a more reasonable power supply (and more reliable power supply in most cases). 12V components will also show less warming for long runs.

- Separate clock - Some LED addressing standards work with a fixed frequency, which is encoded into the data line (WS8212 for example). Others have a separate clock line which can work in a range of frequencies. Fixed frequency devices have a limited refresh rate and can exhibit glitches from long data cables, long led runs and grounding issues. A separate clock line allows for a faster refresh in most cases, and increases signal integrity. A separate clock does however mean one more line of failure, in a quick build it's best to have as few wires as possible.

- Integrated IC - Most addressable have an integrated IC within the LED package. This is usually a positive, the LEDs are smaller and the points of failure are reduced. There are cases for separate ICs, such as custom builds with a non standard LED layout, or higher amperage LEDs.

- Color channels - LEDs generally come as RGB, or RGBW. For a display that is mainly white using the W channel will generally be brighter and more efficient. Using just RGB to make white will have less color integrity and will show as separate colors at close distances and sharp angles. RGBWW or WW, which include a cold and warm white are occasionally found, but less so for addressable LEDs.

In practice, I have mainly used neopixels (WS2812B for RGB and SK6812B for RGBW). These are a family of fairly standardized addressable devices, all running at 5V and with a single data line. Each LED is addressed based on the number of LEDs they are from the controller. For larger and brighter projects I use DotStar (SK9822) which is 12V controller, with separate clock and data. DotStar also has much faster PWM rate which reduces strobing effects and issues with cameras.

Both DotStar and especially Neopixel have robust libraries and examples. Meaning that  getting a display up, changing it for clients and repair are faster and simpler. For fast turnaround projects that are up for a few months, this is a worthwhile compromise than other solutions, that may feature brighter LEDs (the client always wants it to be brighter), better power efficiency or other features.

## Controlling addressable LEDs

### Arduinos and Similar MCUs

For short-term displays, I generally opt for controlling animations with simple microcontroller boards. They are simple, well-documented and fast to get running. If they fail once during the run of a installation, it's only a few dollars to replace. Generally I prefer an adafruit metro mini for very small components, and for many cases this is the fastest way to get a display up. For larger designs, the Adafruit RP2040 Scorpio board has ample memory for storing the Neopixel buffers and shares many of the sample libraries.

The Adafruit Neopixel library is simple to use, and there are several wrappers which make it easy to map matrices, multiple strips and more. I usually end up just using the base library unless I'm using the matrix, but it's good to have options. Adafruit has instructions for installing [here.](https://learn.adafruit.com/adafruit-neopixel-uberguide/arduino-library-installation) While adafruit and similar groups have been pushing circuitpython, python just generally doesn't have the precision or robustness to have me confident of pushing a circuitpython project for even a month-long display.

Adafruit provides a good number of examples for using Neopixels. Here is a basic boilerplace for a neopixel project.

```cpp
#include <Adafruit_NeoPixel.h>

#define PIN 6 // Which pin the neopixel data is on
#define NUMPIXELS 60 // Number of pixels that can be addressed

// Object definition
Adafruit_NeoPixel pixels (NUMPIXELS, PIN, NEO_GRB + NEOKHZ800)

void setup(){
    pixels.begin();
}

void loop(){

}
```

The pin is determined by the hardware you are using. The number of pixels allocates the buffer of pixel colors which is pushed out. I often overestimate this value, data sent to a higher address than physically exists is just pushed out and ignored. This does lower refresh rate, but sometimes it's a easy tradeoff versus checking if it's 110 pixels or 115.

For most displays, the animation I'm asked for is something along the line of icicles dripping, stars or a twinkle. I've found that the easiest way for me to write an effect that can be easily adjusted for a client's whim is to have a object structure which runs the effects.

```cpp
enum Direction{
  Inactive,
  Up,
  Down
}

class Twinkle{
  private:
    int address;
    float max_brightness = 125.0;
    float brightness = 0.0;
    float up_speed = 0.1;
    float down_speed = 0.05;
    Direction state = Direction::Inactive;
  public:
    void seed(int addr, float brightness){
      // Start twinkle
      state = Direction::Up;
      max_brightness = brightness;
      address = addr;
    }
    void update(){
      // Update twinkly
      if (state == Direction::Up){
        // Increasing in brightness
        brightness += up_speed;
        if (brightness >= max_brightness){
          state = Direction::Down;
          brightness = max_brightness;
        }
      }
      else if (state == Direction::Down){
        // Decreasing in brightness
        brightness -= down_speed;
        if (brightness <= 0.0){
          state = Direction::Inactive;
          brightness = 0.0;
        }
      }
      else{
        brightness = 0.0;
      }
    }
    void set(Adafruit_NeoPixel& strand){
      int b = round(brightness); // round to int
      pixels.setPixelColor(i, pixels.Color(b, b, b)); // brightness of assigned pixel
    }
}
```

This is the base object I use for most effects. This is missing some features, the most prominent glitch will be that without managing conflicting addresses, a twinkle starting on top of another one will rapidly change brightness. For a wider twinkle (not just one pixel), I use a fixed array in a bell curve-ish shape. For trailing, the address of the object also updates with a velocity. Twinkle objects can be spawned at a set or random frequency, the rate of which sets the density of whatever effect. Making instances of each effects makes it easy to address client notes, by using clear parameters that can be adjusted, and logically separating functional components.

## Controlling LEDs with video

A programmed effect is great for wide majority of lighting displays I've been asked for. Often clients are looking for just a little more specificity than what commercial christmas lights look like. But for larger pieces, where the client has very specific content that should be displayed, it's best to have an interface that a designer can interface with. Video is a good way to bridge that gap. Designers can produce visual effects using any type of video software, and as long as the pixel mapping of the actual led display is clear, they can happily play with effects. This is best for larger projects where the video-led pixels is more clear.

In this system a computer/small server has video content, or is streamed to by some other control server. The display server grabs all or sections of the video, and pushes them out as packets to the LED display controllers. The method of connection from the computer to the LED controllers can be serial, ethernet or even DVI, depending on the decoding abilities and the required resolution and frame rate. In the past I have used a raspberry pi, but they are somewhat unreliable, and I will probably start using a small computer like an intel nuc with a linux distribution installed.
