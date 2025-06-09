import os

import requests
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, send_from_directory

from io import BytesIO
import time
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# ISBNdb API configuration
API_KEY = os.getenv('API_KEY')
HEADERS = {
    "Authorization": API_KEY,
    "Content-Type": "application/json"
}

class ImageDownloader:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.max_workers = 20  # Thread pool size for image downloads
        self.request_delay = 0.2  # 5 requests per second (1/5 = 0.2)
    
    def fetch_book_data(self, isbn_batch):
        """Fetch book data for a batch of ISBNs"""
        url = "https://api2.isbndb.com/books"
        
        payload = f"isbns={','.join(isbn_batch)}"  
        
        try:
            response = self.session.post(url, json=payload)
            # print("response status code:", response.status_code)
            if response.status_code == 200:
                return response.json()
            # print(response.json())
            return None
        except Exception as e:
            print(f"API request failed: {str(e)}")
            return None
    
    def download_image(self, image_data):
        """Download a single image"""
        isbn, image_url, save_dir = image_data
        try:
            response = self.session.get(image_url, stream=True, timeout=30)
            if response.status_code == 200:
                # Determine file extension from URL
                ext = image_url.split('.')[-1].split('?')[0].lower()
                ext = ext if ext in ['jpg', 'jpeg', 'png', 'webp'] else 'jpg'
                
                # Create safe filename
                filename = f"{isbn}.{ext}"
                filepath = os.path.join(save_dir, filename)
                
                # Save image
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(1024):
                        f.write(chunk)
                return filepath
        except Exception as e:
            print(f"Failed to download image for ISBN {isbn}: {e}")
        return None
    
    def download_images(self, isbn_list, save_dir):
        """Download images for a list of ISBNs"""
        os.makedirs(save_dir, exist_ok=True)
        
        # Process in batches of 100 ISBNs
        batch_size = 100
        all_image_urls = []
        
        for i in range(0, len(isbn_list), batch_size):
            batch = isbn_list[i:i+batch_size]
            book_data = self.fetch_book_data(batch)
            print(f"Fetched data for batch {i//batch_size + 1}: {len(batch)} ISBNs")
            # print("Book data:", book_data)  # Debugging output
            time.sleep(self.request_delay)  # Rate limiting
            
            if book_data and 'data' in book_data:
                for book in book_data.get('data', []):
                    isbn = book.get('isbn13') or book.get('isbn10')
                    image_url = book.get('image_original') or book.get('image')
                    if isbn and image_url:
                        all_image_urls.append((isbn, image_url, save_dir))
        
        # Download images in parallel
        downloaded_files = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = executor.map(self.download_image, all_image_urls)
            for result in results:
                if result:
                    downloaded_files.append(result)
        
        return downloaded_files
