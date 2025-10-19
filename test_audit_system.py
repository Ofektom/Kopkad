"""
Test script to verify the audit system is working correctly.
Run this script to test audit field behavior.

Usage:
    python test_audit_system.py
"""

import sys
import os
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import Session, declarative_base

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.audit import AuditMixin

# Create a test base
Base = declarative_base()


class TestModel(AuditMixin, Base):
    """Test model to verify audit functionality"""
    __tablename__ = "test_audit_model"
    id = Column(Integer, primary_key=True)
    name = Column(String(100))


def test_audit_on_create():
    """Test that audit fields are set correctly on creation"""
    print("\n=== Test 1: Audit on Create ===")
    
    # Test with explicit created_at
    item1 = TestModel(
        name="Test Item 1",
        created_by=1,
        created_at=datetime.now(timezone.utc)
    )
    
    assert item1.created_by == 1, "created_by should be set"
    assert item1.created_at is not None, "created_at should be set"
    print("✓ Explicit created_at: PASSED")
    
    # Test with automatic created_at
    item2 = TestModel(
        name="Test Item 2",
        created_by=2
    )
    # Simulate the before_insert event
    from models.audit import receive_before_insert
    receive_before_insert(None, None, item2)
    
    assert item2.created_by == 2, "created_by should be set"
    assert item2.created_at is not None, "created_at should be auto-set"
    print("✓ Automatic created_at: PASSED")
    
    print("✓ Test 1: PASSED - Audit fields set correctly on create\n")


def test_audit_on_update():
    """Test that audit fields are updated correctly on update"""
    print("=== Test 2: Audit on Update ===")
    
    # Create an item
    item = TestModel(
        name="Original Name",
        created_by=1,
        created_at=datetime.now(timezone.utc)
    )
    
    original_created_at = item.created_at
    original_created_by = item.created_by
    
    # Simulate an update
    import time
    time.sleep(0.1)  # Ensure time difference
    
    item.name = "Updated Name"
    item.updated_by = 2
    
    # Simulate the before_update event
    from models.audit import receive_before_update
    receive_before_update(None, None, item)
    
    assert item.updated_at is not None, "updated_at should be auto-set"
    assert item.updated_by == 2, "updated_by should be set"
    assert item.created_at == original_created_at, "created_at should not change"
    assert item.created_by == original_created_by, "created_by should not change"
    assert item.updated_at > original_created_at, "updated_at should be after created_at"
    
    print("✓ updated_at automatically set: PASSED")
    print("✓ updated_by preserved: PASSED")
    print("✓ created_* fields unchanged: PASSED")
    print("✓ Test 2: PASSED - Audit fields updated correctly\n")


def test_timezone_consistency():
    """Test that all timestamps use UTC timezone"""
    print("=== Test 3: Timezone Consistency ===")
    
    item = TestModel(
        name="Test Timezone",
        created_by=1,
        created_at=datetime.now(timezone.utc)
    )
    
    # Simulate update
    from models.audit import receive_before_update
    item.updated_by = 2
    receive_before_update(None, None, item)
    
    assert item.created_at.tzinfo == timezone.utc, "created_at should use UTC"
    assert item.updated_at.tzinfo == timezone.utc, "updated_at should use UTC"
    
    print("✓ All timestamps use UTC timezone: PASSED")
    print("✓ Test 3: PASSED - Timezone consistency verified\n")


def test_multiple_updates():
    """Test that updated_at changes on each update"""
    print("=== Test 4: Multiple Updates ===")
    
    item = TestModel(
        name="Original",
        created_by=1,
        created_at=datetime.now(timezone.utc)
    )
    
    from models.audit import receive_before_update
    import time
    
    # First update
    time.sleep(0.1)
    item.name = "Update 1"
    item.updated_by = 2
    receive_before_update(None, None, item)
    first_update = item.updated_at
    
    # Second update
    time.sleep(0.1)
    item.name = "Update 2"
    item.updated_by = 3
    receive_before_update(None, None, item)
    second_update = item.updated_at
    
    assert first_update is not None, "First update should set updated_at"
    assert second_update is not None, "Second update should set updated_at"
    assert second_update > first_update, "updated_at should increase with each update"
    assert item.updated_by == 3, "updated_by should reflect last updater"
    
    print("✓ updated_at changes on each update: PASSED")
    print("✓ updated_by tracks last updater: PASSED")
    print("✓ Test 4: PASSED - Multiple updates tracked correctly\n")


def test_null_handling():
    """Test handling of null values"""
    print("=== Test 5: Null Handling ===")
    
    # Create without created_at (should auto-set)
    item = TestModel(
        name="Test Null",
        created_by=1
    )
    
    from models.audit import receive_before_insert
    receive_before_insert(None, None, item)
    
    assert item.created_at is not None, "created_at should be auto-set if not provided"
    assert item.updated_at is None, "updated_at should be None for new records"
    assert item.updated_by is None, "updated_by should be None for new records"
    
    print("✓ Auto-set created_at when None: PASSED")
    print("✓ updated_* fields remain None for new records: PASSED")
    print("✓ Test 5: PASSED - Null handling correct\n")


def run_all_tests():
    """Run all audit system tests"""
    print("\n" + "="*60)
    print("AUDIT SYSTEM TEST SUITE")
    print("="*60)
    
    try:
        test_audit_on_create()
        test_audit_on_update()
        test_timezone_consistency()
        test_multiple_updates()
        test_null_handling()
        
        print("="*60)
        print("ALL TESTS PASSED ✓")
        print("="*60)
        print("\nThe audit system is working correctly!")
        print("\nKey Features Verified:")
        print("  ✓ Automatic created_at setting")
        print("  ✓ Automatic updated_at setting on every update")
        print("  ✓ Preservation of created_by and updated_by")
        print("  ✓ UTC timezone consistency")
        print("  ✓ Multiple updates tracked correctly")
        print("  ✓ Proper null handling")
        print("\n")
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return False
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

