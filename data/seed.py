#!/usr/bin/env python3
"""Seed database and prepare data for Samsara Atlas."""

import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.storage.database import init_db, SessionLocal
from app.storage.models import EmployeeRecord


def load_fixture():
    fixture_path = os.path.join(os.path.dirname(__file__), "employee_fixture.json")
    with open(fixture_path) as f:
        return json.load(f)


def seed_employee_records(db, fixture):
    for emp in fixture["employees"]:
        existing = db.query(EmployeeRecord).filter_by(employee_id=emp["employee_id"]).first()
        if not existing:
            db.add(EmployeeRecord(
                employee_id=emp["employee_id"],
                metadata_json=json.dumps(emp["metadata"]),
                last_activities_json=json.dumps(emp["last_activities"]),
            ))
    db.commit()


def main():
    init_db()
    fixture = load_fixture()
    db = SessionLocal()
    try:
        seed_employee_records(db, fixture)
        print("Seeded employee records successfully.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
