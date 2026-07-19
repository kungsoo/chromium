# Thorium SSE2

This directory contains build config files for compiling 32 bit Thorium/Chromium with [SSE2](https://en.wikipedia.org/wiki/SSE2).

Chromium does not officially support 32-bit Linux anymore and M150 normally
requires SSE3. These argument files select `thorium_x86_profile = "sse2"` for
Thorium's explicitly validated compatibility build. The central compiler
configuration owns the actual ISA flags; this directory does not duplicate
them.
