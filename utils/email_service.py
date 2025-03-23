# utils/email_service.py
import aiosmtplib
from email.message import EmailMessage
import os
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv
import logging

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Retrieve SMTP and BASE_DIR settings from environment variables
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME")
BASE_DIR = os.getenv("BASE_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Log settings for debugging
logger.info(f"BASE_DIR: {BASE_DIR}")
logger.info(f"SMTP_HOST: {SMTP_HOST}")
logger.info(f"SMTP_PORT: {SMTP_PORT}")
logger.info(f"SMTP_USERNAME: {SMTP_USERNAME}")
logger.info(f"SMTP_PASSWORD: {SMTP_PASSWORD[:4]}****")
logger.info(f"SMTP_FROM_EMAIL: {SMTP_FROM_EMAIL}")
logger.info(f"SMTP_FROM_NAME: {SMTP_FROM_NAME}")

template_dir = os.path.join(BASE_DIR, "static", "templates")
logger.info(f"Template directory: {template_dir}")
if not os.path.exists(template_dir):
    raise FileNotFoundError(f"Template directory not found: {template_dir}")
if not os.path.isfile(os.path.join(template_dir, "welcome_email.html")):
    raise FileNotFoundError(f"welcome_email.html not found in {template_dir}")
env = Environment(loader=FileSystemLoader(template_dir))

async def send_email_async(to_email: str, subject: str, body: str):
    message = EmailMessage()
    message["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body, subtype="html")
    
    logger.info(f"Sending email to {to_email}")
    try:
        response = await aiosmtplib.send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USERNAME,
            password=SMTP_PASSWORD,
            use_tls=False,
            start_tls=True,
            timeout=10,
        )
        logger.info(f"Email sent to {to_email}. Result: {response}")
        return {"status": "success", "message": f"Email sent successfully to {to_email}."}
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}. Error: {str(e)}")
        return {"status": "error", "message": f"Failed to send email to {to_email}. Error: {str(e)}"}

async def send_welcome_email(to_email: str, user_name: str, phone_number: str, role: str):
    template = env.get_template("welcome_email.html")
    body = template.render(user_name=user_name, phone_number=phone_number, role=role, app_name="Kopkad")
    result = await send_email_async(to_email, "Welcome to Kopkad!", body)
    return result

async def send_business_created_email(to_email: str, agent_name: str, business_name: str, unique_code: str, created_at: str):
    template = env.get_template("business_created_email.html")
    body = template.render(agent_name=agent_name, business_name=business_name, unique_code=unique_code, created_at=created_at, app_name="Kopkad")
    return await send_email_async(to_email, f"New Business Created: {business_name}", body)

async def send_business_invitation_email(to_email: str, customer_name: str, business_name: str, accept_url: str, reject_url: str):
    template = env.get_template("business_invitation_email.html")
    body = template.render(customer_name=customer_name, business_name=business_name, accept_url=accept_url, reject_url=reject_url, app_name="Kopkad")
    return await send_email_async(to_email, f"Invitation to Join {business_name}", body)