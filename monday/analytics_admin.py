"""Admin Analytics Blueprint: dashboard view, KPI/charts/visits APIs, live feed, user drawer, and CSV export."""
from __future__ import annotations

from flask import Blueprint, Response, abort, jsonify, render_template, request
from flask_login import current_user

from .access import admin_required, question_bank_access_required
from .analytics_service import (
    compute_charts,
    compute_kpis,
    export_visits_csv,
    get_live_feed,
    get_user_drawer_detail,
    get_visit_drawer_detail,
    query_filtered_visits,
)
from .constants import EXAMS
from .models import User, db

bp = Blueprint("analytics", __name__, url_prefix="/admin/analytics")


@bp.route("/")
@admin_required
def dashboard():
    kpis = compute_kpis()
    initial_grid = query_filtered_visits({}, page=1, per_page=25)
    return render_template(
        "admin/analytics.html",
        kpis=kpis,
        exams=EXAMS,
        facets=initial_grid["facets"],
    )


@bp.route("/api/summary")
@admin_required
def api_summary():
    days = request.args.get("days", 30, type=int)
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    return jsonify({
        "kpis": compute_kpis(),
        "charts": compute_charts(days=days, date_from=date_from, date_to=date_to),
    })


@bp.route("/api/visits")
@admin_required
def api_visits():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    return jsonify(query_filtered_visits(request.args, page=page, per_page=per_page, paginate=True))


@bp.route("/export.csv")
@question_bank_access_required
@admin_required
def export_csv():
    csv_body = export_visits_csv(request.args)
    return Response(
        csv_body,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="monday-visits.csv"'},
    )


@bp.route("/api/live")
@admin_required
def api_live():
    limit = request.args.get("limit", 40, type=int)
    kind = (request.args.get("kind") or "all").strip().lower()
    return jsonify({
        "items": get_live_feed(limit=limit, kind=kind),
        "kpis": compute_kpis(),
    })


@bp.route("/api/user/<int:user_id>")
@admin_required
def api_user_detail(user_id: int):
    data = get_user_drawer_detail(user_id)
    if data is None:
        abort(404)
    return jsonify(data)


@bp.route("/api/visit/<visit_id>")
@admin_required
def api_visit_detail(visit_id: str):
    data = get_visit_drawer_detail(visit_id)
    if data is None:
        abort(404)
    return jsonify(data)


@bp.route("/api/user/<int:user_id>/block", methods=["POST"])
@admin_required
def api_user_block(user_id: int):
    if user_id == current_user.id:
        return jsonify({"error": "Нельзя заблокировать собственный аккаунт."}), 400
    u = db.session.get(User, user_id)
    if u is None:
        abort(404)
    payload = request.get_json(silent=True)
    if isinstance(payload, dict) and "blocked" in payload:
        u.is_blocked = bool(payload["blocked"])
    else:
        u.is_blocked = not bool(u.is_blocked)
    if u.is_blocked:
        u.invalidate_sessions()
    db.session.commit()
    return jsonify({"user_id": u.id, "is_blocked": bool(u.is_blocked)})
