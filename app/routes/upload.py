import os
import uuid
from flask import Blueprint, request, send_from_directory, current_app
from flask_jwt_extended import jwt_required
from app.utils.helpers import success_response, error_response

upload_bp = Blueprint("upload", __name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_upload_dir() -> str:
    upload_dir = os.path.join(current_app.root_path, "..", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    return os.path.abspath(upload_dir)


@upload_bp.route("", methods=["POST"])
@jwt_required()
def upload_file():
    if "file" not in request.files:
        return error_response("No file provided")

    file = request.files["file"]
    if not file.filename:
        return error_response("No file selected")

    if not _allowed_file(file.filename):
        return error_response("File type not allowed. Use PNG, JPG, JPEG, GIF, or WEBP")

    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > MAX_FILE_SIZE:
        return error_response("File too large. Maximum size is 5 MB")

    ext = file.filename.rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    upload_dir = _get_upload_dir()
    file.save(os.path.join(upload_dir, filename))

    base_url = request.host_url.rstrip("/")
    file_url = f"{base_url}/api/uploads/{filename}"

    return success_response(
        data={"url": file_url, "filename": filename},
        message="File uploaded successfully",
        status_code=201,
    )


@upload_bp.route("/<filename>", methods=["GET"])
def serve_file(filename):
    upload_dir = _get_upload_dir()
    return send_from_directory(upload_dir, filename)
