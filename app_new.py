import os
import json
import uuid
import threading
from flask import Flask, request, jsonify, render_template
from google.cloud import storage
from auditengine_new import run_llm_audit, highlight_pdf

BUCKET_NAME = "rupeek_compliance_engine"
UPLOAD_PREFIX = "uploads"
OUTPUT_PREFIX = "outputs"
STATUS_PREFIX = "status"
REFERENCE_PREFIX = "reference"

app = Flask(__name__)
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

#HELPERS

def save_status(run_id, status, extra=None):
    data = {"status": status}
    if extra:
        data.update(extra)
    blob = bucket.blob(f"{STATUS_PREFIX}/{run_id}.json")
    blob.upload_from_string(json.dumps(data))


def get_status(run_id):
    blob = bucket.blob(f"{STATUS_PREFIX}/{run_id}.json")
    if not blob.exists():
        return None
    return json.loads(blob.download_as_text())


def upload_to_gcs(local_path, gcs_path):
    bucket.blob(gcs_path).upload_from_filename(local_path)


def generate_signed_url(path):
    return bucket.blob(path).generate_signed_url(expiration=3600)



@app.route("/")
def index():
    return render_template("index.html")



@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("pdf")
    if not file or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files allowed"}), 400

    run_id = str(uuid.uuid4())
    local_path = f"/tmp/{run_id}.pdf"

    file.save(local_path)
    upload_to_gcs(local_path, f"{UPLOAD_PREFIX}/{run_id}.pdf")

    save_status(run_id, "uploaded")
    return jsonify({"run_id": run_id})



@app.route("/run-audit/<run_id>", methods=["POST"])
def run_audit(run_id):

    def process():
        try:
            save_status(run_id, "processing")

            # Download uploaded PDF
            input_pdf = f"/tmp/{run_id}.pdf"
            bucket.blob(f"{UPLOAD_PREFIX}/{run_id}.pdf").download_to_filename(input_pdf)

            # Download reference files
            gt = f"/tmp/{run_id}_gt.pdf"
            clm = f"/tmp/{run_id}_clm.pdf"
            gl = f"/tmp/{run_id}_gl.pdf"

            bucket.blob(f"{REFERENCE_PREFIX}/RBI-KFS.pdf").download_to_filename(gt)
            bucket.blob(f"{REFERENCE_PREFIX}/CLM Guidelines1.pdf").download_to_filename(clm)
            bucket.blob(f"{REFERENCE_PREFIX}/New-Gold-Loan-Regulations1.pdf").download_to_filename(gl)

            output_excel = f"/tmp/{run_id}.xlsx"
            output_pdf = f"/tmp/{run_id}.pdf"

            # Run audit
            results = run_llm_audit(
                ground_truth=gt,
                clm=clm,
                GL_regulation=gl,
                target_doc=input_pdf,
                user_prompt="",
                output_excel_path=output_excel
            )

            # Highlight PDF
            highlight_pdf(input_pdf, output_pdf, results)

            # Upload outputs
            upload_to_gcs(output_pdf, f"{OUTPUT_PREFIX}/{run_id}.pdf")
            upload_to_gcs(output_excel, f"{OUTPUT_PREFIX}/{run_id}.xlsx")

            save_status(run_id, "completed", {
                "pdf": f"{OUTPUT_PREFIX}/{run_id}.pdf",
                "excel": f"{OUTPUT_PREFIX}/{run_id}.xlsx"
            })

        except Exception as e:
            save_status(run_id, "failed", {"error": str(e)})

    threading.Thread(target=process).start()
    return jsonify({"status": "started"})



@app.route("/status/<run_id>")
def status(run_id):
    data = get_status(run_id)
    if not data:
        return jsonify({"error": "Invalid run ID"}), 404

    if data["status"] == "completed":
        return jsonify({
            "status": "completed",
            "pdf": generate_signed_url(data["pdf"]),
            "excel": generate_signed_url(data["excel"])
        })

    return jsonify(data)



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
