import os
import json
import base64
import time
import logging
import pandas as pd
from openpyxl import Workbook, load_workbook
import datetime
from groq import Groq
from dotenv import load_dotenv

# Setup Logging
log_file_path = os.path.join(os.path.dirname(__file__), 'groq_ocr_process.log')
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY tidak ditemukan di file .env")

groq_client = Groq(api_key=GROQ_API_KEY)

EXCEL_FILE = "hasil_ekstraksi_groq_200.xlsx"

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def extract_json(raw_text):
    """Mengekstrak JSON dari respon LLM."""
    import re
    clean_text = raw_text.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(clean_text)
    except Exception:
        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        return None

def process_image_with_groq(image_path, model_name="llama-3.2-90b-vision-preview"):
    """Mengirim gambar ke Groq API dengan prompt robust."""
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    
    base64_image = base64.b64encode(img_bytes).decode('utf-8')
    
    prompt = """
    Kamu adalah sistem OCR ahli nutrisi (Nutritionist AI). 
    Tugasmu adalah mengekstrak data dari gambar label gizi produk dengan SANGAT TELITI.

    PERINGATAN ALIGNMENT BARIS (SANGAT PENTING):
    1. Label gizi seringkali memiliki baris yang berdekatan seperti "Karbohidrat Total" dan di bawahnya "Gula".
    2. JANGAN MENGAMBIL NILAI DARI BARIS YANG SALAH. Pastikan angka yang kamu ambil benar-benar sejajar dengan nama parameternya.
    3. Jika Gula (Sugars) tertulis 3g, jangan sampai kamu mengambil angka dari Karbohidrat (misal 2g). Baca dari kiri ke kanan secara lurus pada baris yang sama.
    4. Jika parameter tidak terbaca dengan jelas (blur) atau kepotong, berikan nilai null.
    
    INSTRUKSI KHUSUS SATUAN:
    1. **SODIUM / NATRIUM / GARAM**: Wajib konversi ke miligram (mg).
    2. **ENERGI**: Angka dalam kkal (kcal).
    3. **GULA / LEMAK / PROTEIN / SERAT / BUAH**: Angka dalam gram (g). 
    4. **TAKARAN SAJI (Serving Size)**: Angka dalam (gram/ml).

    Keluarkan HANYA JSON murni tanpa markdown apapun.

    OUTPUT JSON FORMAT:
    {
        "nama_produk": "Nama produk",
        "takaran_saji": 0.0,
        "energi": 0.0,
        "protein": 0.0,
        "lemak_jenuh": 0.0,
        "gula": 0.0,
        "natrium": 0.0, 
        "serat": 0.0,
        "buah": 0.0
    }
    """
    
    try:
        logging.info(f"Mengirim request OCR ke {model_name} untuk file: {image_path}")
        response = groq_client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                        }
                    ]
                }
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        return extract_json(response.choices[0].message.content)
    except Exception as e:
        print(f"Error dari Groq: {e}")
        logging.error(f"Error dari Groq untuk file {image_path}: {e}")
        raise e

def print_result(data):
    if not data:
        print("Data kosong.")
        return
    print("-" * 70)
    print("HASIL OCR")
    print("-" * 70)
    print(f"Nama Produk  : {data.get('nama_produk')}")
    print(f"Takaran Saji : {data.get('takaran_saji')}")
    print()
    print(f"Energi       : {data.get('energi')}")
    print(f"Protein      : {data.get('protein')}")
    print(f"Lemak Jenuh  : {data.get('lemak_jenuh')}")
    print(f"Gula         : {data.get('gula')}")
    print(f"Natrium      : {data.get('natrium')}")
    print(f"Serat        : {data.get('serat')}")
    print(f"Buah         : {data.get('buah')}")
    print("-" * 70)

def edit_data(data):
    print("\n========== MODE EDIT ==========\n")
    print("Tekan ENTER jika nilai sudah benar.\n")
    
    # Buat salinan data agar data murni OCR tidak tertimpa!
    aktual_data = data.copy()
    
    fields = [
        ("nama_produk", "Nama Produk", str),
        ("takaran_saji", "Takaran Saji", float),
        ("energi", "Energi", float),
        ("protein", "Protein", float),
        ("lemak_jenuh", "Lemak Jenuh", float),
        ("gula", "Gula", float),
        ("natrium", "Natrium", float),
        ("serat", "Serat", float),
        ("buah", "Buah", float)
    ]
    for key, label, tipe in fields:
        current = aktual_data.get(key)
        user_input = input(f"{label} [{current}] : ").strip()
        if user_input == "":
            continue
        try:
            if user_input.lower() in ['none', 'null', '']:
                aktual_data[key] = ""
            elif tipe == int:
                aktual_data[key] = int(user_input)
            elif tipe == float:
                aktual_data[key] = float(user_input)
            else:
                aktual_data[key] = user_input
        except ValueError:
            print("Input tidak valid, nilai lama dipertahankan.")
            
    return aktual_data

def menu_konfirmasi():
    print("\n" + "=" * 60)
    print("Pilihan")
    print("[Y] Ya, hasil OCR sudah benar (Jadikan Aktual = OCR)")
    print("[E] Edit hasil Aktual (OCR murni akan tetap tersimpan)")
    print("[S] Skip gambar ini")
    print("[Q] Keluar")
    print("=" * 60)
    while True:
        pilihan = input("Pilihan : ").strip().upper()
        if pilihan in ["Y", "E", "S", "Q"]:
            return pilihan
        print("Pilihan tidak dikenali.")

def save_to_excel(kondisi, filename, ocr_data, aktual_data):
    headers = [
        "Filename",
        "Kondisi",
        "Status",
        "Aktual_Nama", "Aktual_Energi", "Aktual_Gula", "Aktual_Lemak", 
        "Aktual_Natrium", "Aktual_Protein", "Aktual_Serat", "Aktual_Takaran", "Aktual_Buah",
        "OCR_Nama", "OCR_Energi", "OCR_Gula", "OCR_Lemak", 
        "OCR_Natrium", "OCR_Protein", "OCR_Serat", "OCR_Takaran", "OCR_Buah"
    ]
    
    if not os.path.exists(EXCEL_FILE):
        wb = Workbook()
        ws = wb.active
        ws.title = "Evaluasi Groq"
        ws.append(headers)
        try:
            wb.save(EXCEL_FILE)
        except PermissionError:
            print(f"\n[Error] Gagal menyimpan! Pastikan file {EXCEL_FILE} tidak dibuka di Excel.")
            raise
            
    try:
        wb = load_workbook(EXCEL_FILE)
    except PermissionError:
        print(f"\n[Error] Gagal membuka! Pastikan file {EXCEL_FILE} tidak dibuka di Excel.")
        raise
        
    ws = wb.active
    
    # Cek apakah sudah ada
    for row in ws.iter_rows(min_row=2):
        if row[0].value == filename and row[1].value == kondisi:
            print(f"\n⚠ {filename} [{kondisi}] sudah ada pada Excel.")
            return

    # Tentukan status
    status = "Verified" if ocr_data == aktual_data else "Edited"
    
    row_data = [
        filename,
        kondisi,
        status,
        aktual_data.get("nama_produk", ""),
        aktual_data.get("energi", ""),
        aktual_data.get("gula", ""),
        aktual_data.get("lemak_jenuh", ""),
        aktual_data.get("natrium", ""),
        aktual_data.get("protein", ""),
        aktual_data.get("serat", ""),
        aktual_data.get("takaran_saji", ""),
        aktual_data.get("buah", ""),
        
        ocr_data.get("nama_produk", ""),
        ocr_data.get("energi", ""),
        ocr_data.get("gula", ""),
        ocr_data.get("lemak_jenuh", ""),
        ocr_data.get("natrium", ""),
        ocr_data.get("protein", ""),
        ocr_data.get("serat", ""),
        ocr_data.get("takaran_saji", ""),
        ocr_data.get("buah", "")
    ]
    
    ws.append(row_data)
    try:
        wb.save(EXCEL_FILE)
        print(f"\n✓ Berhasil disimpan ke {EXCEL_FILE}")
        logging.info(f"Berhasil menyimpan {filename} [{kondisi}] ke Excel dengan status: {status}")
    except PermissionError:
        print(f"\n[Error] Gagal menyimpan! Pastikan file {EXCEL_FILE} tidak dibuka di Excel.")
        raise

def main():
    clear_screen()
    print("=" * 70)
    print(" GENERATE GROUND TRUTH & OCR EVALUATION (GROQ VISION)")
    print("=" * 70)
    logging.info("=== MEMULAI GENERATE GROUND TRUTH GROQ ===")
    
    BASE_FOLDER = "dataset_citra_200" 
    KATEGORI_FOLDERS = ["normal", "blur", "gelap", "ketekuk"]
    
    if not os.path.exists(BASE_FOLDER):
        os.makedirs(BASE_FOLDER)
        for kat in KATEGORI_FOLDERS:
            os.makedirs(os.path.join(BASE_FOLDER, kat), exist_ok=True)
        print(f"📂 Folder '{BASE_FOLDER}' dan subfoldernya telah dibuat.")
        print(f"👉 Masukkan foto ke subfolder lalu jalankan script ini lagi.")
        return

    image_list = []
    for kat in KATEGORI_FOLDERS:
        kat_path = os.path.join(BASE_FOLDER, kat)
        if os.path.exists(kat_path):
            for f in os.listdir(kat_path):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    image_list.append({
                        "filename": f,
                        "kategori": kat,
                        "path": os.path.join(kat_path, f)
                    })
    
    if not image_list:
        print(f"❌ Tidak ada gambar yang ditemukan.")
        return

    # Cek gambar yang sudah diproses di Excel
    processed_images = set()
    if os.path.exists(EXCEL_FILE):
        try:
            wb = load_workbook(EXCEL_FILE)
            ws = wb.active
            for row in ws.iter_rows(min_row=2, values_only=True):
                if row[0] and row[1]: # Filename dan Kondisi
                    processed_images.add((row[0], row[1]))
            print(f"✅ Ditemukan {len(processed_images)} gambar yang sudah diproses sebelumnya.")
        except Exception as e:
            print(f"⚠ Gagal membaca file excel untuk resume: {e}")
            logging.warning(f"Gagal membaca file excel untuk resume: {e}")

    # Filter image_list untuk gambar yang belum diproses
    image_list_to_process = [img for img in image_list if (img['filename'], img['kategori']) not in processed_images]

    print(f"\nJumlah gambar total     : {len(image_list)}")
    print(f"Jumlah gambar tersisa   : {len(image_list_to_process)}")
    
    if not image_list_to_process:
        print("🎉 Semua gambar sudah selesai diproses!")
        return

    input("\nTekan ENTER untuk memulai pemrosesan Groq Vision...")
    
    clear_screen()
    total = len(image_list)
    start_index = len(processed_images) + 1
    
    for idx_offset, img_info in enumerate(image_list_to_process):
        index = start_index + idx_offset
        filename = img_info['filename']
        kondisi = img_info['kategori']
        filepath = img_info['path']
        
        print(f"\n[{index}/{total}]")
        print(f"File    : {filename}")
        print(f"Kondisi : {kondisi}")
        print("\nMemproses OCR...")
        logging.info(f"Memproses gambar [{index}/{total}]: {filename} (Kondisi: {kondisi})")
        
        models = ["meta-llama/llama-4-scout-17b-16e-instruct"]
        current_model_idx = 0
        
        # Coba maks 3 kali per gambar
        max_retry = 3
        data = None
        for attempt in range(1, max_retry + 1):
            current_model = models[current_model_idx]
            try:
                data = process_image_with_groq(filepath, model_name=current_model)
                if data is not None:
                    logging.info(f"OCR berhasil untuk {filename} pada percobaan ke-{attempt} dengan model {current_model}")
                    break
            except Exception as e:
                error_text = str(e)
                print(f"⚠ Gagal OCR attempt {attempt}/{max_retry} dengan model {current_model}")
                logging.warning(f"Gagal OCR {filename} pada percobaan ke-{attempt} ({current_model}): {error_text}")
                
                # Cek apakah ini error rate limit (429)
                if "429" in error_text or "rate_limit_exceeded" in error_text:
                    if "tokens per day (TPD)" in error_text:
                        # Limit harian tercapai, segera ganti model jika masih ada model alternatif
                        if current_model_idx < len(models) - 1:
                            current_model_idx += 1
                            print(f"🔄 Limit Harian {current_model} tercapai! Beralih menggunakan model cadangan: {models[current_model_idx]}...")
                            logging.info(f"Fallback model: Beralih ke {models[current_model_idx]}")
                            # Langsung coba lagi dengan model baru
                            continue
                            
                    import re
                    wait_time = 60 # Default wait 60s
                    # Coba parsing waktu dari pesan error, misal: "Please try again in 1m22.08s"
                    match_m_s = re.search(r'try again in (\d+)m([\d\.]+)s', error_text)
                    match_s = re.search(r'try again in ([\d\.]+)s', error_text)
                    
                    if match_m_s:
                        wait_time = int(match_m_s.group(1)) * 60 + float(match_m_s.group(2)) + 2
                    elif match_s:
                        wait_time = float(match_s.group(1)) + 2
                        
                    print(f"⏳ Rate limit tercapai. Menunggu {wait_time:.2f} detik sebelum mencoba lagi...")
                    time.sleep(wait_time)
                else:
                    time.sleep(3)
        
        if data is None:
            print("\n❌ Gagal total OCR untuk gambar ini. Melewati...\n")
            logging.error(f"Gagal total OCR untuk gambar: {filename}")
            continue
            
        print("\n✓ OCR Berhasil\n")
        print_result(data)
        
        while True:
            pilihan = menu_konfirmasi()
            if pilihan == "Y":
                print("\nMenyimpan ke Excel (Aktual = OCR)...")
                logging.info(f"User memilih [Y] untuk {filename}. Menyimpan Aktual = OCR.")
                save_to_excel(kondisi, filename, ocr_data=data, aktual_data=data.copy())
                break
            elif pilihan == "E":
                aktual_data = edit_data(data)
                print("\nMenyimpan ke Excel (Aktual = Edited)...")
                logging.info(f"User memilih [E] untuk {filename}. Mengedit nilai aktual dan menyimpannya.")
                save_to_excel(kondisi, filename, ocr_data=data, aktual_data=aktual_data)
                break
            elif pilihan == "S":
                print("\n⚠ Gambar dilewati.\n")
                logging.info(f"User memilih [S] untuk {filename}. Gambar dilewati.")
                break
            elif pilihan == "Q":
                print("\nProgram dihentikan.\n")
                logging.info("User memilih [Q]. Program dihentikan.")
                return
                
        if index != total:
            print("Menunggu 2 detik untuk rate limit Groq...")
            time.sleep(2)
            input("\nTekan ENTER untuk gambar berikutnya...")
            clear_screen()

    print("\n" + "=" * 70)
    print("SELESAI MEMPROSES SELURUH GAMBAR")
    print("=" * 70)

if __name__ == "__main__":
    main()
