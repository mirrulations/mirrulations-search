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
```

You must run ./db/setup_postgres.sh before to have created the actual database.

This also requires python-dotenv to be intalled which is now added in the requirements.txt file.

Or run pip install python-dotenv in your .venv.

Then run:
```bash
./dev_up.sh
```
