import os
import json
from google.cloud import storage

BUCKET_NAME = "rupeek_compliance_engine"
CACHE_PREFIX = "gemini_cache"
LOCAL_CACHE_FILE = "cache_ids.json"

def write_cache_ids(cache_dict: dict):
    # Always save locally for convenience
    with open(LOCAL_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache_dict, f)
    
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"{CACHE_PREFIX}/cache_ids.json")
        blob.upload_from_string(json.dumps(cache_dict))
    except Exception as e:
        print(f"GCS upload failed (expected in local dev): {e}")

def read_cache_ids():
    # 1. Try local first for faster dev loop
    if os.path.exists(LOCAL_CACHE_FILE):
        with open(LOCAL_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    # 2. Fallback to GCS
    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        blob = bucket.blob(f"{CACHE_PREFIX}/cache_ids.json")

        if blob.exists():
            data = json.loads(blob.download_as_text())
            # Save locally for next time
            with open(LOCAL_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return data
    except Exception:
        pass

    return None
