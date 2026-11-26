"""Translations: every text of the app can be translated, per language, and only APPROVED translations are used.

How it works:
- i18n_sources.json lists the texts of the app (English). They are put into the table "i18n" for every language in LANGS (text empty).
- Reviewers (permission "translations.review", default: admins) write or correct a translation in Admin -> Translations and press "Approve".
  Only approved, non-empty translations are sent to the browsers. Everything else stays English.
- The language list shows "Deutsch (partly translated)" until EVERY text of that language is approved; then it shows just "Deutsch".
- A new language: add it to LANGS below. A new text: Admin -> Translations -> "Add a text" (or add it to i18n_sources.json).
"""
import json
from pathlib import Path

from flask import Blueprint, g, jsonify, request

import audit
import db
from security import ApiError, json_body, perm_required

bp = Blueprint("i18n", __name__, url_prefix="/api")
LANGS = {"de": "Deutsch"}                       # code -> name in its own language. English is the built-in base language.
SOURCES_FILE = Path(__file__).with_name("i18n_sources.json")


def seed():
    """Adds missing (language, text) rows. Never touches rows that exist (admin work stays)."""
    try:
        sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    for lang in LANGS:
        have = {r["source"] for r in db.query("SELECT source FROM i18n WHERE lang = ?", (lang,))}
        with db.transaction() as tx:
            for s in sources:
                if s not in have:
                    tx.execute("INSERT INTO i18n (lang, source, text, approved) VALUES (?, ?, '', 0) ON CONFLICT DO NOTHING", (lang, s))


def _coverage(lang):
    r = db.query("SELECT COUNT(*) AS total, COALESCE(SUM(CASE WHEN approved = 1 AND text <> '' THEN 1 ELSE 0 END), 0) AS ok FROM i18n WHERE lang = ?", (lang,))[0]
    return r["total"], int(r["ok"])


@bp.get("/i18n/languages")
def languages():
    out = [{"code": "en", "name": "English", "complete": True, "percent": 100}]
    for code, name in LANGS.items():
        total, ok = _coverage(code)
        pct = int(100 * ok / total) if total else 0
        out.append({"code": code, "name": name, "complete": total > 0 and ok == total, "percent": pct})
    return jsonify(out)


@bp.get("/i18n/<lang>")
def pack(lang):
    if lang not in LANGS:
        raise ApiError("Unknown language.", 404)
    rows = db.query("SELECT source, text FROM i18n WHERE lang = ? AND approved = 1 AND text <> ''", (lang,))
    return jsonify({"lang": lang, "texts": {r["source"]: r["text"] for r in rows}})


# ---------------------------------------------------------------- review (Admin -> Translations)
@bp.get("/admin/i18n")
@perm_required("translations.review")
def review_list():
    lang = request.args.get("lang", "de")
    if lang not in LANGS:
        raise ApiError("Unknown language.")
    flt = request.args.get("filter", "open")
    q = request.args.get("q", "").strip()[:60]
    where, params = "lang = ?", [lang]
    if flt == "open":
        where += " AND (text = '' )"
    elif flt == "draft":
        where += " AND text <> '' AND approved = 0"
    elif flt == "approved":
        where += " AND approved = 1"
    if q:
        where += " AND (LOWER(source) LIKE ? OR LOWER(text) LIKE ?)"
        params += [f"%{q.lower()}%"] * 2
    rows = db.query(f"SELECT source, text, approved FROM i18n WHERE {where} ORDER BY source LIMIT 100", params)
    total, ok = _coverage(lang)
    return jsonify({"rows": [{**r, "approved": bool(r["approved"])} for r in rows], "total": total, "approved": ok})


@bp.put("/admin/i18n")
@perm_required("translations.review")
def review_save():
    data = json_body()
    lang, source = data.get("lang"), data.get("source")
    text = str(data.get("text", "")).strip()
    if lang not in LANGS or not isinstance(source, str) or len(text) > 600:
        raise ApiError("Invalid translation.")
    if not db.query("SELECT 1 AS x FROM i18n WHERE lang = ? AND source = ?", (lang, source)):
        raise ApiError("Unknown text.", 404)
    approved = 1 if data.get("approved") is True and text else 0
    db.execute("UPDATE i18n SET text = ?, approved = ? WHERE lang = ? AND source = ?", (text, approved, lang, source))
    audit.log(g.user["username"], "i18n_save", f"{lang}", source[:80])
    return jsonify({"ok": True})


@bp.post("/admin/i18n/approve-all")
@perm_required("translations.review")
def approve_all():
    lang = json_body().get("lang")
    if lang not in LANGS:
        raise ApiError("Unknown language.")
    n = db.execute("UPDATE i18n SET approved = 1 WHERE lang = ? AND text <> '' AND approved = 0", (lang,))
    audit.log(g.user["username"], "i18n_approve_all", lang, str(n))
    return jsonify({"approved": n})


@bp.post("/admin/i18n/source")
@perm_required("translations.review")
def add_source():
    s = str(json_body().get("source", "")).strip()
    if not 2 <= len(s) <= 300:
        raise ApiError("The text needs 2 to 300 characters.")
    for lang in LANGS:
        db.execute("INSERT INTO i18n (lang, source, text, approved) VALUES (?, ?, '', 0) ON CONFLICT DO NOTHING", (lang, s))
    return jsonify({"ok": True}), 201
