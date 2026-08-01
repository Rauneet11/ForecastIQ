# Optimization / Security Pass — Summary

Applied directly to `backend/`. Frontend was reviewed; no code changes needed there
(see note on JWT storage at the bottom).

## Critical security fixes (all verified with a live smoke test)

1. **Privilege escalation** — `UserSerializer` had `role` as writable, and
   `ProfileView.put()` used it unfiltered. Any logged-in manager/analyst could
   `PUT /api/auth/profile/` with `{"role": "admin"}` and self-promote.
   Fix: `role` is now read-only on the self-serve serializer; a separate
   `AdminUserSerializer` (admin-only endpoints) can still change it.

2. **IDOR — missing ownership checks** (any authenticated user could access
   another user's data by guessing a numeric id), fixed in:
   - `datasets/views.py` → `DatasetPreviewView` (GET dataset preview)
   - `predictions/views.py` → `RunPredictionView` (run predictions on
     someone else's dataset)
   - `scenarios/views.py` → `SimulateView` (base a simulation on someone
     else's prediction)
   - `reports/views.py` → `GenerateReportView` and, most seriously,
     `ReportDownloadView` (download another user's PDF report containing
     real revenue figures)

3. **Missing permission check** — `AdminUserDetailView`'s GET (retrieve) had
   no role check at all; only PUT/DELETE were guarded. Any authenticated
   user could fetch any other user's full profile. Fixed with a shared
   `core/permissions.py::IsAdmin` class applied at the class level so it
   covers every HTTP method.

4. **Hardcoded secrets / `.env` silently unused** — `python-decouple` was in
   `requirements.txt` but never imported; `settings.py` hardcoded
   `SECRET_KEY`, `DEBUG=True`, `ALLOWED_HOSTS=['*']`, and Postgres creds that
   didn't even match the `.env` (which said sqlite). Rewrote `settings.py` to
   read everything from `.env` via `decouple.config`, with safe defaults.
   `.env` was updated to match.

5. **CORS wide open** — `CORS_ALLOW_ALL_ORIGINS = True` → replaced with an
   explicit `CORS_ALLOWED_ORIGINS` allowlist read from `.env`.

6. **Traceback leakage** — several views (`predictions`, `reports`) returned
   `traceback.format_exc()` directly in the JSON response on error, exposing
   file paths and internals to any client. Now logged server-side via
   Python `logging` only; the client gets a generic message. Added
   `core/exceptions.py` as the DRF `EXCEPTION_HANDLER` for anything that
   isn't already caught locally.

7. **Password-reset token leak** — `ForgotPasswordView` always returned the
   raw reset token in the response body (no email sending was wired up).
   Now only echoed back when `DEBUG=True` (local dev); production gets a
   generic "if that email exists..." message that also avoids leaking
   whether an email is registered.

8. **Unbounded uploads** — no file-size limit on CSV upload, so a huge file
   could be read entirely into memory. Added `MAX_UPLOAD_SIZE_MB` (from
   `.env`, default 25MB) enforced both at the Django layer
   (`DATA_UPLOAD_MAX_MEMORY_SIZE`) and explicitly in `DatasetUploadView`,
   plus a row-count sanity cap in `validate_csv`.

## Correctness / reliability fix

9. **Model file race condition** — `ModelTrainer` always saved to a fixed
   filename per model type (e.g. `xgboost_model.joblib`). Two users training
   an XGBoost model concurrently — or the same user re-running a prediction
   — would silently overwrite each other's model file mid-request, which
   could corrupt in-flight predictions. Fixed by giving every training run a
   unique id-based filename (`xgboost_<uuid>_model.joblib`), verified with a
   test that runs two predictions back-to-back and confirms two independent
   files exist afterward.

## Performance

10. **N+1 queries** — `PredictionSerializer` reads `user.username` and
    `dataset.name` per row; the list/detail views now use `select_related`
    so that's one JOIN instead of 2 extra queries per row. Same treatment
    for `scenarios` (`user`, `prediction`) and `reports` (`user`,
    `prediction`).

11. **Missing DB indexes** — added composite `(user, -created_at)` /
    `(user, -uploaded_at)` indexes on `Dataset`, `Prediction`,
    `ScenarioSimulation`, and `Report`, since every list endpoint filters by
    `user` and orders by that timestamp. Migrations generated and applied
    (`0002_..._idx` in each app).

12. **DB connection reuse** — `CONN_MAX_AGE` added (was opening a fresh DB
    connection every request).

## Code quality

13. **`sys.path` hacking removed** — three different view files
    (`datasets`, `predictions`, `reports`) manually did
    `sys.path.insert(0, .../ml)` then bare `from preprocessor import ...`.
    `ml/` already had an `__init__.py` and Django puts the project root on
    `sys.path` automatically — the hack was unnecessary. Switched to proper
    package imports (`from ml.model_trainer import ModelTrainer`, etc.) and
    made the internal `ml/*.py` imports relative (`from .preprocessor import
    ...`).

14. **Centralized role checks** — added `core/permissions.py` with
    `IsAdmin` / `IsOwnerOrAdmin` instead of repeating
    `if request.user.role != 'admin': return Response(..., 403)` in every
    view.

15. **Input validation** — `RunPredictionView` and `SimulateView` now
    validate `forecast_months`, `model_type`, and numeric fields properly
    (were previously trusting `int()`/`float()` on raw request data with no
    bounds, which could 500 on bad input).

## Not changed (flagged, not fixed — bigger architectural calls)

- **JWT stored in `localStorage`** (`frontend/src/services/api.js`) — works,
  but is vulnerable to token theft via XSS. The fix (httpOnly cookies) is a
  real auth-flow rework on both backend and frontend, not a drop-in patch,
  so I left it as-is rather than guessing at a scope you didn't ask for.
  Worth doing before this goes anywhere near production.
- **Synchronous training inside the request/response cycle**
  (`RunPredictionView`) — every prediction retrains a model live during the
  HTTP request. Fine for a student project's data sizes, but won't scale;
  the real fix is a task queue (Celery + Redis) so training happens async
  and the frontend polls/receives a websocket update. Flagging it since your
  project description says "large-scale."

## To run after pulling these changes

```bash
cd backend
pip install -r requirements.txt
python manage.py migrate    # applies the new index migrations
python manage.py runserver
```

No frontend changes are required — the API contract (request/response
shapes) is unchanged; only server-side ownership/permission checks got
stricter.
