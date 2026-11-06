import os
import sys
import time
import datetime
from openpyxl import Workbook, load_workbook

# Menambahkan root folder proyek ke sys.path agar bisa import module 'core'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.ocr_engine import extract_nutrition_from_image

# ==========================================================
# KONFIGURASI
# ==========================================================
EXCEL_FILE = os.path.join("dataset", "ground_truth.xlsx")
UPLOAD_FOLDER = os.path.join("static", "uploads")
SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")
# Delay antar request Gemini (detik)
REQUEST_DELAY = 2

# ==========================================================
# FUNGSI UTILITAS
# ==========================================================
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_header():
    print("=" * 70)
    print(" NUTRIGUARD AI - GROUND TRUTH GENERATOR")
    print("=" * 70)

def get_image_files_with_conditions(base_folder):
    """
    Mengambil file gambar beserta folder kondisinya.
    Misal folder: static/uploads/normal, static/uploads/blur
    """
    files_with_conditions = []
    
    if not os.path.exists(base_folder):
        return []

    for item in os.listdir(base_folder):
        item_path = os.path.join(base_folder, item)
        if os.path.isdir(item_path):
            kondisi = item
            for file in os.listdir(item_path):
                if file.lower().endswith(SUPPORTED_EXTENSIONS):
                    files_with_conditions.append({
                        "kondisi": kondisi,
                        "filename": file,
                        "filepath": os.path.join(item_path, file)
                    })
        elif item.lower().endswith(SUPPORTED_EXTENSIONS):
            # Jika file ada di root static/uploads (tanpa subfolder kondisi)
            files_with_conditions.append({
                "kondisi": "normal", # Default
                "filename": item,
                "filepath": item_path
            })
            
    files_with_conditions.sort(key=lambda x: (x["kondisi"], x["filename"]))
    return files_with_conditions

def print_result(data):
    print("-" * 70)
    print(f"Nama Produk  : {data.get('nama_produk')}")
    print(f"Brand        : {data.get('brand')}")
    print(f"Kategori     : {data.get('kategori')}")
    print(f"Takaran Saji : {data.get('takaran_saji')}")
    print()
    print(f"Energi       : {data.get('energi')}")
    print(f"Protein      : {data.get('protein')}")
    print(f"Lemak Jenuh  : {data.get('lemak_jenuh')}")
    print(f"Gula         : {data.get('gula')}")
    print(f"Garam        : {data.get('garam')}")
    print(f"Serat        : {data.get('serat')}")
    print(f"Buah         : {data.get('buah')}")
    print("-" * 70)

# ==========================================================
# EDIT DATA OCR
# ==========================================================
def edit_data(data):
    print("\n========== MODE EDIT ==========\n")
    print("Tekan ENTER jika nilai sudah benar.\n")

    fields = [
        ("nama_produk", "Nama Produk", str),
        ("brand", "Brand", str),
        ("kategori", "Kategori", int),
        ("takaran_saji", "Takaran Saji", float),
        ("energi", "Energi", float),
        ("protein", "Protein", float),
        ("lemak_jenuh", "Lemak Jenuh", float),
        ("gula", "Gula", float),
        ("garam", "Garam", float),
        ("serat", "Serat", float),
        ("buah", "Buah", float)
    ]

    for key, label, tipe in fields:
        current = data.get(key)
        user_input = input(f"{label} [{current}] : ").strip()

        if user_input == "":
            continue
        try:
            if tipe == int:
                data[key] = int(user_input)
            elif tipe == float:
                data[key] = float(user_input)
            else:
                data[key] = user_input
        except ValueError:
            print("Input tidak valid, nilai lama dipertahankan.")

    return data

# ==========================================================
# MENU PILIHAN
# ==========================================================
def menu_konfirmasi():
    print("\n")
    print("=" * 60)
    print("Pilihan")
    print("[Y] Ya, hasil OCR sudah benar")
    print("[E] Edit hasil OCR")
    print("[S] Skip gambar ini")
    print("[Q] Keluar")
    print("=" * 60)
    while True:
        pilihan = input("Pilihan : ").strip().upper()
        if pilihan in ["Y", "E", "S", "Q"]:
            return pilihan
        print("Pilihan tidak dikenali.")

# ==========================================================
# SIMPAN KE EXCEL
# ==========================================================
def save_to_excel(kondisi, filename, data, status="Verified"):
    os.makedirs("dataset", exist_ok=True)

    headers = [
        "filename",
        "kondisi",
        "tanggal",
        "status",
        "nama_produk",
        "brand",
        "kategori",
        "takaran_saji",
        "energi",
        "protein",
        "lemak_jenuh",
        "gula",
        "garam",
        "serat",
        "buah"
    ]

    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.title = "Ground Truth"
        ws.append(headers)
        try:
            wb.save(EXCEL_FILE)
        except PermissionError:
            print(f"\n[Error] Gagal menyimpan! Pastikan file {EXCEL_FILE} tidak sedang dibuka di Excel.")
            raise

    try:
        wb = load_workbook(EXCEL_FILE)
    except PermissionError:
        print(f"\n[Error] Gagal membuka! Pastikan file {EXCEL_FILE} tidak sedang dibuka di Excel.")
        raise
        
    ws = wb.active
    for row in ws.iter_rows(min_row=2):
        if row[0].value == filename and row[1].value == kondisi:
            print(f"\n⚠ {filename} [{kondisi}] sudah ada pada Excel.")
            return

    tanggal = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append([
        filename,
        kondisi,
        tanggal,
        status,
        data.get("nama_produk"),
        data.get("brand"),
        data.get("kategori"),
        data.get("takaran_saji"),
        data.get("energi"),
        data.get("protein"),
        data.get("lemak_jenuh"),
        data.get("gula"),
        data.get("garam"),
        data.get("serat"),
        data.get("buah")
    ])

    try:
        wb.save(EXCEL_FILE)
        print("\n✓ Berhasil disimpan ke ground_truth.xlsx")
    except PermissionError:
        print(f"\n[Error] Gagal menyimpan! Pastikan file {EXCEL_FILE} tidak sedang dibuka di Excel.")
        raise

# ==========================================================
# OCR DENGAN RETRY
# ==========================================================
def run_ocr_with_retry(image_path, max_retry=5):
    for attempt in range(1, max_retry + 1):
        try:
            data, raw_text = extract_nutrition_from_image(image_path)
            return data, raw_text
        except Exception as e:
            error_text = str(e)
            print(f"\nOCR gagal ({attempt}/{max_retry})")
            print(error_text)
            
            if (
                "429" in error_text
                or "RESOURCE_EXHAUSTED" in error_text
                or "quota" in error_text.lower()
                or "rate" in error_text.lower()
            ):
                wait_time = 60
                print(f"\nRate limit.")
                print(f"Menunggu {wait_time} detik...\n")
                time.sleep(wait_time)
                continue
            raise
    raise Exception("Melebihi batas retry OCR.")

# ==========================================================
# MAIN PROGRAM
# ==========================================================
def main():
    clear_screen()
    print_header()

    if not os.path.exists(UPLOAD_FOLDER):
        print(f"\nFolder tidak ditemukan : {UPLOAD_FOLDER}")
        return

    images_info = get_image_files_with_conditions(UPLOAD_FOLDER)
    
    if len(images_info) == 0:
        print("\nTidak ada gambar pada folder uploads. Buatlah folder kondisi seperti 'normal', 'blur', 'gelap', 'ketekuk' di dalam 'static/uploads/' dan letakkan gambar di dalamnya.")
        return

    print(f"\nJumlah gambar ditemukan : {len(images_info)}")
    input("\nTekan ENTER untuk memulai OCR...")
    
    clear_screen()
    print_header()

    total = len(images_info)
    
    for index, info in enumerate(images_info, start=1):
        filename = info["filename"]
        kondisi = info["kondisi"]
        filepath = info["filepath"]

        print(f"\n[{index}/{total}]")
        print(f"File    : {filename}")
        print(f"Kondisi : {kondisi}")
        print("\nMemproses OCR...")
        
        try:
            data, raw_text = run_ocr_with_retry(filepath)
            
            print("\n✓ OCR Berhasil\n")
            print_result(data)

            status_ocr = "Verified"

            while True:
                pilihan = menu_konfirmasi()

                if pilihan == "Y":
                    print("\nMenyimpan ke Excel...\n")
                    try:
                        save_to_excel(kondisi, filename, data, status_ocr)
                    except PermissionError:
                        print("Mohon tutup Microsoft Excel lalu coba lagi.")
                    break
                elif pilihan == "E":
                    data = edit_data(data)
                    status_ocr = "Edited"
                    print("\nHasil setelah diedit\n")
                    print_result(data)
                elif pilihan == "S":
                    print("\n⚠ Gambar dilewati.\n")
                    break
                elif pilihan == "Q":
                    print("\nProgram dihentikan.\n")
                    return

        except Exception as e:
            print("\n❌ OCR Gagal")
            print(e)
            
        print("\n")
        
        if index != total:
            print(f"Menunggu {REQUEST_DELAY} detik...")
            time.sleep(REQUEST_DELAY)
            input("\nTekan ENTER untuk gambar berikutnya...")
            clear_screen()
            print_header()

    print("\n")
    print("=" * 70)
    print("SELESAI MEMPROSES SELURUH GAMBAR")
    print("=" * 70)

# ==========================================================
# ENTRY POINT
# ==========================================================
if __name__ == "__main__":
    main()
