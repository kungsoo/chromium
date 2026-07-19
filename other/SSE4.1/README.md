# Thorium SSE4.1

This directory contains build config files for compiling Thorium/Chromium with [SSE4.1](https://en.wikipedia.org/wiki/SSE4#SSE4.1).

SSE4.1 targets Penryn-generation Core 2 processors and newer CPUs. Earlier
Core 2 processors without SSE4.1 are not compatible.

The argument files select `thorium_x86_profile = "sse4_1"`, which explicitly
requires SSE3, SSSE3, and SSE4.1 without adding SSE4.2 or AVX.
