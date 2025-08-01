# Lists/Collections in Forth direct to assembly

I am trying to think through a concept for my forth-like which includes lists as a core data type. So consider something like this:

```forth
[1 2] 3 +
```

This should push `[4 5]` to the stack.

Now eventually I want to add direct vector addition to my cpu, which will require its own implementation, but with just a basic RISC-V I32 ISA, how could I implement this?

Let's say I store all data with a tag and corresponding data. For an integer, the data can just be the value, but for a list, it would be a pointer to the list and then the length.

One way to implement this would be to write an add function which checks for data types.

```c
int pop(*sp){
    tag = &(sp-1);
    switch (tag){
        INT => {
            // Return constant integer
            int v = &(sp-2);
            sp -= 2;
            return v;
        },
        LIST => {
            int* p = &(sp-2);
            let len = &p; // length is stored at p+0        

            // data stack
            // i.e. 1 and 1st item in list
            &dp = {len, p+1};
            dp -= 2; // push to data stack
    
            return &p; // 0th item in list
        }
    }
}


void add(*sp){
    let a = pop(sp);
    let b = pop(sp);
}
```


