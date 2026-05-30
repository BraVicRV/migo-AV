"""
🎙️ PRUEBA DE PIPER TTS - Voz en español
"""

import subprocess
import tempfile
import os

# CONFIGURACIÓN - Rutas correctas
PIPER_PATH = r"D:\piper_windows_amd64\piper\piper.exe"
MODEL_PATH = r"D:\piper_windows_amd64\piper\es_ES-carlfm-x_low.onnx"  # ← SIN .json

# Textos de prueba en español
TEXTOS_PRUEBA = [
    "Hola, soy AURA, tu amiga virtual. ¿En qué puedo ayudarte hoy?",
    "Me alegra mucho escucharte. Cuéntame cómo te sientes.",
    "Recuerda que siempre estoy aquí para ti.",
    "¿Quieres que te ponga música para relajarte?",
    "Es hora de descansar. Has trabajado mucho hoy."
]

def probar_voz(texto, numero):
    """Genera audio con Piper TTS"""
    print(f"\n🎵 Probando voz #{numero}...")
    print(f"   Texto: {texto[:50]}...")
    
    try:
        # Crear archivo temporal para el audio
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as f:
            wav_path = f.name
        
        # Generar audio con Piper
        process = subprocess.Popen(
            [PIPER_PATH, "--model", MODEL_PATH, "--output_file", wav_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        stdout, stderr = process.communicate(input=texto)
        
        if process.returncode == 0:
            print(f"   ✅ Audio generado: {wav_path}")
            
            # Reproducir el audio (Windows)
            os.system(f'start "" "{wav_path}"')
            
            import time
            time.sleep(3)
            
            return True
        else:
            print(f"   ❌ Error de Piper: {stderr}")
            return False
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return False

def main():
    """Función principal"""
    print("=" * 60)
    print("🎙️  PRUEBA DE PIPER TTS - Voz en español")
    print("=" * 60)
    print(f"\n📁 Piper: {PIPER_PATH}")
    print(f"📁 Modelo: {MODEL_PATH}")
    
    # Verificar archivos
    if not os.path.exists(PIPER_PATH):
        print(f"\n❌ ERROR: No se encontró Piper en: {PIPER_PATH}")
        return
        
    if not os.path.exists(MODEL_PATH):
        print(f"\n❌ ERROR: No se encontró el modelo .onnx en: {MODEL_PATH}")
        print("   Asegúrate de descargar el archivo .onnx (no solo el .json)")
        return
    
    # Verificar que existe el .json también (Piper lo necesita)
    json_path = MODEL_PATH + ".json"
    if not os.path.exists(json_path):
        print(f"\n⚠️ ADVERTENCIA: No se encontró {json_path}")
        print("   Piper necesita ambos archivos: .onnx y .json")
    
    print("\n✅ Archivos encontrados. Iniciando pruebas...\n")
    
    # Probar cada texto
    for i, texto in enumerate(TEXTOS_PRUEBA, 1):
        probar_voz(texto, i)
        input("\n   Presiona ENTER para continuar...")
    
    print("\n" + "=" * 60)
    print("✅ Pruebas completadas")
    print("=" * 60)

if __name__ == "__main__":
    main()