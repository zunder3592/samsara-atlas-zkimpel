#!/usr/bin/env python3
"""Load test: 200 concurrent POST /cases with same idempotency_key.
Expects: 1 case, 1 case note. Reveals idempotency race and duplicate case notes."""

import concurrent.futures
import requests
import time

API_BASE = "http://localhost:8000"
IDEMPOTENCY_KEY = "load-test-same-key"
CONCURRENT_REQUESTS = 200

payload = {
    "inputs": {
        "employee_id": "E10234",
        "case_transcript": "Load test case transcript.",
        "tone": "empathetic",
    },
    "idempotency_key": IDEMPOTENCY_KEY,
}


def post_case():
    try:
        resp = requests.post(f"{API_BASE}/cases", json=payload, timeout=60)
        return resp.status_code, resp.json() if resp.ok else None
    except Exception as e:
        return None, str(e)


def main():
    print("Checking API...")
    try:
        r = requests.get(f"{API_BASE}/cases", timeout=5)
        if r.status_code != 200:
            print("API not ready. Run 'make api' first.")
            return 1
    except requests.exceptions.ConnectionError:
        print("API not running. Run 'make api' first.")
        return 1

    print(f"Firing {CONCURRENT_REQUESTS} concurrent POST /cases with idempotency_key={IDEMPOTENCY_KEY}")
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=50) as ex:
        futures = [ex.submit(post_case) for _ in range(CONCURRENT_REQUESTS)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    elapsed = time.time() - start
    print(f"Completed in {elapsed:.2f}s")

    case_ids = set()
    for status, data in results:
        if data and isinstance(data, dict) and "case_id" in data:
            case_ids.add(data["case_id"])

    cases_resp = requests.get(f"{API_BASE}/cases", timeout=10)
    all_cases = cases_resp.json().get("case_ids", []) if cases_resp.ok else []

    total_case_notes = 0
    for case_id in list(case_ids)[:100]:
        try:
            r = requests.get(f"{API_BASE}/cases/{case_id}", timeout=5)
            if r.ok:
                total_case_notes += len(r.json().get("case_notes", []))
        except Exception:
            pass

    cases_with_same_key = len(case_ids)
    print("")
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Expected cases for idempotency_key: 1")
    print(f"Actual cases created (unique case_ids from responses): {cases_with_same_key}")
    if cases_with_same_key > 1:
        print(f"  *** DUPLICATES DETECTED: {cases_with_same_key} cases for same idempotency key! ***")
    print(f"Expected case notes: 1")
    print(f"Actual case notes (sum across returned cases): {total_case_notes}")
    if total_case_notes > 1:
        print(f"  *** DUPLICATES DETECTED: {total_case_notes} case notes! In production this could mean an employee ***")
        print(f"      sees conflicting HR responses, or receives a duplicate outbound communication. ***")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    exit(main())
