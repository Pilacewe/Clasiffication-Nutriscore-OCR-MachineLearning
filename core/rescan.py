import os
import time
import logging
import pandas as pd
from openpyxl import load_workbook, Workbook
from generate_ground_truth_groq import process_image_with_groq

# Setup Logging
log_file_path = os.path.join(os.path.dirname(__file__), 'groq_ocr_rescan.log')
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def process_value(val, field_name):
    if val is None or str(val).lower() in ['none', 'null', 'nan', '']:
        if field_name == "nama_produk":
            return ""
        else:
            return 0
    return val

def main():
    INPUT_EXCEL = "hasil_ekstraksi_groq_200.xlsx"
    OUTPUT_EXCEL = "hasil_ekstraksi_groq_200_pure_ocr.xlsx"
    BASE_FOLDER = "dataset_citra_200"

    clear_screen()
    print("=" * 70)
    print(" RESCAN PURE OCR GROQ (MEMPERTAHANKAN AKTUAL, UPDATE OCR)")
    print("=" * 70)

    if not os.path.exists(INPUT_EXCEL):
        print(f"❌ File {INPUT_EXCEL} tidak ditemukan!")
        return

    try:
        df = pd.read_excel(INPUT_EXCEL)
    except Exception as e:
        print(f"❌ Gagal membaca {INPUT_EXCEL}: {e}")
        return

    if len(df) == 0:
        print("❌ Data Excel kosong.")
        return

    # Buat list dictionaries untuk menyimpan hasil akhir
    results = []
    total = len(df)
    
    # Cek progress sebelumnya jika program sempat terhenti
    processed_images = {}
    if os.path.exists(OUTPUT_EXCEL):
        try:
            df_out = pd.read_excel(OUTPUT_EXCEL)
            for idx, row in df_out.iterrows():
                processed_images[(row['Filename'], row['Kondisi'])] = row.to_dict()
            print(f"✅ Melanjutkan dari {len(processed_images)} gambar yang sudah diproses di {OUTPUT_EXCEL}...")
        except Exception as e:
            print(f"⚠ Gagal membaca file output untuk resume: {e}")

    print(f"Total gambar yang akan diproses: {total - len(processed_images)}")
    
    for index, row in df.iterrows():
        filename = row.get("Filename")
        kondisi = row.get("Kondisi", "normal")
        status = row.get("Status", "Verified")
        
        if (filename, kondisi) in processed_images:
            # Masukkan hasil dari file output yang sudah punya nilai OCR terbaru
            results.append(processed_images[(filename, kondisi)])
            continue
            
        print(f"\n[{index+1}/{total}] Memproses: {filename} ({kondisi})")
        
        # Path gambar
        filepath = os.path.join(BASE_FOLDER, str(kondisi), str(filename))
        if not os.path.exists(filepath):
            # Coba cari di root folder
            filepath = os.path.join(BASE_FOLDER, str(filename))
            if not os.path.exists(filepath):
                print(f"⚠ Gambar tidak ditemukan: {filepath}")
                logging.warning(f"Gambar tidak ditemukan: {filepath}")
                # Tetap masukkan baris asli ke hasil akhir
                results.append(row.to_dict())
                continue

        # Proses OCR dengan retries & fallback model
        models = ["meta-llama/llama-4-scout-17b-16e-instruct"]
        current_model_idx = 0
        max_retry = 3
        ocr_data = None
        
        for attempt in range(1, max_retry + 1):
            current_model = models[current_model_idx]
            try:
                ocr_data = process_image_with_groq(filepath, model_name=current_model)
                if ocr_data is not None:
                    logging.info(f"OCR berhasil untuk {filename} pada percobaan ke-{attempt} dengan model {current_model}")
                    break
            except Exception as e:
                error_text = str(e)
                print(f"⚠ Gagal OCR attempt {attempt}/{max_retry} dengan model {current_model}")
                
                if "429" in error_text or "rate_limit_exceeded" in error_text:
                    if "tokens per day (TPD)" in error_text:
                        if current_model_idx < len(models) - 1:
                            current_model_idx += 1
                            print(f"🔄 Limit Harian {current_model} tercapai! Beralih ke model: {models[current_model_idx]}...")
                            continue
                            
                    import re
                    wait_time = 60
                    match_m_s = re.search(r'try again in (\d+)m([\d\.]+)s', error_text)
                    match_s = re.search(r'try again in ([\d\.]+)s', error_text)
                    if match_m_s:
                        wait_time = int(match_m_s.group(1)) * 60 + float(match_m_s.group(2)) + 2
                    elif match_s:
                        wait_time = float(match_s.group(1)) + 2
                        
                    print(f"⏳ Rate limit tercapai. Menunggu {wait_time:.2f} detik...")
                    time.sleep(wait_time)
                else:
                    time.sleep(3)

        row_dict = row.to_dict()

        if ocr_data:
            print("✓ OCR Berhasil")
            # Update nilai OCR, ubah None menjadi 0 atau "" sesuai permintaan
            row_dict["OCR_Nama"] = process_value(ocr_data.get("nama_produk"), "nama_produk")
            row_dict["OCR_Energi"] = process_value(ocr_data.get("energi"), "energi")
            row_dict["OCR_Gula"] = process_value(ocr_data.get("gula"), "gula")
            row_dict["OCR_Lemak"] = process_value(ocr_data.get("lemak_jenuh"), "lemak_jenuh")
            row_dict["OCR_Natrium"] = process_value(ocr_data.get("natrium"), "natrium")
            row_dict["OCR_Protein"] = process_value(ocr_data.get("protein"), "protein")
            row_dict["OCR_Serat"] = process_value(ocr_data.get("serat"), "serat")
            row_dict["OCR_Takaran"] = process_value(ocr_data.get("takaran_saji"), "takaran_saji")
            row_dict["OCR_Buah"] = process_value(ocr_data.get("buah"), "buah")
        else:
            print("❌ OCR Gagal, nilai OCR dibiarkan seperti sebelumnya.")
            
        results.append(row_dict)
        
        # Simpan ke Excel setiap kali selesai memproses 1 gambar agar aman
        try:
            out_df = pd.DataFrame(results)
            out_df.to_excel(OUTPUT_EXCEL, index=False)
        except Exception as e:
            print(f"⚠ Gagal menyimpan progres ke Excel: {e}")

        # Rate limit delay ringan
        if index + 1 < total:
            time.sleep(2)

    print("\n" + "=" * 70)
    print(f"✅ Selesai memproses seluruh gambar! File tersimpan di: {OUTPUT_EXCEL}")
    print("=" * 70)

if __name__ == "__main__":
    main()
