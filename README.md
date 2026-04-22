# mirrulations-search
## Local Development (macOS) 

This section is for running mirrulations-search **locally on your laptop**, using:
- Python virtualenv
- Local PostgreSQL
- The built React frontend

* Create and activate a virtual environment

  ```
  python3 -m venv .venv
  source .venv/bin/activate
  ```


* Install Dependencies

  ```
  pip install -r requirements.txt
  ```

* Install source as a package named `mirrsearch`

  ```
  pip install -e .
  ```

  NOTE: `-e` means the package is editable

## How build react

First CD into frontend

run
`npm install`

Then to build the project run
`npm run build`

## Run the Flask Server

Because the code is in a module, you can run it with the `-m` switch:

```
python -m mirrsearch.app
```

If you are in `src/mirrsearch`, you can run `app.py` directly:

```
python app.py
```

## Run with Gunicorn using the Postgres database

Create a `.env` file in the root directory with the following variables:
```bash
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mirrulations
DB_USER=your_macOS_username (You can find this by doing `whoami` in your terminal)
DB_PASSWORD=
BASE_URL:http://localhost (This is the base URL of your application. Localhost in dev)
GOOGLE_CLIENT_ID:The <client_id> value from OAuth Client JSON in 1Password
GOOGLE_CLIENT_SECRET:The <client_secret> value from OAuth Client JSON in 1Password (this value starts with GOC..) 
```

Now install dependencies:
```
pip install -r requirements.txt
```

Run this command if rollout issues persist: 
```
npm install react-router-dom
```

You must run ./db/setup_postgres.sh before to have created the actual database.

Then run:
```bash
./dev_up.sh
```

