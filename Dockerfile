# পাইথন ও লিনাক্স এনভায়রনমেন্ট সেট করা
FROM python:3.10-slim

# সবচেয়ে গুরুত্বপূর্ণ ধাপ: FFmpeg ইন্সটল করা
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# কাজের ফোল্ডার ঠিক করা
WORKDIR /app

# ফাইল কপি এবং লাইব্রেরি ইন্সটল
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# সার্ভার রান করা (Gunicorn দিয়ে)
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "app:app"]