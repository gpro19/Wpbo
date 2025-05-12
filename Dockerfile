# Gunakan Python 3.9 sebagai base image
FROM python:3.9-slim

# Set working directory di dalam kontainer
WORKDIR /app

# Salin requirements.txt ke dalam kontainer
COPY requirements.txt .

# Instal semua dependent packages
RUN pip install --no-cache-dir -r requirements.txt

# Salin semua file Python ke dalam kontainer
COPY . .

# Tentukan port yang akan digunakan
EXPOSE 8000

# Perintah untuk menjalankan aplikasi
CMD ["python", "app.py"]
