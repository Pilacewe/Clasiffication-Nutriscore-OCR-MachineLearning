import os
import MySQLdb
from dotenv import load_dotenv

# Muat variabel rahasia dari .env
load_dotenv()

def get_db_connection():
    """Membuat koneksi ke database MySQL."""
    try:
        connection = MySQLdb.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            passwd=os.getenv('DB_PASS', ''),
            db=os.getenv('DB_NAME', 'db_nutriscan'),
            autocommit=True # Otomatis simpan data saat ada INSERT/UPDATE
        )
        return connection
    except Exception as e:
        print(f"⚠️ Gagal terhubung ke MySQL: {e}")
        return None