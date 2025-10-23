#!/bin/bash

# Set up Python environment
echo "Setting up Python environment..."
python -m venv venv || { echo "Failed to create virtual environment"; exit 1; }
source venv/bin/activate || { echo "Failed to activate virtual environment"; exit 1; }

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt || { echo "Failed to install dependencies"; exit 1; }

# Run the FastAPI application
echo "Starting the server..."
python -m uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000