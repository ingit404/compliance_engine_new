# FROM python:3.11-slim-bookworm
# # Environment
# ENV PYTHONDONTWRITEBYTECODE=1 \
#     PYTHONUNBUFFERED=1 \
#     PORT=8080

# WORKDIR /app

# # System dependencies (required for PyMuPDF)
# RUN apt-get update && apt-get install -y \
#     libglib2.0-0 \
#     libgl1 \
#     && rm -rf /var/lib/apt/lists/*

# # Install Python dependencies
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt

# # Copy application
# COPY . .

# # Cloud Run port
# EXPOSE 8080

# # Run app
# CMD ["python", "app_new.py"]

#gunicorn deocker image



FROM python:3.11-slim-bookworm
WORKDIR /app

RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["gunicorn", "app_new:app", "--workers=1", "--threads=2", "--bind=0.0.0.0:8080"]

