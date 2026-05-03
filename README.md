# Cloud Contact Data Purge

Enterprise-grade bulk contact data purge utility for genesys cloud platforms. Removes target data fields (e.g. email addresses) from external contact records at scale, with multiple safety modes, paginated bulk processing, full audit trail export, and AWS-native deployment.

---

## Background

Deployed to address a bulk data compliance requirement across an enterprise genesys cloud platform managing hundreds of thousands of external contact records. The platform's native tooling had no bulk field-removal capability, and the REST API imposed a hard 1,000-record limit per query.

The MULTI_BATCH mode was designed to bypass this constraint — splitting the contact population into date or alphabetical name ranges, each processed in a separate scheduled run. Deployed on AWS Lambda with credentials in Secrets Manager, audit CSVs archived to S3, and execution logs shipped to CloudWatch.

---

## Project Structure

```
cloud-contact-data-purge/
├── main.py                          ← pipeline orchestrator + CLI entry point
├── contact_data_purge/
│   ├── config.py                    ← all env vars and batch range definitions
│   ├── auth.py                      ← Secrets Manager + .env credential loading, OAuth2
│   ├── client.py                    ← authenticated API request wrapper
│   ├── contacts.py                  ← retrieval, pagination, date filtering, email ID
│   ├── purge.py                     ← bulk field removal, CSV audit trail, preview
│   └── modes.py                     ← mode dispatcher (PREVIEW → MULTI_BATCH)
└── aws/
    ├── lambda_handler.py            ← Lambda entry point, EventBridge, S3 audit upload
    └── cloudwatch_logger.py         ← structured JSON logging to CloudWatch Logs
```

---

## Safety Modes

The tool enforces a progressive safety model. All destructive modes require explicit confirmation.

| Mode | What it does |
|---|---|
| `PREVIEW` | Identify all matching contacts, export to CSV. **No changes.** |
| `TEST_ONE` | Modify 1 contact only. Requires confirmation. |
| `TEST_BATCH` | Modify `TEST_BATCH_SIZE` contacts. Requires confirmation. |
| `FULL_PURGE` | Modify all matching contacts. Requires double confirmation. |
| `MULTI_BATCH` | Paginate beyond API limits, one batch per run. |

**Recommended progression:** `PREVIEW` → `TEST_ONE` → `TEST_BATCH` → `FULL_PURGE` or `MULTI_BATCH`

---

## MULTI_BATCH Pagination Strategy

The platform API caps queries at 1,000 records. MULTI_BATCH splits the contact population into ranges and processes one per run.

**Date ranges** (`FILTER_METHOD=DATE_RANGE`):
```
Batch 0: modified 2024-01-01 → 2024-03-31
Batch 1: modified 2024-04-01 → 2024-06-30
...
```

**Name ranges** (`FILTER_METHOD=NAME_RANGE`):
```
Batch 0: last name A–E
Batch 1: last name F–J
...
```

Increment `CURRENT_BATCH_INDEX` between runs. Lambda handles this via the EventBridge event payload.

---

## Setup (Local)

```bash
git clone https://github.com/your-username/cloud-contact-data-purge.git
cd cloud-contact-data-purge
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in credentials and mode settings
python main.py
```

---

## AWS Deployment

### Lambda

```bash
# Package
zip -r function.zip . -x "*.env" -x "output/*" -x ".git/*" -x "venv/*"

# Deploy
aws lambda update-function-code \
  --function-name cloud-contact-purge \
  --zip-file fileb://function.zip
```

Lambda environment variables:
```
AWS_SECRET_NAME      = prod/contact-purge/api-credentials
MODE                 = MULTI_BATCH
FILTER_METHOD        = DATE_RANGE
CURRENT_BATCH_INDEX  = 0
BATCH_SIZE           = 50
S3_BUCKET            = your-audit-bucket
```

EventBridge event payload (to step through batches):
```json
{ "mode": "MULTI_BATCH", "batch_index": 1, "filter_method": "DATE_RANGE" }
```

IAM permissions: `secretsmanager:GetSecretValue`, `s3:PutObject`, `logs:*`

### EC2 (for long-running or interactive jobs)

```bash
# Credentials from instance role via Secrets Manager
AWS_SECRET_NAME=prod/contact-purge/api-credentials python main.py
```

---

## Credentials

**Production (AWS):** stored in Secrets Manager as a JSON secret:
```json
{
  "client_id": "...",
  "client_secret": "...",
  "region": "mypurecloud.com.au",
  "verify_cert": true
}
```

`auth.py` detects `AWS_SECRET_NAME` and loads from Secrets Manager automatically. Falls back to `.env` if not set.

---

## Audit Trail

Every run produces timestamped CSVs in `output/`:
```
output/
├── preview_20260504_143022.csv       ← PREVIEW export
└── purge_audit_20260504_143022.csv   ← modification audit log (SUCCESS / FAILED per contact)
```

In production, audit files are archived to S3 via `aws/lambda_handler.py`.

---

## Stack

Python · requests · boto3 · python-dotenv  
AWS: Lambda · EventBridge · Secrets Manager · CloudWatch Logs · S3 · EC2
