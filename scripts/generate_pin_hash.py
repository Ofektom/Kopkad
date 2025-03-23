from utils.auth import hash_password

if __name__ == "__main__":
    pin = "51985"  # Change this if needed
    hashed_pin = hash_password(pin)
    print(hashed_pin)