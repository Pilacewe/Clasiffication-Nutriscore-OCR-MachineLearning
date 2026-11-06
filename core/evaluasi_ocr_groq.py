import os
import pandas as pd
import logging

# Setup Logging
log_file_path = os.path.join(os.path.dirname(__file__), 'groq_ocr_evaluation.log')
logging.basicConfig(
    filename=log_file_path,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def levenshtein_distance(s1, s2):
    """Menghitung Levenshtein distance antara dua string."""
    s1 = str(s1).lower().strip()
    s2 = str(s2).lower().strip()

    if len(s1) > len(s2):
        s1, s2 = s2, s1

    distances = range(len(s1) + 1)
    for i2, c2 in enumerate(s2):
        distances_ = [i2+1]
        for i1, c1 in enumerate(s1):
            if c1 == c2:
                distances_.append(distances[i1])
            else:
                distances_.append(1 + min((distances[i1], distances[i1 + 1], distances_[-1])))
        distances = distances_
    return distances[-1]

def normalize_val(val):
    s = str(val).strip()
    if s.lower() in ["nan", "none", ""]:
        return ""
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return str(f)
    except ValueError:
        return s

def calculate_metrics(gt_val, ocr_val):
    """Menghitung Field Accuracy (0 atau 1) dan CER untuk 1 field."""
    gt_str = normalize_val(gt_val)
    ocr_str = normalize_val(ocr_val)
    
    is_match = 1 if gt_str.lower() == ocr_str.lower() else 0
    
    dist = levenshtein_distance(gt_str, ocr_str)
    char_len = len(gt_str)
    
    return is_match, dist, char_len

def main():
    INPUT_FILE = "hasil_ekstraksi_groq_200_pure_ocr.xlsx"
    OUTPUT_FILE = "laporan_evaluasi_groq_200_pure_ocr.xlsx"
    
    print("=" * 70)
    print(" NUTRIGUARD AI - EVALUASI OCR (GROQ VISION ONLY)")
    print("=" * 70)
    
    logging.info("=== MEMULAI EVALUASI OCR GROQ ===")
    
    if not os.path.exists(INPUT_FILE):
        print(f"\n❌ [Error] File {INPUT_FILE} tidak ditemukan!")
        logging.error(f"File input {INPUT_FILE} tidak ditemukan.")
        print("Silakan jalankan 'generate_ground_truth_groq.py' terlebih dahulu dan isi kolom Aktual_...-nya.")
        return
        
    try:
        df = pd.read_excel(INPUT_FILE)
    except Exception as e:
        print(f"❌ Gagal membaca {INPUT_FILE}: {e}")
        logging.error(f"Gagal membaca {INPUT_FILE}: {e}")
        return
        
    if len(df) == 0:
        print("\n[Info] Data masih kosong. Belum ada yang bisa dievaluasi.")
        logging.info("Data excel masih kosong, belum bisa dievaluasi.")
        return

    fields = ["Energi", "Gula", "Lemak", "Natrium", "Protein", "Serat", "Takaran", "Buah"]
    
    results = []
    kondisi_metrics = {}
    total_avg_field_acc = 0
    total_avg_cer = 0
    
    print(f"✅ Menemukan {len(df)} data. Memulai kalkulasi...")
    logging.info(f"Ditemukan {len(df)} baris data. Memulai kalkulasi Field Accuracy & CER.")
    
    for index, row in df.iterrows():
        filename = row.get("Filename", f"Row_{index+1}")
        kondisi = row.get("Kondisi", "normal")
        if pd.isna(kondisi):
            kondisi = "normal"
        kondisi = str(kondisi)
        
        matched_fields = 0
        total_char_dist = 0
        total_char_len = 0
        
        row_result = {
            "Filename": filename,
            "Kondisi": kondisi
        }
        
        for field in fields:
            aktual_val = row.get(f"Aktual_{field}", "")
            ocr_val = row.get(f"OCR_{field}", "")
            
            # Jika aktual kosong (misal tidak ada di label/blur parah), kita skip penghitungan utk field ini
            # atau bisa juga diset sebagai wajib sama-sama kosong
            if pd.isna(aktual_val): aktual_val = ""
            if pd.isna(ocr_val): ocr_val = ""
            
            # Menyimpan nilai untuk laporan
            row_result[f"Aktual_{field}"] = aktual_val
            row_result[f"OCR_{field}"] = ocr_val
            
            # Hanya hitung akurasi jika memang ada data aktual yang diharapkan, ATAU jika keduanya kosong
            # Mari hitung semua secara harfiah.
            is_match, dist, char_len = calculate_metrics(aktual_val, ocr_val)
            matched_fields += is_match
            total_char_dist += dist
            
            # Untuk field yang aktualnya kosong (char_len=0) tapi ocr-nya menebak (dist>0),
            # kita jadikan char_len minimal 1 agar CER bisa dihitung (penalty).
            if char_len == 0 and dist > 0:
                char_len = dist
                
            total_char_len += char_len
            
        field_accuracy = (matched_fields / len(fields)) * 100
        cer = (total_char_dist / total_char_len) * 100 if total_char_len > 0 else 0
        
        row_result["Field_Accuracy(%)"] = round(field_accuracy, 2)
        row_result["CER(%)"] = round(cer, 2)
        
        results.append(row_result)
        
        total_avg_field_acc += field_accuracy
        total_avg_cer += cer
        
        if kondisi not in kondisi_metrics:
            kondisi_metrics[kondisi] = {"total": 0, "acc": 0, "cer": 0}
        kondisi_metrics[kondisi]["total"] += 1
        kondisi_metrics[kondisi]["acc"] += field_accuracy
        kondisi_metrics[kondisi]["cer"] += cer
        
        logging.info(f"File {filename} ({kondisi}) - Field Acc: {field_accuracy:.2f}%, CER: {cer:.2f}%")

    # Menyimpan laporan akhir
    try:
        out_df = pd.DataFrame(results)
        out_df.to_excel(OUTPUT_FILE, index=False)
        print(f"\n✅ Laporan detail berhasil disimpan ke {OUTPUT_FILE}")
        logging.info(f"Laporan berhasil disimpan ke {OUTPUT_FILE}")
    except Exception as e:
        print(f"❌ Gagal menyimpan {OUTPUT_FILE}: {e}")
        logging.error(f"Gagal menyimpan laporan {OUTPUT_FILE}: {e}")

    # Mencetak ringkasan
    print("\n" + "=" * 70)
    print(" RINGKASAN EVALUASI")
    print("=" * 70)
    
    total_data = len(df)
    print(f"Total Gambar Dievaluasi : {total_data}")
    print(f"Rata-rata Field Acc     : {total_avg_field_acc / total_data:.2f}%")
    print(f"Rata-rata CER           : {total_avg_cer / total_data:.2f}%")
    
    logging.info(f"Ringkasan: Total Gambar={total_data}, Avg Field Acc={total_avg_field_acc/total_data:.2f}%, Avg CER={total_avg_cer/total_data:.2f}%")
    
    print("\n--- Rincian Berdasarkan Kondisi Citra ---")
    # Urutkan untuk report agar rapi
    for k in sorted(kondisi_metrics.keys()):
        v = kondisi_metrics[k]
        if v["total"] > 0:
            k_acc = v["acc"] / v["total"]
            k_cer = v["cer"] / v["total"]
            print(f"Kondisi '{k}' (Total: {v['total']} citra):")
            print(f"  - Field Acc : {k_acc:.2f}%")
            print(f"  - CER       : {k_cer:.2f}%")
            logging.info(f"Kondisi '{k}' - Total: {v['total']}, Avg Acc: {k_acc:.2f}%, Avg CER: {k_cer:.2f}%")

if __name__ == "__main__":
    main()
