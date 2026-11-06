import os
import json
import io
import base64
import re
from PIL import Image
from google import genai
from google.genai import types
from groq import Groq
from dotenv import load_dotenv

# --- 1. SETUP API & AUTENTIKASI ---
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if GEMINI_API_KEY:
    # Memakai SDK Google GenAI yang baru
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
else:
    print("⚠️ PERINGATAN: GEMINI_API_KEY tidak ditemukan di file .env!")
    gemini_client = None

if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    print("⚠️ PERINGATAN: GROQ_API_KEY tidak ditemukan di file .env!")
    groq_client = None

def extract_json(raw_text):
    """Fungsi pembantu untuk mengekstrak dan mem-parsing JSON dari teks kotor."""
    clean_text = raw_text.replace("```json", "").replace("```", "").strip()
    # Coba parsing langsung
    try:
        return json.loads(clean_text), clean_text
    except Exception:
        # Jika gagal, coba gunakan regex untuk mencari blok JSON
        match = re.search(r'\{.*\}', clean_text, re.DOTALL)
        if match:
            json_str = match.group(0)
            return json.loads(json_str), json_str
        raise ValueError(f"Tidak dapat menemukan JSON valid dalam teks:\n{raw_text}")


def extract_nutrition_from_image(image_path):
    print(f"🤖 [OCR Engine] Memproses gambar: {image_path}...")
    
    try:
        if not gemini_client and not groq_client:
            raise Exception("API Key belum dikonfigurasi. Periksa file .env!")

        # --- 2. PEMROSESAN GAMBAR ---
        with Image.open(image_path) as img_object:
            if img_object.mode in ("RGBA", "P"):
                img_object = img_object.convert("RGB")
            
            img_byte_arr = io.BytesIO()
            img_object.save(img_byte_arr, format='JPEG') 
            img_bytes = img_byte_arr.getvalue()

        # Konversi bytes ke dalam Part format SDK baru
        image_part = types.Part.from_bytes(
            data=img_bytes,
            mime_type='image/jpeg'
        )

        # --- 3. PROMPT ENGINEERING ---
        prompt = """
        Kamu adalah sistem OCR ahli nutrisi (Nutritionist AI). Tugasmu adalah mengekstrak data AKURAT dari gambar label gizi produk.

        INSTRUKSI KHUSUS SATUAN (WAJIB DIPATUHI):
        1. **SODIUM / NATRIUM / GARAM**: Wajib konversi ke miligram (mg).
        2. **ENERGI**: Angka dalam kkal (kcal).
        3. **GULA / LEMAK / PROTEIN / SERAT / BUAH**: Angka dalam gram (g). 
        4. **TAKARAN SAJI (Serving Size)**: Cari teks seperti "Takaran Saji", "Serving Size", "Porsi", "Sajian", atau "Berat Bersih". Ekstrak hanya nilai angkanya saja dalam (gram/ml).
        5. **KATEGORI**: ml -> 0, gram -> 1.
        6. **TIDAK TERBACA ATAU TIDAK ADA**: Jika nama parameter (misal: Gula, Garam, Energi) TIDAK ADA di label, ATAU jika namanya ada tetapi ANGKA/NILAINYA buram/blur/kepotong dan tidak bisa dibaca dengan pasti, WAJIB berikan nilai null (jangan menebak angka, jangan berikan 0.0). Hanya berikan 0.0 jika di label tertulis jelas angka 0.
        7. **GAMBAR BLUR / ANTI-HALUSINASI**: Jika secara keseluruhan tabel gizi buram, tidak fokus, kepotong atau sangat sulit dibaca, JANGAN MENGGUNAKAN PENGETAHUAN SEBELUMNYA ATAU MENEBAK ANGKA BERDASARKAN MERK. Jika angka secara visual di gambar tidak bisa dibaca dengan yakin 100%, berikan nilai null untuk semua parameter angka dan WAJIB set "gambar_blur_atau_gelap": true.

        OUTPUT JSON FORMAT:
        {
            "nama_produk": "Nama produk",
            "brand": "Nama merk",
            "kategori": 1, 
            "takaran_saji": null,
            "energi": null,
            "protein": null,
            "lemak_jenuh": null,
            "gula": null,
            "garam": null, 
            "serat": null,
            "buah": null,
            "gambar_blur_atau_gelap": false 
        }
        Catatan: Set "gambar_blur_atau_gelap" ke true JIKA gambar terlalu blur, buram, kepotong, atau gelap sehingga sulit atau tidak bisa dibaca dengan baik.
        """

        data = None
        clean_text = ""

        # --- 4. KONFIGURASI DAN EKSEKUSI AI (Dengan Fallback yang Benar) ---
        try:
            if not gemini_client:
                raise Exception("Gemini client tidak tersedia.")

            # Memaksa model menjawab hanya dalam bentuk JSON
            config = types.GenerateContentConfig(
                temperature=0.1,
                response_mime_type="application/json",
            )

            # Menggunakan gemini-flash-latest untuk performa OCR yang sangat akurat
            print("⏳ [OCR Engine] Menggunakan API Gemini (gemini-flash-latest)...")
            response = gemini_client.models.generate_content(
                model="gemini-flash-latest",
                contents=[prompt, image_part],
                config=config
            )

            print("✅ [OCR Engine] Respon AI Gemini Diterima!") 
            # PENTING: Pindahkan ekstraksi JSON ke dalam try-block agar 
            # jika gagal parsing (misal Extra data / teks kotor), langsung lempar error & masuk fallback Groq
            data, clean_text = extract_json(response.text)

        except Exception as e_gemini:
            print(f"⚠ [OCR Engine] Gemini Gagal (API Error / Format JSON tidak valid): {e_gemini}")
            
            if groq_client:
                print("🔄 [OCR Engine] Fallback: Mengalihkan ke API Groq...")
                try:
                    # Groq butuh base64
                    base64_image = base64.b64encode(img_bytes).decode('utf-8')
                    
                    # Supaya bisa memaksa JSON output tanpa error dari Groq, text prompt harus menyuruh keluarkan "JSON" murni.
                    prompt_groq = prompt + "\n\nPENTING: Perhatikan baik-baik teks 'Takaran Saji' atau 'Serving Size' atau 'Berat Bersih'. Anda WAJIB mengisi kunci \"takaran_saji\" dengan angka tersebut.\nKeluarkan HANYA JSON murni tanpa markdown (jangan gunakan ```json)."
                    response_groq = groq_client.chat.completions.create(
                        model="meta-llama/llama-4-scout-17b-16e-instruct",
                        messages=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt_groq},
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/jpeg;base64,{base64_image}",
                                        },
                                    },
                                ],
                            }
                        ],
                        temperature=0.1,
                        response_format={"type": "json_object"}
                    )

                    print("✅ [OCR Engine] Respon API Groq Diterima!") 
                    data, clean_text = extract_json(response_groq.choices[0].message.content)
                except Exception as e_groq:
                    print(f"❌ [OCR Engine] Groq juga gagal: {e_groq}")
                    raise Exception("Semua API (Gemini & Groq) gagal.")
            else:
                print("❌ [OCR Engine] Groq tidak dikonfigurasi, gagal total.")
                raise Exception("Semua API (Gemini & Groq) gagal.")

        # --- 5. VALIDASI & PEMBERSIHAN ---
        # Perbaikan kunci json yang sering tertukar oleh model fallback
        if "serving_size" in data and data.get("takaran_saji") is None:
            data["takaran_saji"] = data["serving_size"]
        if "berat_bersih" in data and data.get("takaran_saji") is None:
            data["takaran_saji"] = data["berat_bersih"]
        if "takaran" in data and data.get("takaran_saji") is None:
            data["takaran_saji"] = data["takaran"]

        kunci_angka = ["energi", "protein", "lemak_jenuh", "gula", "garam", "serat", "buah", "takaran_saji"]

        
        # Hitung berapa banyak parameter yang bernilai None (tidak ditemukan)
        missing_count = 0
        for key in kunci_angka:
            if data.get(key) is None:
                missing_count += 1
                
        # Simpan status flag
        data["missing_gula"] = data.get("gula") is None
        
        # MEMAKSA status blur jika 3 atau lebih parameter tidak ditemukan, atau jika AI mendeteksi blur
        is_blur_by_ai = data.get("gambar_blur_atau_gelap", False)
        if missing_count >= 3:
            print(f"⚠ [OCR Engine] Terdeteksi {missing_count} parameter kosong. Memaksa status blur = True.")
            data["gambar_blur"] = True
        else:
            data["gambar_blur"] = is_blur_by_ai

        # Ubah nilai None menjadi 0.0 agar frontend tidak error
        for key in kunci_angka:
            if data.get(key) is None:
                data[key] = 0.0

        return data, clean_text

    except Exception as e:
        print(f"❌ [OCR Engine] CRITICAL ERROR: {e}")
        # Data Cadangan agar aplikasi tidak error frontend
        fallback_data = {
            "nama_produk": "Gagal Terbaca",
            "brand": "-",
            "kategori": 1,
            "takaran_saji": 100.0,
            "energi": 0.0, 
            "protein": 0.0, 
            "lemak_jenuh": 0.0, 
            "gula": 0.0, 
            "garam": 0.0, 
            "serat": 0.0, 
            "buah": 0.0,
            "missing_gula": False,
            "gambar_blur": False
        }
        return fallback_data, f"Error System: {str(e)}"
