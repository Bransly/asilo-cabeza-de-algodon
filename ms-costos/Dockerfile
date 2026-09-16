# Imagen ligera oficial de Python
FROM python:3.11-slim

WORKDIR /app

# Se instalan primero las dependencias para aprovechar la cache de Docker
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Luego se copia el codigo del microservicio
COPY app ./app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
