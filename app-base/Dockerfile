FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --create-home --uid 1000 asilo && chown -R asilo /app
USER asilo

EXPOSE 8000

# --preload: la carga inicial corre una sola vez (ver wsgi.py).
CMD ["gunicorn", "--preload", "--workers", "3", "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", "wsgi:app"]
