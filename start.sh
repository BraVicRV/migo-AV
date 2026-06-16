#!/bin/bash
# start.sh - Script de inicio para AURA

echo "=================================="
echo "  AURA - Amigo Virtual con IA"
echo "=================================="

# Verificar Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 no encontrado"
    exit 1
fi

# Verificar .env
if [ ! -f .env ]; then
    echo "Creando .env desde template..."
    cp .env.example .env
    echo "Por favor edita .env con tus API keys"
fi

# Instalar dependencias
echo "Instalando dependencias..."
pip install -r requirements.txt

# Iniciar servidor
echo "Iniciando AURA..."
python3 -m uvicorn web_app:app --host 0.0.0.0 --port 8000 --reload