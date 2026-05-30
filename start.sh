#!/bin/bash

echo "🎭 Iniciando Amigo Virtual AURA..."
echo ""

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 no encontrado. Instala Python 3.8+"
    exit 1
fi

# Verificar dependencias
echo "📦 Verificando dependencias..."
pip3 install -q -r requirements.txt

# Verificar Ollama
if ! command -v ollama &> /dev/null; then
    echo "⚠️ Ollama no detectado. Funcionará en modo básico."
    echo "   Descarga Ollama desde: https://ollama.com"
    echo ""
fi

# Iniciar
echo "🚀 Iniciando..."
python3 main.py
