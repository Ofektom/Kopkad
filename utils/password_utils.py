"""
Utilities for generating and encrypting temporary passwords for admin accounts.
"""
import secrets
import string
from cryptography.fernet import Fernet
from config.settings import settings
import logging
import hashlib

logger = logging.getLogger(__name__)

# Get encryption key from settings or generate one
# In production, set ENCRYPTION_KEY env variable to a stable key
if hasattr(settings, 'ENCRYPTION_KEY') and settings.ENCRYPTION_KEY:
    ENCRYPTION_KEY = settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY
else:
    # Generate a key - WARNING: This will change on restart!
    # For production, always set ENCRYPTION_KEY in environment
    ENCRYPTION_KEY = Fernet.generate_key()
    logger.warning("No ENCRYPTION_KEY in settings - using generated key (will change on restart!)")

cipher = Fernet(ENCRYPTION_KEY)


def generate_secure_password(length: int = 12) -> str:
    """
    Generate a secure random password.
    
    Password includes:
    - Uppercase letters
    - Lowercase letters  
    - Digits
    - Special characters (!@#$%^&*)
    
    Args:
        length: Password length (default 12)
        
    Returns:
        str: Secure random password
        
    Example:
        >>> pwd = generate_secure_password(12)
        >>> len(pwd)
        12
    """
    # Ensure password has at least one of each character type
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    
    # Generate password ensuring it has variety
    password = [
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.digits),
        secrets.choice("!@#$%^&*"),
    ]
    
    # Fill the rest
    password.extend(secrets.choice(alphabet) for _ in range(length - 4))
    
    # Shuffle to randomize position of required characters
    secrets.SystemRandom().shuffle(password)
    
    return ''.join(password)


def encrypt_password(password: str) -> str:
    """
    Encrypt a password for secure storage.
    
    Args:
        password: Plain text password
        
    Returns:
        str: Encrypted password (base64 encoded)
        
    Example:
        >>> encrypted = encrypt_password("MyPassword123!")
        >>> len(encrypted) > len("MyPassword123!")
        True
    """
    try:
        encrypted_bytes = cipher.encrypt(password.encode())
        return encrypted_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to encrypt password: {str(e)}")
        raise ValueError("Password encryption failed")


def decrypt_password(encrypted: str) -> str:
    """
    Decrypt a stored password.
    
    Args:
        encrypted: Encrypted password (base64 encoded)
        
    Returns:
        str: Plain text password
        
    Example:
        >>> encrypted = encrypt_password("MyPassword123!")
        >>> decrypted = decrypt_password(encrypted)
        >>> decrypted == "MyPassword123!"
        True
    """
    try:
        decrypted_bytes = cipher.decrypt(encrypted.encode())
        return decrypted_bytes.decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to decrypt password: {str(e)}")
        raise ValueError("Password decryption failed - password may have been encrypted with different key")


def generate_admin_credentials(business_name: str, unique_code: str):
    """
    Generate admin credentials for a new business.
    
    Args:
        business_name: Name of the business
        unique_code: Business unique code
        
    Returns:
        dict: {
            'phone': Generated phone number,
            'email': Generated email,
            'password': Secure password,
            'pin': First 5 digits of password (for PIN login)
        }
    """
    temp_password = generate_secure_password(12)
    
    # Generate unique identifiers
    admin_phone = f"+234{unique_code}"  # Using business code for uniqueness
    admin_email = f"admin.{unique_code.lower()}@kopkad.com"
    
    return {
        'phone': admin_phone,
        'email': admin_email,
        'password': temp_password,
        'pin': temp_password[:5],  # First 5 chars as PIN
        'full_name': f"{business_name} Admin"
    }

def generate_otp(length=6):
    """Generate a secure 6-digit OTP."""
    return ''.join(secrets.choice('0123456789') for _ in range(length))

def hash_otp(otp: str) -> str:
    """Hash OTP for secure storage (SHA-256)."""
    return hashlib.sha256(otp.encode()).hexdigest()
