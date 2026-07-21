import os
import zipfile
import re
import json
import io

# Intento de importar Pillow para el procesamiento de imágenes
try:
    from PIL import Image
except ImportError:
    print("[!] La librería 'Pillow' es necesaria para procesar imágenes.")
    print("    Instálala ejecutando: pip install Pillow")
    exit(1)

SONGS_DIR = "songs_osz"
COVERS_DIR = "covers"
JSON_FILE = "beatmaps.json"
# Escalado 4X manteniendo la relación de aspecto exacta de 212:69 para alta densidad (Retina/4K)
TARGET_WIDTH = 848
TARGET_HEIGHT = 276
TARGET_ASPECT = 212 / 69  # 212 / 69 ~= 3.072

def find_json_file():
    """Busca 'beatmaps.json' en el directorio actual o en directorios cercanos."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        JSON_FILE,
        os.path.join(script_dir, JSON_FILE),
        os.path.join(script_dir, "..", JSON_FILE),
        os.path.join(os.getcwd(), JSON_FILE)
    ]
    for path in candidates:
        if os.path.isfile(path):
            return os.path.abspath(path)
    return None

def find_songs_dir(json_dir):
    """Detecta la carpeta donde están los archivos .osz (pack, songs_osz o la raíz)."""
    possible_dirs = ["pack", SONGS_DIR, "."]
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    search_base_paths = [os.getcwd(), json_dir, script_dir]
    
    for base in search_base_paths:
        for folder in possible_dirs:
            full_path = os.path.abspath(os.path.join(base, folder))
            if os.path.exists(full_path) and any(f.lower().endswith('.osz') for f in os.listdir(full_path)):
                return full_path
    return os.getcwd()

def crop_center_cover(img, target_w, target_h):
    """
    Realiza un recorte centrado manteniendo la máxima proporción posible (Cover Crop).
    Garantiza que la imagen ocupe la relación de aspecto 212:69 en alta resolución (848x276).
    """
    orig_w, orig_h = img.size
    orig_aspect = orig_w / orig_h

    if orig_aspect > TARGET_ASPECT:
        # La imagen original es más ancha que el objetivo -> Recortar lados (izquierda/derecha)
        crop_h = orig_h
        crop_w = int(orig_h * TARGET_ASPECT)
        left = (orig_w - crop_w) // 2
        top = 0
        right = left + crop_w
        bottom = orig_h
    else:
        # La imagen original es más alta que el objetivo -> Recortar arriba/abajo
        crop_w = orig_w
        crop_h = int(orig_w / TARGET_ASPECT)
        left = 0
        top = (orig_h - crop_h) // 2
        right = orig_w
        bottom = top + crop_h

    # Recortar área centrada
    cropped_img = img.crop((left, top, right, bottom))
    
    # Redimensionar a la versión HD del target (848x276)
    resample_filter = getattr(Image, 'Resampling', Image).LANCZOS
    final_img = cropped_img.resize((target_w, target_h), resample_filter)
    
    return final_img

def extract_bg_from_osz(osz_path, bg_filename):
    """Extrae y carga en memoria la imagen de fondo desde el zip .osz."""
    if not bg_filename:
        return None

    bg_filename_clean = bg_filename.strip('"').replace('\\', '/')
    bg_base_name = os.path.basename(bg_filename_clean).lower()

    try:
        with zipfile.ZipFile(osz_path, 'r') as z:
            for item in z.infolist():
                item_name_clean = item.filename.replace('\\', '/').lower()
                # Coincidencia por nombre exacto o nombre de archivo base
                if item_name_clean == bg_filename_clean.lower() or os.path.basename(item_name_clean) == bg_base_name:
                    with z.open(item) as img_file:
                        img_data = img_file.read()
                        image = Image.open(io.BytesIO(img_data))
                        if image.mode != 'RGB':
                            image = image.convert('RGB')
                        return image
    except Exception as e:
        print(f"  [!] Error leyendo imagen del archivo ZIP: {e}")
    return None

def main():
    print("=== Extractor y Recortador de Portadas para Taiko Web ===")
    print(f" - Resolución objetivo: {TARGET_WIDTH} x {TARGET_HEIGHT} px (recorte centrado)")

    json_path = find_json_file()
    if not json_path:
        print(f"[!] No se encontró '{JSON_FILE}'. Ejecuta primero 'generate_beatmaps_json.py'.")
        return

    json_dir = os.path.dirname(json_path)
    covers_output_dir = os.path.join(json_dir, COVERS_DIR)

    # Crear carpeta destino para las imágenes de portada si no existe
    if not os.path.exists(covers_output_dir):
        os.makedirs(covers_output_dir)

    # Detectar directorio objetivo de canciones (pack, songs_osz, etc.)
    target_songs_dir = find_songs_dir(json_dir)

    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    beatmapsets = data.get("beatmapsets", [])
    processed_count = 0

    print(f"Leyendo: {json_path}")
    print(f"Buscando .osz en: {target_songs_dir}")
    print(f"Procesando {len(beatmapsets)} beatmapsets de '{JSON_FILE}'...\n")

    for bset in beatmapsets:
        mapset_id = bset.get("beatmapset_id", 0)
        filename = bset.get("filename", "")
        osz_path = os.path.join(target_songs_dir, filename)

        if not os.path.exists(osz_path):
            # Intentar buscar en la raíz o en subcarpetas
            alt_path = os.path.join(json_dir, filename)
            if os.path.exists(alt_path):
                osz_path = alt_path

        # Obtener el nombre de la imagen de fondo desde la primera dificultad disponible
        bg_image_name = None
        for diff in bset.get("difficulties", []):
            if diff.get("background_image"):
                bg_image_name = diff.get("background_image")
                break

        cover_filename = f"{mapset_id if mapset_id else bset.get('title', 'cover')}.jpg"
        cover_filename = re.sub(r'[\\/*?:"<>|]', "", cover_filename)
        cover_relative_path = f"{COVERS_DIR}/{cover_filename}"
        cover_output_path = os.path.join(covers_output_dir, cover_filename)

        image_extracted = False

        if os.path.exists(osz_path) and bg_image_name:
            img = extract_bg_from_osz(osz_path, bg_image_name)
            if img:
                cropped_img = crop_center_cover(img, TARGET_WIDTH, TARGET_HEIGHT)
                # Guardar en calidad máxima sin compresión agresiva de píxeles
                cropped_img.save(cover_output_path, "JPEG", quality=98, subsampling=0)
                image_extracted = True
                processed_count += 1
                print(f"  [✓] Portada recortada HD ({TARGET_WIDTH}x{TARGET_HEIGHT}): {bset['artist']} - {bset['title']}")

        if not image_extracted:
            print(f"  [!] Sin imagen de fondo accesible para: {bset.get('artist')} - {bset.get('title')}")

        # Añadir la ruta del repo al JSON
        bset["cover_image"] = cover_relative_path

    # Guardar el JSON actualizado
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("\n" + "="*50)
    print(f"¡Proceso finalizado!")
    print(f" - Imágenes recortadas guardadas en: {covers_output_dir}")
    print(f" - {json_path} actualizado con la propiedad 'cover_image'.")
    print(f" - Total procesados con éxito: {processed_count}/{len(beatmapsets)}")
    print("="*50)

if __name__ == "__main__":
    main()