#!/usr/bin/env python3
"""
Fully automated Porkbun + Resend domain setup for transactional email.

Usage:
  export PORKBUN_API_KEY=pk1_...
  export PORKBUN_SECRET_KEY=sk1_...
  export RESEND_API_KEY=re_...
  export DOMAIN=thecampus.app          # domain to register
  python scripts/setup_email_domain.py

What this script does:
  1. (Optional) Check domain availability on Porkbun
  2. Register the domain on Porkbun
  3. Add the domain to Resend and retrieve required DNS records
  4. Create those DNS records in Porkbun's nameservers
  5. Trigger domain verification on Resend
  6. Print the result

Requirements:
  pip install requests
"""

import json
import os
import sys
import time

import requests

PORKBUN_BASE = "https://porkbun.com/api/json/v3"
RESEND_BASE = "https://api.resend.com"

PORKBUN_API_KEY = os.environ["PORKBUN_API_KEY"]
PORKBUN_SECRET_KEY = os.environ["PORKBUN_SECRET_KEY"]
RESEND_API_KEY = os.environ["RESEND_API_KEY"]
DOMAIN = os.environ["DOMAIN"]

PB_AUTH = {"apikey": PORKBUN_API_KEY, "secretapikey": PORKBUN_SECRET_KEY}
RS_HEADERS = {"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"}


# ── helpers ──────────────────────────────────────────────────────────────────

def pb_post(path: str, payload: dict) -> dict:
    resp = requests.post(f"{PORKBUN_BASE}{path}", json={**PB_AUTH, **payload}, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    if data.get("status") != "SUCCESS":
        raise RuntimeError(f"Porkbun error on {path}: {data}")
    return data


def rs_post(path: str, payload: dict) -> dict:
    resp = requests.post(f"{RESEND_BASE}{path}", headers=RS_HEADERS, json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def rs_get(path: str) -> dict:
    resp = requests.get(f"{RESEND_BASE}{path}", headers=RS_HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.json()


# ── step 1: check availability ────────────────────────────────────────────────

def check_availability() -> None:
    print(f"[1/5] Checking availability of {DOMAIN} ...")
    data = pb_post(f"/domain/checkAndGetPricing/{DOMAIN}", {})
    print(f"      Available ✓  (registration: ${data['pricing']['registration']})")


# ── step 2: register domain ───────────────────────────────────────────────────

def register_domain() -> None:
    print(f"[2/5] Registering {DOMAIN} on Porkbun ...")
    # Porkbun API registration requires whois contact data
    # These are generic defaults — update if needed
    payload = {
        "years": 1,
        "firstName": "The",
        "lastName": "Campus",
        "address1": "123 Main St",
        "city": "Almaty",
        "state": "Almaty",
        "zip": "050000",
        "country": "KZ",
        "phone": "+7.7271234567",
        "email": "admin@thecampus.app",
    }
    pb_post(f"/domain/create/{DOMAIN}", payload)
    print(f"      Registered ✓")


# ── step 3: add domain to Resend ──────────────────────────────────────────────

def add_to_resend() -> dict:
    print(f"[3/5] Adding {DOMAIN} to Resend ...")
    data = rs_post("/domains", {"name": DOMAIN})
    print(f"      Created Resend domain (id={data['id']}) ✓")
    return data  # contains id + records[]


# ── step 4: set DNS records via Porkbun ───────────────────────────────────────

def set_dns_records(resend_domain: dict) -> None:
    print(f"[4/5] Setting DNS records in Porkbun ...")
    records = resend_domain.get("records", [])
    if not records:
        print("      Warning: Resend returned no DNS records — verify manually in Resend dashboard")
        return

    for rec in records:
        rec_type = rec["type"]        # TXT, CNAME, MX
        rec_name = rec["name"]        # e.g. "resend._domainkey" or "@"
        rec_value = rec["value"]
        rec_ttl = str(rec.get("ttl", 300))

        # Porkbun wants subdomain part only (without the base domain)
        subdomain = rec_name.replace(f".{DOMAIN}", "").replace(DOMAIN, "")

        payload = {
            "type": rec_type,
            "name": subdomain,
            "content": rec_value,
            "ttl": rec_ttl,
        }
        pb_post(f"/dns/create/{DOMAIN}", payload)
        print(f"      {rec_type} {subdomain or '@'} → {rec_value[:40]}... ✓")


# ── step 5: trigger verification ─────────────────────────────────────────────

def trigger_verification(domain_id: str) -> None:
    print(f"[5/5] Triggering Resend domain verification ...")
    # Wait a bit for DNS to propagate before verifying
    time.sleep(5)
    rs_post(f"/domains/{domain_id}/verify", {})
    print(f"      Verification triggered ✓")
    print()

    # Check status
    data = rs_get(f"/domains/{domain_id}")
    status = data.get("status", "unknown")
    print(f"  Domain status: {status}")
    if status == "verified":
        print(f"  ✅ {DOMAIN} is fully verified. Set RESEND_API_KEY and EMAIL_FROM_DOMAIN={DOMAIN} in Railway env vars.")
    else:
        print(f"  ⏳ DNS propagation can take up to 24h. Run this to re-check:")
        print(f"     curl -H 'Authorization: Bearer {RESEND_API_KEY}' {RESEND_BASE}/domains/{domain_id}")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{'='*60}")
    print(f"  The Campus — Email domain setup: {DOMAIN}")
    print(f"{'='*60}\n")

    skip_registration = "--skip-registration" in sys.argv

    if not skip_registration:
        check_availability()
        register_domain()
    else:
        print("[1/5] Skipped availability check (--skip-registration)")
        print("[2/5] Skipped registration (--skip-registration)")

    resend_domain = add_to_resend()
    set_dns_records(resend_domain)
    trigger_verification(resend_domain["id"])

    print(f"\n{'='*60}")
    print("  Done! Next steps:")
    print(f"  1. Set RESEND_API_KEY={RESEND_API_KEY[:8]}... in Railway backend env vars")
    print(f"  2. Set EMAIL_FROM_DOMAIN={DOMAIN} in Railway backend env vars")
    print(f"  3. Set FRONTEND_URL=https://the-campus-frontend-production.up.railway.app in Railway backend env vars")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
