# my_messier_tracker/Dockerfile
FROM python:3.11-slim

# (Optional but small) OS deps used by some wheels and for debugging
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (better layer caching)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy the app
COPY . /app

# Make sure uploads directory exists
RUN mkdir -p /app/static/uploads

EXPOSE 5000
# Run the Flask app via gunicorn; 'app:app' matches app.py's Flask instance
CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5000", "app:app"]
