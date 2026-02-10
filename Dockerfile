# পাইথন ভার্সন সেটআপ
FROM python:3.10-slim

# FFmpeg ইন্সটল করা (অডিও কনভার্ট করার জন্য বাধ্যতামূলক)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# ওয়ার্কিং ডিরেক্টরি
WORKDIR /app

# রিকোয়ারমেন্টস কপি এবং ইন্সটল
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# বাকি সব ফাইল কপি
COPY . .

# Render এর জন্য পোর্ট ১০০০০ খুলে দেওয়া
EXPOSE 10000

# Gunicorn রান কমান্ড (Port 10000 এ বাইন্ড করা হলো)
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "--timeout", "120", "app:app"]
