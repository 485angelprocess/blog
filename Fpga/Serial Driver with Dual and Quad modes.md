## Serial Driver with Dual and Quad modes

I am working on a project which involves fast reading from an on-board flash chip. This means having a serial driver with an AXI bus interface which can run standard, dual and quad serial read and write commands.

## Test device

To test behavior, I need a object which parses spi data and can easily report what was received. I can also load in responses.

## Module Design

First, I breakdown the module into six operating states:

| State      | Condition                    | Behavior                                                                   |
| ---------- | ---------------------------- | -------------------------------------------------------------------------- |
| Idle       | No data in/out               | CS is held high, no data is sent                                           |
| Standard   | Data on standard fifo        | CS is low, data is written to mosi, data is read from miso                 |
| Dual write | Data in dual transmit fifo   | CS is low, data is written on io0 and io1, no data is read in              |
| Dual read  | Data flagged as dual read    | CS is low, data is read from io0 and io1, no data is written out           |
| Quad write | Data in quad transmit fifo   | CS is low, data is written on io0, io1, io2 and io3, no data is read in    |
| Quad read  | Data is flagged as quad read | CS is low, data is read from io0, io1, io2 and io3, no data is written out |

From the controller side, I want to be able to load commands in, have them run, and know when data is finished. So I need buffers for data, and flags which indicate if a transaction has finished and if data is ready.

| Reg                    | R/W        | Use                                                                                   |
| ---------------------- | ---------- | ------------------------------------------------------------------------------------- |
| Reset                  | Write only | Software reset                                                                        |
| Flush                  | Write only | Flush all buffers                                                                     |
| Inhibit                | RW         | While set, prevents data from sending, automatically set when transaction is finished |
| Length of transaction  | RW         | Number of bytes to write and read                                                     |
| Write address          | RW         | Address of byte to edit                                                               |
| Write data             | RW         | Read or write to byte in spi buffer                                                   |
| Write width            | RW         | Read or write to width of data in spi buffer                                          |
| Write r/w              | RW         | Set data to a read or write value, use to mask out dual and quad transaction          |
| Transaction done       | Read only  | Is set when transaction has finished                                                  |
| Receive data fifo      | Read only  | Loads a byte of data from receive data fifo                                           |
| Receive data occupancy | Read only  | Number of bytes in receive data buffer                                                |

The AMD Quad SPI IP uses fifo interfaces on both transmit and receiving sides. While this makes a minimal interface, and fifos are more efficient than arrays, it leads to some design issues. First, the Quad mode infers address length, dummy data length and other information based on the first byte of data. This is opaque from the controller end. It also means that every command must be reloaded after a transaction is finished. For my needs, I am trying to sequence reads, with as little interruption as possible. Using a non-volatile write buffer reduces bus transactions between commands.

I am leaving off some functionality from the AMD Quad SPI, such as more fine grained fifo information, interrupts and LSB/MSB setting.

To make the interface easier/faster, I am also adding a few convenience registers.

| Reg                         | R/W        | Use                                                                                                    |
| --------------------------- | ---------- | ------------------------------------------------------------------------------------------------------ |
| Set command                 | Write only | Sets the first byte of the transaction to this byte, sets the width to standard, and the mask to write |
| Set long address (32 bits)  | Write only | Sets bytes 1, 2, 3, 4 to address                                                                       |
| Set short address (24 bits) | Write only | Sets byte 1, 2, 3 to address                                                                           |
| Set mode                    | Write only | Sets data 1-end to mode (standard, dual or quad)                                                       |
| Set write length            | Write only | Sets data 0-N-1 to write and data N-end to read                                                        |

These registers handle the main use cases of the flash memory, but keeps finer operations exposed for other use cases.
