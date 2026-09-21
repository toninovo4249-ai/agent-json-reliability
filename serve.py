"""Standalone HTTP server. Independent of Hunter."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> None:
    import uvicorn
    from products.beta.app import create_json_beta_app

    host = os.environ.get("HOST", "127.0.0.1")
    if host not in {"127.0.0.1", "localhost", "::1"} and os.environ.get("PUBLIC_BETA_CONFIRM", "").lower() not in {
        "1",
        "true",
        "yes",
    }:
        raise SystemExit("Refusing non-local bind. Set PUBLIC_BETA_CONFIRM=true explicitly.")
    port = int(os.environ.get("PORT", "8770"))
    print("STATUS=BETA version=0.1.0 PAYMENT_REQUIRED=false FREE_BETA=true")
    print("Set PUBLIC_BASE_URL for OpenAPI/manifest when exposing HTTPS yourself.")
    uvicorn.run(create_json_beta_app(), host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
