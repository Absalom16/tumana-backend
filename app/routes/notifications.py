from datetime import datetime, timezone
from flask import Blueprint, request
from flask_jwt_extended import jwt_required
from sqlalchemy import desc
from app import db
from app.models.notification import Notification
from app.utils.helpers import success_response, error_response, get_current_user, paginate_query

notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.route("", methods=["GET"])
@jwt_required()
def get_notifications():
    user = get_current_user()
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("perPage", 20))
    unread_only = request.args.get("unread") == "true"

    query = Notification.query.filter_by(user_id=user.id)
    if unread_only:
        query = query.filter_by(is_read=False)
    query = query.order_by(desc(Notification.created_at))

    result = paginate_query(query, page, per_page)
    unread_count = Notification.query.filter_by(user_id=user.id, is_read=False).count()

    return success_response(
        data={
            "notifications": [n.to_dict() for n in result["items"]],
            "pagination": result["pagination"],
            "unread_count": unread_count,
        }
    )


@notifications_bp.route("/<int:notification_id>/read", methods=["PUT"])
@jwt_required()
def mark_notification_read(notification_id):
    user = get_current_user()
    notif = Notification.query.filter_by(id=notification_id, user_id=user.id).first()
    if not notif:
        return error_response("Notification not found", 404)
    notif.is_read = True
    notif.read_at = datetime.now(timezone.utc)
    db.session.commit()
    return success_response(message="Notification marked as read")


@notifications_bp.route("/read-all", methods=["PUT"])
@jwt_required()
def mark_all_read():
    user = get_current_user()
    Notification.query.filter_by(user_id=user.id, is_read=False).update(
        {"is_read": True, "read_at": datetime.now(timezone.utc)}
    )
    db.session.commit()
    return success_response(message="All notifications marked as read")


@notifications_bp.route("/<int:notification_id>", methods=["DELETE"])
@jwt_required()
def delete_notification(notification_id):
    user = get_current_user()
    notif = Notification.query.filter_by(id=notification_id, user_id=user.id).first()
    if not notif:
        return error_response("Notification not found", 404)
    db.session.delete(notif)
    db.session.commit()
    return success_response(message="Notification deleted")
