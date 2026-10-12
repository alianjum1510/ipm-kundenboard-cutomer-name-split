import os

# Must be set before app.config is imported.
os.environ.setdefault("MONDAY_SIGNING_SECRET", "test-signing-secret-0123456789abcdef")
os.environ.setdefault("MONDAY_API_TOKEN", "test-api-token")
os.environ.setdefault("SOURCE_COLUMN_ID", "text_mkt92ar9")
os.environ.setdefault("TARGET_COLUMN_ID", "text_mksb1npw")
