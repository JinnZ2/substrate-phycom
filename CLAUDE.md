# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is
The connective layer above three repos: geometric-to-binary (encoder),
BE2-communication (transport), orbital-phycom (one expander). This repo
makes the EXPANDER pluggable and adds a terrestrial (geomagnetic/field)
expander so the architecture runs with no orbit.

## Core invariant
You transmit the SEED, not the message. A shared deterministic physics
model (the Expander) regenerates the message. The model never crosses the
wire — it is both the compression and the gate.

## Layout
- core/seed.py      : the unit crossing every layer (120-bit + model_id + epoch + CRC16)
- core/expander.py  : abstract Expander. Same seed in, deterministic schedule out.
- expanders/orbital.py     : reference adapter to orbital-phycom (Kepler)
- expanders/geomagnetic.py : terrestrial field-model expander (the new piece)
- integration/demo.py      : end-to-end, two carriers, the shared-model gate
- tests/test_stack.py      : determinism + round-trip + gate

## House rules
- stdlib only. No deps. Must run on a phone.
- CC0. No extraction.
- Determinism is the contract. Same seed + same model + same epoch = identical output.
- New carrier? Implement Expander, reuse seed.py + BE2 transports unchanged.

## Run
PYTHONPATH=. python -m integration.demo
PYTHONPATH=. python tests/test_stack.py
