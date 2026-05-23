# QEMU MCP Specification

## Goal

Build an MCP-compatible execution environment capable of:

- Running VxWorks RTP binaries inside QEMU
- Running Python RTP applications
- Supporting pub/sub application pairs
- Capturing isolated logs per RTP
- Managing RTP lifecycle deterministically
- Providing structured interaction through MCP tools

The system should behave like a lightweight orchestration/runtime layer for VxWorks applications.

## Recommended Architecture

```ascii
         +------------------------------------------------------+
         |                    MCP Server                        |
         |------------------------------------------------------|
         | Generic orchestration                                |
         | Session management                                   |
         | Tool routing                                         |
         | Artifact handling                                    |
         +-------------------------+----------------------------+
                                   |
                                   v
+-----------------------------------------------------------------------+
|                          Runtime Abstraction                          |
|-----------------------------------------------------------------------|
|                     <<interface>> TargetRuntime                       |
|-----------------------------------------------------------------------|
|  + upload(host_path, remote_path) : bool                              |
|  + exec(path, args, options) : TargetID                               |
|  + kill(target_id) : bool                                             |
|  + status(target_id) : StatusJSON                                     |
|  + fetch_logs(target_id, tail_lines) : string                         |
|  + inspect(mode) : StructuredJSON                                     |
+-----------------------------------+-----------------------------------+
                                    |
                    +---------------+---------------+
                    |                               |
                    v                               v
+---------------------------------------+   +---------------------------------------+
|            VxWorks Runtime            |   |            Zephyr Runtime             |
|---------------------------------------|   |---------------------------------------|
|  + upload() -> Write to NFS/FTP       |   |  + upload() -> Flash to RAM via Shell |
|  + exec()   -> rtpSp (Spawn Process)  |   |  + exec()   -> Dynamic thread spawn   |
|  + kill()   -> rtpDelete(RTP_ID)      |   |  + kill()   -> k_thread_abort(Ptr)    |
|  + status() -> rtpShow(RTP_ID)        |   |  + status() -> k_thread_custom_lookup |
|  + fetch_logs() -> ioTaskStdSet pipe  |   |  + fetch_logs() -> Filter UART tags   |
|  + inspect() -> Parse taskShow/rtpShow|   |  + inspect() -> Parse kernel threads  |
+---------------------------------------+   +---------------------------------------+
                                    |
                                    v (Communicates via raw Serial/Telnet/SSH)
+-----------------------------------------------------------------------+
|                             QEMU Backend                              |
|-----------------------------------------------------------------------|
|  * Manages VM Lifecycle (VM start, VM stop, VM reset)                 |
|  * Exposes interactive Serial / Telnet pipes to the Runtime layer     |
|  * Manages hypervisor snapshots (QMP)                                 |
+-----------------------------------------------------------------------+
```

```ascii
+-------------------------------------------------------------------------------+

|  STRICT 1:1 INTERFACE & IMPLEMENTATION BOUNDARY COMPLETE                      |
+-------------------------------------------------------------------------------+
| MCP LAYER  --> Standardized JSON-RPC Tools & Subscriptions                    |
| INTERFACE  --> Polymorphic Contract: 6 Methods, Matching Signatures           |
| OS GUEST   --> Software Only (VxWorks Processes / Zephyr Threads)             |
| HYPERVISOR --> Machine Only (QEMU States, Shell Pipes, Snaps)                 |
+-------------------------------------------------------------------------------+
```

## Interface & Sub-Runtime Mapping

| Interface Method | VxWorks Runtime Mapping (Process-Centric) | Zephyr Runtime Mapping (Thread-Centric) |
| :--- | :--- | :--- |
| **`upload(host_path, remote_path)`** | Copies binaries (`.vxe`) or Python code to target storage (NFS, TFTP, or TFFS). | Writes binary modules directly into target RAM/Flash sectors using MCUMGR or serial protocol blocks. |
| **`exec(path, args, options)`** | Invokes `rtpSp` via shell. Uses `ioTaskStdSet` for descriptor isolation. Returns **RTP ID**. | Instantiates a dynamic thread context from memory. Returns **Thread Control Block (TCB) Pointer**. |
| **`kill(target_id)`** | Calls `rtpDelete(rtp_id)` or sends a structural POSIX signal to terminate the process cleanly. | Calls `k_thread_abort(thread_ptr)` to instantly purge the execution state from the kernel scheduler. |
| **`status(target_id)`** | Executes `rtpShow(rtp_id)`. Returns lifecycle tokens: `STATE` (RUNNING, ZOMBIE), `EXIT_CODE`, and active execution `ERRNO`. | Scans thread metadata fields. Returns lifecycle tokens: `STATE` (READY, SUSPENDED, DEAD), and scheduler `PRIORITY`. |
| **`fetch_logs(target_id, tail_lines)`** | Reads directly from the isolated network socket or file path generated by `ioTaskStdSet`. | Filters the monolithic UART console stream using thread-matching printk log-module headers. |
| **`inspect(mode)`** | Parses human-readable ASCII tables from `taskShow`, `rtpShow`, or `iosFdShow` into unified JSON. | Parses human-readable diagnostic tables from Zephyr's internal shell modules (`kernel threads`, `kernel memory`). |


## References

* https://github.com/Kevin4562/QEMU-MCP
* https://github.com/Neanderthal/mcp-qemu-vm
* https://github.com/Abdalla-Eldoumani/qemu-mcp-server

