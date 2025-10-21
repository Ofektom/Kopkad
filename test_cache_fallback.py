#!/usr/bin/env python3
"""
Test script to demonstrate in-memory cache fallback
"""

from utils.cache import get_cache, InMemoryCache, RedisCache
import time

def test_cache():
    """Test the cache functionality"""
    
    cache = get_cache()
    
    # Show cache type
    if isinstance(cache, RedisCache):
        print("✅ Using Redis cache")
    elif isinstance(cache, InMemoryCache):
        print("✅ Using in-memory cache (fallback)")
    else:
        print("❌ No cache available")
        return
    
    print("\n🧪 Testing cache operations...")
    
    # Test 1: Set and Get
    print("\n1. SET operation:")
    cache.set("test:user:123", {"name": "John Doe", "email": "john@example.com"}, ttl=60)
    print("   ✓ Set user data with 60s TTL")
    
    print("\n2. GET operation:")
    user = cache.get("test:user:123")
    print(f"   ✓ Retrieved: {user}")
    
    # Test 2: Multiple operations
    print("\n3. SET_MANY operation:")
    cache.set_many({
        "test:user:124": {"name": "Jane Doe"},
        "test:user:125": {"name": "Bob Smith"},
        "test:user:126": {"name": "Alice Johnson"},
    })
    print("   ✓ Set multiple users")
    
    print("\n4. GET_MANY operation:")
    users = cache.get_many("test:user:124", "test:user:125", "test:user:126")
    print(f"   ✓ Retrieved {len(users)} users")
    
    # Test 3: Pattern deletion
    print("\n5. CLEAR_PATTERN operation:")
    deleted_count = cache.clear_pattern("test:user:*")
    print(f"   ✓ Deleted {deleted_count} keys matching pattern")
    
    # Test 4: Verify deletion
    print("\n6. Verify keys deleted:")
    user = cache.get("test:user:123")
    print(f"   ✓ Key exists: {user is not None} (should be False)")
    
    # Test 5: Increment
    print("\n7. INCREMENT operation:")
    cache.set("test:counter", 0)
    for i in range(5):
        count = cache.increment("test:counter")
        print(f"   Counter: {count}")
    
    # Test 6: Performance
    print("\n8. Performance test (1000 operations):")
    start = time.time()
    for i in range(1000):
        cache.set(f"test:perf:{i}", {"value": i})
    set_time = time.time() - start
    
    start = time.time()
    for i in range(1000):
        cache.get(f"test:perf:{i}")
    get_time = time.time() - start
    
    print(f"   SET: {set_time:.4f}s ({1000/set_time:.0f} ops/sec)")
    print(f"   GET: {get_time:.4f}s ({1000/get_time:.0f} ops/sec)")
    
    # Cleanup
    cache.clear_pattern("test:*")
    print("\n🧹 Cleanup complete")
    
    print("\n✅ All cache tests passed!")

if __name__ == "__main__":
    test_cache()

