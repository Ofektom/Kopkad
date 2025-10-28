import logging
from sqlalchemy import select, insert, update, text
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from database.postgres_optimized import SessionLocal
from database import get_db_models

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def migrate_old_data(db: Session):
    """Migrate old data to support units, user_units, and pending_business_requests.unit_id."""
    # Get models dynamically
    models = get_db_models()
    User = next(m for m in models if m.__name__ == "User")
    Business = next(m for m in models if m.__name__ == "Business")
    Unit = next(m for m in models if m.__name__ == "Unit")
    PendingBusinessRequest = next(m for m in models if m.__name__ == "PendingBusinessRequest")
    user_units = Unit.__table__.metadata.tables["user_units"]

    try:
        # Step 1: Create default units for businesses without units
        logger.info("Creating default units for businesses...")
        existing_business_ids = db.execute(
            select(Unit.business_id.distinct())
        ).scalars().all()
        existing_business_ids = set(existing_business_ids)

        businesses_without_units = db.execute(
            select(Business.id, Business.name, Business.address)
            .where(Business.id.notin_(existing_business_ids))
        ).all()

        if businesses_without_units:
            units_to_insert = [
                {
                    "name": f"{business.name} Default Unit",
                    "business_id": business.id,
                    "location": business.address,
                    "created_at": datetime.now(timezone.utc),
                    "created_by": None,
                }
                for business in businesses_without_units
            ]
            db.execute(insert(Unit), units_to_insert)
            db.commit()
            logger.info(f"Created {len(units_to_insert)} units.")
        else:
            logger.info("No units to create.")

        # Step 2: Assign users to units
        logger.info("Assigning users to units...")
        user_unit_assignments = db.execute(
            text("""
                SELECT ub.user_id, u.id as unit_id
                FROM user_business ub
                JOIN units u ON u.business_id = ub.business_id
                WHERE NOT EXISTS (
                    SELECT 1 FROM user_units uu
                    WHERE uu.user_id = ub.user_id AND uu.unit_id = u.id
                )
            """)
        ).all()

        if not user_unit_assignments:
            logger.info("No assignments via user_business, falling back to Business.agent_id...")
            user_unit_assignments = db.execute(
                text("""
                    SELECT b.agent_id as user_id, u.id as unit_id
                    FROM businesses b
                    JOIN units u ON u.business_id = b.id
                    WHERE b.agent_id IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1 FROM user_units uu
                        WHERE uu.user_id = b.agent_id AND uu.unit_id = u.id
                    )
                """)
            ).all()

        if user_unit_assignments:
            user_units_to_insert = [
                {"user_id": row.user_id, "unit_id": row.unit_id}
                for row in user_unit_assignments
            ]
            db.execute(insert(user_units), user_units_to_insert)
            db.commit()
            logger.info(f"Assigned {len(user_unit_assignments)} users to units.")
        else:
            logger.info("No user-unit assignments to create.")

        # Step 3: Update pending_business_requests with unit_id
        logger.info("Updating pending_business_requests...")
        updated_rows = db.execute(
            update(PendingBusinessRequest)
            .where(PendingBusinessRequest.unit_id.is_(None))
            .values(
                unit_id=select(Unit.id)
                .where(Unit.business_id == PendingBusinessRequest.business_id)
                .limit(1)
                .scalar_subquery()
            )
        )
        db.commit()
        logger.info(f"Updated {updated_rows.rowcount} pending_business_requests.")

        logger.info("Migration completed successfully.")
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
        db.rollback()
        raise

def main():
    """Run the migration."""
    logger.info("Starting migration of old data...")
    db = SessionLocal()
    try:
        migrate_old_data(db)
    except Exception as e:
        logger.error(f"Migration failed: {str(e)}")
    finally:
        db.close()

if __name__ == "__main__":
    main()