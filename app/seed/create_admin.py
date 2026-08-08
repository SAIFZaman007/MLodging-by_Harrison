"""
Create (or promote) an admin/staff dashboard user.

There is deliberately no public /register endpoint — accounts are provisioned
by whoever controls the server, via this script.

Usage:
    python -m app.seed.create_admin --email chris@8888masters.com --name "Chris Stocks" --role admin
    (you'll be prompted for a password, hidden from terminal echo)
"""
import argparse
import asyncio
import getpass

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.user import User


async def create_admin(email: str, full_name: str, role: UserRole, password: str) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == email.lower()))
        existing = result.scalar_one_or_none()

        if existing:
            existing.hashed_password = hash_password(password)
            existing.full_name = full_name
            existing.role = role
            existing.is_active = True
            print(f"Updated existing user {email} -> role={role.value}")
        else:
            db.add(
                User(
                    email=email.lower(),
                    hashed_password=hash_password(password),
                    full_name=full_name,
                    role=role,
                    is_active=True,
                )
            )
            print(f"Created new user {email} with role={role.value}")

        await db.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create/update an admin dashboard user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True, dest="full_name")
    parser.add_argument("--role", choices=[r.value for r in UserRole], default="admin")
    args = parser.parse_args()

    password = getpass.getpass("Password (min 10 chars, hidden): ")
    if len(password) < 10:
        raise SystemExit("Password must be at least 10 characters.")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        raise SystemExit("Passwords did not match.")

    asyncio.run(create_admin(args.email, args.full_name, UserRole(args.role), password))


if __name__ == "__main__":
    main()
