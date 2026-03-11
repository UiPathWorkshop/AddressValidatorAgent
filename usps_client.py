import os
import time
from typing import Any, Optional
import dotenv
import httpx
from uipath.tracing import traced

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(dotenv_path=os.path.join(_PROJECT_ROOT, ".env"))

USPS_OAUTH_URL = "https://apis.usps.com/oauth2/v3/token"
USPS_ADDRESS_URL = "https://apis.usps.com/addresses/v3/address"

_cached_token: Optional[str] = None
_token_expires_at: float = 0.0


def _first_env(*names: str) -> str:
    """Return first non-empty environment variable from provided names."""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""



async def get_usps_token() -> str:
    print("Getting USPS token")
    global _cached_token, _token_expires_at

    if _cached_token and time.time() < _token_expires_at:
        print("Using cached token")
        return _cached_token

    client_id = _first_env("USPS_CONSUMER_KEY", "USPS_CLIENT_ID", "USPS_CONSUMER_ID")
    client_secret = _first_env(
        "USPS_CONSUMER_SECRET", "USPS_CLIENT_SECRET", "USPS_CONSUMER_PASSWORD"
    )

    if not client_id or not client_secret:
        print("USPS credentials are not fully configured")
        raise ValueError(
            "Missing USPS credentials. Set USPS_CONSUMER_KEY and USPS_CONSUMER_SECRET."
        )

    async with httpx.AsyncClient() as client:
        print("Posting to USPS OAuth URL")
        resp = await client.post(
            USPS_OAUTH_URL,
            json={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
            },
            headers={"Content-Type": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()

    _cached_token = data["access_token"]
    _token_expires_at = time.time() + data.get("expires_in", 3600) - 60
    return _cached_token


@traced(name="validate_address", span_type="tool")
async def validate_address(
    street: str,
    secondary: str = "",
    city: str = "",
    state: str = "",
    zip_code: str = "",
    zip_plus4: str = "",
) -> Optional[dict[str, Any]]:
    try:
        token = await get_usps_token()

    except Exception:
        return None

    params: dict[str, str] = {"streetAddress": street}
    if secondary:
        params["secondaryAddress"] = secondary
    if city:
        params["city"] = city
    if state:
        params["state"] = state
    if zip_code:
        params["ZIPCode"] = zip_code
    if zip_plus4:
        params["ZIPPlus4"] = zip_plus4

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                USPS_ADDRESS_URL,
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10.0,
            )
            print("Response: ", resp.json())
            resp.raise_for_status()
            print(resp.json())
            return resp.json()
    except Exception:
        return None

if __name__ == "__main__":
    import asyncio
    print("--------------------------------")
    print("Starting validation")
    result = asyncio.run(validate_address("6492 e sun circle", "", "tucson", "AZ", "85750",""))
    print("--------------------------------")
    print(result)