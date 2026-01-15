import os
from prompt_cache import init_compliance_caches

# Mirroring the paths used in the user's local app.py
BASE_DIR = os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, "data")
REFERENCE_DIR = os.path.join(DATA_DIR, "reference")

gt = os.path.join(REFERENCE_DIR, "RBI-KFS.pdf")
clm = os.path.join(REFERENCE_DIR, "CLM Guidelines1.pdf")
gl = os.path.join(REFERENCE_DIR, "New-Gold-Loan-Regulations.pdf")

print("--- Initializing Gemini Compliance Caches ---")
print(f"Ground Truth: {gt}")
print(f"CLM: {clm}")
print(f"GL: {gl}")

if not all(os.path.exists(p) for p in [gt, clm, gl]):
    print("ERROR: One or more reference files are missing in data/reference/")
    print("Please ensure RBI-KFS.pdf, CLM Guidelines1.pdf, and New-Gold-Loan-Regulations.pdf are present.")
else:
    try:
        cache_ids = init_compliance_caches(gt, clm, gl)
        print("\nSUCCESS! Caches created and IDs saved to cache_ids.json")
        print(f"Cache IDs: {cache_ids}")
    except Exception as e:
        print(f"\nFAILED: {e}")
