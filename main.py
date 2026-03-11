import re
from datetime import (
    datetime,
    timezone
)
from langchain_core.messages import (
    HumanMessage,
    SystemMessage
)
from langgraph.graph import START, StateGraph, END
from pydantic import (
    BaseModel,
    Field
)
from pydantic import (
    ConfigDict
)
from typing import (
    Optional,
    Sequence
)
from uipath.agent.react import (
    AGENT_SYSTEM_PROMPT_TEMPLATE
)
from uipath_langchain.agent.react import (
    create_agent
)
from uipath_langchain.chat.chat_model_factory import (
    get_chat_model
)
from usps_client import validate_address
from utils import (
    interpolate_legacy_message
)



# LLM Model Configuration
llm = get_chat_model(
    model='gpt-5.2-2025-12-11',
    temperature=0.0,
    max_tokens=16384,
    agenthub_config="agentsruntime",
)


# Collect all tools
all_tools = []

# Input/Output Models
class AgentInput(BaseModel):
    model_config = ConfigDict(extra='allow')
    address: str = Field(..., description="The full raw address string to parse and verify. Example: '123 N Main St Apt 4, Springfield, IL 62701'. Should be a single-line or multi-line US-style address. Do not guess if empty or missing — return an error.")


class AgentOutput(BaseModel):
    model_config = ConfigDict(extra='allow')
    streetNumber: str = Field(..., description="The house or building number. Example: '123'. Empty string if not found.")
    preDirectional: str = Field(..., description="The directional prefix before the street name. Values: N, S, E, W, NE, NW, SE, SW. Empty string if not present.")
    streetName: str = Field(..., description="The primary street name without number, direction, or type. Example: 'Main'. Empty string if not found.")
    streetType: str = Field(..., description="The street suffix/type. Examples: St, Ave, Blvd, Dr, Ln, Rd, Ct, Pl, Way, Cir. Abbreviated form preferred. Empty string if not found.")
    postDirectional: str = Field(..., description="The directional suffix after the street name/type. Values: N, S, E, W, NE, NW, SE, SW. Empty string if not present.")
    unitType: str = Field(..., description="The secondary address unit designator. Examples: Apt, Suite, Unit, Bldg, Floor, Rm. Empty string if not present.")
    unitNumber: str = Field(..., description="The secondary address unit number or letter. Example: '4', 'B'. Empty string if not present.")
    city: str = Field(..., description="The city or municipality name. Example: 'Springfield'. Empty string if not found.")
    state: str = Field(..., description="The US state or territory as a 2-letter abbreviation (e.g., 'IL', 'CA'). Empty string if not found.")
    zipCode: str = Field(..., description="The 5-digit ZIP code. Example: '62701'. Empty string if not found.")
    zipPlus4: str = Field(..., description="The 4-digit ZIP+4 extension, without the dash. Example: '1234'. Empty string if not present.")
    country: str = Field(..., description="The country code. Defaults to 'US' if not specified in the input.")
    formattedAddress: str = Field(..., description="The full address reassembled in standard USPS format. Example: '123 N Main St Apt 4, Springfield, IL 62701'.")
    confidence: str = Field(..., description="Confidence level of the parse. 'high' = all key parts found clearly. 'medium' = some parts inferred or ambiguous. 'low' = significant parts missing or unclear.")
    notes: str = Field(..., description="Any warnings, ambiguities, or issues encountered during parsing. Empty string if none.")
    usps_validated: bool = Field(False, description="Whether the address was successfully validated against the USPS API.")
    usps_match_code: str = Field("", description="The USPS address match code from the Addresses v3 API. Empty string if not validated.")

# Agent Messages Function
def create_messages(state: AgentInput) -> Sequence[SystemMessage | HumanMessage]:
    # Extract values safely from state
    address = getattr(state, 'address', '')

    # Apply system prompt template
    current_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    system_prompt_content = """## Role
You are an Address Verification Agent. Your job is to parse a raw address string into its standardized component parts (street number, directional, street name, street type, unit, city, state, ZIP, etc.) and return the result as structured JSON.

## Work Steps
1. Receive the raw address string from the input.
2. Normalize the address: trim whitespace, fix obvious typos in state names or abbreviations, expand or standardize common abbreviations (e.g., \"St\" → \"St\", \"Avenue\" → \"Ave\", \"North\" → \"N\").
3. Parse the address into its component parts:
   - streetNumber: the house/building number.
   - preDirectional: directional prefix before the street name (N, S, E, W, NE, NW, SE, SW).
   - streetName: the primary street name only, without number, direction, or suffix.
   - streetType: the street suffix (St, Ave, Blvd, Dr, Ln, Rd, Ct, Pl, Way, Cir, etc.) in abbreviated form.
   - postDirectional: directional suffix after the street name/type.
   - unitType: secondary designator (Apt, Suite, Unit, Bldg, Floor, Rm, #).
   - unitNumber: the unit number or letter.
   - city: the city or municipality.
   - state: 2-letter US state/territory abbreviation.
   - zipCode: 5-digit ZIP code.
   - zipPlus4: 4-digit ZIP+4 extension (no dash). Empty if not provided.
   - country: defaults to \"US\" unless explicitly stated otherwise.
4. Reassemble the parsed parts into a standardized formattedAddress in USPS format.
5. Assess confidence:
   - \"high\": all key parts (streetNumber, streetName, city, state, zipCode) clearly identified.
   - \"medium\": some parts inferred or ambiguous (e.g., city guessed from ZIP, direction unclear).
   - \"low\": significant parts missing or unparseable.
6. Add any warnings or ambiguities to the notes field.

## Output Rules
- Return ONLY JSON that matches the outputSchema exactly. No extra keys. No markdown. No extra text.
- Every field in the output must be present. Use an empty string \"\" for any component not found or not applicable.
- Do not guess or fabricate address parts that are not present in the input. Use empty string and lower the confidence instead.
- If the input is empty, blank, or clearly not an address, return all fields as empty strings, confidence as \"low\", and explain in notes.

## Final Reminder
Parse the address precisely, return strict JSON matching the outputSchema, and never invent data that is not in the input."""
    system_prompt_content = interpolate_legacy_message(system_prompt_content, state.model_dump())
    enhanced_system_prompt = (
        AGENT_SYSTEM_PROMPT_TEMPLATE
        .replace('{{systemPrompt}}', system_prompt_content)
        .replace('{{currentDate}}', current_date)
        .replace('{{agentName}}', 'Mr Assistant')
    )

    return [
        SystemMessage(content=enhanced_system_prompt),
        HumanMessage(content=interpolate_legacy_message("""## Task
Parse the following raw address into its standardized component parts and return structured JSON.

## Input
- Raw address: <address>{{address}}</address>

## Steps
1. Read the raw address provided above.
2. If the address is empty, blank, or nonsensical, return all fields as empty strings with confidence \"low\" and a note explaining the issue.
3. Normalize the address (trim whitespace, standardize abbreviations).
4. Extract each component: streetNumber, preDirectional, streetName, streetType, postDirectional, unitType, unitNumber, city, state, zipCode, zipPlus4, country.
5. Reassemble into formattedAddress in standard USPS format (e.g., \"123 N Main St Apt 4, Springfield, IL 62701\").
6. Assess confidence level (high, medium, or low) based on how many key parts were clearly identified.
7. Add any warnings or ambiguities to notes.

## Output Rules
- Return ONLY valid JSON matching the outputSchema exactly.
- Every required field must be present. Use empty string \"\" for missing components.
- Do not add any text, markdown, or explanation outside the JSON object.""", state.model_dump())),
    ]

# Create inner react agent graph
_inner_agent = create_agent(model=llm, messages=create_messages, tools=all_tools, input_schema=AgentInput, output_schema=AgentOutput).compile()


# Wrapper state that carries all fields through the graph
class WrapperState(BaseModel):
    model_config = ConfigDict(extra='allow')
    address: str = ""
    streetNumber: str = ""
    preDirectional: str = ""
    streetName: str = ""
    streetType: str = ""
    postDirectional: str = ""
    unitType: str = ""
    unitNumber: str = ""
    city: str = ""
    state: str = ""
    zipCode: str = ""
    zipPlus4: str = ""
    country: str = ""
    formattedAddress: str = ""
    confidence: str = ""
    notes: str = ""
    usps_validated: bool = False
    usps_match_code: str = ""


def _parse_street_components(street_address: str) -> dict:
    """Parse a USPS-returned streetAddress into number, preDirectional, name, type, postDirectional."""
    parts = street_address.strip().split()
    result = {
        "streetNumber": "",
        "preDirectional": "",
        "streetName": "",
        "streetType": "",
        "postDirectional": "",
    }
    if not parts:
        return result

    directionals = {"N", "S", "E", "W", "NE", "NW", "SE", "SW"}
    street_types = {
        "ST", "AVE", "BLVD", "DR", "LN", "RD", "CT", "PL", "WAY", "CIR",
        "TER", "PKWY", "HWY", "SQ", "TRL", "LOOP", "ALY", "WALK",
    }

    idx = 0
    # Street number
    if parts[idx][0].isdigit():
        result["streetNumber"] = parts[idx]
        idx += 1

    if idx >= len(parts):
        return result

    # Pre-directional
    if parts[idx].upper() in directionals:
        result["preDirectional"] = parts[idx].upper()
        idx += 1

    if idx >= len(parts):
        return result

    # Collect remaining to parse name, type, post-directional
    remaining = parts[idx:]

    # Check last token for post-directional
    if len(remaining) > 1 and remaining[-1].upper() in directionals:
        result["postDirectional"] = remaining[-1].upper()
        remaining = remaining[:-1]

    # Check last token for street type
    if len(remaining) > 1 and remaining[-1].upper().rstrip(".") in street_types:
        result["streetType"] = remaining[-1].rstrip(".")
        remaining = remaining[:-1]

    result["streetName"] = " ".join(remaining)
    return result


def _parse_secondary(secondary: str) -> dict:
    """Parse a USPS-returned secondaryAddress into unitType and unitNumber."""
    if not secondary or not secondary.strip():
        return {"unitType": "", "unitNumber": ""}
    parts = secondary.strip().split(None, 1)
    if len(parts) == 2:
        return {"unitType": parts[0], "unitNumber": parts[1]}
    if len(parts) == 1:
        if parts[0][0].isdigit():
            return {"unitType": "", "unitNumber": parts[0]}
        return {"unitType": parts[0], "unitNumber": ""}
    return {"unitType": "", "unitNumber": ""}


def _infer_confidence_from_components(
    street_number: str,
    street_name: str,
    city: str,
    state: str,
    zip_code: str,
) -> str:
    """Infer confidence from core parsed components when USPS has no match."""
    has_street_number = bool(street_number.strip())
    has_street_name = bool(street_name.strip())
    has_city = bool(city.strip())
    has_state = bool(state.strip())
    has_zip = bool(zip_code.strip())

    if has_street_number and has_street_name and has_city and has_state and has_zip:
        return "high"
    if has_street_name and has_city and (has_state or has_zip):
        return "medium"
    return "low"


def _normalize_street_name_and_type(street_name: str, street_type: str) -> tuple[str, str]:
    """Normalize street type from trailing street name token when missing."""
    if street_type.strip():
        return street_name, street_type
    if not street_name.strip():
        return street_name, street_type

    type_map = {
        "STREET": "ST",
        "ST": "ST",
        "AVENUE": "AVE",
        "AVE": "AVE",
        "BOULEVARD": "BLVD",
        "BLVD": "BLVD",
        "DRIVE": "DR",
        "DR": "DR",
        "LANE": "LN",
        "LN": "LN",
        "ROAD": "RD",
        "RD": "RD",
        "COURT": "CT",
        "CT": "CT",
        "PLACE": "PL",
        "PL": "PL",
        "WAY": "WAY",
        "CIRCLE": "CIR",
        "CIR": "CIR",
        "TERRACE": "TER",
        "TER": "TER",
        "PARKWAY": "PKWY",
        "PKWY": "PKWY",
        "HIGHWAY": "HWY",
        "HWY": "HWY",
        "SQUARE": "SQ",
        "SQ": "SQ",
        "TRAIL": "TRL",
        "TRL": "TRL",
        "LOOP": "LOOP",
        "ALLEY": "ALY",
        "ALY": "ALY",
        "WALK": "WALK",
    }

    tokens = street_name.strip().split()
    if not tokens:
        return street_name, street_type

    candidate = tokens[-1].upper().rstrip(".")
    normalized_type = type_map.get(candidate, "")
    if not normalized_type:
        return street_name, street_type

    normalized_name = " ".join(tokens[:-1]).strip()
    if not normalized_name:
        # Keep original if extracting type would erase the street name.
        return street_name, street_type
    return normalized_name, normalized_type


def _looks_like_intersection(street_name: str) -> bool:
    """Detect common intersection-style street name patterns."""
    normalized = re.sub(r"\s+", " ", (street_name or "").strip().lower())
    if not normalized:
        return False
    return " and " in normalized or " & " in normalized


async def agent_node(state: WrapperState) -> dict:
    """Run the inner react agent and extract output fields."""
    result = await _inner_agent.ainvoke({"address": state.address})
    # The inner agent returns AgentOutput fields at the top level
    output_fields = {}
    for field_name in AgentOutput.model_fields:
        if field_name in result:
            output_fields[field_name] = result[field_name]
    return output_fields


async def validate_address_node(state: WrapperState) -> dict:
    """Call the USPS API to validate/correct the parsed address."""
    normalized_street_name, normalized_street_type = _normalize_street_name_and_type(
        state.streetName, state.streetType
    )

    # Build street address from components for the API call
    street_parts = []
    if state.streetNumber:
        street_parts.append(state.streetNumber)
    if state.preDirectional:
        street_parts.append(state.preDirectional)
    if normalized_street_name:
        street_parts.append(normalized_street_name)
    if normalized_street_type:
        street_parts.append(normalized_street_type)
    if state.postDirectional:
        street_parts.append(state.postDirectional)
    street = " ".join(street_parts)

    secondary = ""
    if state.unitType or state.unitNumber:
        secondary = f"{state.unitType} {state.unitNumber}".strip()

    if not street:
        return {
            "notes": (state.notes + " USPS validation skipped: no street address to validate.").strip(),
        }

    usps_state = state.state.strip().upper()[:2] if state.state else ""

    usps_result = await validate_address(
        street=street,
        secondary=secondary,
        city=state.city,
        state=usps_state,
        zip_code=state.zipCode,
        zip_plus4=state.zipPlus4,
    )

    if usps_result is None:
        confidence = _infer_confidence_from_components(
            street_number=state.streetNumber,
            street_name=normalized_street_name or state.streetName,
            city=state.city,
            state=state.state,
            zip_code=state.zipCode,
        )
        notes_suffix = "USPS returned no match (or is temporarily unavailable); keeping parsed values."
        if _looks_like_intersection(normalized_street_name or state.streetName):
            confidence = "low"
            notes_suffix = (
                "Input appears to be an intersection-style location; USPS delivery-point validation is ambiguous. "
                + notes_suffix
            )
        return {
            "streetName": normalized_street_name,
            "streetType": normalized_street_type,
            "confidence": confidence,
            "usps_validated": False,
            "usps_match_code": "",
            "notes": (
                state.notes
                + f" {notes_suffix}"
            ).strip(),
        }

    # Extract the address from USPS response
    addr = usps_result.get("address", {})
    updates: dict = {}

    # Parse street components from USPS response
    usps_street = addr.get("streetAddress", "")
    if usps_street:
        parsed = _parse_street_components(usps_street)
        updates.update(parsed)

    # Parse secondary address
    usps_secondary = addr.get("secondaryAddress", "")
    if usps_secondary:
        sec_parsed = _parse_secondary(usps_secondary)
        updates.update(sec_parsed)
    elif not addr.get("secondaryAddress"):
        updates["unitType"] = state.unitType
        updates["unitNumber"] = state.unitNumber

    # Override city, state, ZIP from USPS
    if addr.get("city"):
        updates["city"] = addr["city"]
    if addr.get("state"):
        updates["state"] = addr["state"]
    if addr.get("ZIPCode"):
        updates["zipCode"] = addr["ZIPCode"]
    if addr.get("ZIPPlus4"):
        updates["zipPlus4"] = addr["ZIPPlus4"]

    # Rebuild formatted address from USPS values
    fmt_parts = []
    sn = updates.get("streetNumber", state.streetNumber)
    pre = updates.get("preDirectional", state.preDirectional)
    name = updates.get("streetName", state.streetName)
    stype = updates.get("streetType", state.streetType)
    post = updates.get("postDirectional", state.postDirectional)
    line1_parts = [p for p in [sn, pre, name, stype, post] if p]
    fmt_parts.append(" ".join(line1_parts))

    ut = updates.get("unitType", state.unitType)
    un = updates.get("unitNumber", state.unitNumber)
    if ut or un:
        fmt_parts[0] += " " + f"{ut} {un}".strip()

    city = updates.get("city", state.city)
    st = updates.get("state", state.state)
    zc = updates.get("zipCode", state.zipCode)
    zp4 = updates.get("zipPlus4", state.zipPlus4)
    city_state_zip = f"{city}, {st} {zc}"
    if zp4:
        city_state_zip += f"-{zp4}"
    fmt_parts.append(city_state_zip)

    updates["formattedAddress"] = ", ".join(fmt_parts) if fmt_parts else state.formattedAddress

    additional_info = usps_result.get("additionalInfo", {})
    dpv = additional_info.get("DPVConfirmation", "")
    match_code = dpv
    updates["usps_match_code"] = match_code

    # DPVConfirmation codes:
    #   Y = Confirmed for both primary and (if present) secondary numbers
    #   D = Confirmed for primary number only; secondary number info was missing
    #   S = Confirmed for primary number only; secondary number was present but not confirmed
    #   N = Both primary and (if present) secondary numbers were not confirmed
    DPV_DESCRIPTIONS = {
        "Y": "Confirmed for both primary and secondary address numbers",
        "D": "Confirmed for primary number only; secondary number info missing",
        "S": "Confirmed for primary number only; secondary number present but not confirmed",
        "N": "Neither primary nor secondary address numbers confirmed",
    }

    is_valid = dpv == "Y"
    updates["usps_validated"] = is_valid
    updates["confidence"] = "high" if is_valid else "medium"

    dpv_desc = DPV_DESCRIPTIONS.get(dpv, f"Unknown DPV code '{dpv}'")
    notes = state.notes
    if is_valid:
        notes_suffix = f"USPS validated (DPVConfirmation: Y — {dpv_desc})."
    else:
        notes_suffix = f"USPS DPVConfirmation: '{dpv}' — {dpv_desc}. Address not fully confirmed."
    updates["notes"] = (notes + " " + notes_suffix).strip()

    return updates


async def output_node(state: WrapperState) -> AgentOutput:
    return AgentOutput(
        streetNumber=state.streetNumber,
        preDirectional=state.preDirectional,
        streetName=state.streetName,
        streetType=state.streetType,
        postDirectional=state.postDirectional,
        unitType=state.unitType,
        unitNumber=state.unitNumber,
        city=state.city,
        state=state.state,
        zipCode=state.zipCode,
        zipPlus4=state.zipPlus4,
        country=state.country,
        formattedAddress=state.formattedAddress,
        confidence=state.confidence,
        notes=state.notes,
        usps_validated=state.usps_validated,
        usps_match_code=state.usps_match_code,
    )


# Build the wrapper graph
builder = StateGraph(WrapperState, input=AgentInput, output=AgentOutput)
builder.add_node("agent", agent_node)
builder.add_node("validate_address", validate_address_node)
builder.add_node("output", output_node)
builder.add_edge(START, "agent")
builder.add_edge("agent", "validate_address")
builder.add_edge("validate_address", "output")
builder.add_edge("output", END)

graph = builder.compile()
