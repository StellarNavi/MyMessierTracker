# dockerfile testing - havingto run seperately atm (logging in instructions)

# FROM python:3.1
# WORKDIR /app
# COPY requirements.txt /app/
# RUN pip install -r requirements.txt
# COPY . /app
# RUN mkdir -p /app/static/uploads
# # Run the Flask app via gunicorn - pending


# testing Dockerfile for render
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
CMD gunicorn -b 0.0.0.0:$PORT app:app
