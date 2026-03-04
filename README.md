# Address Verification Agent

A UiPath coded agent that parses raw US address strings into standardized components and validates them against the USPS Addresses v3 API.

## What It Does

1. **Parses** a raw address string (e.g., `"123 N Main St Apt 4, Springfield, IL 62701"`) into structured fields: street number, directional, street name, street type, unit, city, state, ZIP, etc.
2. **Validates** the parsed address against the USPS API, correcting components and returning DPV confirmation codes.
3. **Returns** a structured JSON response with all address components, a formatted address, confidence level, and USPS validation status.

## Architecture

The agent uses a LangGraph `StateGraph` with three nodes:

```
START -> agent -> validate_address -> output -> END
```

- **agent** - An LLM-powered react agent (GPT-5.2) that parses the raw address into structured components.
- **validate_address** - Calls the USPS Addresses v3 API to validate and correct the parsed address.
- **output** - Assembles the final `AgentOutput` response.

## Project Structure

| File | Description |
|------|-------------|
| `main.py` | Agent definition: input/output models, graph nodes, LangGraph wiring |
| `usps_client.py` | USPS OAuth token management and address validation API client |
| `utils.py` | Template interpolation utilities |
| `pyproject.toml` | Python project config and dependencies |
| `evaluations/` | Evaluation sets for testing agent performance |

## Prerequisites

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- UiPath platform credentials (for `UiPathChat` / LLM Gateway)
- USPS API credentials

## Setup

1. **Install dependencies:**
   ```bash
   uv sync
   ```

2. **Configure environment variables** in a `.env` file:
   ```
   USPS_CONSUMER_KEY=<your-usps-consumer-key>
   USPS_CONSUMER_SECRET=<your-usps-consumer-secret>
   ```

3. **Initialize the project** (regenerates schema if Input/Output models change):
   ```bash
   uv run uipath init
   ```

## Usage

Run the agent locally:

```bash
uv run uipath run main.py '{"address": "123 N Main St Apt 4, Springfield, IL 62701"}'
```

Run with an input file:

```bash
uv run uipath run main.py --file input.json
```

## Input

| Field | Type | Description |
|-------|------|-------------|
| `address` | `string` | The full raw address string to parse and verify |

## Output

| Field | Type | Description |
|-------|------|-------------|
| `streetNumber` | `string` | House/building number |
| `preDirectional` | `string` | Directional prefix (N, S, E, W, etc.) |
| `streetName` | `string` | Primary street name |
| `streetType` | `string` | Street suffix (St, Ave, Blvd, etc.) |
| `postDirectional` | `string` | Directional suffix |
| `unitType` | `string` | Unit designator (Apt, Suite, Unit, etc.) |
| `unitNumber` | `string` | Unit number or letter |
| `city` | `string` | City or municipality |
| `state` | `string` | 2-letter state abbreviation |
| `zipCode` | `string` | 5-digit ZIP code |
| `zipPlus4` | `string` | 4-digit ZIP+4 extension |
| `country` | `string` | Country code (defaults to US) |
| `formattedAddress` | `string` | Full address in standard USPS format |
| `confidence` | `string` | Parse confidence: high, medium, or low |
| `notes` | `string` | Warnings or ambiguities encountered |
| `usps_validated` | `bool` | Whether USPS API confirmed the address |
| `usps_match_code` | `string` | USPS DPV confirmation code |

## Evaluation

```bash
uv run uipath eval
```
