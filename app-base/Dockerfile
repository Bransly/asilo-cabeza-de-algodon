FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# El proceso no corre como root dentro del contenedor.
RUN useradd --create-home --uid 1000 asilo && chown -R asilo /app
USER asilo

EXPOSE 8000

# Servidor de produccion (Gunicorn), sin modo debug. --preload crea las tablas
# y carga los datos iniciales una sola vez antes de levantar los trabajadores.
CMD ["gunicorn", "--preload", "--workers", "3", "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", "wsgi:app"]
