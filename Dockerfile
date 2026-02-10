# ১. পাইথন ও লিনাক্স এনভায়রনমেন্ট সেট করা
FROM python:3.10-slim

# ২. সবচেয়ে গুরুত্বপূর্ণ ধাপ: FFmpeg ইন্সটল করা (অডিও কনভার্ট করার জন্য বাধ্যতামূলক)
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# ৩. কাজের ফোল্ডার ঠিক করা
WORKDIR /app

# ৪. রিকোয়ারমেন্টস কপি এবং ইন্সটল
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ৫. বাকি সব ফাইল কপি
COPY . .

# ৬. Render এর ডিফল্ট পোর্ট (10000) খুলে দেওয়া
EXPOSE 10000

# ৭. সার্ভার রান করা (Gunicorn দিয়ে)
# -w 1: একটা ওয়ার্কার (ফ্রি টিয়ারের জন্য ভালো)
# --timeout 120: অডিও জেনারেট হতে দেরি হলে যাতে বন্ধ না হয় (২ মিনিট সময় পাবে)
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:10000", "--timeout", "120", "app:app"]