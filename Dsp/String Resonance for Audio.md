# String Resonance VST

I'm interested in audio effects using string resonance. Digitally modeling a string can be done using a delay line and a low pass filter.  This is the Karplus-Strong algorithm,

$$
y(n)=x(n)+h(x(n-K))
\\
y(n):= Output
\\
x(n):=Input
\\
x(n - K):=Delay
\\
h(v):=Filter
$$

The length of the delay line represents the time a soundwave takes to travel to and from the length of a string. The filter represents the physical dampening of instrument elements (the nut, the bridge, the body). A real instrument has multiple resonant delay lines, but we can make fictional and interesting string models by layering multiple blocks.

## Pure Data Model

A quick testing model can be made in pure data. This allows a quick way to get baseline parameters and play with the audio. The input is a short burst of noise, which simulates a pluck.

![pd_string.png](C:\Users\magen\Documents\Blog\Resources\string_resonance\pd_string.png)

With a basic model to go back to, I can start implementing on different platforms to improve playability.

## Rust implementation

The next step I wanted to get into a rust implementation, and put it into a nice plugin format so it can be used with a DAW. It's looking like `nih-plugin` is the most built out and supported framework for CLAP and VST3 right now so I'm going to look into that. The implementation of the model was fairly minimal using a basic array as a delay line and using neodsp's `simper-filter`  as starting point for the filter.

## Delay Line

A basic delay line just requires some container class that can be written to at one point and read from another point N samples prior. For my implementation I used a basic array. A vector could be used to have dynamic memory size. However since I am aiming towards an embedded version of this effect, I'd rather have set memory bounds.

The buffer is declared as

```rust
#[derive(Debug, Copy, Clone)]
pub struct DelayLine<T>{
    pub amount: usize,
    buffer: [T; MAX_LENGTH],
    wp: usize,
    y0: T
}
```

Then we can write and read samples using `pop` and `push` methods. The struct keeps track of a write pointer, and calculates a read pointer which is N samples behind the write head.

```rust
impl<'a, T: std::marker::Copy + Float + Default + FromPrimitive + 'a> DelayLine<T>{
    pub fn new() -> Self{
        Self{
            amount: 0,
            buffer: [T::default(); MAX_LENGTH],
            wp: 0,
            y0: T::default()
        }
    }
    pub fn push(&mut self, data: T){
        self.buffer[self.wp] = data;
        self.wp = (self.wp + 1) % MAX_LENGTH;
    }
    pub fn pop(&mut self) -> T{
        let rp: isize = (self.wp as isize) - (self.amount as isize);
        self.y0 = self.buffer[wrap_value(rp)];
        self.y0
    }
}
```

The `wrap_value` function just sets the read pointer to a valid index:

```rust
fn wrap_value(v: isize) -> usize{
    if v < 0{
        ((v + MAX_LENGTH as isize) as usize) % MAX_LENGTH
    }
    else{
        (v as usize) % MAX_LENGTH
    }
}
```

Then to adjust the delay length I added a method to set from a frequency value:

```rust
pub fn set_frequency(&mut self, f: f32, sampling: f32){
        let delay = sampling / f;
        self.amount = delay.round() as usize;
        if self.amount >= MAX_LENGTH{
            self.amount = MAX_LENGTH - 1;
        }
    }
```

## Filter

The filter implementation is fairly simple, because I'm using an existing filter class. It's wrapped in a generic object, so that I can play with some other filter objects. The trait sets up the basic interface for the filter:

```rust
pub trait Filter<F: Float + Default>{
    fn tick(&mut self, _input: F) -> F {
        /* Input one sample into filter and get result */
        F::default() 
    } 
    fn set_cutoff(&mut self, _cutoff: F){
        /* Set the cutoff frequency of the filter */
        ()
    }
    fn set_q(&mut self, _q: F){
        /* Set the resonance of the filter */
        ()
    }
}
```

Although some filters might call for more setters, for most low performance cost filters, this will work fine. 

For the Simper Filter, wrapping an `Svf` object is straightforward I use a struct with the parameters:

```rust
#[derive(Default, Clone)]
pub struct FilterSetting<F: Float + Copy>{
    pub filter_type: FilterType,
    pub sample_rate: F,
    pub cutoff: F,
    pub q: F,
    pub gain: F
}

impl<F: Float + Default> FilterSetting<F>{
    pub fn to_svf_coeff(&self) -> SvfCoefficients<F>{
        let mut coeffs = SvfCoefficients::default();
        let _result = coeffs.set(self.filter_type.clone(), self.sample_rate, self.cutoff, self.q, self.gain);
        coeffs
}
```

And then add a method to update the filter:

```rust
fn set(&mut self){
    self.filter.set_coeffs(self.setting.to_svf_coeff());
}
```

Then the trait implementation looks like this:

```rust
impl<F: Float + Default> Filter<F> for SimperFilter<F>{
    fn tick(&mut self, input: F) -> F {
        self.filter.tick(input)   
    }
    fn set_cutoff(&mut self, cutoff: F) {
        self.setting.cutoff = cutoff;
        self.set(); 
    }
    fn set_q(&mut self, q: F) {
        self.setting.q = q;
        self.set();
    }
}
```

## NIH Plugin

With those two building blocks done, I can create an audio plugin. I use the `NIH-plugin` framework which can generate CLAP and VST3 plugins.  I used the 

[gain example](https://github.com/robbert-vdh/nih-plug/tree/master/plugins/examples/gain) as a starting point.

For a VST which transforms audio->audio (i.e. no real midi processing), the plugin has to provide the params, which appear to the DAW as controls. And the core audio processing step.

I set each "string" as it's own struct. This just combines a delay line with a filter with a an easy way to process an incoming sample.

```rust
#[derive(Debug, Copy, Clone)]
pub struct Model<F: Float + Default, ModelFilter: Filter<F>>{
    pub filter: ModelFilter,
    pub delay: DelayLine<F>
}

impl<F: Float + Default + FromPrimitive, ModelFilter: Filter<F> + Default>Default for Model<F, ModelFilter>{
    fn default() -> Self {
        let f = ModelFilter::default();
        Self{
            filter: f,
            delay: DelayLine::new()
        }
    }
}

impl<F: Float + Default + FromPrimitive, ModelFilter: Filter<F>> Model<F, ModelFilter>{
    pub fn process(&mut self, input: F) -> F{
        /* Process one sample */
        // Get delayed sample
        let delay_out = self.delay.pop();
        // Filter delayed sample
        let f_result = self.filter.tick(delay_out);

        // Combine input and filtered result into start of delay
        let delay_result = f_result + input;
        self.delay.push(delay_result);

        // Return delayed sample
        delay_out
    }
}
```

In the top-level `lib.rs`, the actual plugin contains a pointer to the `Params`, and a array of four strings. I also have an oscillator which can be used to change the string tuning over time.

```rust
const NUM_STRINGS: usize = 4;

struct StringModel{
    params: Arc<StringParams>,
    model: [Model<f32, SimperFilter<f32>>; NUM_STRINGS],
    lfo: lfo::LFO
}
```

If I wanted to experiment with other filters, I can drop in a struct with my filter.

For the parameters, the plugin provides controls for dry and wet gain, lfo controls and the base note of the resonator strings. Each string has a gain, offset pitch and filter controls.

```rust
#[derive(Params)]
struct StringParams{
    #[id = "dry"]
    pub dry: FloatParam,

    #[id = "wet"]
    pub wet: FloatParam,

    #[id = "note"]
    pub base: IntParam,

    #[id = "lfo rate"]
    pub lfo_rate: FloatParam,

    #[id = "lfo depth"]
    pub lfo_depth: FloatParam,

    #[nested(array, group = "String Parameters")]
    pub element_params: [ElementParams; NUM_STRINGS]

}

#[derive(Params)]
struct ElementParams{
    #[id = "gain"]
    pub gain: FloatParam,
    #[id = "offset"]
    pub offset: IntParam,
    #[id = "Cutoff"]
    pub cutoff: FloatParam,
    #[id = "Q"]
    pub q: FloatParam
}
```

The range and type of each parameter are set in the Default implementation. Because I have a few gain controls, I added a function to setup a control which is shown in dB but  provides a logarithmically mapped value.

```rust
fn db_param(name: &str, min: f32, max: f32) -> FloatParam{
    FloatParam::new(
        name,
        util::db_to_gain(0.0),
        FloatRange::Skewed { 
            min: util::db_to_gain(min), 
            max: util::db_to_gain(max), 
            factor: FloatRange::gain_skew_factor(min, max) }
    )
    .with_smoother(SmoothingStyle::Logarithmic(50.0))
    .with_unit(" dB")
    .with_value_to_string(formatters::v2s_f32_gain_to_db(2))
    .with_string_to_value(formatters::s2v_f32_gain_to_db())
}
```

The implementation for the controls looks like this.

```rust
impl Default for StringParams{
    fn default() -> Self {
        Self{
            dry: db_param("dry", -60.0,20.0),
            wet: db_param("wet", -60.0,20.0),
            base: IntParam::new("Note base", 0, IntRange::Linear { min: -44, max: 44 }),
            lfo_rate: FloatParam::new("Lfo Rate", 1.0, FloatRange::Linear { min: 0.1, max: 30.0 }),
            lfo_depth: FloatParam::new("Lfo Depth", 0.0, FloatRange::Linear { min: 0.0, max: 5.0 }),
            element_params: Default::default()
        }
    }
}


impl Default for ElementParams{
    fn default() -> Self {
        Self{
            gain: db_param("gain", -30.0, 0.0),
            offset: IntParam::new("Note offset", 0, 
                IntRange::Linear { min: 0, max: 36 }),
            cutoff: FloatParam::new("Cutoff", 440.0,
                    FloatRange::Linear { min: 10.0, max: 22000.0 }),
            q: FloatParam::new("Q", 0.771, FloatRange::Linear { min: 0.5, max: 1.0 })
        }
    }
}
```

Most of the plugin resembles the gain plugin, but the audio process step consists of retrieving control values, and then processing through each string resonator. There's no real optimizations here, but the core processing of each sample is fairly fast.

```rust
fn process(
    &mut self,
    buffer: &mut Buffer,
    _aux: &mut AuxiliaryBuffers,
    _context: &mut impl ProcessContext<Self>,
) -> ProcessStatus {
    for channel_samples in buffer.iter_samples
(){

        let wet_gain = self.params.wet.smoothed.next();
        let dry_gain = self.params.dry.smoothed.next();

        self.lfo.amount = self.params.lfo_depth.smoothed.next();
        self.lfo.set_freq(self.params.lfo_rate.smoothed.next());

        let mut elem_gain = [0.0; NUM_STRINGS];

        for i in 0..self.model.len(){
            elem_gain[i] = wet_gain * self.params.element_params[i].gain.smoothed.next();
            self.model[i].filter.set_cutoff(self.params.element_params[i].cutoff.smoothed.next());
            self.model[i].filter.set_q(self.params.element_params[i].q.smoothed.next());
        }

        // Base note of delay
        let base_note = self.params.base.smoothed.next();

        let mut note = [0.0; NUM_STRINGS];

        // Each element
        for i in 0..self.model.len(){
            note[i] = (base_note + self.params.element_params[i].offset.smoothed.next()) as f32;
        }

        // Process each sample
        for sample in channel_samples{
            let dry_value = *sample;
            *sample = dry_gain * dry_value;
            let lfo_value = self.lfo.next();

            for i in 0..self.model.len(){
                self.model[i].delay.set_frequency(note_to_freq(note[i] + lfo_value, 440.0), 441000.0);
                *sample += (elem_gain[i]) * self.model[i].process(dry_value);
            }

            // Clip
            if *sample < -1.0{
                *sample = 0.0;
            }
            if *sample > 1.0{
                *sample = 1.0;
            }
        }
    }
    ProcessStatus::Normal
}
```

I am holding off on writing the front end, but this is functional. I did use [Free-audio's CLAP validator](https://github.com/free-audio/clap-validator) to get some basic logging information about the device. I'm not sure if any DAW provides easy to find logging information. When I initially tried running the plugin, it crashed immediately. I had to reduce the delay line max size to prevent it from using more stack memory than is allocated for the plugin. Using a vec would get around this (allocated to heap). For this plugin, the maximum delay is relatively short, as it should be in audible range.

Without a frontend, most daws render plugins with slider/dropdown widgets.

![basic_clap.png](C:\Users\magen\Documents\Blog\Resources\string_resonance\basic_clap.png)

## Build details

The NIH Plugin crate can be added to `Cargo.toml`

```toml
[dependencies]
nih_plug = { git = "https://github.com/robbert-vdh/nih-plug.git", features = ["assert_process_allocs"] }
parking_lot = "0.12"
```

In order to bundle into CLAP and VST, I used an xtask subproject, the main function runs from the `nih_plug_xtask` crate.

```rust
fn main() -> nih_plug_xtask::Result<()> {
    nih_plug_xtask::main()
}
```

This can be added to the build in the top-level `Cargo.toml` with the workspace tag.

```toml
[workspace]
members = [
  "xtask",
]
```

Code and CLAP plugin are here: [GitHub - 485angelprocess/string_resonator_plugin: CLAP/VST Plugin modeling string resonance](https://github.com/485angelprocess/string_resonator_plugin)
