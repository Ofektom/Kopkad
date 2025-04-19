# test_email.py
import aiosmtplib
from email.message import EmailMessage
import asyncio
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


async def test_email():
    # Retrieve SMTP settings from environment variables
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT"))
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_from_email = os.getenv("SMTP_FROM_EMAIL")
    smtp_from_name = os.getenv("SMTP_FROM_NAME")

    # Log settings for debugging
    print(f"SMTP_HOST: {smtp_host}")
    print(f"SMTP_PORT: {smtp_port}")
    print(f"SMTP_USERNAME: {smtp_username}")
    print(f"SMTP_PASSWORD: {smtp_password[:4]}****")  # Mask most of the password
    print(f"SMTP_FROM_EMAIL: {smtp_from_email}")
    print(f"SMTP_FROM_NAME: {smtp_from_name}")

    message = EmailMessage()
    message["From"] = f"{smtp_from_name} <{smtp_from_email}>"
    message["To"] = smtp_username  # Sending to self for testing
    message["Subject"] = "Test Email"
    message.set_content("<h1>Hello, this is a test!</h1>", subtype="html")

    try:
        response = await aiosmtplib.send(
            message,
            hostname=smtp_host,
            port=smtp_port,
            username=smtp_username,
            password=smtp_password,
            use_tls=False,
            start_tls=True,
        )
        print(f"Success: {response}")
    except Exception as e:
        print(f"Error: {str(e)}")


if __name__ == "__main__":
    asyncio.run(test_email())
