# Local Development Setup & RDS Connection Guide

## Prerequisites

- AWS CLI installed and configured with your credentials
- Access to the shared AWS account

---

## Step 1: Set Up Your `.env` File

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

---

## Step 2: Run the App

From the project root:

```bash
source activate_env.sh && bash dev_up.sh
```

The app will be available at `http://localhost`.

---

## Step 3: Shut Down

```bash
source deactivate_env.sh
```

This clears your environment variables from the session.
