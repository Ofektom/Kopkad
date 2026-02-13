
import sys
import os
from pathlib import Path

# Add the parent directory to python path to allow imports
current_dir = Path(__file__).resolve().parent
parent_dir = current_dir.parent
sys.path.append(str(parent_dir))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv(current_dir.parent / ".env")

from models.savings import SavingsAccount, SavingsMarking, SavingsStatus, SavingsType
from models.savings_group import SavingsGroup, GroupFrequency
from models.expenses import ExpenseCard 
from models.payments import Commission
from models.business import Business
from models.user import User
from models.settings import Settings as UserSettings

from database.postgres_optimized import Base
from config.settings import settings
from database.postgres_optimized import Base
from config.settings import settings

# Setup DB connection
# Assuming settings.POSTGRES_URI is available
DATABASE_URL = settings.POSTGRES_URI
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def backfill_group_markings():
    db = SessionLocal()
    try:
        print("Starting backfill for group savings markings...")
        
        # Get all savings accounts that belong to a group (cooperative)
        # and checking if they have markings is a good idea, but simple approach is to check
        # if they have 0 markings.
        
        # Debug: Print all savings groups
        all_groups = db.query(SavingsGroup).all()
        print(f"Total savings groups in DB: {len(all_groups)}")
        for g in all_groups:
             print(f"  - Group ID: {g.id}, Name: {g.name}, Frequency: {g.frequency}")

        # Debug: Print all savings accounts
        all_savings = db.query(SavingsAccount).all()
        print(f"Total savings accounts in DB: {len(all_savings)}")
        for s in all_savings:
            print(f"  - ID: {s.id}, Type: {s.savings_type}, GroupID: {s.group_id}, Tracking: {s.tracking_number}")

        savings_accounts = db.query(SavingsAccount).filter(
            SavingsAccount.group_id.isnot(None)
        ).all()
        
        print(f"Found {len(savings_accounts)} savings accounts with group_id.")
        
        for account in savings_accounts:
            # Check if markings exist
            existing_markings_count = db.query(SavingsMarking).filter(
                SavingsMarking.savings_account_id == account.id
            ).count()
            
            if existing_markings_count > 0:
                print(f"Account {account.tracking_number} already has {existing_markings_count} markings. Skipping.")
                continue
                
            group = db.query(SavingsGroup).filter(SavingsGroup.id == account.group_id).first()
            if not group:
                print(f"Warning: Group not found for account {account.tracking_number}. Skipping.")
                continue
                
            print(f"Generating markings for account {account.tracking_number} (Group: {group.name}, Freq: {group.frequency})")
            
            current_date = account.start_date
            # Use account end_date if available, otherwise calculate from duration or group end_date
            end_date = account.end_date
            if not end_date:
                if group.end_date:
                    end_date = group.end_date
                else:
                    # Fallback to duration months from account
                    end_date = account.start_date + relativedelta(months=account.duration_months)
            
            markings = []
            while current_date <= end_date:
                marking = SavingsMarking(
                    savings_account_id=account.id,
                    unit_id=None,
                    marked_date=current_date,
                    amount=group.contribution_amount,
                    status=SavingsStatus.PENDING,
                )
                markings.append(marking)

                if group.frequency == GroupFrequency.WEEKLY:
                    current_date += relativedelta(weeks=1)
                elif group.frequency == GroupFrequency.BI_WEEKLY:
                    current_date += relativedelta(weeks=2)
                elif group.frequency == GroupFrequency.MONTHLY:
                    current_date += relativedelta(months=1)
                elif group.frequency == GroupFrequency.QUARTERLY:
                    current_date += relativedelta(months=3)
                else:
                    current_date += relativedelta(months=1)
            
            if markings:
                db.add_all(markings)
                print(f"  -> Added {len(markings)} markings.")
            else:
                print("  -> No markings generated (date range issue?).")
                
        db.commit()
        print("Backfill completed successfully.")
        
    except Exception as e:
        print(f"Error during backfill: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    backfill_group_markings()
