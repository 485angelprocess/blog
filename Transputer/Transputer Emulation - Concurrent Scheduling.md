# Transputer Emulation - Concurrent Scheduling

One of the key features of the transputer architecture is low-level support for concurrent processes. The transputer runs multiple processes without any need for the OS or other programs to manage them. This is going to be a description of this part of the architecture, as I figure out how to design my emulation of it.

Each process has a priority, which can be high or low. They have an instruction pointer (program counter) and a workspace pointer (stack pointer). There is a separate internal scheduler which runs on the transputer which handles switching. the scheduler has a queue of existing processes. Transputer features several instructions which act as descheduling, including the `jump` instruction. When these instructions occur, there is a check that runs to check if the process should be switched.

There are a few rules which handle when processes will be interrupted.

- If there are only low priority processes in the queue, adding a high priority process will interrupt these processes, and run until it is completed.
  
  - As far as I can tell the high priority process is only started when the currently running low priority process is descheduled. The register state is not stored when switching processes, so interrupting atomic instructions would cause undefined behavior in the low priority process.

- If there are multiple low priority processes, or multiple high priority processes, they are switched between at descheduling points.

Because it relies on descheduling points to switch processes, a good transputer program that exploits multiprocessing should have short runs of atomic processes with many points to context switch. The process manager keeps track of the queue in two lists (one for each priority). Each list contains workspace descriptors of the process. The head pointer is the process at the head of the queue. If no processes are in the queue, that pointer will be -1, or `0x8000_0000`, labeled as `NotProcess.p` in documentation.

There are several instructions for scheduling new processes. All work by setting the state of the ongoing process, and letting the scheduler microcode run from there. The state is set using the 6 words from the workspace location.

| Workspace offset | Use                                                                  |
| ---------------- | -------------------------------------------------------------------- |
| 0                | Offset to guard routine to execute (only used for "alternation")     |
| -1               | Stores the instruction pointer                                       |
| -2               | Wdesc of the next process in queue (linked list)                     |
| -3               | Address of the message buffer (`State.s`)                            |
| -4               | Wdesc of the next process waiting for the timer, or `NotProcess.p+1` |
| -5               | Time process waiting to awaken at                                    |

## STARTP and ENDP

`STARTP` and `ENDP` are used to start and end concurrent processes. The documentation I have is a little mysterious of what exactly is done here, so I'm going to write out how it seems like these instruction works.

Based on the assembly guide, the basic use of `STARTP` is:

```asm
            ldc NEW_PROC - L_START; load offset to process to start
            ldlp WORKSPACE; load address of workspace new process

L_START:    startp; start new process
            ...
            ...
NEW_PROC:   ; // new process
```

This starts a new concurrent process. It's slightly unclear what the operations enclosed in `STARTP` are doing, so I looked at the emulator written by Julian Highfield (archived here: [Transputer Emulator](https://web.archive.org/web/20130515034826/http://spirit.lboro.ac.uk/emulator.html)). It is a C emulator which is pretty easy to go through. In Julian's code the `STARTP` instruction is written as:

```c
case 0x0d: /* startp      */
			   temp = (AReg & 0xfffffffe);
			   IPtr++;
			   writeword (index (temp, -1), (IPtr + BReg));
			   schedule (temp, CurPriority);
			   break;
```

The first line just masks off bit 0 from the contents of register A. I believe the lowest bit stores the priority, although it's not used here. The rest of A contains the address of the new processes' workspace. This must be a multiple 4. Then the program counter is incremented to get the next instruction. Next, the program counter of the offset is saved to -1 offset of the new workspace. 

Finally Julian runs a schedule routine. This is written as:

```c
/* Add a process to the relevant priority process queue. */
void schedule (unsigned long wptr, unsigned long pri)
{
	unsigned long ptr;
	unsigned long temp;

	/* Remove from timer queue if a ready alt. */
	temp = word (index (wptr, -3));
	if (temp == Ready_p)
		purge_timer ();

	/* If a high priority process is being scheduled */
	/* while a low priority process runs, interrupt! */
	if ((pri == HiPriority) && (CurPriority == LoPriority))
	{
		interrupt ();

		CurPriority = HiPriority;
		WPtr = wptr;
		IPtr = word (index (WPtr, -1));
	}
	else
	{
		/* Get front of process list pointer. */
		if (pri == HiPriority)
		{
			ptr = FPtrReg0;
		}
		else
		{
			ptr = FPtrReg1;
		}

		if (ptr == NotProcess_p)
		{
			/* Empty process list. Create. */
			if (pri == HiPriority)
			{
				FPtrReg0 = wptr;
				BPtrReg0 = wptr;
			}
			else
			{
				FPtrReg1 = wptr;
				BPtrReg1 = wptr;
			}
		}
		else
		{
			/* Process list already exists. Update. */

			/* Get workspace pointer of last process in list. */
			if (pri == HiPriority)
			{
				ptr = BPtrReg0;
			}
			else
			{
				ptr = BPtrReg1;
			}

			/* Link new process onto end of list. */
			writeword (index (ptr, -2), wptr);

			/* Update end-of-process-list pointer. */
			if (pri == HiPriority)
			{
				BPtrReg0 = wptr;
			}
			else
			{
				BPtrReg1 = wptr;
			}
		}
	}
}
```

This is a little long, but it's essentially just handling the cases for different priorities. The basic case is scheduling a new low priority process from a low priority thread. In pseudo code this looks like:

```
let new_wp := workspace pointer of new process

let front_process = front_process_reg;
if front_process == NOT_PROCESS{
    // No processes in queue, create process list
    front_process_reg = new_wp;
    back_process_reg = new_wp;
}
else{
    let back_process = back_process_reg;
    
    // Append to linked list
    write_mem(back_process - 8, new_wp);

    back_process_reg = new_wp;
}
```

The scheduling uses two registers to store the first and last workspace locations in a linked list. Each entry on the linked list stores the next one. To schedule a new one, a pointer to the next process is stored in the list. When a process is descheduled, the pointer can be checked, and if a new process is available it can be gone to.
