import os
import json
from google.cloud import storage
from dotenv import load_dotenv

load_dotenv()

BUCKET_NAME = "rupeek_compliance_engine"

def verify_gcs():
    print(f"--- GCS Connectivity Test ---")
    
    # Check for credentials
    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    if creds:
        print(f"INFO: Using service account key at: {creds}")
    else:
        print("INFO: No GOOGLE_APPLICATION_CREDENTIALS set. Will attempt default auth.")

    try:
        client = storage.Client()
        bucket = client.bucket(BUCKET_NAME)
        
        print(f"Attempting to reach bucket: {BUCKET_NAME}...")
        if not bucket.exists():
            print(f"ERROR: Bucket '{BUCKET_NAME}' does not exist or you don't have access.")
            return

        print(f"SUCCESS: Connected to bucket '{BUCKET_NAME}'.")
        
        # Test basic write/read
        test_blob = bucket.blob("test_connection.txt")
        test_blob.upload_from_string("GCS connection is working!")
        print("SUCCESS: Write test passed.")
        
        content = test_blob.download_as_text()
        print(f"SUCCESS: Read test passed. Content: {content}")
        
        # Cleanup
        test_blob.delete()
        print("SUCCESS: Delete test passed. GCS is fully operational.")

    except Exception as e:
        print(f"FAILED: {str(e)}")

if __name__ == "__main__":
    verify_gcs()
