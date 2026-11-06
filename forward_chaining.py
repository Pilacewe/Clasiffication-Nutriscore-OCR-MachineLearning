# ==============================================================================
# forward_chaining.py
# Modul Mesin Inferensi untuk Perhitungan Status Gizi & Batas Gula
# ==============================================================================

def hitung_imt(berat_kg, tinggi_cm):
    """Menghitung Indeks Massa Tubuh (IMT) dan kategorinya (Standar Asia)"""
    tinggi_m = tinggi_cm / 100
    imt = berat_kg / (tinggi_m ** 2)
    
    # Aturan IF-THEN untuk Kategori IMT
    if imt < 18.5:
        kategori = "Berat Badan Kurang"
    elif 18.5 <= imt <= 22.9:
        kategori = "Berat Badan Normal"
    elif 23.0 <= imt <= 24.9:
        kategori = "Kelebihan Berat Badan"
    elif 25.0 <= imt <= 29.9:
        kategori = "Obesitas Tingkat I"
    else:
        kategori = "Obesitas Tingkat II"
        
    return round(imt, 2), kategori

def hitung_bbi(tinggi_cm, gender):
    """Menghitung Berat Badan Ideal (BBI) menggunakan Modifikasi Rumus Broca"""
    gender = gender.lower()
    
    if (gender == 'pria' and tinggi_cm >= 160) or (gender == 'wanita' and tinggi_cm >= 150):
        bbi = (tinggi_cm - 100) - (0.10 * (tinggi_cm - 100))
    else:
        bbi = tinggi_cm - 100
        
    return round(bbi, 2)

def hitung_kebutuhan_kalori(bbi, gender, kategori_imt, umur, aktivitas):
    """Menghitung kalori dasar dan melakukan koreksi berdasarkan status gizi, umur, dan aktivitas"""
    gender = gender.lower()
    aktivitas = aktivitas.lower()
    
    # 1. Hitung Kalori Dasar
    if gender == 'pria':
        kalori_dasar = 30 * bbi
    else:
        kalori_dasar = 25 * bbi
        
    # 2. Koreksi Umur (Sederhana sesuai PERKENI)
    koreksi_umur = 0
    if 40 <= umur <= 59:
        koreksi_umur = -0.05
    elif 60 <= umur <= 69:
        koreksi_umur = -0.10
    elif umur >= 70:
        koreksi_umur = -0.20
        
    # 3. Koreksi Aktivitas Fisik
    if aktivitas == "istirahat":
        koreksi_aktivitas = 0.10
    elif aktivitas == "ringan":
        koreksi_aktivitas = 0.20
    elif aktivitas == "sedang":
        koreksi_aktivitas = 0.30
    elif aktivitas == "berat":
        koreksi_aktivitas = 0.40
    elif aktivitas == "sangat berat":
        koreksi_aktivitas = 0.50
    else:
        koreksi_aktivitas = 0 # Default jika tidak diisi
        
    # 4. Koreksi Status Gizi (IMT)
    if kategori_imt == "Berat Badan Kurang":
        koreksi_bb = 0.20
    elif kategori_imt in ["Kelebihan Berat Badan", "Obesitas Tingkat I", "Obesitas Tingkat II"]:
        koreksi_bb = -0.20
    else:
        koreksi_bb = 0
        
    # 5. Total Kalori Keseluruhan
    total_kalori = kalori_dasar + (kalori_dasar * koreksi_aktivitas) + (kalori_dasar * koreksi_umur) + (kalori_dasar * koreksi_bb)
        
    return round(total_kalori, 2)

def hitung_batas_gula(total_kalori):
    """Menghitung batas maksimal konsumsi gula harian (5% dari total kalori)"""
    # 1 gram karbohidrat = 4 kkal
    batas_gula_gram = (0.05 * total_kalori) / 4
    return round(batas_gula_gram, 2)

def evaluasi_produk(gula_produk, batas_gula_harian):
    """Mesin Inferensi Utama (Aturan IF-THEN penentu peringatan)"""
    if gula_produk > batas_gula_harian:
        status = "BAHAYA"
        pesan = f"Peringatan! Kandungan gula produk ({gula_produk}g) melebihi batas aman harian Anda ({batas_gula_harian}g)."
    elif gula_produk > (0.5 * batas_gula_harian):
        status = "WASPADA"
        pesan = f"Hati-hati, kandungan gula produk ({gula_produk}g) sudah memakan lebih dari setengah batas harian Anda."
    else:
        status = "AMAN"
        pesan = f"Produk aman dikonsumsi. Kandungan gula ({gula_produk}g) masih di bawah batas harian."
        
    return status, pesan

# ==============================================================================
# BLOK TESTING (Hanya jalan jika file ini di-run langsung)
# ==============================================================================
if __name__ == "__main__":
    print("--- TESTING MESIN FORWARD CHAINING (UPDATE PERKENI) ---")
    
    # Data Simulasi Sdr. Asep
    berat_user = 80       # kg
    tinggi_user = 165     # cm
    gender_user = "Pria"
    umur_user = 35        # tahun
    aktivitas_user = "sedang"
    gula_dari_ocr = 12    # gram (hasil baca label kemasan)
    
    imt_val, imt_kat = hitung_imt(berat_user, tinggi_user)
    bbi_val = hitung_bbi(tinggi_user, gender_user)
    
    # Masukkan Umur dan Aktivitas ke dalam fungsi
    kalori = hitung_kebutuhan_kalori(bbi_val, gender_user, imt_kat, umur_user, aktivitas_user)
    batas_gula = hitung_batas_gula(kalori)
    status_izin, pesan_sistem = evaluasi_produk(gula_dari_ocr, batas_gula)
    
    print(f"1. IMT Pengguna: {imt_val} ({imt_kat})")
    print(f"2. BBI Pengguna: {bbi_val} kg")
    print(f"3. Total Kalori: {kalori} kkal")
    print(f"4. Batas Gula  : {batas_gula} gram/hari")
    print(f"5. HASIL AKHIR : [{status_izin}] {pesan_sistem}")