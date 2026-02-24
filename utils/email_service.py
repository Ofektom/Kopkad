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
SMTP_PORT_STR = os.getenv("SMTP_PORT", "587")
try:
    SMTP_PORT = int(SMTP_PORT_STR)
except (ValueError, TypeError):
    SMTP_PORT = 587
    logger.warning(f"Invalid SMTP_PORT '{SMTP_PORT_STR}', defaulting to 587")
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME")
BASE_DIR = os.getenv("BASE_DIR") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)

# Initialize template environment with error handling
template_dir = os.path.join(BASE_DIR, "static", "templates")
env = None

try:
    if os.path.exists(template_dir):
        env = Environment(loader=FileSystemLoader(template_dir))
        logger.info(f"Template directory initialized: {template_dir}")
    else:
        logger.warning(f"Template directory not found: {template_dir}. Template-based emails will fail.")
except Exception as e:
    logger.warning(f"Failed to initialize template environment: {str(e)}. Template-based emails will fail.")

# Log settings for debugging (only if available)
if SMTP_HOST:
    logger.info(f"SMTP_HOST: {SMTP_HOST}")
    logger.info(f"SMTP_PORT: {SMTP_PORT}")
    logger.info(f"SMTP_USERNAME: {SMTP_USERNAME}")
if SMTP_PASSWORD:
    logger.info(f"SMTP_PASSWORD: {SMTP_PASSWORD[:4]}****")
    logger.info(f"SMTP_FROM_EMAIL: {SMTP_FROM_EMAIL}")
    logger.info(f"SMTP_FROM_NAME: {SMTP_FROM_NAME}")
else:
    logger.warning("SMTP configuration not found. Email sending will fail.")





# utils/email_service.py
import aiosmtplib
from email.message import EmailMessage
import os
from jinja2 import Environment, FileSystemLoader
from dotenv import load_dotenv
import logging
from typing import Optional

# Load environment variables
load_dotenv()

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# SMTP Configuration
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Kopkad")
BASE_DIR = os.getenv("BASE_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Template environment
template_dir = os.path.join(BASE_DIR, "static", "templates")
env = None
if os.path.exists(template_dir):
    env = Environment(loader=FileSystemLoader(template_dir))
    logger.info(f"Email templates loaded from: {template_dir}")
else:
    logger.warning(f"Email template directory not found: {template_dir}")

# Log config (mask password)
if SMTP_HOST:
    logger.info(f"SMTP Config - Host: {SMTP_HOST}, Port: {SMTP_PORT}, User: {SMTP_USERNAME}, From: {SMTP_FROM_EMAIL}")
else:
    logger.warning("SMTP configuration missing - email sending will fail.")



async def send_email_async(to_email: str, subject: str, html_body: str, text_body: Optional[str] = None):
    """
    Core async email sender using aiosmtplib.
    Supports both HTML and plain text fallback.
    """
    if not all([SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM_EMAIL]):
        logger.error("Incomplete SMTP configuration - cannot send email")
        return {"status": "error", "message": "Email service not configured"}

    message = EmailMessage()
    message["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    message["To"] = to_email
    message["Subject"] = subject

    if html_body:
        message.set_content(text_body or "This email requires HTML support.", subtype="plain")
        message.add_alternative(html_body, subtype="html")
    else:
        message.set_content(text_body or "No content provided.", subtype="plain")


    logger.info(f"Preparing to send email to {to_email}")
    # Log config at INFO level to verify in production (masking password)
    logger.info(f"SMTP Config: Host={SMTP_HOST}, Port={SMTP_PORT}, User={SMTP_USERNAME}, Timeout=60s")
    
    try:
        import asyncio
        logger.info("Initiating SMTP connection...")
        response = await aiosmtplib.send(
            message,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USERNAME,
            password=SMTP_PASSWORD,
            use_tls=False,
            start_tls=True,
            timeout=60,
        )
        logger.info(f"Email sent successfully to {to_email}. Response: {response}")
        return {
            "status": "success",
            "message": f"Email sent successfully to {to_email}.",
        }
    except asyncio.TimeoutError:
        error_msg = f"Timeout connecting to SMTP server {SMTP_HOST}:{SMTP_PORT}. Check network/firewall."
        logger.error(error_msg)
        return {
            "status": "error",
            "message": error_msg,
        }
    except Exception as e:
        logger.exception(f"Failed to send email to {to_email}. ExceptionType: {type(e).__name__}")
        return {
            "status": "error",
            "message": f"Failed to send email to {to_email}. Error: {str(e)}",
        }


async def send_welcome_email(
    to_email: str, user_name: str, phone_number: str, role: str
):
    """Send a welcome email to a new user."""
    if env is None:
        logger.error("Template environment not initialized. Cannot send welcome email.")
        return {
            "status": "error",
            "message": "Email template system not available.",
        }
    try:
        template = env.get_template("welcome_email.html")
        body = template.render(
            user_name=user_name, phone_number=phone_number, role=role, app_name="Kopkad"
        )
        result = await send_email_async(to_email, "Welcome to Kopkad!", body)
        return result
    except Exception as e:
        logger.error(f"Failed to send welcome email: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to send welcome email: {str(e)}",
        }


async def send_business_created_email(
    to_email: str,
    agent_name: str,
    business_name: str,
    unique_code: str,
    created_at: str,
):
    template = env.get_template("business_created_email.html")
    body = template.render(
        agent_name=agent_name,
        business_name=business_name,
        unique_code=unique_code,
        created_at=created_at,
        app_name="Kopkad",
    )
    return await send_email_async(
        to_email, f"New Business Created: {business_name}", body
    )


async def send_business_invitation_email(
    to_email: str,
    customer_name: str,
    business_name: str,
    accept_url: str,
    reject_url: str,
):
    """Send a business invitation email to a customer."""
    if env is None:
        logger.error("Template environment not initialized. Cannot send business invitation email.")
        return {
            "status": "error",
            "message": "Email template system not available.",
        }
    try:
        template = env.get_template("business_invitation_email.html")
        body = template.render(
            customer_name=customer_name,
            business_name=business_name,
            accept_url=accept_url,
            reject_url=reject_url,
            app_name="Kopkad",
        )
        return await send_email_async(to_email, f"Invitation to Join {business_name}", body)
    except Exception as e:
        logger.error(f"Failed to send business invitation email: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to send business invitation email: {str(e)}",
        }


async def send_setup_account_email(
    to_email: str,
    user_name: str,
    business_name: str,
    setup_url: str,
):
    """Send a setup account email to a new cooperative member."""
    if env is None:
        logger.error("Template environment not initialized. Cannot send setup account email.")
        return {
            "status": "error",
            "message": "Email template system not available.",
        }
    try:
        template = env.get_template("setup_account_email.html")
        body = template.render(
            user_name=user_name,
            business_name=business_name,
            setup_url=setup_url,
            app_name="Kopkad",
        )
        return await send_email_async(to_email, f"Welcome to {business_name} - Set Up Your Account", body)
    except Exception as e:
        logger.error(f"Failed to send setup account email: {str(e)}")
        return {
            "status": "error",
            "message": f"Failed to send setup account email: {str(e)}",
        }


async def send_email(to_email: str, subject: str, html_content: str):
    """
    Backwards-compatible helper to send arbitrary HTML emails.
    This is the main export function for Uvicorn and other services.
    """
    return await send_email_async(to_email, subject, html_content)


async def send_reset_password_email_async(to_email: str, full_name: str, reset_url: str):
    """Send password reset email with secure link."""
    if env is None:
        return {"status": "error", "message": "Email template system unavailable"}

    try:
        template = env.get_template("reset_password.html")
        html_body = template.render(
            full_name=full_name or "User",
            reset_url=reset_url,
            app_name="Kopkad",
            expiry_hours=1,
        )
        text_body = (
            f"Hello {full_name or 'User'},\n\n"
            f"You requested a password reset. Click here to set a new PIN:\n{reset_url}\n"
            f"This link expires in 1 hour.\n\n"
            f"If you didn't request this, ignore this email."
        )
        return await send_email_async(to_email, "Kopkad Password Reset", html_body, text_body)
    except Exception as e:
        logger.error(f"Reset password email failed: {str(e)}")
        return {"status": "error", "message": str(e)}


async def send_invitation_email_async(
    to_email: str,
    recipient_name: str,
    business_name: str,
    accept_url: str,
    reject_url: str = None,
):
    """Send business/cooperative invitation email."""
    if env is None:
        return {"status": "error", "message": "Email template system unavailable"}

    try:
        template = env.get_template("business_invitation.html")
        html_body = template.render(
            recipient_name=recipient_name,
            business_name=business_name,
            accept_url=accept_url,
            reject_url=reject_url,
            app_name="Kopkad",
        )
        text_body = (
            f"Hello {recipient_name},\n\n"
            f"You are invited to join {business_name} on Kopkad.\n"
            f"Accept: {accept_url}\n"
            f"Reject: {reject_url or 'Reply to this email'}\n\n"
            f"Best regards,\nKopkad Team"
        )
        return await send_email_async(
            to_email,
            f"Invitation to Join {business_name}",
            html_body,
            text_body
        )
    except Exception as e:
        logger.error(f"Invitation email failed: {str(e)}")
        return {"status": "error", "message": str(e)}



# Explicit exports for better IDE support and Uvicorn imports
__all__ = [
    "send_email",
    "send_email_async",
    "send_welcome_email",
    "send_business_created_email",
    "send_business_invitation_email",
    "send_setup_account_email",
    "send_reset_password_email_async",
    "send_invitation_email_async",
]
