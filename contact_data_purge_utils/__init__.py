"""
contact_data_purge/
────────────────────
Enterprise bulk contact data purge utility.

Modules
───────
  config   — environment variables and batch range definitions
  auth     — credential loading (Secrets Manager + .env fallback) and OAuth2
  client   — authenticated API request wrapper
  contacts — contact retrieval, pagination, date filtering, email identification
  purge    — bulk field removal, CSV audit trail, contact preview
  modes    — mode dispatcher (PREVIEW / TEST_ONE / TEST_BATCH / FULL_PURGE / MULTI_BATCH)
"""
