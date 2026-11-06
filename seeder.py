import pandas as pd
import math
from core.db_config import get_db_connection

def seed_database():
    print("🌱 Menjalankan Seeder Database NutriScan...")
    conn = get_db_connection()
    
    if not conn:
        print("❌ Gagal terhubung ke MySQL. Pastikan Laragon menyala.")
        return

    try:
        # Ganti nama file ini sesuai dengan nama CSV datamu yang sebenarnya
        file_path = 'final_indo_scored.csv' 
        print(f"📖 Membaca data dari {file_path}...")
        
        # Membaca CSV menggunakan Pandas
        df = pd.read_csv(file_path)
        
        cursor = conn.cursor()
        berhasil = 0

        for index, row in df.iterrows():
            # Mengatasi nilai NaN/Kosong dari CSV agar tidak error di MySQL
            nama = str(row.get('nama_produk', 'Produk Tanpa Nama'))
            grade = str(row.get('nutriscore_grade', 'E')).upper()
            kategori = str(row.get('kategori', 'makanan'))
            
            # Helper untuk mengubah NaN menjadi 0.0
            def clean_float(val):
                return 0.0 if pd.isna(val) or math.isnan(float(val)) else float(val)

            kalori = clean_float(row.get('kalori', 0))
            gula = clean_float(row.get('gula', 0))
            lemak = clean_float(row.get('lemak_jenuh', 0))
            garam = clean_float(row.get('garam', 0))

            # Cek apakah produk sudah ada (mencegah duplikat saat dijalankan 2x)
            cursor.execute("SELECT id FROM products WHERE nama_produk = %s LIMIT 1", (nama,))
            if cursor.fetchone():
                continue # Lewati jika sudah ada

            # Masukkan ke database
            cursor.execute("""
                INSERT INTO products (nama_produk, kategori, nutriscore_grade, kalori, gula, lemak_jenuh, garam)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (nama, kategori, grade, kalori, gula, lemak, garam))
            
            berhasil += 1

        print(f"✅ Seeder Selesai! Berhasil memasukkan {berhasil} produk baru ke Database.")

    except Exception as e:
        print(f"❌ Error saat seeding: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    seed_database()