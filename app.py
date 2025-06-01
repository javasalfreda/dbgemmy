from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
from faker import Faker
import random
import uuid
import datetime
import os
import zipfile
import json
from dotenv import load_dotenv
import google.generativeai as genai
import time

load_dotenv()

app = Flask(__name__)
CORS(app)

fake = Faker('id_ID')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, 'generated_files')
os.makedirs(OUTPUT_DIR, exist_ok=True)

GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
gemini_model_instance = None

# BARU: Jumlah saran AI yang diminta per kolom ai_text
NUM_AI_SUGGESTIONS_PER_COLUMN = int(os.getenv('NUM_AI_SUGGESTIONS_PER_COLUMN', 20)) # Default 20 jika tidak ada di .env

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
        gemini_model_instance = genai.GenerativeModel('gemini-1.5-flash-latest')
        print("Kunci API Gemini berhasil dimuat dan model diinisialisasi.")
    except Exception as e:
        print(f"Error saat konfigurasi API Gemini atau inisialisasi model: {e}")
        GEMINI_API_KEY = None
else:
    print("GEMINI_API_KEY tidak ditemukan dalam file .env. Fitur AI akan terbatas/nonaktif.")

def parse_options_str(options_str):
    params = {}
    if not options_str: return params
    try:
        parts = options_str.split(',')
        for part in parts:
            if '=' not in part: continue
            key, value = part.split('=', 1)
            key = key.strip(); value = value.strip()
            if value.lower() == 'true': params[key] = True
            elif value.lower() == 'false': params[key] = False
            elif value.isdigit(): params[key] = int(value)
            else:
                try: params[key] = float(value)
                except ValueError: params[key] = value
    except Exception as e: print(f"Peringatan parse opsi: '{options_str}'. E: {e}")
    return params

# MODIFIKASI: Fungsi ini sekarang meminta *DAFTAR* saran
def generate_ai_suggestions_list(col_name, table_name, database_context="data umum", user_hint="", num_suggestions=NUM_AI_SUGGESTIONS_PER_COLUMN, temperature=0.7, max_tokens_multiplier=30):
    if not gemini_model_instance:
        print("Peringatan: Model AI tidak tersedia untuk generate_ai_suggestions_list.")
        return []
    try:
        base_prompt = f"Anda adalah generator data ahli. Konteks DB: '{database_context}'. "
        specific_prompt = ""
        col_name_lower = col_name.lower()

        # Logika prompt disesuaikan untuk meminta daftar
        if any(k in col_name_lower for k in ['deskripsi', 'catatan', 'keterangan', 'summary', 'description', 'notes', 'comments', 'detail']):
            specific_prompt = f"Berikan {num_suggestions} contoh '{col_name}' yang realistis & deskriptif (masing-masing 1-3 kalimat pendek) untuk entitas di tabel '{table_name}'."
        elif any(k in col_name_lower for k in ['nama', 'judul', 'title', 'name']):
            if any(k in col_name_lower for k in ['perusahaan', 'company', 'organisasi', 'supplier', 'pelanggan', 'customer']):
                specific_prompt = f"Berikan {num_suggestions} contoh nama '{col_name}' yang cocok untuk entitas di tabel '{table_name}'."
            elif any(k in col_name_lower for k in ['produk', 'product', 'barang', 'item', 'layanan', 'service']):
                specific_prompt = f"Berikan {num_suggestions} contoh nama produk/layanan yang menarik & spesifik (masing-masing 2-5 kata) untuk kolom '{col_name}' di tabel '{table_name}'."
            else:
                specific_prompt = f"Berikan {num_suggestions} contoh '{col_name}' umum & relevan (masing-masing 2-5 kata) untuk entitas di tabel '{table_name}'."
        elif any(k in col_name_lower for k in ['slogan', 'tagline', 'motto']):
            specific_prompt = f"Berikan {num_suggestions} contoh slogan/tagline singkat & menarik untuk kolom '{col_name}' yang relevan dengan tabel '{table_name}'."
        else:
            specific_prompt = f"Berikan {num_suggestions} contoh nilai data yang realistis, singkat, & relevan untuk kolom '{col_name}' di tabel '{table_name}'."

        if user_hint:
            specific_prompt += f" Pertimbangkan petunjuk ini: '{user_hint}'."

        full_prompt = base_prompt + specific_prompt + f" Format output HARUS berupa array JSON string yang valid, contoh: [\"nilai1\", \"nilai2\", ..., \"nilai{num_suggestions}\"]. JANGAN sertakan markdown atau teks lain di luar array JSON."
        
        # Perkirakan max_output_tokens berdasarkan jumlah saran dan perkiraan panjang per saran
        # Ini adalah perkiraan kasar, mungkin perlu disesuaikan
        estimated_max_tokens = num_suggestions * max_tokens_multiplier
        
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            max_output_tokens=estimated_max_tokens,
            response_mime_type="application/json" # Meminta JSON secara eksplisit
        )
        print(f"  Meminta {num_suggestions} saran AI untuk {table_name}.{col_name} (max_tokens: {estimated_max_tokens})...")
        
        response = gemini_model_instance.generate_content(full_prompt, generation_config=generation_config)
        
        content = response.text.strip()
        # Membersihkan jika ada ```json ... ``` (meskipun response_mime_type seharusnya menangani ini)
        if content.startswith("```json"):
            content = content[len("```json"):]
        if content.endswith("```"):
            content = content[:-len("```")]
        content = content.strip()

        if not content:
            print(f"  Peringatan: AI tidak memberikan respons untuk saran {table_name}.{col_name}.")
            return []

        try:
            suggestions = json.loads(content)
            if isinstance(suggestions, list) and all(isinstance(s, str) for s in suggestions):
                print(f"  Berhasil mendapatkan {len(suggestions)} saran AI untuk {table_name}.{col_name}.")
                return suggestions
            else:
                print(f"  Peringatan: Format respons AI tidak sesuai (bukan list of string) untuk {table_name}.{col_name}: {content}")
                return []
        except json.JSONDecodeError as jde:
            print(f"  Error decoding JSON dari AI untuk {table_name}.{col_name}: {jde}. Respons mentah: {content}")
            return []
    except Exception as e:
        print(f"  Error saat generate AI suggestions list untuk {table_name}.{col_name}: {e}")
        import traceback
        traceback.print_exc()
        return []

# MODIFIKASI: generate_value sekarang menggunakan ai_suggestions_list untuk tipe 'ai_text'
def generate_value(col_name, table_name, col_type, col_options_str, database_context="data umum", 
                   existing_values_set=None, nullable=False, nullable_chance=0, 
                   ai_suggestions_list=None): # Parameter baru
    if nullable and random.randint(1, 100) <= nullable_chance:
        return None
    
    options = parse_options_str(col_options_str)
    val = None

    if col_type == 'ai_text':
        if ai_suggestions_list: # Gunakan daftar saran yang sudah ada
            if not ai_suggestions_list: # Jika daftar kosong (misal AI gagal)
                 val = f"Data AI tidak tersedia (saran kosong untuk {col_name})"
            elif existing_values_set is not None:
                # Jika kolom harus unik, coba cari yang unik dari daftar saran
                available_suggestions = [s for s in ai_suggestions_list if s not in existing_values_set]
                if available_suggestions:
                    val = random.choice(available_suggestions)
                    existing_values_set.add(val)
                else:
                    # Tidak ada saran unik tersisa, ambil saja salah satu (bisa duplikat)
                    # atau jika nullable, pertimbangkan untuk mengembalikan None
                    # Ini adalah kompromi jika num_rows > num_suggestions unik
                    print(f"Peringatan: Tidak ada saran AI unik yang tersisa untuk kolom '{col_name}' (unik). Menggunakan nilai acak dari daftar.")
                    val = random.choice(ai_suggestions_list) 
                    # existing_values_set.add(val) # Jangan tambahkan jika bisa duplikat & sudah ada
            else: # Kolom tidak perlu unik
                val = random.choice(ai_suggestions_list)
            return val # Langsung return, tidak perlu loop unik di bawah untuk ai_text
        else:
            # Ini seharusnya tidak terjadi jika alur pra-pengambilan berfungsi
            print(f"Peringatan: Tidak ada daftar saran AI yang diberikan untuk {col_name} di {table_name}. Mengembalikan placeholder.")
            return f"AI suggestions not pre-fetched for {col_name}"

    # Logika untuk tipe data lain (tidak berubah)
    max_unique_tries = 100
    tries = 0
    while tries < max_unique_tries:
        if col_type == 'string': min_l = options.get('min_len', 5); max_l = options.get('max_len', 20); val = fake.pystr(min_chars=min_l, max_chars=max_l)
        elif col_type == 'text': val = fake.paragraph(nb_sentences=random.randint(2,5))
        elif col_type == 'integer': min_v=options.get('min',0);max_v=options.get('max',1000);val=random.randint(min_v,max_v)
        elif col_type == 'float': min_v=options.get('min',0.0);max_v=options.get('max',100.0);prec=options.get('precision',2);val=round(random.uniform(min_v,max_v),prec)
        elif col_type == 'date': s_dt=options.get('start','2000-01-01');e_dt=options.get('end','today');s_d=datetime.datetime.strptime(s_dt,'%Y-%m-%d').date() if s_dt!='today' else datetime.date.today();e_d=datetime.date.today() if e_dt=='today' else datetime.datetime.strptime(e_dt,'%Y-%m-%d').date();val=fake.date_between_dates(date_start=s_d,date_end=e_d).strftime('%Y-%m-%d')
        elif col_type == 'email': val = fake.email()
        elif col_type == 'fullname': val = fake.name()
        elif col_type == 'address': val = fake.address().replace('\n',', ')
        elif col_type == 'uuid': val = str(uuid.uuid4())
        elif col_type == 'boolean': val = random.choice([True, False])
        elif col_type == 'custom_list': itms_s=col_options_str;itms=[i.strip() for i in itms_s.split(',') if i.strip()];val=random.choice(itms) if itms else ""
        else: val = f"Tipe tdk dikenal: {col_type}"
        
        if existing_values_set is None or val not in existing_values_set:
            if existing_values_set is not None and val is not None: # Pastikan val bukan None sebelum menambah ke set
                existing_values_set.add(val)
            break
        tries += 1
    if tries >= max_unique_tries and existing_values_set is not None:
        print(f"Warning: Gagal menghasilkan nilai unik setelah {max_unique_tries} percobaan untuk kolom '{col_name}' (tipe: {col_type}). Nilai terakhir: '{val}'")
    return val

@app.route('/')
def index(): return send_from_directory(BASE_DIR, 'index.html')
@app.route('/script.js')
def script_js_route(): return send_from_directory(BASE_DIR, 'script.js')
@app.route('/style.css')
def style_css_route(): return send_from_directory(BASE_DIR, 'style.css', mimetype='text/css')

@app.route('/suggest-schema-ai', methods=['POST'])
def suggest_schema_ai_route():
    if not gemini_model_instance: return jsonify({"error": "AI tidak aktif."}), 503
    user_context = request.json.get('context')
    if not user_context: return jsonify({"error": "Konteks kosong."}), 400
    try:
        prompt = f"""
        Anda adalah seorang Desainer Database Profesional dan Analis Sistem yang sangat berpengalaman.
        Tugas Anda adalah merancang struktur database (skema) yang optimal, logis, dan relevan berdasarkan konteks yang diberikan pengguna.

        Konteks dari Pengguna: "{user_context}"

        Langkah-langkah yang harus Anda ikuti:
        1.  PAHAMI SECARA MENDALAM konteks pengguna. Identifikasi entitas-entitas utama, informasi penting apa yang perlu disimpan tentang entitas tersebut, dan bagaimana entitas-entitas tersebut mungkin saling berhubungan.
        2.  RANCANG TABEL-TABEL yang diperlukan. Setiap tabel harus mewakili satu entitas atau konsep utama.
        3.  TENTUKAN KOLOM-KOLOM untuk setiap tabel. Kolom harus mencerminkan atribut-atribut penting dari entitas tabel tersebut.
            - Gunakan NAMA TABEL dan NAMA KOLOM yang jelas, deskriptif dalam Bahasa Indonesia (jika konteksnya Bahasa Indonesia), dan mengikuti konvensi penamaan yang baik (misalnya, PascalCase untuk Tabel, snake_case untuk kolom). Hindari singkatan yang ambigu.
            - Untuk setiap kolom, pilih TIPE DATA yang paling sesuai dan efisien dari daftar berikut: [String, Integer, Float, Date, Email, FullName, Address, UUID, Boolean, Text, ai_text, Custom_List].
            - Tentukan apakah sebuah kolom nilainya harus 'unique' (unik).
            - Tentukan apakah sebuah kolom 'nullable' (boleh kosong) dan berapa 'nullable_chance' (0-100%) jika boleh kosong.
            - Sertakan 'options' yang relevan (misalnya untuk String: min_len=X,max_len=Y; Integer/Float: min=A,max=B; Date: start=YYYY-MM-DD,end=YYYY-MM-DD; ai_text: hint=PetunjukTambahan; Custom_List: item1,item2,item3). Untuk ai_text, jika ada petunjuk spesifik untuk generasi konten, letakkan di 'options' sebagai 'hint=isi_petunjuk'.
        4.  BAYANGKAN KUALITAS HASIL: Pikirkan tentang bagaimana Anda akan menyajikan contoh tabel dengan data jika diminta langsung oleh pengguna. Skema yang Anda rancang harus mencerminkan tingkat detail dan relevansi yang sama.

        PERSYARATAN OUTPUT JSON (SANGAT PENTING):
        Format HANYA sebagai objek JSON yang valid. Root: {{ "tables": [ {{ "name": "NamaTabel", "columns": [{{ "name": "nama_kolom", "type": "TipeData", "options": "opsi_kolom_jika_ada", "unique": false, "nullable": false, "nullable_chance": 0 }}] }} ] }}
        Pastikan nama tabel dan kolom sesuai konvensi (PascalCase untuk Tabel, snake_case untuk kolom).
        Contoh opsi: "min_len=5,max_len=10" untuk String, "hint=Buat deskripsi produk makanan ringan" untuk ai_text, "aktif,tidak aktif,pending" untuk Custom_List.

        Sekarang, berdasarkan konteks pengguna: "{user_context}", berikan rancangan skema database dalam format JSON yang diminta.
        """
        generation_config = genai.types.GenerationConfig(temperature=0.1, response_mime_type="application/json")
        response = gemini_model_instance.generate_content(prompt, generation_config=generation_config)
        
        cleaned_response_text = response.text.strip()
        # Pembersihan tambahan jika mime type tidak sepenuhnya menangani ```json
        if cleaned_response_text.startswith("```json"): cleaned_response_text = cleaned_response_text[len("```json"):]
        if cleaned_response_text.endswith("```"): cleaned_response_text = cleaned_response_text[:-len("```")]
        cleaned_response_text = cleaned_response_text.strip()

        if not cleaned_response_text: raise ValueError("Respons AI skema kosong.")
        suggested_schema = json.loads(cleaned_response_text)
        if not isinstance(suggested_schema, dict) or "tables" not in suggested_schema: raise ValueError("Format JSON skema AI salah (tables).")
        # Validasi lebih lanjut bisa ditambahkan di sini jika perlu
        return jsonify(suggested_schema)
    except Exception as e:
        import traceback
        print(f"Error suggest-schema-ai: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": f"Error saat menyarankan skema AI: {str(e)}"}), 500

@app.route('/generate-data', methods=['POST'])
def handle_generate_data():
    try:
        schema = request.json
        num_rows = schema.get('num_rows', 10)
        tables_data = schema.get('tables', [])
        schema_database_context = schema.get('database_context', "data umum")
        requested_format = schema.get('requested_format', 'csv').lower()

        if requested_format not in ['csv', 'excel']:
            requested_format = 'csv'

        if not tables_data: return jsonify({"error": "Tidak ada definisi tabel."}), 400

        processed_files_details = []
        
        # BARU: Cache untuk menyimpan saran AI per kolom
        ai_suggestions_cache = {}

        # --- TAHAP 1: Pra-pengambilan Saran AI untuk kolom 'ai_text' ---
        if gemini_model_instance: # Hanya lakukan jika AI aktif
            print(f"\n--- Mengumpulkan saran AI (jika ada kolom 'ai_text', {NUM_AI_SUGGESTIONS_PER_COLUMN} saran per kolom) ---")
            for table_def_for_ai_prefetch in tables_data:
                table_name_for_prefetch = table_def_for_ai_prefetch.get('name', f'TabelTanpaNama_{random.randint(1000,9999)}')
                columns_def_for_prefetch = table_def_for_ai_prefetch.get('columns', [])
                for col_def_prefetch in columns_def_for_prefetch:
                    if col_def_prefetch['type'] == 'ai_text':
                        col_name_prefetch = col_def_prefetch['name']
                        cache_key = (table_name_for_prefetch, col_name_prefetch)
                        
                        # Dapatkan user_hint dari options
                        col_options_str = col_def_prefetch.get('options', '')
                        options = parse_options_str(col_options_str)
                        user_hint = options.get('hint', col_options_str if '=' not in col_options_str and col_options_str else '')

                        # Panggil Gemini untuk mendapatkan daftar saran
                        # Max_tokens_multiplier bisa disesuaikan jika saran sering terpotong
                        suggestions = generate_ai_suggestions_list(
                            col_name=col_name_prefetch,
                            table_name=table_name_for_prefetch,
                            database_context=schema_database_context,
                            user_hint=user_hint,
                            num_suggestions=NUM_AI_SUGGESTIONS_PER_COLUMN,
                            max_tokens_multiplier=40 # Naikkan sedikit untuk jaga-jaga
                        )
                        ai_suggestions_cache[cache_key] = suggestions
                        if not suggestions:
                             print(f"  Peringatan: Tidak ada saran AI yang didapatkan untuk {table_name_for_prefetch}.{col_name_prefetch}")
                        time.sleep(1) # Small delay to avoid hitting API rate limits if many ai_text columns
        else:
            print("\n--- Model AI tidak aktif, melewati pengumpulan saran AI ---")

        # --- TAHAP 2: Generasi Data Aktual ---
        for table_def in tables_data:
            table_name = table_def.get('name', f'TabelTanpaNama_{random.randint(1000,9999)}')
            columns_def = table_def.get('columns', [])
            if not columns_def: continue
            
            data_rows = []
            unique_sets = { cd['name']: set() for cd in columns_def if cd.get('unique') }
            
            print(f"\n--- Menghasilkan data untuk tabel: {table_name} ({num_rows} baris) ---")
            for i_row in range(num_rows):
                # Logika log progres
                contains_ai_text_in_current_table = any(col['type'] == 'ai_text' for col in columns_def)
                # Jika ada ai_text (bahkan jika dari cache), log lebih sering karena bisa jadi lebih lambat jika cache miss & fallback
                log_freq = 1 if contains_ai_text_in_current_table and num_rows <= 20 else \
                           (5 if contains_ai_text_in_current_table else 10) 
                if num_rows <= log_freq or (i_row + 1) % log_freq == 0 or i_row == 0 :
                    print(f"  Memproses baris {i_row + 1}/{num_rows}...")

                row = {}
                for col_def in columns_def:
                    col_name = col_def['name']
                    col_type = col_def['type']
                    
                    current_ai_suggestions = []
                    if col_type == 'ai_text':
                        cache_key = (table_name, col_name)
                        current_ai_suggestions = ai_suggestions_cache.get(cache_key, []) # Ambil dari cache
                        if not current_ai_suggestions and gemini_model_instance: # Jika cache kosong & AI aktif (seharusnya tidak terjadi)
                            print(f"  Peringatan: Cache AI kosong untuk {table_name}.{col_name} saat generasi baris. Ini tidak diharapkan.")
                    
                    row[col_name] = generate_value(
                        col_name, table_name, col_type, 
                        col_def.get('options',''), schema_database_context,
                        unique_sets.get(col_name) if col_def.get('unique') else None,
                        col_def.get('nullable',False), int(col_def.get('nullable_chance',0)),
                        ai_suggestions_list=current_ai_suggestions # Teruskan daftar saran
                    )
                data_rows.append(row)
            
            df = pd.DataFrame(data_rows) if data_rows else pd.DataFrame(columns=[cd['name'] for cd in columns_def])

            safe_table_name = "".join(c if c.isalnum() or c in ('_','-') else '_' for c in table_name)
            timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S%f")
            
            actual_filename = ""
            file_path_for_zip = ""
            file_url_for_download = ""

            if requested_format == 'csv':
                actual_filename = f"{safe_table_name}_{timestamp}.csv"
                file_path_for_zip = os.path.join(OUTPUT_DIR, actual_filename)
                df.to_csv(file_path_for_zip, index=False)
            elif requested_format == 'excel':
                actual_filename = f"{safe_table_name}_{timestamp}.xlsx"
                file_path_for_zip = os.path.join(OUTPUT_DIR, actual_filename)
                df.to_excel(file_path_for_zip, index=False, engine='openpyxl')
            
            file_url_for_download = f"/download/{actual_filename}"
            
            processed_files_details.append({
                "table_name": table_name,
                "url": file_url_for_download,
                "filename": actual_filename,
                "format": requested_format,
                "path_for_zip": file_path_for_zip
            })
            print(f"  Tabel '{table_name}' telah digenerate dan disimpan sebagai '{actual_filename}'.")
        
        if not processed_files_details: return jsonify({"error": "Tidak ada file yang digenerate."}), 400

        response_payload = {"download_info": {}}
        if len(processed_files_details) > 1:
            zip_filename = f"dbgenie_export_{requested_format}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.zip"
            zip_path = os.path.join(OUTPUT_DIR, zip_filename)
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_info in processed_files_details:
                    if os.path.exists(file_info['path_for_zip']):
                        zipf.write(file_info['path_for_zip'], arcname=file_info['filename'])
            
            response_payload["download_info"] = {
                "is_zip": True,
                "url": f"/download/{zip_filename}",
                "filename": zip_filename,
                "format": requested_format
            }
        elif processed_files_details:
            single_file_info = processed_files_details[0]
            response_payload["download_info"] = {
                "is_zip": False,
                "files": [{
                    "table_name": single_file_info["table_name"],
                    "url": single_file_info["url"],
                    "filename": single_file_info["filename"],
                    "format": single_file_info["format"]
                }]
            }
        else:
            return jsonify({"error": "Gagal menggenerate file akhir."}), 500
        
        return jsonify(response_payload)

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error saat generate data: {error_trace}")
        return jsonify({"error": f"Kesalahan server internal: {str(e)}. Detail ada di log."}), 500

@app.route('/download/<filename>')
def download_file(filename):
    if ".." in filename or filename.startswith("/"):
        return "Nama file tidak valid.", 400
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)

if __name__ == '__main__':
    print(f"Kunci API Gemini dimuat: {'Ya' if GEMINI_API_KEY else 'Tidak'}. Instans model: {'Ada' if gemini_model_instance else 'Tidak Ada'}")
    print(f"Menyajikan file dari: {BASE_DIR}. File output akan disimpan di: {OUTPUT_DIR}")
    print(f"Jumlah saran AI per kolom 'ai_text': {NUM_AI_SUGGESTIONS_PER_COLUMN}")
    app.run(debug=True, port=5000)