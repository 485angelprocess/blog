# RISC-V OSes in QEMU

This post is just about getting some OSes up in RISC-V. As much as I like running baremetal, it's nice to run some more abstracted software. The [RISC-V - Getting Started Guide](https://risc-v-getting-started-guide.readthedocs.io/en/latest/index.html) has some very nice guides for it.

## Zephyr

 [Zephyr](https://docs.zephyrproject.org/latest/index.html) is a security-minded RTOS for embedded systems. I haven't ended up using it but it'll be nice to check out. For most of my use cases, I have mainly had a smaller, unsophisticated mcu, or just a computer running linux, but most of things I've worked on are quick turnaround one offs. Adding some sophistication and options can really help for longer and wider-scope projects. Most of my projects also had the worst security failure to be that the lights were the wrong color. Anyway, following the RISC-V docs, I installed dependencies.

```bash
sudo apt-get install --no-install-recommends git cmake ninja-build gperf \
  ccache dfu-util device-tree-compiler wget python3-pip python3-setuptools \
  python3-wheel xz-utils file make gcc gcc-multilib
```

After checking the [zephyr getting started guide](https://docs.zephyrproject.org/latest/develop/getting_started/index.html). I created a virtual environment to silo off the python requirements. Zephyr uses `west` which they made for meta management.

Creating a virtual environment:

```bash
$ mkdir zephyr
$ cd zephyr
$ python3 -m venv .venv
```

Activate the environment:

```bash
$ source .venv/bin/activate
```

Once in the virtual environment, python packages will only be installed in that scope. First install `west`

```bash
$ pip install west
```

And then get the source code:

```bash
# in ur projects parent directory
$ west init zephyr
$ cd zephyr
$ west update
```

Then I exported the CMake package:

```bash
$ west zephyr-export
```

And installed python dependencies and sdk

```bash
$ west packages pip --install
```

And installed the sdk, I had to run around the permissions/virtual environment issue and this workaround was functional.

```bash
$ sudo -E PATH="$PATH" west sdk install --install-dir /opt/zephyr-sdk
```

That is everything installed! Now I can run an example:

```bash
$ mkdir build-example
$ cd build-example
$ cmake -DBOARD=qemu_riscv32 $ZEPHYR_BASE/samples/hello_world
$ make -j $(nproc)
```

Note that `$ZEPHYR_BASE` is set to the location of the `zephyr` folder which was made with `west init`.

and run:

```bash
$ make run
```

And we get output!

```bash
[QEMU] CPU: riscv64
*** Booting Zephyr OS build v4.1.0-1109-g8b77098ca135 ***
Hello World! qemu_riscv64/qemu_virt_riscv64
```

I'll circle back to Zephyr again, it has some nice features I saw while looking around waiting for installs and downloads. The integrated test environment seems particularly interesting, having never really found a fast and good testing framework for embedded systems.

## Linux

Yay linux! I also just wanted to get a basic linux OS up. This workflow requires `qemu`, `linux`, `busybox` and the rust toolchain which I had already installed from source. [Busybox](https://www.busybox.net/about.html) is a nice set of UNIX utilities for embedded development.

First I downloaded the sources:

```bash
$ git clone https://github.com/torvalds/linux
$ git clone https://git.busybox.net/busybox
```

I already have QEMU setup, so then I built and compiled linux for a RISC-V target:

```bash
$ cd linux
$ make ARCH=riscv CROSS_COMPILE=riscv64-unknown-linux-gnu- defconfig
$ make ARCH=riscv CROSS_COMPILE=riscv64-unknown-linux-gnu- -j $(nproc)


```

And then built busybox

```bash
$ cd busybox
$ CROSS_COMPILE=riscv64-unknown-linux-gnu- make defconfig
$ CROSS_COMPILE=riscv64-unknown-linux-gnu- make -j $(nproc)
```

Then to run my QEMU machine:

```bash
$ sudo qemu-system-riscv64 -nographic -machine virt \
     -kernel linux/arch/riscv/boot/Image -append "root=/dev/vda ro console=ttyS0" \
     -drive file=busybox/busybox,format=raw,id=hd0 \
     -device virtio-blk-device,drive=hd0
```

So this is from the RISC-V docs, and something has changed, I get a kernel panic trying to mound `/dev/vda`. 

The reason looks like I don't have a filesystem setup. Going from this [source](https://risc-v-machines.readthedocs.io/en/latest/linux/simple/), I create a filesystem structure:

```bash
mkdir initramfs
cd initramfs
mkdir -p {bin,sbin,dev,etc,home,mnt,proc,sys,usr,tmp}
mkdir -p usr/{bin,sbin}
mkdir -p proc/sys/kernel
cd dev
sudo mknod sda b 8 0 
sudo mknod console c 5 1
cd ..
```

I copy the `busybox` executable into bin and then create the filesystem:

```bash
$ find . -print0 | cpio --null -ov --format=newc | gzip -9 > initramfs.cpio.gz
```

And I try to run 

```bash
$ qemu-system-riscv64 -nographic -machine virt \
  -kernel linux/arch/riscv/boot/Image \
  -initrd initramfs/initramfs.cpio.gz \
  -append "console=ttyS0"
```

Which still gives me a similarly panic, so I'm missing something. After looking through a few forums which really didn't give a clear answer, I got to this post [Linux & Python on RISC-V using QEMU from scratch](https://embeddedinn.com/articles/tutorial/Linux-Python-on-RISCV-using-QEMU-from-scratch/). Instead of making the init filesystem a regular file, they created a null disk and created the filesystem in there.

Creating the NULL disk and formatting it:

```bash
$ dd if=/dev/zero of=root.bin bs=1M count=64
$ mkfs.ext2 -F root.bin
```

And setting setting up the fs, and setting busybox as the init:

```bash
mkdir mnt
sudo mount -o loop root.bin mnt
cd mnt 
sudo mkdir -p bin etc dev lib proc sbin tmp usr usr/bin usr/lib usr/sbin
sudo cp ~/busybox/busybox bin
sudo ln -s ../bin/busybox sbin/init
sudo ln -s ../bin/busybox bin/sh
cd ..
sudo umount mnt
```

Then I was able to launch QEMU with this command:

```bash
$ qemu-system-riscv64 -nographic -machine virt \
                    -kernel linux/arch/riscv/boot/Image \
                    -append "root=/dev/vda rw console=ttyS0" \
                    -drive file=root.bin,format=raw,id=hd0 \
                    -device virtio-blk-device,drive=hd0
```

I'm not sure if the difference was my QEMU configuration, or if this was implicityl set up somewhere else. Bouncing around forums, it seems there are some toolkits for getting linux up and running, but this does launch. When QEMU boots, I get a console terminal. Install busybox tools using:

```bash
# /bin/busybox --install -s
```

Now I have access to basic unix utilities in a RISCV environment.

```bash
# uname -a
Linux (none) 6.12.0 #2 SMP Sat Mar 22 11:24:52 EDT 2025 riscv64 GNU/Linux
```

That's good progress for today. It's nice to have all these little containers running architectures.


