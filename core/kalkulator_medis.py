# ==========================================
# core/kalkulator_medis.py
# Mesin Perhitungan Medis dan Forward Chaining
# Berdasarkan Pedoman PERKENI
# ==========================================


def _to_float(value, default=0.0):
    """Konversi nilai ke float dengan fallback."""
    try:
        if value is None or value == "":
            return default

        # Mendukung input desimal dengan koma, misalnya "20,5"
        if isinstance(value, str):
            value = value.replace(",", ".").strip()

        return float(value)
    except Exception:
        return default


def _to_int(value, default=0):
    """Konversi nilai ke integer dengan fallback."""
    try:
        if value is None or value == "":
            return default

        if isinstance(value, str):
            value = value.replace(",", ".").strip()

        return int(float(value))
    except Exception:
        return default


def normalisasi_gender(gender):
    """
    Menyamakan format gender agar fungsi tetap berjalan meskipun
    input berasal dari database/form dengan format berbeda.

    Output:
    - "L" = laki-laki/pria
    - "P" = perempuan/wanita
    """
    gender = str(gender).upper().strip()

    laki_laki = ["L", "LAKI-LAKI", "LAKI LAKI", "PRIA", "MALE", "M"]
    perempuan = ["P", "PEREMPUAN", "WANITA", "FEMALE", "F"]

    if gender in laki_laki:
        return "L"

    if gender in perempuan:
        return "P"

    # Default jika tidak terbaca
    return "P"


def normalisasi_aktivitas(aktivitas):
    """
    Menyamakan format aktivitas fisik agar input dari form tetap konsisten.
    """
    aktivitas = str(aktivitas).lower().strip()

    mapping = {
        "istirahat": "istirahat",
        "bed rest": "istirahat",
        "tidak aktif": "istirahat",

        "ringan": "ringan",
        "aktivitas ringan": "ringan",

        "sedang": "sedang",
        "aktivitas sedang": "sedang",

        "berat": "berat",
        "aktivitas berat": "berat",

        "sangat berat": "sangat berat",
        "aktivitas sangat berat": "sangat berat",
    }

    return mapping.get(aktivitas, aktivitas)


def hitung_bbi(tinggi_cm, gender):
    """
    Menghitung Berat Badan Ideal (BBI) menggunakan modifikasi Rumus Broca.

    Rumus utama:
    - Pria dengan tinggi badan >= 160 cm:
      BBI = 90% x (TB - 100)

    - Wanita dengan tinggi badan >= 150 cm:
      BBI = 90% x (TB - 100)

    Pengecualian:
    - Pria dengan tinggi badan < 160 cm:
      BBI = TB - 100

    - Wanita dengan tinggi badan < 150 cm:
      BBI = TB - 100

    Catatan:
    - TB menggunakan satuan sentimeter.
    - Gender digunakan untuk menentukan batas tinggi pengecualian,
      bukan untuk membedakan persentase BBI.
    """
    tinggi_cm = _to_float(tinggi_cm)
    gender = normalisasi_gender(gender)

    if tinggi_cm <= 0:
        return 0.0

    nilai_dasar = tinggi_cm - 100

    if gender == "L":
        if tinggi_cm < 160:
            bbi = nilai_dasar
        else:
            bbi = 0.90 * nilai_dasar
    else:
        if tinggi_cm < 150:
            bbi = nilai_dasar
        else:
            bbi = 0.90 * nilai_dasar

    return round(max(bbi, 0), 2)


def hitung_imt(berat_kg, tinggi_cm):
    """
    Menghitung Indeks Massa Tubuh (IMT) menggunakan standar Asia-Pasifik.

    Rumus:
    IMT = BB / (TB dalam meter)^2
    """
    berat_kg = _to_float(berat_kg)
    tinggi_cm = _to_float(tinggi_cm)

    if berat_kg <= 0 or tinggi_cm <= 0:
        return 0.0, "Data Tidak Valid"

    tinggi_m = tinggi_cm / 100
    imt = berat_kg / (tinggi_m * tinggi_m)

    if imt < 18.5:
        status = "Berat Badan Kurang "
    elif 18.5 <= imt < 23.0:
        status = "Berat Badan Normal"
    elif 23.0 <= imt < 25.0:
        status = "Kelebihan Berat Badan "
    elif 25.0 <= imt < 30.0:
        status = "Obesitas Tingkat I"
    else:
        status = "Obesitas Tingkat II"

    return round(imt, 2), status


def hitung_kalori_dasar(bbi, gender):
    """
    Menghitung kalori dasar berdasarkan jenis kelamin.

    Ketentuan:
    - Pria   = 30 kkal x BBI
    - Wanita = 25 kkal x BBI
    """
    bbi = _to_float(bbi)
    gender = normalisasi_gender(gender)

    if bbi <= 0:
        return 0.0

    if gender == "L":
        return bbi * 30

    return bbi * 25


def hitung_kebutuhan_kalori(berat_kg, tinggi_cm, usia, gender, aktivitas):
    """
    Menghitung total kebutuhan kalori harian berdasarkan:
    - Berat Badan Ideal (BBI)
    - Jenis kelamin
    - Usia
    - Aktivitas fisik
    - Status IMT

    Return:
    - total_kalori
    - imt
    - status_imt
    """
    berat_kg = _to_float(berat_kg)
    tinggi_cm = _to_float(tinggi_cm)
    usia = _to_int(usia)
    gender = normalisasi_gender(gender)
    aktivitas = normalisasi_aktivitas(aktivitas)

    # 1. Hitung BBI
    bbi = hitung_bbi(tinggi_cm, gender)

    # 2. Hitung kalori dasar berdasarkan jenis kelamin
    kalori_dasar = hitung_kalori_dasar(bbi, gender)

    # 3. Koreksi usia
    koreksi_umur = 0.0
    if 40 <= usia <= 59:
        koreksi_umur = -0.05
    elif 60 <= usia <= 69:
        koreksi_umur = -0.10
    elif usia >= 70:
        koreksi_umur = -0.20

    # 4. Koreksi aktivitas fisik
    koreksi_aktivitas = 0.0
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

    # 5. Hitung IMT dan status gizi
    imt, status_imt = hitung_imt(berat_kg, tinggi_cm)

    # 6. Koreksi status berat badan berdasarkan IMT
    koreksi_bb = 0.0

    if status_imt == "Kurus":
        koreksi_bb = 0.20
    elif "Gemuk" in status_imt or "Obesitas" in status_imt:
        koreksi_bb = -0.20

    # 7. Hitung total kalori
    penambahan_aktivitas = kalori_dasar * koreksi_aktivitas
    penyesuaian_usia = kalori_dasar * koreksi_umur
    penyesuaian_bb = kalori_dasar * koreksi_bb

    total_kalori = (
        kalori_dasar
        + penambahan_aktivitas
        + penyesuaian_usia
        + penyesuaian_bb
    )

    if total_kalori < 0:
        total_kalori = 0.0

    return round(total_kalori, 1), imt, status_imt


def hitung_batas_gula_harian(total_kalori):
    """
    Menghitung batas konsumsi gula harian.

    Pedoman:
    - Gula sederhana maksimal 5% dari total kalori harian.
    - 1 gram gula/karbohidrat = 4 kkal.

    Rumus:
    Batas Gula = (5% x Total Kalori) / 4
    """
    total_kalori = _to_float(total_kalori)

    if total_kalori <= 0:
        return 0.0

    kalori_dari_gula = total_kalori * 0.05
    batas_gula_gram = kalori_dari_gula / 4

    return round(batas_gula_gram, 2)


def hitung_detail_profil(berat_kg, tinggi_cm, usia, gender, aktivitas):
    """
    Fungsi tambahan untuk kebutuhan dashboard atau validasi.
    Mengembalikan detail lengkap hasil perhitungan profil pengguna.
    """
    berat_kg = _to_float(berat_kg)
    tinggi_cm = _to_float(tinggi_cm)
    usia = _to_int(usia)
    gender = normalisasi_gender(gender)
    aktivitas = normalisasi_aktivitas(aktivitas)

    bbi = hitung_bbi(tinggi_cm, gender)
    kalori_dasar = hitung_kalori_dasar(bbi, gender)

    total_kalori, imt, status_imt = hitung_kebutuhan_kalori(
        berat_kg,
        tinggi_cm,
        usia,
        gender,
        aktivitas
    )

    batas_gula = hitung_batas_gula_harian(total_kalori)

    return {
        "berat_kg": berat_kg,
        "tinggi_cm": tinggi_cm,
        "usia": usia,
        "gender": gender,
        "aktivitas": aktivitas,
        "imt": imt,
        "status_imt": status_imt,
        "bbi": bbi,
        "kalori_dasar": round(kalori_dasar, 1),
        "total_kalori": total_kalori,
        "batas_gula": batas_gula
    }


def evaluasi_forward_chaining_integratif(
    gula_produk=0.0,
    batas_gula_personal=None,
    grade_nutriscore=None,
    sisa_batas_gula=None,
    **kwargs
):
    """
    Mesin inferensi Forward Chaining berdasarkan Rule Base:

    R1:
    IF Kandungan Gula <= Batas Gula Personal
    AND Grade Nutri-Score = A OR B
    THEN Dalam Batas Normal

    R2:
    IF Kandungan Gula <= Batas Gula Personal
    AND Grade Nutri-Score = C OR D
    THEN Waspada

    R3:
    IF Kandungan Gula > Batas Gula Personal
    OR Grade Nutri-Score = E
    THEN Perlu Dibatasi

    Catatan:
    - batas_gula_personal digunakan untuk pemanggilan terbaru.
    - sisa_batas_gula disediakan agar kompatibel jika ada file lama
      yang masih memanggil nama lama.
    """

    gula = _to_float(gula_produk)

    # Prioritaskan batas_gula_personal.
    # Jika kosong, pakai sisa_batas_gula untuk kompatibilitas.
    if batas_gula_personal is None:
        batas = _to_float(sisa_batas_gula)
    else:
        batas = _to_float(batas_gula_personal)

    grade = str(grade_nutriscore).upper().strip()

    if batas < 0:
        batas = 0.0

    # R3: Perlu Dibatasi
    if gula > batas or grade == "E":
        status = "Perlu Dibatasi"
        pesan = (
            f"Kandungan gula produk ({round(gula, 2)}g) melebihi batas gula personal "
            f"pengguna ({round(batas, 2)}g) atau produk memiliki grade Nutri-Score {grade}. "
            f"Konsumsi produk sebaiknya dibatasi."
        )

    # R1: Dalam Batas Normal
    elif gula <= batas and grade in ["A", "B"]:
        status = "Dalam Batas Normal"
        pesan = (
            f"Kandungan gula produk ({round(gula, 2)}g) masih berada dalam batas gula personal "
            f"pengguna ({round(batas, 2)}g) dan memiliki grade Nutri-Score {grade}. "
            f"Produk dapat dikonsumsi secukupnya sesuai kebutuhan."
        )

    # R2: Waspada
    elif gula <= batas and grade in ["C", "D"]:
        status = "Waspada"
        pesan = (
            f"Kandungan gula produk ({round(gula, 2)}g) masih berada dalam batas gula personal "
            f"pengguna ({round(batas, 2)}g), tetapi kualitas gizi produk kurang optimal "
            f"dengan grade Nutri-Score {grade}. Produk sebaiknya dikonsumsi secukupnya."
        )

    # Kondisi cadangan
    else:
        status = "Waspada"
        pesan = (
            f"Produk perlu diperhatikan. Kandungan gula produk ({round(gula, 2)}g), "
            f"batas gula personal ({round(batas, 2)}g), dan grade Nutri-Score {grade} "
            f"belum memenuhi aturan dalam batas normal secara penuh."
        )

    return status, pesan


def evaluasi_forward_chaining_gula(gula_produk, sisa_batas_gula):
    """
    Fungsi lama: hanya membandingkan gula produk dengan batas gula.
    Disediakan agar tidak error jika masih ada file lain yang memanggilnya.

    Status disesuaikan dengan hasil validasi ahli gizi:
    - Dalam Batas Normal
    - Perlu Dibatasi
    """
    gula = _to_float(gula_produk)
    batas = _to_float(sisa_batas_gula)

    if batas < 0:
        batas = 0.0

    if gula > batas:
        status = "Perlu Dibatasi"
        pesan = (
            f"Kandungan gula produk ({round(gula, 2)}g) melebihi batas gula harian "
            f"personal pengguna ({round(batas, 2)}g). Konsumsi produk sebaiknya dibatasi."
        )
    else:
        status = "Dalam Batas Normal"
        pesan = (
            f"Kandungan gula produk ({round(gula, 2)}g) masih berada dalam batas gula "
            f"harian personal pengguna ({round(batas, 2)}g)."
        )

    return status, pesan