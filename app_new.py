import os
import json
import uuid
import threading
import tempfile
import io

from flask import Flask, request, jsonify, render_template, send_file
from google.cloud import storage
from auditengine_new import run_llm_audit, highlight_pdf

# =============================
# CONFIG
# =============================

BUCKET_NAME = "rupeek_compliance_engine"
UPLOAD_PREFIX = "uploads"
OUTPUT_PREFIX = "outputs"
STATUS_PREFIX = "status"
REFERENCE_PREFIX = "reference"

app = Flask(__name__)
storage_client = storage.Client()
bucket = storage_client.bucket(BUCKET_NAME)

# =============================
# HELPERS
# =============================

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


# =============================
# ROUTES
# =============================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("pdf")
    if not file or not file.filename.lower().endswith(".pdf"):
        return jsonify({"error": "Only PDF files allowed"}), 400

    run_id = str(uuid.uuid4())
    tmp = tempfile.gettempdir()
    local_path = os.path.join(tmp, f"{run_id}.pdf")

    file.save(local_path)
    upload_to_gcs(local_path, f"{UPLOAD_PREFIX}/{run_id}.pdf")

    save_status(run_id, "uploaded")
    return jsonify({"run_id": run_id})


@app.route("/run-audit/<run_id>", methods=["POST"])
def run_audit(run_id):

    def process():
        try:
            save_status(run_id, "processing")
            tmp = tempfile.gettempdir()

            # ---- Download input
            input_pdf = os.path.join(tmp, f"{run_id}.pdf")
            bucket.blob(f"{UPLOAD_PREFIX}/{run_id}.pdf").download_to_filename(input_pdf)

            # ---- Reference docs
            gt = os.path.join(tmp, f"{run_id}_gt.pdf")
            clm = os.path.join(tmp, f"{run_id}_clm.pdf")
            gl = os.path.join(tmp, f"{run_id}_gl.pdf")

            bucket.blob(f"{REFERENCE_PREFIX}/RBI-KFS.pdf").download_to_filename(gt)
            bucket.blob(f"{REFERENCE_PREFIX}/CLM Guidelines1.pdf").download_to_filename(clm)
            bucket.blob(f"{REFERENCE_PREFIX}/New-Gold-Loan-Regulations1.pdf").download_to_filename(gl)

            output_pdf = os.path.join(tmp, f"{run_id}_annotated.pdf")
            output_excel = os.path.join(tmp, f"{run_id}.xlsx")

            results = run_llm_audit(
                ground_truth=gt,
                clm=clm,
                GL_regulation=gl,
                target_doc=input_pdf,
                user_prompt="",
                output_excel_path=output_excel
            )

            # Not a loan document
            if (
                isinstance(results, list)
                and len(results) == 1
                and results[0].get("whats_wrong") == "Not a loan document"
            ):
                save_status(run_id, "not_loan", {
                    "message": "This is not a loan document"
                })
                return

            # Highlight & upload
            highlight_pdf(input_pdf, output_pdf, results)

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


# ✅ FIXED STATUS ENDPOINT
@app.route("/status/<run_id>")
def status(run_id):
    data = get_status(run_id)
    if not data:
        return jsonify({"error": "Invalid run ID"}), 404

    if data["status"] == "not_loan":
        return jsonify(data)

    if data["status"] == "completed":
        return jsonify({
            "status": "completed",
            "pdf": f"/download/{run_id}/pdf",
            "excel": f"/download/{run_id}/excel"
        })

    return jsonify(data)


# ✅ DOWNLOAD ROUTE (NO SIGNED URL)
@app.route("/download/<run_id>/<file_type>")
def download_file(run_id, file_type):
    data = get_status(run_id)
    if not data or data["status"] != "completed":
        return "File not ready", 404

    if file_type == "pdf":
        path = data["pdf"]
        mimetype = "application/pdf"
        filename = "audit_report.pdf"
    elif file_type == "excel":
        path = data["excel"]
        mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "audit_report.xlsx"
    else:
        return "Invalid file type", 400

    blob = bucket.blob(path)
    file_bytes = blob.download_as_bytes()

    return send_file(
        io.BytesIO(file_bytes),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
