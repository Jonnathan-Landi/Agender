from __future__ import annotations

import argparse, base64, json, sys
from datetime import UTC, datetime
from pathlib import Path

from argon2 import PasswordHasher
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "license-authority" / "license_private_key.pem"
PUBLIC = ROOT / "backend" / "security" / "license_public_key.pem"
MODULES = {"hydromet", "requests", "diary", "agenda"}

def canonical(payload):
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()

def keys():
    if not PRIVATE.exists():
        key=Ed25519PrivateKey.generate(); PRIVATE.parent.mkdir(parents=True,exist_ok=True); PUBLIC.parent.mkdir(parents=True,exist_ok=True)
        PRIVATE.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        PUBLIC.write_bytes(key.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo))
    return serialization.load_pem_private_key(PRIVATE.read_bytes(),password=None)

def main():
    parser=argparse.ArgumentParser(description="Generador privado de licencias Agender")
    parser.add_argument("output",type=Path); parser.add_argument("--id",required=True); parser.add_argument("--customer",required=True)
    parser.add_argument("--modules",nargs="+",choices=sorted(MODULES),default=sorted(MODULES)); parser.add_argument("--expires")
    parser.add_argument("--username",required=True); parser.add_argument("--password",required=True); parser.add_argument("--admin",action="store_true")
    args=parser.parse_args(); key=keys()
    selected=set(MODULES if args.admin else args.modules)
    if "hydromet" in selected: selected.update({"viewer", "settings"})
    selected=sorted(selected)
    payload={"version":1,"licenseId":args.id,"customer":args.customer,"issuedAt":datetime.now(UTC).date().isoformat(),
             "expiresAt":args.expires,"modules":selected,"provision":{"username":args.username,"passwordHash":PasswordHasher().hash(args.password),"role":"admin" if args.admin else "user"}}
    payload["signature"]=base64.b64encode(key.sign(canonical(payload))).decode(); args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Licencia creada: {args.output}\nClave pública: {PUBLIC}")
if __name__=="__main__": main()
