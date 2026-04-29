"""
Run this ONCE to register your agent on Moltbook.

Usage:
    AGENT_NAME="MyAgent" AGENT_DESCRIPTION="What I do" python register.py

After running:
  1. Copy the api_key from the output and save it in GCP Secret Manager as MOLTBOOK_API_KEY
  2. Open the claim_url in your browser and follow the steps (email + tweet verification)
  3. Your agent is live!
"""

import asyncio
import json
import os
import sys
import httpx

BASE_URL = "https://www.moltbook.com/api/v1"


async def main() -> None:
    name = os.environ.get("AGENT_NAME", "").strip()
    description = os.environ.get("AGENT_DESCRIPTION", "").strip()

    if not name:
        print("Error: set AGENT_NAME environment variable")
        sys.exit(1)
    if not description:
        print("Error: set AGENT_DESCRIPTION environment variable")
        sys.exit(1)

    print(f"Registering agent '{name}' on Moltbook...")
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
        r = await c.post(
            "/agents/register",
            headers={"Content-Type": "application/json"},
            json={"name": name, "description": description},
        )
        r.raise_for_status()
        result = r.json()

    agent = result.get("agent", result)
    api_key = agent.get("api_key", "")
    claim_url = agent.get("claim_url", "")
    verification_code = agent.get("verification_code", "")

    print("\n" + "=" * 60)
    print("SUCCESS — Agent registered!")
    print("=" * 60)
    print(f"\n  API Key       : {api_key}")
    print(f"  Claim URL     : {claim_url}")
    print(f"  Verify code   : {verification_code}")
    print("\n⚠️  Save your API key NOW — it won't be shown again.")
    print("\nNext steps:")
    print("  1. Save the api_key to GCP Secret Manager:")
    print(f'     echo -n "{api_key}" | gcloud secrets versions add MOLTBOOK_API_KEY --data-file=-')
    print(f"  2. Open the claim URL in your browser and complete verification:")
    print(f"     {claim_url}")
    print("  3. Re-deploy Cloud Run so it picks up the new secret:")
    print("     cd .. && ./deploy.sh")
    print("=" * 60)

    creds_path = os.path.expanduser("~/.config/moltbook/credentials.json")
    os.makedirs(os.path.dirname(creds_path), exist_ok=True)
    with open(creds_path, "w") as f:
        json.dump({"api_key": api_key, "agent_name": name}, f, indent=2)
    print(f"\nCredentials also saved locally to {creds_path}")


if __name__ == "__main__":
    asyncio.run(main())
