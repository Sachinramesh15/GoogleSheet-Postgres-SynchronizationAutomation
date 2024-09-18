import os
import psycopg2
import requests
from contextlib import contextmanager
from dotenv import load_dotenv
from decimal import Decimal
from datetime import date
import time

load_dotenv()

DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

LISTEN_CHANNEL = 'db_changes'
NGROK_URL = os.getenv("NGROK_URL")


@contextmanager
def get_db_connection():
    """Context manager to connect to the PostgreSQL database using psycopg2."""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def create_table():
    """Create a table in the database with lead_id as the primary key."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    lead_id INT PRIMARY KEY,  
                    client_name VARCHAR(255),
                    lead_status VARCHAR(50),
                    assigned_sales_rep VARCHAR(100),
                    expected_value NUMERIC,
                    close_date DATE
                );
            """)


def insert_data(values):
    """Insert or update data in the PostgreSQL database based on lead_id."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany("""
                INSERT INTO leads (lead_id, client_name, lead_status, assigned_sales_rep, expected_value, close_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (lead_id)  -- Handle conflict based on lead_id
                DO UPDATE SET
                    client_name = EXCLUDED.client_name,
                    lead_status = EXCLUDED.lead_status,
                    assigned_sales_rep = EXCLUDED.assigned_sales_rep,
                    expected_value = EXCLUDED.expected_value,
                    close_date = EXCLUDED.close_date;
            """, values)


def convert_data_for_json(data):
    """Convert Decimal and date objects in the data to serializable formats."""
    return [
        [float(value) if isinstance(value, Decimal) else value.strftime(
            '%Y-%m-%d') if isinstance(value, date) else value for value in row]
        for row in data
    ]


def fetch_data():
    """Fetch data from the PostgreSQL database."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM leads;")
            rows = cur.fetchall()
            return convert_data_for_json(rows)


def delete_rows(lead_ids):
    """Delete rows from the database based on lead_ids."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if len(lead_ids) == 1:
                cur.execute("""
                    DELETE FROM leads
                    WHERE lead_id = %s;
                """, (list(lead_ids)[0],))
            else:
                cur.execute("""
                    DELETE FROM leads
                    WHERE lead_id IN %s;
                """, (tuple(lead_ids),))
            conn.commit()


def setup_triggers():
    """Set up PostgreSQL triggers to notify on changes, if not already created."""
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*)
                FROM pg_proc
                WHERE proname = 'notify_db_change';
            """)
            function_exists = cur.fetchone()[0] > 0

            if not function_exists:
                cur.execute("""
                    CREATE OR REPLACE FUNCTION notify_db_change() RETURNS trigger AS $$
                    BEGIN
                        PERFORM pg_notify(%s, 'Data changed');
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                """, (LISTEN_CHANNEL,))

            cur.execute("""
                SELECT COUNT(*)
                FROM pg_trigger
                WHERE tgname = 'db_change_trigger';
            """)
            trigger_exists = cur.fetchone()[0] > 0

            if not trigger_exists:
                cur.execute("""
                    CREATE TRIGGER db_change_trigger
                    AFTER INSERT OR UPDATE OR DELETE ON leads
                    FOR EACH ROW EXECUTE FUNCTION notify_db_change();
                """)


def listen_for_changes():
    """Listen for changes on PostgreSQL and call the sync endpoint."""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    with conn.cursor() as cur:
        cur.execute(f"LISTEN {LISTEN_CHANNEL};")
        print("Listening for database changes...")

        while True:
            conn.poll()
            if conn.notifies:
                for notify in conn.notifies:
                    print(f"Received notification: {notify.payload}")
                    try:
                        response = requests.post(NGROK_URL)
                        print(f"Sync response: {response.json()}")
                    except requests.RequestException as e:
                        print(f"Error sending sync request: {e}")
                conn.notifies.clear()
            time.sleep(1)