"""Database-backed SAT Math Roadmap loader, real progress/Journal sync, and API endpoints."""
from __future__ import annotations

import json
from collections import Counter

from flask import Blueprint, jsonify, render_template, request, url_for
from flask_login import current_user
from sqlalchemy import inspect as sa_inspect, text as sa_text

from . import formulas
from .access import admin_required, student_required
from .models import (
    Attempt,
    AttemptAnswer,
    ContentNode,
    RoadmapMilestone,
    RoadmapNode,
    RoadmapProgress,
    db,
    utcnow,
)
from .services import open_mistakes

bp = Blueprint("roadmap", __name__)

DOMAIN_FORMULA_KEY = {
    "algebra": "sat_algebra",
    "advanced": "sat_advanced",
    "psda": "sat_data",
    "geometry": "sat_geometry",
}

GOAL_TIERS = {
    "600": ["foundation"],
    "650": ["foundation", "medium"],
    "700": ["foundation", "medium", "advanced"],
    "750+": ["foundation", "medium", "advanced", "challenge"],
}


def ensure_roadmap_schema() -> None:
    """Additively ensure new roadmap columns exist on existing DBs without altering data."""
    insp = sa_inspect(db.engine)
    tables = set(insp.get_table_names())
    alters = []
    if "roadmap_milestone" in tables:
        cols = {c["name"] for c in insp.get_columns("roadmap_milestone")}
        for col, ddl in (
            ("guide_ru", "TEXT NOT NULL DEFAULT ''"),
            ("guide_en", "TEXT NOT NULL DEFAULT ''"),
            ("guide_draft_ru", "TEXT NOT NULL DEFAULT ''"),
            ("guide_status", "VARCHAR(20) NOT NULL DEFAULT 'published'"),
        ):
            if col not in cols:
                alters.append(f'ALTER TABLE roadmap_milestone ADD COLUMN {col} {ddl}')
    if "roadmap_node" in tables:
        cols = {c["name"] for c in insp.get_columns("roadmap_node")}
        for col, ddl in (
            ("body_ru", "TEXT NOT NULL DEFAULT ''"),
            ("body_en", "TEXT NOT NULL DEFAULT ''"),
            ("body_draft_ru", "TEXT NOT NULL DEFAULT ''"),
            ("body_status", "VARCHAR(20) NOT NULL DEFAULT 'published'"),
            ("widget_json", "TEXT NOT NULL DEFAULT ''"),
        ):
            if col not in cols:
                alters.append(f'ALTER TABLE roadmap_node ADD COLUMN {col} {ddl}')
    if alters:
        with db.engine.begin() as conn:
            for stmt in alters:
                conn.execute(sa_text(stmt))


def _load_formula_preview(tpl_key: str, topic_id: str) -> dict | None:
    if not tpl_key:
        return None
    tpl = formulas.find_template(tpl_key)
    if not tpl:
        return None
    topic = next((t for t in tpl.get("topics", []) if t.get("id") == topic_id), None)
    if not topic and tpl.get("topics"):
        topic = tpl["topics"][0]
    if not topic:
        return None
    fms = topic.get("formulas") or []
    if not fms:
        return None
    fm = fms[0]
    ex = (fm.get("examples") or [None])[0]
    return {
        "tpl_key": tpl_key,
        "topic_name": topic.get("name", ""),
        "name": fm.get("name", ""),
        "expr": fm.get("expr", ""),
        "note": fm.get("note", ""),
        "example_q": ex.get("q", "") if isinstance(ex, dict) else "",
        "example_sol": ex.get("sol", "") if isinstance(ex, dict) else "",
    }


def _domain_diagnostic_stats(user_id: int, milestones: list[RoadmapMilestone]) -> tuple[str | None, set[str]]:
    """Compute per-domain accuracy from user's SAT attempts; return (weakest_domain_key, strong_domains)."""
    domain_keys = {"algebra", "advanced", "psda", "geometry"}
    skill_to_domain: dict[int, str] = {}
    for m in milestones:
        if m.key not in domain_keys:
            continue
        for n in m.nodes:
            try:
                sids = json.loads(n.skill_ids_json or "[]")
            except Exception:
                sids = []
            for sid in sids:
                skill_to_domain[int(sid)] = m.key

    # Look at all answered questions by this student
    ans_rows = (
        db.session.query(AttemptAnswer.skill_id, AttemptAnswer.is_correct)
        .join(Attempt, Attempt.id == AttemptAnswer.attempt_id)
        .filter(Attempt.user_id == user_id, AttemptAnswer.is_correct.isnot(None))
        .all()
    )
    if not ans_rows:
        return None, set()

    tot = Counter()
    ok = Counter()
    for sid, is_ok in ans_rows:
        dom = skill_to_domain.get(sid)
        if dom:
            tot[dom] += 1
            if is_ok:
                ok[dom] += 1

    if not tot:
        return None, set()

    accs = {d: (ok[d] / tot[d]) for d in tot if tot[d] > 0}
    weakest = min(accs, key=lambda d: accs[d]) if accs else None
    strong = {d for d, acc in accs.items() if acc >= 0.80 and tot[d] >= 3}
    return weakest, strong


def build_sat_roadmap(user_id: int, topics: list[dict], q: str = "", lang: str = "ru") -> dict:
    """Build the SAT Math Roadmap from DB tables with live Bank, Journal, and Diagnostic sync."""
    ensure_roadmap_schema()
    milestones_db = RoadmapMilestone.query.filter_by(exam="SAT").order_by(RoadmapMilestone.step.asc()).all()
    if not milestones_db:
        from scripts.seed_roadmap import seed_sat_roadmap
        seed_sat_roadmap(dry_run=False)
        milestones_db = RoadmapMilestone.query.filter_by(exam="SAT").order_by(RoadmapMilestone.step.asc()).all()

    q_norm = (q or "").strip().lower()
    use_en = (lang or "ru").startswith("en")

    # Index real skill stats from skill_map
    skill_stats: dict[int, dict] = {}
    for t in topics:
        for it in t.get("items", []):
            if it.get("state") == "outside" or not it.get("skill"):
                continue
            sk = it["skill"]
            skill_stats[sk.id] = {
                "id": sk.id,
                "name": sk.name,
                "state": it.get("state", "new"),
                "n": it.get("n", 0),
                "accuracy": it.get("accuracy"),
            }

    # Unresolved Journal errors per skill_id
    mistakes = open_mistakes(user_id)
    err_counts = Counter(a.skill_id for a in mistakes if a.skill_id)

    # Top 3 weak topics from Journal for dynamic review milestone
    weak_journal = []
    if err_counts:
        top_sids = [sid for sid, _cnt in err_counts.most_common(3)]
        nodes_by_id = {n.id: n for n in ContentNode.query.filter(ContentNode.id.in_(top_sids)).all()}
        for sid in top_sids:
            cn = nodes_by_id.get(sid)
            if cn:
                weak_journal.append({"skill_id": sid, "name": cn.name, "errors": err_counts[sid]})

    # Saved RoadmapProgress completions
    prog_rows = {
        r.node_key: r.status
        for r in RoadmapProgress.query.filter_by(user_id=user_id).all()
    }

    # Diagnostic placement
    weakest_domain, strong_domains = _domain_diagnostic_stats(user_id, milestones_db)

    # Score goal
    score_goal = (current_user.pref("sat_score_goal") if current_user.is_authenticated else None) or "700"
    if score_goal not in GOAL_TIERS:
        score_goal = "700"
    recommended_tiers = GOAL_TIERS[score_goal]

    milestones_out = []
    total_nodes = 0
    done_nodes = 0

    for m in milestones_db:
        m_title = m.title_en if use_en else m.title_ru
        gate = None
        if m.gate_json:
            try:
                gate = json.loads(m.gate_json)
            except Exception:
                gate = None

        nodes_db = m.nodes.order_by(RoadmapNode.position.asc()).all()
        left_groups_map: dict[str, dict] = {}
        right_groups_map: dict[str, dict] = {}
        m_total = 0
        m_done = 0

        for n in nodes_db:
            title = n.title_en if use_en else n.title_ru
            g_title = (n.group_en if use_en else n.group_ru) or ""
            haystack = " ".join([n.title_ru, n.title_en, n.group_ru, n.group_en, m.title_ru, m.title_en]).lower()
            if q_norm and q_norm not in haystack:
                continue

            try:
                sids = [int(x) for x in json.loads(n.skill_ids_json or "[]")]
            except Exception:
                sids = []
            try:
                link_hint = json.loads(n.link_hint_json or "{}")
            except Exception:
                link_hint = {}
            try:
                soft_prereqs = json.loads(n.soft_prereqs_json or "[]")
            except Exception:
                soft_prereqs = []

            # Compute node real status
            errors = sum(err_counts.get(sid, 0) for sid in sids)
            q_avail = sum(skill_stats[sid]["n"] for sid in sids if sid in skill_stats)
            matched_skills = [skill_stats[sid] for sid in sids if sid in skill_stats]
            accs = [s["accuracy"] for s in matched_skills if s.get("accuracy") is not None]
            avg_acc = (sum(accs) / len(accs)) if accs else None
            any_mastered = any(s["state"] == "mastered" for s in matched_skills)
            any_progress = any(s["state"] in ("progress", "mastered") for s in matched_skills)

            if errors > 0:
                status = "needs_review"
            elif prog_rows.get(n.key) == "completed":
                status = "completed"
            elif any_mastered or (m.key in strong_domains and n.tier == "foundation" and n.kind == "topic"):
                status = "mastered"
            elif any_progress:
                status = "in_progress"
            else:
                status = "not_started"

            is_done = status in ("completed", "mastered")
            m_total += 1
            total_nodes += 1
            if is_done:
                m_done += 1
                done_nodes += 1

            # Resolve URL & formula preview
            url = None
            if n.kind == "exam":
                url = url_for("student.collections", exam="SAT")
            elif n.kind == "practice":
                if "compilation" in link_hint:
                    url = url_for("student.collections", exam="SAT")
                elif "bank_tags" in link_hint:
                    url = url_for("bank.index", exam="SAT")
                else:
                    url = url_for("student.sessions")
            elif n.formula_tpl:
                url = url_for("student.formula_template", template_id=n.formula_tpl)

            formula_preview = _load_formula_preview(n.formula_tpl, n.formula_topic_id) if n.kind == "topic" else None
            bank_k = f"s:{sids[0]}" if sids else ""
            try:
                widget_obj = json.loads(n.widget_json) if n.widget_json else None
            except Exception:
                widget_obj = None

            node_dict = {
                "key": n.key,
                "title": title,
                "kind": n.kind,
                "tier": n.tier or "foundation",
                "status": status,
                "is_done": is_done,
                "errors": errors,
                "q_avail": q_avail,
                "skill_ids": sids,
                "bank_k": bank_k,
                "accuracy_pct": round(avg_acc * 100) if avg_acc is not None else None,
                "summary_ru": n.body_ru or n.summary_ru,
                "widget": widget_obj,
                "formula": formula_preview,
                "url": url,
                "journal_url": url_for("student.journal") if errors > 0 else None,
                "soft_prerequisites": soft_prereqs,
            }

            target_map = left_groups_map if n.side == "left" else right_groups_map
            if g_title not in target_map:
                target_map[g_title] = {"title": g_title, "nodes": []}
            target_map[g_title]["nodes"].append(node_dict)

        left_g = list(left_groups_map.values())
        right_g = list(right_groups_map.values())
        if not left_g and not right_g:
            continue

        milestones_out.append({
            "step": m.step,
            "key": m.key,
            "title": m_title,
            "description": m.description_ru,
            "guide": (m.guide_en if use_en and m.guide_en else m.guide_ru) or m.description_ru,
            "official_question_share": m.official_question_share,
            "gate": gate,
            "is_domain": m.key in DOMAIN_FORMULA_KEY,
            "is_recommended_start": m.key == weakest_domain,
            "done_count": m_done,
            "total_count": m_total,
            "left_groups": left_g,
            "right_groups": right_g,
            "weak_journal": weak_journal if m.key == "review" else [],
        })

    return {
        "meta": {"title_ru": "Роадмап SAT Math", "title_en": "SAT Math Roadmap"},
        "milestones": milestones_out,
        "total_nodes": total_nodes,
        "done_nodes": done_nodes,
        "score_goal": score_goal,
        "recommended_tiers": recommended_tiers,
        "weakest_domain": weakest_domain,
        "checklist_state": (current_user.pref("sat_test_checklist") if current_user.is_authenticated else None) or {},
    }


@bp.post("/api/roadmap/node/<node_key>/complete")
@student_required
def api_complete_node(node_key: str):
    data = request.get_json(silent=True) or {}
    done = bool(data.get("done", True))
    row = RoadmapProgress.query.filter_by(user_id=current_user.id, node_key=node_key).first()
    if done:
        if row is None:
            row = RoadmapProgress(user_id=current_user.id, node_key=node_key, status="completed", updated_at=utcnow())
            db.session.add(row)
        else:
            row.status = "completed"
            row.updated_at = utcnow()
    else:
        if row is not None:
            db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True, "node_key": node_key, "done": done})


@bp.post("/api/roadmap/goal")
@student_required
def api_set_goal():
    data = request.get_json(silent=True) or {}
    goal = str(data.get("goal") or "").strip()
    if goal not in GOAL_TIERS:
        return jsonify({"ok": False, "error": "invalid_goal"}), 400
    current_user.set_prefs(sat_score_goal=goal)
    db.session.commit()
    return jsonify({"ok": True, "goal": goal, "recommended_tiers": GOAL_TIERS[goal]})


@bp.post("/api/roadmap/checklist")
@student_required
def api_checklist():
    data = request.get_json(silent=True) or {}
    item_id = str(data.get("id") or "").strip()[:64]
    checked = bool(data.get("checked"))
    if not item_id:
        return jsonify({"ok": False}), 400
    state = dict(current_user.pref("sat_test_checklist") or {})
    if checked:
        state[item_id] = True
    else:
        state.pop(item_id, None)
    current_user.set_prefs(sat_test_checklist=state)
    db.session.commit()
    return jsonify({"ok": True, "checklist": state})


@bp.route("/admin/roadmap", methods=["GET", "POST"])
@admin_required
def admin_roadmap():
    ensure_roadmap_schema()
    milestones = RoadmapMilestone.query.filter_by(exam="SAT").order_by(RoadmapMilestone.step.asc()).all()
    saved_msg = ""
    if request.method == "POST":
        target_type = request.form.get("target_type")
        target_key = request.form.get("target_key")
        action = request.form.get("action") or "draft"
        text_val = request.form.get("content") or ""
        if target_type == "milestone":
            row = RoadmapMilestone.query.filter_by(exam="SAT", key=target_key).first()
            if row:
                row.guide_draft_ru = text_val
                if action == "publish":
                    row.guide_ru = text_val
                    row.guide_status = "published"
                    saved_msg = "Гайд главы опубликован."
                else:
                    row.guide_status = "draft"
                    saved_msg = "Черновик главы сохранён."
                row.updated_at = utcnow()
                db.session.commit()
        elif target_type == "node":
            row = RoadmapNode.query.filter_by(key=target_key).first()
            if row:
                row.body_draft_ru = text_val
                if action == "publish":
                    row.body_ru = text_val
                    row.summary_ru = text_val
                    row.body_status = "published"
                    saved_msg = "Пояснение шага опубликовано."
                else:
                    row.body_status = "draft"
                    saved_msg = "Черновик шага сохранён."
                db.session.commit()

    sel_type = request.args.get("type") or "milestone"
    sel_key = request.args.get("key") or (milestones[0].key if milestones else "")
    nodes = RoadmapNode.query.order_by(RoadmapNode.milestone_id.asc(), RoadmapNode.position.asc()).all()
    current_text = ""
    current_status = "published"
    if sel_type == "milestone":
        m = next((x for x in milestones if x.key == sel_key), milestones[0] if milestones else None)
        if m:
            sel_key = m.key
            current_text = m.guide_draft_ru or m.guide_ru
            current_status = m.guide_status
    else:
        n = next((x for x in nodes if x.key == sel_key), nodes[0] if nodes else None)
        if n:
            sel_key = n.key
            current_text = n.body_draft_ru or n.body_ru or n.summary_ru
            current_status = n.body_status

    return render_template(
        "admin/roadmap.html",
        milestones=milestones,
        nodes=nodes,
        sel_type=sel_type,
        sel_key=sel_key,
        current_text=current_text,
        current_status=current_status,
        saved_msg=saved_msg,
    )
