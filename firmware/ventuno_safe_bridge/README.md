# VENTUNO Q STM32 safe bridge

This firmware is the initial MyAI MCU-side trust boundary.

It intentionally exposes only read-only diagnostic RPC methods:

- `myai_ping`
- `myai_uptime_ms`
- `myai_mcu_status`

All methods use `Bridge.provide_safe()`, so callbacks execute in the safe/main-loop context provided by Arduino RouterBridge.

There are deliberately:
- no GPIO write methods
- no PWM methods
- no motor methods
- no relay methods
- no arbitrary pin access
- no Linux-to-MCU command passthrough

The Linux MyAI configuration must still explicitly enable RPC before these methods can be called.

Physical output methods must be added later one at a time with:
1. a fixed semantic method name
2. parameter validation on both Linux and MCU sides
3. physical limits
4. MCU watchdog/failsafe behavior
5. explicit MyAI write allowlist
6. hardware testing before normal use

Do not replace this boundary with a generic `digitalWrite(pin, value)` RPC exposed to natural language.
