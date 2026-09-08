# Local Postgres Setup (Doctor Support)

Doctor Support can store per-customer history in a database so you can:
- create/select a customer
- generate summaries/RX for that customer
- load previous encounters by clicking in the sidebar

## Option A: Docker Postgres (recommended)

Start Postgres:
```bash
docker run --name doctor-support-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=doctor_support \
  -p 5432:5432 \
  -d postgres:16
```

Set DB URL (macOS terminal):
```bash
export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/doctor_support"
```

## Option B: SQLite (default)

If you don’t set `DATABASE_URL`, the app uses:
- `sqlite:///./doctor_support.db`

## Run the app

```bash
cd "/Users/sathya/Downloads/customer support/doctor support"
source doctor-venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql+psycopg2://postgres:postgres@localhost:5432/doctor_support"

python -m streamlit run streamlit_app.py
```

## Notes

- Tables are created automatically on first run (`SQLModel.metadata.create_all`).
- The Streamlit sidebar now has `Customers` and `History`.

