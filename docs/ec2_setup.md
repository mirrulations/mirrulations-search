# Local Development & EC2 Setup Guide

---

## Local Development

### Prerequisites

- AWS CLI installed and configured with your credentials
- Access to the shared AWS account

### Step 1: Set Up Your `.env` File

Create a `.env` file inside `src/mirrsearch/`:

```bash
nano src/mirrsearch/.env
```

Add the following with your actual credentials from AWS Secrets Manager:

```bash
DB_HOST=your_db_host
DB_PORT=5432
DB_NAME=your_db_name
DB_USER=your_username
DB_PASSWORD=your_password
USE_POSTGRES=true
```

> **Never commit your `.env` file.** It is already listed in `.gitignore`.

### Step 2: Run the App

From the project root:

```bash
bash dev_up.sh
```

The app will be available at `http://localhost`.

### Step 3: Shut Down

```bash
source deactivate_env.sh
```

This clears your environment variables from the session.

---

## EC2 Deployment

### Prerequisites

- Access to the shared AWS account

### Step 1: Fill In the AWS Secrets Manager Details in `db.py`

In `src/mirrsearch/db.py`, find `_get_secrets_from_aws()` and replace the placeholders with the real values:

```python
client = boto3.client(
    "secretsmanager",
    region_name="us-east-1"  # replace with your region
)
response = client.get_secret_value(
    SecretId="your-secret-name"  # replace with your secret name
)
```

Commit this change before deploying.

### Step 2: Pull the Latest Code

Go to the AWS Console → EC2 → select the instance → Connect, then run:

```bash
cd mirrulations-search
git pull origin main
```

### Step 3: Run the Production Script

```bash
bash prod_up.sh
```

This will install dependencies, obtain an SSL certificate, and start the app as a systemd service. The `mirrsearch.service` file already has `USE_AWS_SECRETS=true` set, so the app will automatically pull credentials from AWS Secrets Manager.

The app will be available at `https://dev.mirrulations.org`.
