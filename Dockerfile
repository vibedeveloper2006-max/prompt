FROM python:3.11-slim

WORKDIR /app

# Install dependencies directly
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Fix permissions
RUN chmod -R 755 /app

# Run server. Use PORT injected by Cloud Run.
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
