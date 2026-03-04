import os
import time
from typing import Any, Optional
import dotenv
import httpx

dotenv.load_dotenv()

USPS_OAUTH_URL = "https://apis.usps.com/oauth2/v3/token"
USPS_ADDRESS_URL = "https://apis.usps.com/addresses/v3/address"

_cached_token: Optional[str] = None
_token_expires_at: float = 0.0



async def get_usps_token() -> str:
    print("Getting USPS token")
    global _cached_token, _token_expires_at

    if _cached_token and time.time() < _token_expires_at:
        print("Using cached token")
        print(_cached_token)
        return _cached_token

    client_id = os.environ.get("USPS_CONSUMER_KEY", "")

    client_secret = os.environ.get("USPS_CONSUMER_SECRET", "")

    if not client_id or not client_secret:
        print("Client ID or secret is not set")
        raise ValueError("USPS_CONSUMER_KEY and USPS_CONSUMER_SECRET must be set")

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