import bcrypt

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


if __name__ == "__main__":
    pin = "51985"
    hashed_pin = hash_password(pin)
    print(hashed_pin)
