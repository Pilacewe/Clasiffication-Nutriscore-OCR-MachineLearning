import os
from google import genai
from dotenv import load_dotenv

# Load API Key dari .env
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    print("❌ API Key tidak ditemukan di .env!")
    exit()

print(f"Menggunakan API Key: {API_KEY[:15]}...")

try:
    client = genai.Client(api_key=API_KEY)
    print("\n✅ Daftar Model yang TERSEDIA dan BISA digunakan:")
    
    models = client.models.list()
    found = False
    for model in models:
        # Kita cari model yang mendukung generateContent (untuk OCR/teks)
        if "generateContent" in model.supported_generation_methods:
            # Hapus tulisan "models/" agar namanya lebih bersih
            clean_name = model.name.replace("models/", "")
            print(f"- {clean_name}")
            found = True
            
    if not found:
        print("⚠ Tidak ada model yang mendukung generateContent untuk API Key ini.")
        
except Exception as e:
    print(f"\n❌ GAGAL MENGAMBIL DAFTAR MODEL:\n{e}")