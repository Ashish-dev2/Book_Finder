import os
import requests
from typing import List
import zipfile
from io import BytesIO
import time

# Configuration
MAX_ISBN_PER_REQUEST = 100
REQUESTS_PER_SECOND = 5
IMAGE_TIMEOUT = 30
RETRY_ATTEMPTS = 2
SAVE_DIR = "book_images"

class ImageDownloader:
    def __init__(self):
        self.headers = {"Authorization": os.getenv('API_KEY')}

    def fetch_book_data(self, isbn_batch: List[str]):
        url = "https://api2.isbndb.com/books"
        headers = {
            "Authorization": os.getenv('API_KEY'),
            "Content-Type": "application/json"  
        }
        payload = f"isbns={','.join(isbn_batch)}"  

        for attempt in range(RETRY_ATTEMPTS):
            try:
                response = requests.post(url, data=payload, headers=headers, timeout=IMAGE_TIMEOUT)
                # print("RESPONSE:", response.status_code, response.text)
                if response.status_code == 200:
                    return response.json()
            except Exception as e:
                print(f" Attempt {attempt+1} failed: {e}")
                time.sleep(1)

        return None

    def download_image(self, isbn: str, image_url: str, save_dir: str):
        try:
            response = requests.get(image_url, timeout=IMAGE_TIMEOUT)
            if response.status_code == 200:
                ext = image_url.split('.')[-1].lower()
                ext = ext if ext in ['jpg', 'jpeg', 'png', 'webp'] else 'jpg'
                file_path = os.path.join(save_dir, f"{isbn}.{ext}")

                with open(file_path, 'wb') as f:
                    f.write(response.content)
                return file_path
        except Exception:
            return None

    def process_batch(self, isbn_batch: List[str], save_dir: str):
        book_data = self.fetch_book_data(isbn_batch)
        if not book_data or 'data' not in book_data:
            # print(" No 'data' field in response or empty result") 
            return []

        downloaded_files = []
        for book in book_data.get('data', []):
            isbn = book.get('isbn13') or book.get('isbn10')
            image_url = book.get('image_original') or book.get('image')
            # print(f" ISBN: {isbn}, Image URL: {image_url}")  

            if isbn and image_url:
                path = self.download_image(isbn, image_url, save_dir)
                if path:
                    downloaded_files.append(path)
        return downloaded_files

    def download_images_sync(self, isbn_list: List[str], save_dir: str = SAVE_DIR):
        os.makedirs(save_dir, exist_ok=True)

        batches = [isbn_list[i:i+MAX_ISBN_PER_REQUEST]
                   for i in range(0, len(isbn_list), MAX_ISBN_PER_REQUEST)]

        results = []
        for batch in batches:
            start_time = time.time()
            batch_results = self.process_batch(batch, save_dir)
            results.extend(batch_results)

            elapsed = time.time() - start_time
            if elapsed < 1 / REQUESTS_PER_SECOND:
                time.sleep((1 / REQUESTS_PER_SECOND) - elapsed)

        return results

    def create_zip(self, image_paths: List[str]):
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for img_path in image_paths:
                if os.path.exists(img_path):
                    zipf.write(img_path, os.path.basename(img_path))
        zip_buffer.seek(0)
        return zip_buffer
