#!/bin/bash

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "Creating virtual environment..."
    python -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
fi

# Run the FastAPI application
uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000