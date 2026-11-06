import os
import time
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import joblib

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

from dotenv import load_dotenv
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

# ==========================================
# LOAD ENVIRONMENT VARIABLE
# ==========================================
load_dotenv()


# ==========================================
# IMPORT MESIN DARI FOLDER CORE
# ==========================================
from core.db_config import get_db_connection
from core.kalkulator_medis import (
    hitung_imt,
    hitung_bbi,
    hitung_kebutuhan_kalori,
    hitung_batas_gula_harian,
    evaluasi_forward_chaining_integratif
)
from core.ocr_engine import extract_nutrition_from_image



# ==========================================
# 1. INISIALISASI APLIKASI
# ==========================================
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'kunci_rahasia_cadangan_123')
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)


# ==========================================
# 1A. KONFIGURASI EMAIL RESET PASSWORD
# ==========================================
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'true').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'false').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv(
    'MAIL_DEFAULT_SENDER',
    os.getenv('MAIL_USERNAME')
)

mail = Mail(app)

password_reset_serializer = URLSafeTimedSerializer(app.secret_key)
PASSWORD_RESET_SALT = os.getenv(
    'PASSWORD_RESET_SALT',
    'nutriguard-reset-password-salt'
)
RESET_TOKEN_MAX_AGE = int(os.getenv('RESET_TOKEN_MAX_AGE', 1800))  # 30 menit


# ==========================================
# 2. LOAD MODEL RANDOM FOREST, SCALER, ENCODER
# ==========================================
MODEL_PATH = os.path.join('model', 'random_forest_nutriscore.pkl')
SCALER_PATH = os.path.join('model', 'scaler.pkl')
ENCODER_PATH = os.path.join('model', 'encoder_label.pkl')

FITUR_FINAL = [
    'energy-kcal_100g',
    'sugars_100g',
    'saturated-fat_100g',
    'sodium_100g',
    'proteins_100g',
    'fiber_100g',
    'fruits-vegetables-nuts-estimate-from-ingredients_100g',
    'kategori_encoded'
]

try:
    rf_model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    label_encoder = joblib.load(ENCODER_PATH)
    print("✅ Model Random Forest, Scaler, dan Encoder berhasil dimuat.")
except Exception as e:
    rf_model = None
    scaler = None
    label_encoder = None
    print(f"⚠️ Gagal memuat model/scaler/encoder: {e}")





# ==========================================
# 4. HELPER FUNCTION
# ==========================================
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def safe_float(value, default=0.0):
    """
    Konversi nilai ke float dengan fallback default.
    Mendukung angka desimal dengan koma, misalnya "20,5".
    """
    try:
        if value is None or value == '':
            return default

        if isinstance(value, str):
            value = value.replace(",", ".").strip()

        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    """
    Konversi nilai ke integer dengan fallback default.
    """
    try:
        if value is None or value == '':
            return default

        if isinstance(value, str):
            value = value.replace(",", ".").strip()

        return int(float(value))
    except Exception:
        return default


def hitung_usia_dari_tanggal_lahir(tanggal_lahir, default=0):
    """
    Menghitung usia otomatis berdasarkan tanggal lahir.
    Bisa menerima format:
    - string YYYY-MM-DD dari input HTML
    - object date dari MySQL
    - object datetime
    """
    try:
        if not tanggal_lahir:
            return default

        if isinstance(tanggal_lahir, str):
            tanggal_lahir = tanggal_lahir.strip()
            tanggal_lahir = datetime.strptime(tanggal_lahir, "%Y-%m-%d").date()

        elif isinstance(tanggal_lahir, datetime):
            tanggal_lahir = tanggal_lahir.date()

        hari_ini = date.today()

        usia = hari_ini.year - tanggal_lahir.year

        if (hari_ini.month, hari_ini.day) < (tanggal_lahir.month, tanggal_lahir.day):
            usia -= 1

        if usia < 0:
            return default

        return usia

    except Exception:
        return default


def create_reset_token(email):
    """
    Membuat token reset password berdasarkan email.
    Token berlaku sesuai RESET_TOKEN_MAX_AGE.
    """
    return password_reset_serializer.dumps(
        email,
        salt=PASSWORD_RESET_SALT
    )


def verify_reset_token(token):
    """
    Membaca token reset password dan mengembalikan email.
    """
    try:
        email = password_reset_serializer.loads(
            token,
            salt=PASSWORD_RESET_SALT,
            max_age=RESET_TOKEN_MAX_AGE
        )
        return email
    except SignatureExpired:
        return None
    except BadSignature:
        return None
    except Exception:
        return None


def send_reset_password_email(email, reset_url, nama_lengkap=None):
    """
    Mengirim email reset password ke pengguna.
    """
    nama = nama_lengkap or "Pengguna"

    subject = "Reset Kata Sandi Akun Nutri-Guard"
    body = f"""
Halo {nama},

Kami menerima permintaan untuk mengatur ulang kata sandi akun Nutri-Guard Anda.

Silakan klik link berikut untuk membuat kata sandi baru:

{reset_url}

Link ini berlaku selama 30 menit.

Jika Anda tidak meminta reset kata sandi, abaikan email ini.

Salam,
Nutri-Guard AI
"""

    msg = Message(
        subject=subject,
        recipients=[email],
        body=body
    )

    mail.send(msg)


def parse_kategori(value):
    """
    Mengubah input kategori dari OCR menjadi format biner:
    0 = Minuman
    1 = Makanan padat
    """
    text = str(value).strip().lower()

    if text in ['0', 'minuman', 'beverage', 'beverages', 'drink', 'cair']:
        return 0

    return 1


def build_random_forest_input(data, kategori_biner):
    """
    Mengubah hasil OCR menjadi format fitur yang sama dengan data training Random Forest.
    Model dilatih menggunakan fitur per 100 gram/ml.
    """

    takaran = safe_float(data.get('takaran_saji'))
    if takaran <= 0:
        takaran = 100.0

    factor = 100 / takaran

    energi_100g = safe_float(data.get('energi')) * factor
    gula_100g = safe_float(data.get('gula')) * factor
    lemak_jenuh_100g = safe_float(data.get('lemak_jenuh')) * factor
    protein_100g = safe_float(data.get('protein')) * factor
    serat_100g = safe_float(data.get('serat')) * factor

    # OCR mengeluarkan natrium/garam dalam mg.
    # Dataset Open Food Facts memakai sodium_100g dalam gram.
    sodium_mg_100g = safe_float(data.get('garam')) * factor
    sodium_100g = sodium_mg_100g / 1000

    # Buah/sayur berupa persen estimasi.
    buah_100g = safe_float(data.get('buah'))

    # Disamakan dengan preprocessing training
    energi_100g = np.clip(energi_100g, 0, 1000)
    gula_100g = np.clip(gula_100g, 0, 100)
    lemak_jenuh_100g = np.clip(lemak_jenuh_100g, 0, 100)
    sodium_100g = np.clip(sodium_100g, 0, 100)
    protein_100g = np.clip(protein_100g, 0, 100)
    serat_100g = np.clip(serat_100g, 0, 100)
    buah_100g = np.clip(buah_100g, 0, 100)

    input_model = pd.DataFrame([{
        'energy-kcal_100g': energi_100g,
        'sugars_100g': gula_100g,
        'saturated-fat_100g': lemak_jenuh_100g,
        'sodium_100g': sodium_100g,
        'proteins_100g': protein_100g,
        'fiber_100g': serat_100g,
        'fruits-vegetables-nuts-estimate-from-ingredients_100g': buah_100g,
        'kategori_encoded': kategori_biner
    }], columns=FITUR_FINAL)

    return input_model


def prediksi_nutriscore_random_forest(data, kategori_biner):
    """
    Melakukan prediksi Nutri-Score menggunakan model Random Forest hasil training.
    """

    if rf_model is None or scaler is None or label_encoder is None:
        raise RuntimeError(
            "Model Random Forest, scaler, atau encoder belum berhasil dimuat. "
            "Pastikan file model/random_forest_nutriscore.pkl, model/scaler.pkl, "
            "dan model/encoder_label.pkl tersedia."
        )

    input_model = build_random_forest_input(data, kategori_biner)

    # Scaling
    input_scaled_array = scaler.transform(input_model)

    # Dikembalikan ke DataFrame agar nama fitur tetap valid untuk RandomForest
    input_scaled = pd.DataFrame(input_scaled_array, columns=FITUR_FINAL)

    pred_encoded = rf_model.predict(input_scaled)[0]

    prob = rf_model.predict_proba(input_scaled)[0]

    confidence = round(np.max(prob) * 100, 2)

    grade = label_encoder.inverse_transform([pred_encoded])[0]

    return {
        "grade": str(grade).upper(),
        "confidence": confidence
    }


# ==========================================
# 5. ROUTE HALAMAN PUBLIK
# ==========================================
@app.route('/')
def index():
    return render_template('pages/beranda.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = str(request.form.get('email', '')).strip().lower()
        password = request.form.get('password')

        conn = get_db_connection()
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, nama_lengkap, email, password_hash FROM users WHERE email = %s",
                (email,)
            )
            user_data = cursor.fetchone()
            conn.close()

            if user_data and check_password_hash(user_data[3], password):
                session['user_id'] = user_data[0]
                session['nama_lengkap'] = user_data[1]
                flash('Login berhasil! Selamat datang di Nutri-Guard.', 'success')
                return redirect(url_for('dashboard'))

            flash('Login gagal. Periksa kembali email dan password Anda.', 'danger')

    return render_template('auth/login.html')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = str(request.form.get('email', '')).strip().lower()

        if not email:
            flash('Silakan masukkan alamat email terlebih dahulu.', 'warning')
            return redirect(url_for('forgot_password'))

        conn = get_db_connection()
        if not conn:
            flash('Database sedang tidak tersedia.', 'danger')
            return redirect(url_for('forgot_password'))

        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, nama_lengkap, email FROM users WHERE email = %s",
            (email,)
        )
        user_data = cursor.fetchone()
        conn.close()

        if not user_data:
            flash('Email tidak ditemukan. Pastikan email yang dimasukkan sudah terdaftar.', 'danger')
            return redirect(url_for('forgot_password'))

        if not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
            flash('Konfigurasi email belum lengkap. Periksa file .env.', 'danger')
            return redirect(url_for('forgot_password'))

        try:
            token = create_reset_token(email)
            reset_url = url_for('reset_password', token=token, _external=True)

            send_reset_password_email(
                email=email,
                reset_url=reset_url,
                nama_lengkap=user_data[1]
            )

            flash('Link reset kata sandi telah dikirim ke email Anda. Silakan cek inbox atau spam.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            print(f"ERROR KIRIM EMAIL RESET PASSWORD: {e}")
            flash('Gagal mengirim email reset password. Periksa konfigurasi Gmail dan App Password.', 'danger')
            return redirect(url_for('forgot_password'))

    return render_template('auth/forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    email = verify_reset_token(token)

    if not email:
        flash('Link reset password tidak valid atau sudah kedaluwarsa. Silakan minta link baru.', 'danger')
        return redirect(url_for('forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not password or not confirm_password:
            flash('Password dan konfirmasi password wajib diisi.', 'warning')
            return redirect(url_for('reset_password', token=token))

        if password != confirm_password:
            flash('Konfirmasi password tidak sesuai.', 'danger')
            return redirect(url_for('reset_password', token=token))

        if len(password) < 6:
            flash('Password minimal 6 karakter.', 'warning')
            return redirect(url_for('reset_password', token=token))

        hashed_pw = generate_password_hash(password)

        conn = get_db_connection()
        if not conn:
            flash('Database sedang tidak tersedia.', 'danger')
            return redirect(url_for('reset_password', token=token))

        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET password_hash = %s WHERE email = %s",
            (hashed_pw, email)
        )
        conn.commit()
        conn.close()

        flash('Kata sandi berhasil diperbarui. Silakan login dengan password baru.', 'success')
        return redirect(url_for('login'))

    return render_template('auth/reset_password.html', token=token, email=email)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        nama = str(request.form.get('nama', '')).strip()
        email = str(request.form.get('email', '')).strip().lower()
        password = request.form.get('password')

        tanggal_lahir = request.form.get('tanggal_lahir')
        berat = safe_float(request.form.get('berat', 60), 60)
        tinggi = safe_float(request.form.get('tinggi', 165), 165)
        gender = request.form.get('gender', 'L')
        aktivitas = request.form.get('aktivitas', 'sedang')

        usia = hitung_usia_dari_tanggal_lahir(tanggal_lahir)

        if not nama or not email or not password:
            flash('Nama, email, dan kata sandi wajib diisi.', 'warning')
            return redirect(url_for('register'))

        if len(password) < 6:
            flash('Kata sandi minimal 6 karakter.', 'warning')
            return redirect(url_for('register'))

        if not tanggal_lahir or usia <= 0 or usia > 120:
            flash('Tanggal lahir tidak valid. Silakan periksa kembali.', 'warning')
            return redirect(url_for('register'))

        total_kalori, imt, status_imt = hitung_kebutuhan_kalori(
            berat, tinggi, usia, gender, aktivitas
        )

        hashed_pw = generate_password_hash(password)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO users 
                (nama_lengkap, email, tanggal_lahir, password_hash, usia, berat_badan, tinggi_badan, gender, aktivitas, bmr_limit)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                nama,
                email,
                tanggal_lahir,
                hashed_pw,
                usia,
                berat,
                tinggi,
                gender,
                aktivitas,
                total_kalori
            ))

            conn.commit()
            conn.close()

            flash(f'Registrasi berhasil! Usia Anda terhitung {usia} tahun dan profil medis PERKENI telah dibuat.', 'success')
            return redirect(url_for('login'))

        except Exception as e:
            print("ERROR REGISTER:", e)
            flash('Pendaftaran gagal. Email mungkin sudah terdaftar atau kolom tanggal_lahir belum ditambahkan di database.', 'danger')

    return render_template('auth/register.html')


@app.route('/logout')
def logout():
    session.clear()
    flash('Anda telah berhasil keluar.', 'info')
    return redirect(url_for('login'))


# ==========================================
# 6. ROUTE APLIKASI UTAMA
# ==========================================
@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        return "Database Offline"

    cursor = conn.cursor()
    user_id = session['user_id']

    # A. Profil Fisik
    cursor.execute("""
        SELECT berat_badan, tinggi_badan, usia, gender, aktivitas, bmr_limit, tanggal_lahir
        FROM users 
        WHERE id = %s
    """, (user_id,))
    fisik = cursor.fetchone()

    bmi = 0
    bmi_status = "Tidak Diketahui"
    bbi = 0
    bmr_limit = 2000
    batas_gula = 25.0
    usia = 0

    if fisik:
        berat = safe_float(fisik[0])
        tinggi_cm = safe_float(fisik[1])
        usia_db = safe_int(fisik[2], 25)
        gender = fisik[3] if fisik[3] else "L"
        aktivitas = fisik[4] if fisik[4] else "sedang"
        tanggal_lahir = fisik[6]

        # Usia dihitung otomatis dari tanggal lahir.
        # Kalau tanggal_lahir kosong untuk akun lama, pakai usia dari database.
        if tanggal_lahir:
            usia = hitung_usia_dari_tanggal_lahir(tanggal_lahir, usia_db)
        else:
            usia = usia_db

        # Hitung ulang dari data profil agar selalu terbaru
        bmi, bmi_status = hitung_imt(berat, tinggi_cm)
        bbi = hitung_bbi(tinggi_cm, gender)

        bmr_limit, _, _ = hitung_kebutuhan_kalori(
            berat, tinggi_cm, usia, gender, aktivitas
        )

        batas_gula = hitung_batas_gula_harian(bmr_limit)

        # Update usia dan bmr_limit supaya database ikut terbaru
        cursor.execute("""
            UPDATE users
            SET usia = %s, bmr_limit = %s
            WHERE id = %s
        """, (usia, bmr_limit, user_id))
        conn.commit()

    # B. Statistik Hari Ini
    today = date.today()
    cursor.execute("""
        SELECT SUM(kalori), SUM(gula), SUM(garam), SUM(lemak_jenuh)
        FROM scan_history
        WHERE user_id = %s AND DATE(tanggal_scan) = %s AND is_consumed = 1
    """, (user_id, today))
    stats = cursor.fetchone()

    today_cals = int(safe_float(stats[0])) if stats and stats[0] else 0
    today_sugar = round(safe_float(stats[1]), 1) if stats and stats[1] else 0
    today_salt = round(safe_float(stats[2]), 1) if stats and stats[2] else 0
    today_fat = round(safe_float(stats[3]), 1) if stats and stats[3] else 0

    # C. Health Score & Distribusi Grade
    cursor.execute(
        "SELECT nutriscore_grade FROM scan_history WHERE user_id = %s AND is_consumed = 1",
        (user_id,)
    )
    all_grades = cursor.fetchall()

    health_score = 100
    grade_counts = {'A': 0, 'B': 0, 'C': 0, 'D': 0, 'E': 0}

    for g in all_grades:
        grade = str(g[0]).upper()
        if grade in grade_counts:
            grade_counts[grade] += 1
        if grade in ['A', 'B']:
            health_score += 5
        elif grade in ['D', 'E']:
            health_score -= 2

    # D. Riwayat Terakhir
    cursor.execute("""
        SELECT id, nama_produk, nutriscore_grade, kalori, is_consumed, tanggal_scan, gula, garam, lemak_jenuh
        FROM scan_history
        WHERE user_id = %s
        ORDER BY tanggal_scan DESC
        LIMIT 15
    """, (user_id,))
    history = cursor.fetchall()

    # E. Tren Gula 7 Hari Terakhir
    past_7_days = today - timedelta(days=6)
    cursor.execute("""
        SELECT DATE(tanggal_scan), SUM(gula)
        FROM scan_history
        WHERE user_id = %s 
          AND is_consumed = 1 
          AND DATE(tanggal_scan) >= %s
        GROUP BY DATE(tanggal_scan)
        ORDER BY DATE(tanggal_scan) ASC
    """, (user_id, past_7_days))
    trend_data_raw = cursor.fetchall()

    trend_labels = []
    trend_values = []
    trend_dict = {str(row[0]): safe_float(row[1]) for row in trend_data_raw}

    for i in range(7):
        current_date = past_7_days + timedelta(days=i)
        date_str = str(current_date)
        trend_labels.append(current_date.strftime("%d %b"))
        trend_values.append(trend_dict.get(date_str, 0.0))

    conn.close()

    return render_template(
        'pages/dashboard.html',
        bmi=bmi,
        bmi_status=bmi_status,
        bbi=bbi,
        usia=usia,
        bmr_limit=int(round(bmr_limit)),
        batas_gula=batas_gula,
        today_cals=today_cals,
        today_sugar=today_sugar,
        today_salt=today_salt,
        today_fat=today_fat,
        health_score=health_score,
        history=history,
        grade_counts=grade_counts,
        trend_labels=trend_labels,
        trend_values=trend_values
    )


@app.route('/profil', methods=['GET', 'POST'])
def profil():
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        return "Database Error"

    cursor = conn.cursor()
    user_id = session['user_id']

    if request.method == 'POST':
        berat = safe_float(request.form.get('berat'))
        tinggi = safe_float(request.form.get('tinggi'))
        gender = request.form.get('gender')
        aktivitas = request.form.get('aktivitas')

        tanggal_lahir_input = request.form.get('tanggal_lahir')

        # Ambil tanggal lahir lama agar kalau form profil belum punya input tanggal_lahir,
        # data lama tidak hilang.
        cursor.execute("""
            SELECT tanggal_lahir, usia
            FROM users
            WHERE id = %s
        """, (user_id,))
        old_data = cursor.fetchone()

        tanggal_lahir_lama = old_data[0] if old_data else None
        usia_lama = safe_int(old_data[1], 25) if old_data else 25

        tanggal_lahir_final = tanggal_lahir_input if tanggal_lahir_input else tanggal_lahir_lama

        if tanggal_lahir_final:
            usia = hitung_usia_dari_tanggal_lahir(tanggal_lahir_final, usia_lama)
        else:
            usia = safe_int(request.form.get('usia'), usia_lama)

        total_kalori, imt, status_imt = hitung_kebutuhan_kalori(
            berat, tinggi, usia, gender, aktivitas
        )

        cursor.execute("""
            UPDATE users
            SET berat_badan=%s, tinggi_badan=%s, tanggal_lahir=%s, usia=%s, gender=%s, aktivitas=%s, bmr_limit=%s
            WHERE id=%s
        """, (
            berat,
            tinggi,
            tanggal_lahir_final,
            usia,
            gender,
            aktivitas,
            total_kalori,
            user_id
        ))

        conn.commit()
        conn.close()

        flash('Data fisik berhasil diperbarui! Usia, batas kalori, dan batas gula telah disesuaikan.', 'success')
        return redirect(url_for('profil'))

    cursor.execute("""
        SELECT nama_lengkap, email, usia, berat_badan, tinggi_badan, gender, aktivitas, tanggal_lahir
        FROM users
        WHERE id = %s
    """, (user_id,))
    user = cursor.fetchone()

    # Update usia otomatis ketika halaman profil dibuka
    if user:
        tanggal_lahir = user[7]
        usia_db = safe_int(user[2], 25)

        if tanggal_lahir:
            usia_baru = hitung_usia_dari_tanggal_lahir(tanggal_lahir, usia_db)

            if usia_baru != usia_db:
                cursor.execute("""
                    UPDATE users
                    SET usia = %s
                    WHERE id = %s
                """, (usia_baru, user_id))
                conn.commit()

                cursor.execute("""
                    SELECT nama_lengkap, email, usia, berat_badan, tinggi_badan, gender, aktivitas, tanggal_lahir
                    FROM users
                    WHERE id = %s
                """, (user_id,))
                user = cursor.fetchone()

    conn.close()

    return render_template('pages/profil.html', user=user)

# ==========================================
# 6A. ROUTE RIWAYAT DAN REKAP KONSUMSI
# ==========================================
BULAN_ID = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
]


def parse_date_param(value, fallback=None):
    try:
        if not value:
            return fallback or date.today()
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return fallback or date.today()


def parse_month_param(value, fallback=None):
    try:
        if not value:
            base = fallback or date.today()
            return date(base.year, base.month, 1)

        month_date = datetime.strptime(value, "%Y-%m").date()
        return date(month_date.year, month_date.month, 1)
    except Exception:
        base = fallback or date.today()
        return date(base.year, base.month, 1)


def format_tanggal_id(value):
    try:
        if isinstance(value, str):
            value = datetime.strptime(value, "%Y-%m-%d").date()

        return f"{value.day} {BULAN_ID[value.month - 1]} {value.year}"
    except Exception:
        return str(value)


def get_status_gula(total_gula, batas_gula):
    total_gula = safe_float(total_gula)
    batas_gula = safe_float(batas_gula, 1)

    if total_gula <= 0:
        return {
            "label": "Belum Ada Konsumsi",
            "class": "secondary",
            "icon": "fa-clock",
            "message": "Belum ada produk yang ditandai sebagai dikonsumsi pada periode ini."
        }

    if total_gula > batas_gula:
        return {
            "label": "Melebihi Batas",
            "class": "danger",
            "icon": "fa-triangle-exclamation",
            "message": "Total gula telah melebihi batas gula harian personal."
        }

    if total_gula >= (0.8 * batas_gula):
        return {
            "label": "Waspada",
            "class": "warning",
            "icon": "fa-circle-exclamation",
            "message": "Total gula sudah mendekati batas harian. Konsumsi gula perlu dibatasi."
        }

    return {
        "label": "Aman",
        "class": "success",
        "icon": "fa-circle-check",
        "message": "Total gula masih berada dalam batas harian personal."
    }


@app.route('/riwayat')
def riwayat():
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    conn = get_db_connection()
    if not conn:
        return "Database Offline"

    cursor = conn.cursor()
    user_id = session['user_id']

    today = date.today()

    selected_date_obj = parse_date_param(
        request.args.get('tanggal'),
        today
    )
    selected_date = selected_date_obj.strftime("%Y-%m-%d")

    selected_month_obj = parse_month_param(
        request.args.get('bulan'),
        selected_date_obj
    )
    selected_month = selected_month_obj.strftime("%Y-%m")

    if selected_month_obj.month == 12:
        next_month_obj = date(selected_month_obj.year + 1, 1, 1)
    else:
        next_month_obj = date(selected_month_obj.year, selected_month_obj.month + 1, 1)

    prev_date = (selected_date_obj - timedelta(days=1)).strftime("%Y-%m-%d")
    next_date_obj = selected_date_obj + timedelta(days=1)
    next_date = next_date_obj.strftime("%Y-%m-%d")

    # Ambil batas gula personal dari profil user
    cursor.execute("""
        SELECT bmr_limit
        FROM users
        WHERE id = %s
    """, (user_id,))
    user_limit = cursor.fetchone()

    bmr_limit = safe_float(user_limit[0], 2000) if user_limit else 2000
    batas_gula = hitung_batas_gula_harian(bmr_limit)

    # Statistik harian berdasarkan produk yang benar-benar dikonsumsi
    cursor.execute("""
        SELECT
            COALESCE(SUM(CASE WHEN is_consumed = 1 THEN kalori ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN is_consumed = 1 THEN gula ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN is_consumed = 1 THEN garam ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN is_consumed = 1 THEN lemak_jenuh ELSE 0 END), 0),
            COUNT(*),
            COALESCE(SUM(CASE WHEN is_consumed = 1 THEN 1 ELSE 0 END), 0)
        FROM scan_history
        WHERE user_id = %s
          AND DATE(tanggal_scan) = %s
    """, (user_id, selected_date_obj))
    daily_raw = cursor.fetchone()

    total_kalori = safe_float(daily_raw[0]) if daily_raw else 0
    total_gula = safe_float(daily_raw[1]) if daily_raw else 0
    total_garam = safe_float(daily_raw[2]) if daily_raw else 0
    total_lemak = safe_float(daily_raw[3]) if daily_raw else 0
    total_scan = safe_int(daily_raw[4]) if daily_raw else 0
    total_dikonsumsi = safe_int(daily_raw[5]) if daily_raw else 0

    sisa_gula = batas_gula - total_gula
    if sisa_gula < 0:
        sisa_gula = 0

    daily_percent = 0
    if batas_gula > 0:
        daily_percent = min(100, round((total_gula / batas_gula) * 100, 1))

    daily_status = get_status_gula(total_gula, batas_gula)

    daily_stats = {
        "total_kalori": round(total_kalori, 1),
        "total_gula": round(total_gula, 1),
        "total_garam": round(total_garam, 1),
        "total_lemak": round(total_lemak, 1),
        "total_scan": total_scan,
        "total_dikonsumsi": total_dikonsumsi,
        "sisa_gula": round(sisa_gula, 1),
        "daily_percent": daily_percent
    }

    # Daftar produk pada tanggal terpilih
    cursor.execute("""
        SELECT id, nama_produk, nutriscore_grade, kalori, gula, garam, lemak_jenuh, is_consumed, tanggal_scan
        FROM scan_history
        WHERE user_id = %s
          AND DATE(tanggal_scan) = %s
        ORDER BY tanggal_scan DESC
    """, (user_id, selected_date_obj))
    daily_items_raw = cursor.fetchall()

    daily_items = []
    for item in daily_items_raw:
        tanggal_scan = item[8]

        if hasattr(tanggal_scan, "strftime"):
            jam_scan = tanggal_scan.strftime("%H:%M")
        else:
            jam_scan = "-"

        daily_items.append({
            "id": item[0],
            "nama_produk": item[1],
            "grade": str(item[2]).upper(),
            "kalori": round(safe_float(item[3]), 1),
            "gula": round(safe_float(item[4]), 1),
            "garam": round(safe_float(item[5]), 1),
            "lemak_jenuh": round(safe_float(item[6]), 1),
            "is_consumed": safe_int(item[7]),
            "jam_scan": jam_scan
        })

    # Rekap bulanan per hari
    cursor.execute("""
        SELECT
            DATE(tanggal_scan),
            COALESCE(SUM(CASE WHEN is_consumed = 1 THEN kalori ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN is_consumed = 1 THEN gula ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN is_consumed = 1 THEN garam ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN is_consumed = 1 THEN lemak_jenuh ELSE 0 END), 0),
            COUNT(*),
            COALESCE(SUM(CASE WHEN is_consumed = 1 THEN 1 ELSE 0 END), 0)
        FROM scan_history
        WHERE user_id = %s
          AND tanggal_scan >= %s
          AND tanggal_scan < %s
        GROUP BY DATE(tanggal_scan)
        ORDER BY DATE(tanggal_scan) DESC
    """, (user_id, selected_month_obj, next_month_obj))
    monthly_raw = cursor.fetchall()

    monthly_rows = []
    total_gula_bulan = 0
    total_kalori_bulan = 0
    hari_tercatat = 0
    hari_aman = 0
    hari_waspada = 0
    hari_melebihi = 0

    for row in monthly_raw:
        tanggal_row = row[0]

        if isinstance(tanggal_row, str):
            tanggal_obj = parse_date_param(tanggal_row, today)
        else:
            tanggal_obj = tanggal_row

        kalori_harian = safe_float(row[1])
        gula_harian = safe_float(row[2])
        garam_harian = safe_float(row[3])
        lemak_harian = safe_float(row[4])
        scan_harian = safe_int(row[5])
        konsumsi_harian = safe_int(row[6])

        status_row = get_status_gula(gula_harian, batas_gula)

        if konsumsi_harian > 0:
            hari_tercatat += 1
            total_gula_bulan += gula_harian
            total_kalori_bulan += kalori_harian

            if status_row["class"] == "success":
                hari_aman += 1
            elif status_row["class"] == "warning":
                hari_waspada += 1
            elif status_row["class"] == "danger":
                hari_melebihi += 1

        monthly_rows.append({
            "tanggal": tanggal_obj.strftime("%Y-%m-%d"),
            "tanggal_display": format_tanggal_id(tanggal_obj),
            "kalori": round(kalori_harian, 1),
            "gula": round(gula_harian, 1),
            "garam": round(garam_harian, 1),
            "lemak_jenuh": round(lemak_harian, 1),
            "total_scan": scan_harian,
            "total_dikonsumsi": konsumsi_harian,
            "status": status_row
        })

    rata_gula = round(total_gula_bulan / hari_tercatat, 1) if hari_tercatat > 0 else 0
    rata_kalori = round(total_kalori_bulan / hari_tercatat, 1) if hari_tercatat > 0 else 0

    monthly_summary = {
        "bulan_display": f"{BULAN_ID[selected_month_obj.month - 1]} {selected_month_obj.year}",
        "hari_tercatat": hari_tercatat,
        "total_gula": round(total_gula_bulan, 1),
        "rata_gula": rata_gula,
        "rata_kalori": rata_kalori,
        "hari_aman": hari_aman,
        "hari_waspada": hari_waspada,
        "hari_melebihi": hari_melebihi
    }

    conn.close()

    return render_template(
        'pages/riwayat.html',
        selected_date=selected_date,
        selected_date_display=format_tanggal_id(selected_date_obj),
        selected_month=selected_month,
        today_str=today.strftime("%Y-%m-%d"),
        prev_date=prev_date,
        next_date=next_date,
        next_date_disabled=next_date_obj > today,
        batas_gula=round(batas_gula, 1),
        daily_stats=daily_stats,
        daily_status=daily_status,
        daily_items=daily_items,
        monthly_rows=monthly_rows,
        monthly_summary=monthly_summary
    )
    
# ==========================================
# 7. ROUTE SCAN DAN PREDIKSI
# ==========================================
@app.route('/scan')
def scan_page():
    if 'user_id' not in session:
        flash('Silakan masuk terlebih dahulu.', 'warning')
        return redirect(url_for('login'))

    return render_template('pages/scan.html')


@app.route('/scan_ocr', methods=['POST'])
def scan_ocr():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Silakan login terlebih dahulu.'}), 401

    if 'file' not in request.files:
        return jsonify({'status': 'error', 'message': 'File tidak ditemukan.'})

    file = request.files['file']

    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'status': 'error', 'message': 'Format gambar tidak didukung.'})

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    try:
        data, debug_text = extract_nutrition_from_image(filepath)

        if os.path.exists(filepath):
            try:
                time.sleep(0.5)
                os.remove(filepath)
            except Exception:
                pass

        return jsonify({
            'status': 'success',
            'ocr_status': 'Berhasil',
            'data': data
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/predict', methods=['POST'])
def analyze_nutrition():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Silakan login terlebih dahulu.'}), 401

    try:
        data = request.json or {}

        nama_produk = str(data.get('nama_produk') or 'Produk Scan').strip().title()

        # Kategori dari OCR diubah menjadi format biner sesuai training model
        kategori_biner = parse_kategori(data.get('kategori', 1))

        # Nilai asli per sajian dari OCR
        gula_total = safe_float(data.get('gula'))
        sodium_mg = safe_float(data.get('garam'))

        # ==========================================
        # PREDIKSI NUTRI-SCORE MENGGUNAKAN RANDOM FOREST
        # ==========================================
        hasil = prediksi_nutriscore_random_forest(
            data,
            kategori_biner
        )

        grade = hasil["grade"]
        confidence = hasil["confidence"]

        

        # ==========================================
        # EVALUASI MEDIS FORWARD CHAINING
        # ==========================================
        user_id = session['user_id']
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT berat_badan, tinggi_badan, usia, gender, aktivitas, tanggal_lahir
            FROM users
            WHERE id = %s
        """, (user_id,))
        profil_user = cursor.fetchone()

        if profil_user:
            berat = safe_float(profil_user[0], 60)
            tinggi = safe_float(profil_user[1], 165)
            usia_db = safe_int(profil_user[2], 25)
            gender = profil_user[3] if profil_user[3] else "L"
            aktivitas = profil_user[4] if profil_user[4] else "sedang"
            tanggal_lahir = profil_user[5]

            if tanggal_lahir:
                usia = hitung_usia_dari_tanggal_lahir(tanggal_lahir, usia_db)
            else:
                usia = usia_db

            bmr_limit, _, _ = hitung_kebutuhan_kalori(
                berat, tinggi, usia, gender, aktivitas
            )

            cursor.execute("""
                UPDATE users
                SET usia = %s, bmr_limit = %s
                WHERE id = %s
            """, (usia, bmr_limit, user_id))
            conn.commit()

        else:
            bmr_limit = 2000

        cursor.execute("""
            SELECT SUM(gula)
            FROM scan_history
            WHERE user_id = %s 
              AND DATE(tanggal_scan) = %s 
              AND is_consumed = 1
        """, (user_id, date.today()))

        gula_hari_ini = cursor.fetchone()[0]
        gula_hari_ini = safe_float(gula_hari_ini)

        conn.close()

        batas_gula_harian = hitung_batas_gula_harian(bmr_limit)
        sisa_gula = batas_gula_harian - gula_hari_ini

        if sisa_gula < 0:
            sisa_gula = 0.0

        status_medis, pesan_medis = evaluasi_forward_chaining_integratif(
            gula_produk=gula_total,
            batas_gula_personal=sisa_gula,
            grade_nutriscore=grade
        )
        print("========== HASIL PREDIKSI ==========")
        print("Grade :", grade)
        print("Confidence :", confidence)
        print("===================================")
        return jsonify({
            'status': 'success',
            'grade': grade,
            'confidence': confidence,
            'product_name': nama_produk,
        
            'forward_chaining': {
                'status': status_medis,
                'pesan': pesan_medis
            },
            'save_payload': {
                'nama_produk': nama_produk,
                'grade': grade,
                'gula': round(gula_total, 2),
                'garam': round(sodium_mg, 2),
                'lemak_jenuh': round(safe_float(data.get('lemak_jenuh')), 2),
                'kalori': round(safe_float(data.get('energi')), 2)
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': str(e)}), 500


# ==========================================
# 8. ROUTE RIWAYAT DAN KONTRIBUSI PRODUK
# ==========================================
@app.route('/save_result', methods=['POST'])
def save_result():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Pengguna belum login.'})

    try:
        data = request.json or {}
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO scan_history 
            (user_id, nama_produk, nutriscore_grade, kalori, gula, garam, lemak_jenuh, is_consumed)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 0)
        """, (
            session['user_id'],
            data.get('nama_produk'),
            data.get('grade'),
            data.get('kalori'),
            data.get('gula'),
            data.get('garam'),
            data.get('lemak_jenuh')
        ))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Tersimpan di jurnal Anda!'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/consume_product/<int:scan_id>', methods=['POST'])
def consume_product(scan_id):
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Pengguna belum login.'})

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE scan_history SET is_consumed = 1 WHERE id = %s AND user_id = %s",
        (scan_id, session['user_id'])
    )
    conn.commit()
    conn.close()

    return jsonify({'status': 'success'})


@app.route('/contribute_product/<int:scan_id>', methods=['POST'])
def contribute_product(scan_id):
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Pengguna belum login.'})

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT nama_produk, nutriscore_grade, kalori, gula, garam, lemak_jenuh
            FROM scan_history
            WHERE id = %s AND user_id = %s
        """, (scan_id, session['user_id']))
        item = cursor.fetchone()

        if not item:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Data tidak ditemukan.'})

        nama_produk, grade = item[0], str(item[1]).upper()

        cursor.execute(
            "SELECT id FROM products WHERE LOWER(nama_produk) = LOWER(%s) LIMIT 1",
            (nama_produk,)
        )

        if cursor.fetchone():
            conn.close()
            return jsonify({
                'status': 'info',
                'message': 'Terima kasih telah membantu! Namun produk ini sudah ada di database.'
            })

        cursor.execute("""
            INSERT INTO products 
            (nama_produk, brand, kategori, nutriscore_grade, kalori, gula, lemak_jenuh, garam, protein, serat, buah)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            nama_produk,
            'Kontribusi User',
            1,
            grade,
            item[2],
            item[3],
            item[5],
            item[4],
            0,
            0,
            0
        ))

        conn.commit()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Berhasil! Data Anda telah ditambahkan ke database publik.'
        })

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


# ==========================================
# 9. RUN APLIKASI
# ==========================================
if __name__ == "__main__":
    print("🚀 NutriScan AI System Starting...")
    app.run(debug=True, port=5000)