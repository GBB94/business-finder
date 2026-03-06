#!/usr/bin/env python3
"""Create a user account. Intended for first-run bootstrap.

Usage:
    python scripts/create_user.py user@example.com
    docker compose exec api python scripts/create_user.py user@example.com
"""
from __future__ import annotations

import getpass
import sys

from passlib.hash import bcrypt

from app.database import SessionLocal
from app.models.user import User


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/create_user.py <email> [display_name]")
        sys.exit(1)

    email = sys.argv[1]
    display_name = sys.argv[2] if len(sys.argv) > 2 else email.split("@")[0]

    db = SessionLocal()

    existing = db.query(User).filter_by(email=email).first()
    if existing:
        print(f"User {email} already exists (id={existing.id})")
        db.close()
        sys.exit(1)

    password = getpass.getpass("Password: ")
    if not password:
        print("Password cannot be empty.")
        db.close()
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.")
        db.close()
        sys.exit(1)

    user = User(
        email=email,
        display_name=display_name,
        password_hash=bcrypt.hash(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"Created user {user.email} (id={user.id})")

    # Seed default scoring weights for this user
    from app.models.config import ScoringWeight, DEFAULT_WEIGHTS

    for dimension, weight in DEFAULT_WEIGHTS.items():
        db.add(ScoringWeight(user_id=user.id, dimension=dimension, weight=weight))
    db.commit()
    print(f"Seeded scoring weights ({len(DEFAULT_WEIGHTS)} dimensions)")

    db.close()


if __name__ == "__main__":
    main()
