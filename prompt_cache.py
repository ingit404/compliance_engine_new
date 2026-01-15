import os
from google import genai
from google.genai import types
from dotenv import load_dotenv
from prompt import SYSTEM_PROMPT
from gcs_cache import write_cache_ids

load_dotenv()

model_2 = "gemini-3-flash-preview"
model_3 = "gemini-3-pro-preview"
CACHE_TTL = "43200s"

def init_compliance_caches(
    ground_truth: str,
    clm: str,
    gl_regulation: str
) -> dict:
    """
    Creates Gemini prompt caches for Flash and Pro models.
    Should be executed ONCE per deployment.
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY missing")

    client = genai.Client(api_key=api_key)

    # Upload static reference documents (GCS paths are OK)
    ground_truth_file = client.files.upload(file=ground_truth)
    clm_file = client.files.upload(file=clm)
    gl_file = client.files.upload(file=gl_regulation)

    cache_ids = {}

    for key, model_id in {
        "flash": model_2,
        "pro": model_3
    }.items():

        cached = client.caches.create(
            model=model_id,
            config=types.CreateCachedContentConfig(
                display_name=f"compliance_cache_{key}",
                contents=[
                    types.Content(
                        role="user",
                        parts=[
                            types.Part.from_uri(file_uri=ground_truth_file.uri, mime_type=ground_truth_file.mime_type),
                            types.Part.from_uri(file_uri=clm_file.uri, mime_type=clm_file.mime_type),
                            types.Part.from_uri(file_uri=gl_file.uri, mime_type=gl_file.mime_type),
                        ]
                    )
                ],
                system_instruction=types.Content(parts=[types.Part(text=SYSTEM_PROMPT)]),
                ttl=CACHE_TTL
            )
        )

        cache_ids[key] = cached.name

    write_cache_ids(cache_ids)
    return cache_ids
