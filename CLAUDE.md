# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Address Verification Agent — a UiPath coded agent that parses raw US address strings into standardized components and validates them against the USPS Addresses v3 API. Built with LangGraph, the UiPath Python SDK, and GPT-5.2.

## Commands

```bash
# Install dependencies
uv sync

# Run the agent locally
uv run uipath run main.py '{"address": "123 N Main St Apt 4, Springfield, IL 62701"}'

# Run with input file
uv run uipath run main.py --file input.json

# Run evaluations
uv run uipath eval

# Regenerate schema after modifying Input/Output models
uv run uipath init
```

## Architecture

The agent lives in `AddressValidatorAgent/` and uses a LangGraph `StateGraph` with three nodes:

```
START -> agent -> validate_address -> output -> END
```

- **`agent` node** (`main.py:agent_node`) — Wraps an inner react agent (created via `uipath_langchain.agent.react.create_agent`) that uses GPT-5.2 to parse the raw address string into structured `AgentOutput` fields.
- **`validate_address` node** (`main.py:validate_address_node`) — Reassembles parsed components into a street string, calls the USPS Addresses v3 API via `usps_client.py`, then overwrites fields with USPS-corrected values and sets DPV confirmation codes.
- **`output` node** (`main.py:output_node`) — Maps `WrapperState` fields to the final `AgentOutput` Pydantic model.

### Key Models (main.py)

- `AgentInput` — single `address` string field
- `AgentOutput` — 17 fields covering parsed components, formatted address, confidence, notes, and USPS validation status
- `WrapperState` — carries all fields through the graph (superset of Input + Output)

### USPS Client (usps_client.py)

- OAuth token management with in-memory caching (`get_usps_token`)
- `validate_address()` calls USPS Addresses v3 API with `httpx.AsyncClient`
- Requires `USPS_CONSUMER_KEY` and `USPS_CONSUMER_SECRET` env vars (in `.env`)

### Evaluations

- Eval sets in `evaluations/eval-sets/evaluation-set-default.json` — 5 test cases covering valid addresses, invalid addresses, misspellings, and messy formatting
- Two evaluators: LLM Judge Semantic Similarity and LLM Judge Trajectory
- Run with `uv run uipath eval`

## UiPath Agent Conventions

- All agents must define `Input`, `State`, and `Output` Pydantic models (here named `AgentInput`, `WrapperState`, `AgentOutput`)
- All node functions must be async
- The final output node returns the `Output` model
- Graph compiled as `graph = builder.compile()` — this variable name is referenced in `langgraph.json`
- Use `UiPathChat` or `get_chat_model` for LLM initialization (not direct OpenAI/Anthropic clients)
- After changing Input/Output models, run `uv run uipath init` to regenerate `entry-points.json` and `uipath.json`
- Reference docs in `.agent/` directory: `REQUIRED_STRUCTURE.md`, `SDK_REFERENCE.md`, `CLI_REFERENCE.md`
