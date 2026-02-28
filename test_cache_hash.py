import hashlib

def cache_key(*args, **kwargs) -> str:
    def _is_cacheable(obj):
        if hasattr(obj, "__class__"):
            c_name = obj.__class__.__name__
            if c_name in {"Session", "SessionLocal", "BackgroundTasks"} or \
               c_name.endswith("Repository"):
                return False
        return True

    filtered_args = tuple(arg for arg in args if _is_cacheable(arg))
    filtered_kwargs = {k: v for k, v in kwargs.items() if _is_cacheable(v)}
    
    key_data = str(filtered_args) + str(sorted(filtered_kwargs.items()))
    print(f"Key data: {key_data}")
    return hashlib.md5(key_data.encode()).hexdigest()

print("User 1:")
print(cache_key("1", None, tracking_number="123", business_id=None))
print("User 2:")
print(cache_key("2", None, tracking_number="123", business_id=None))

print("Metrics User 1:")
print(cache_key("1", None, tracking_number=None, business_id=None))
print("Metrics User 2:")
print(cache_key("2", None, tracking_number=None, business_id=None))
