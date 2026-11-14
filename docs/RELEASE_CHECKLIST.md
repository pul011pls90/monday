# Monday Release Checklist (Deploy Safety)

## 1. Before Deploying
1. **Environment variables on Render:**
   - Verify `DATABASE_URL` points to the external PostgreSQL database (never ephemeral SQLite in production).
   - Verify `MONDAY_SECRET_KEY` is persistent across deploys so student sessions stay signed in.
   - Verify `ADMIN_API_TOKEN` is configured for CLI maintenance announcements.
2. **Pre-announce maintenance (recommended 10–15 min before deploy):**
   - Open `/admin/maintenance` (or run `python3 scripts/announce_maintenance.py --url https://... --state scheduled --minutes 10`).
   - Confirm students see the scheduled banner via `/api/site-status`.
3. **Database migration safety:**
   - Ensure any schema additions are strictly additive (`activity_draft`, `client_op`, `maintenance_state`, `maintenance_log` are created automatically via `ensure_deploy_safety_tables()` without altering or deleting existing rows).

## 2. During Deploy
1. Switch maintenance state to `active` (`--state active --minutes 5`) right before pushing/redeploying if downtime is expected.
2. Push to the deploy branch / trigger Render deploy.
3. Verify `/api/version` updates to the new `RENDER_GIT_COMMIT` hash.

## 3. After Deploy
1. Smoke-check `/api/site-status` and `/api/version` return HTTP 200.
2. Verify `/admin/maintenance` audit log and set maintenance state back to `off` ("Снять уведомление").
3. Confirm in-progress activities flush queued answers and resume cleanly on Главная ("С возвращением! Продолжим с того места, где вы остановились?").
