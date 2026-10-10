FROM python:3.11-slim

WORKDIR /app

# Se instalan primero las dependencias para aprovechar la cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Luego se copia el codigo del microservicio
COPY app ./app

# El proceso no corre como root dentro del contenedor.
RUN useradd --create-home --uid 1000 asilo && chown -R asilo /app
USER asilo

EXPOSE 8002

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
