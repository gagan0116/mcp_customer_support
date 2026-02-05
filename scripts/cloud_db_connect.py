import os
from dotenv import load_dotenv
from google.cloud.sql.connector import Connector, IPTypes

load_dotenv()

INSTANCE = os.environ["CLOUD_INSTANCE"]
DB_USER  = os.environ["CLOUD_DB_USER"]
DB_PASS  = os.environ["CLOUD_DB_PASS"]
DB_NAME  = os.environ["CLOUD_DB_NAME"]

connector = Connector()

try:
    conn = connector.connect(
        INSTANCE,
        "pg8000",
        user=DB_USER,
        password=DB_PASS,
        db=DB_NAME,
        ip_type=IPTypes.PUBLIC,  # laptop-friendly
    )
    cur = conn.cursor()
    cur.execute("SELECT * FROM customers;")
    print("✅ Connected. Server time:", cur.fetchone())
    cur.close()
    conn.close()
finally:
    connector.close()