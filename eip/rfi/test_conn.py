from sqlalchemy import create_engine, text
import psycopg2
from config import RFI_DB, SERVING_DB

def test_rfidb():
    print("Testing RFIDB...")
    engine = create_engine(RFI_DB)

    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ MySQL connected:", result.scalar())
    except Exception as e:
        print("❌ MySQL failed:", e)

def test_servingdb():
    print("Testing SERVINGDB...")
    engine = create_engine(SERVING_DB)

    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✅ Supabase connected:", result.scalar())
    except Exception as e:
        print("❌ Supabase failed:", e)

test_rfidb()
test_servingdb()