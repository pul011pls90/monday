# Project Agent Instructions (Monday Academy)

## Knowledge Base & CRM Bot Guidelines
When working on CRM workflows, lead classification, manager reply macros, or the Telegram CRM bot, load and follow the canonical reference documents:
- @docs/crm_bot/catalog_and_pricing.md
- @docs/crm_bot/scenarios_and_objections.md
- @docs/crm_bot/reply_macros.md
- @docs/crm_bot/learned_rules.md

## Environment & Engineering Standards
- **Test command:** `unset DATABASE_URL && /Users/apple/Desktop/Monday/venv/bin/python -m pytest -q`
- **Migrations:** Verify Alembic revisions round-trip (`upgrade` -> `downgrade` -> `upgrade`) and `flask --app app db check` shows zero drift on both SQLite and Postgres.
- **Security & CSP:** Never commit secrets (read `TELEGRAM_BOT_TOKEN`, `TELEGRAM_WEBHOOK_SECRET`, `GEMINI_API_KEY` strictly from environment variables). Keep Jinja templates CSP-clean (no inline `<script>` or `on*=` attributes), enforce RBAC (`403` on unauthorized access), CSRF protection on browser POSTs, and AuditLog records on lead/support mutations. Never hard-delete leads from automated bots—use soft archiving (`is_archived=True`).
