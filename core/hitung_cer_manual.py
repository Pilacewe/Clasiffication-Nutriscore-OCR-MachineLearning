import os
import sys
from openpyxl import load_workbook

# Menambahkan root folder proyek ke sys.path agar bisa import module 'core'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

HASIL_EVALUASI_FILE = os.path.join("dataset", "hasil_evaluasi_ocr.xlsx")

# ==========================================================
# FUNGSI UTILITAS
# ==========================================================
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

def calculate_metrics_manual(gt_data, ocr_data):
    """
    Menghitung Field Accuracy dan Character Error Rate (CER).
    Sesuai permintaan, HANYA mengecek field numerik/kategori (mengabaikan nama_produk dan brand).
    """
    fields = [
        "kategori", "takaran_saji",
        "energi", "protein", "lemak_jenuh", "gula",
        "garam", "serat", "buah"
    ]
    
    total_fields = 0
    matched_fields = 0
    total_char_dist = 0
    total_char_len = 0
    
    for field in fields:
        gt_val = str(gt_data.get(f"{field}_gt", "")).strip()
        if gt_val == "None": gt_val = ""
        
        ocr_val = str(ocr_data.get(f"{field}_ocr", "")).strip()
        if ocr_val == "None": ocr_val = ""
        
        # --- Hitung Field Accuracy ---
        total_fields += 1
        
        # Kita coba handle perbandingan angka supaya lebih toleran 
        # (misal 10.0 dianggap sama dengan 10)
        try:
            gt_float = float(gt_val)
            ocr_float = float(ocr_val)
            if gt_float == ocr_float:
                matched_fields += 1
            else:
                pass
        except ValueError:
            # Jika bukan angka, bandingkan string
            if gt_val.lower() == ocr_val.lower():
                matched_fields += 1
            
        # --- Hitung Character Error Rate (CER) ---
        # Untuk CER, .0 di belakang string sering membuat error menjadi tinggi padahal secara makna sama
        def clean_num_str(val):
            if val.endswith(".0"):
                return val[:-2]
            return val
            
        gt_clean = clean_num_str(gt_val)
        ocr_clean = clean_num_str(ocr_val)
        
        dist = levenshtein_distance(gt_clean, ocr_clean)
        total_char_dist += dist
        total_char_len += len(gt_clean)
        
    field_accuracy = (matched_fields / total_fields) * 100 if total_fields > 0 else 0
    # CER dapat melebihi 100% jika banyak insersi, kita ubah jadi bentuk persentase
    cer = (total_char_dist / total_char_len) * 100 if total_char_len > 0 else 0
    
    return field_accuracy, cer

# ==========================================================
# MAIN PROGRAM
# ==========================================================
def main():
    print("=" * 70)
    print(" NUTRIGUARD AI - HITUNG CER & FIELD ACCURACY MANUAL")
    print("=" * 70)
    
    if not os.path.exists(HASIL_EVALUASI_FILE):
        print(f"\n[Error] File {HASIL_EVALUASI_FILE} tidak ditemukan!")
        return
        
    # Membaca data hasil evaluasi
    wb = load_workbook(HASIL_EVALUASI_FILE)
    ws = wb.active
    
    headers = [cell.value for cell in ws[1]]
    if not headers or "filename" not in headers:
        print("\n[Error] Format Excel tidak valid atau kosong!")
        return
        
    print("Memulai perhitungan ulang metrik...\n")
    
    total_avg_field_acc = 0
    total_avg_cer = 0
    berhasil = 0
    
    # Metrik per kondisi
    kondisi_metrics = {}
    
    # Mencari index untuk Field Accuracy (%) dan CER (%)
    # Jika tidak ada, tambahkan header baru
    if "Field Accuracy (%)" not in headers:
        ws.cell(row=1, column=len(headers)+1, value="Field Accuracy (%)")
        acc_col_idx = len(headers) + 1
    else:
        acc_col_idx = headers.index("Field Accuracy (%)") + 1

    if "CER (%)" not in headers:
        ws.cell(row=1, column=len(headers)+2, value="CER (%)")
        cer_col_idx = len(headers) + 2
    else:
        cer_col_idx = headers.index("CER (%)") + 1

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0]: # skip baris kosong
            continue
            
        record = dict(zip(headers, row))
        filename = record.get("filename")
        kondisi = record.get("kondisi", "normal") # Ambil kondisi jika ada
        
        # Ekstrak data GT dan OCR dari record
        gt_data = {k: v for k, v in record.items() if k and k.endswith("_gt")}
        ocr_data = {k: v for k, v in record.items() if k and k.endswith("_ocr")}
        
        field_acc, cer = calculate_metrics_manual(gt_data, ocr_data)
        
        # Update nilai di file Excel
        ws.cell(row=row_idx, column=acc_col_idx, value=round(field_acc, 2))
        ws.cell(row=row_idx, column=cer_col_idx, value=round(cer, 2))
        
        print(f"[{berhasil+1}] Memproses: {filename} [{kondisi}]")
        print(f"    ✓ Selesai. Field Acc: {field_acc:.2f}%, CER: {cer:.2f}%")
        
        total_avg_field_acc += field_acc
        total_avg_cer += cer
        berhasil += 1
        
        # Tambahkan ke metrik kondisi
        if kondisi not in kondisi_metrics:
            kondisi_metrics[kondisi] = {"total": 0, "acc": 0, "cer": 0}
        kondisi_metrics[kondisi]["total"] += 1
        kondisi_metrics[kondisi]["acc"] += field_acc
        kondisi_metrics[kondisi]["cer"] += cer
        
    # Simpan file evaluasi
    try:
        wb.save(HASIL_EVALUASI_FILE)
        print(f"\n[Info] Berhasil menyimpan pembaruan ke {HASIL_EVALUASI_FILE}")
    except PermissionError:
        print(f"\n[Error] Gagal menyimpan! Pastikan file {HASIL_EVALUASI_FILE} tidak sedang dibuka di Excel (TUTUP EXCEL SEBELUM MENJALANKAN).")
    
    print("\n" + "=" * 70)
    print(" PERHITUNGAN SELESAI")
    print("=" * 70)
    
    if berhasil > 0:
        avg_field_acc = total_avg_field_acc / berhasil
        avg_cer = total_avg_cer / berhasil
        print(f"Total Gambar Dievaluasi : {berhasil}")
        print(f"Rata-rata Field Acc     : {avg_field_acc:.2f}%")
        print(f"Rata-rata CER           : {avg_cer:.2f}%")
        
        print("\n--- Rincian Berdasarkan Kondisi ---")
        for k, v in kondisi_metrics.items():
            if v["total"] > 0:
                k_acc = v["acc"] / v["total"]
                k_cer = v["cer"] / v["total"]
                print(f"Kondisi '{k}' (Total: {v['total']}):")
                print(f"  - Field Acc : {k_acc:.2f}%")
                print(f"  - CER       : {k_cer:.2f}%")

if __name__ == "__main__":
    main()
