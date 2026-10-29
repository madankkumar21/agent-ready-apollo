"""Local identity provider for the demo: an RSA key, a JWKS file the router
reads, and two tokens.

  agent: campaign:read proposal:write
  human: campaign:read proposal:write pii:read budget:write

`uv run python -m auth.tokens` writes auth/jwks.json, auth/private.pem and
auth/agent.jwt / auth/human.jwt (all gitignored except this script).
"""

import json
import time
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

HERE = Path(__file__).parent
KID = "demo-key-1"
SCOPES = {
    "agent": "campaign:read proposal:write",
    "human": "campaign:read proposal:write pii:read budget:write",
}


def main():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    (HERE / "private.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
    jwk.update({"kid": KID, "alg": "RS256", "use": "sig"})
    (HERE / "jwks.json").write_text(json.dumps({"keys": [jwk]}, indent=2))
    now = int(time.time())
    for who, scope in SCOPES.items():
        token = jwt.encode({"sub": who, "scope": scope, "iat": now, "exp": now + 30 * 24 * 3600},
                           key, algorithm="RS256", headers={"kid": KID})
        (HERE / f"{who}.jwt").write_text(token)
    print("wrote", ", ".join(p.name for p in sorted(HERE.glob("*.j*"))))


if __name__ == "__main__":
    main()
