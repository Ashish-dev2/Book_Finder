import os
import re
import io
import requests
import pandas as pd
from flask import Flask, request, send_file, jsonify
import asyncio
import tempfile
import shutil
import os
import zipfile
from io import BytesIO
from getImages import ImageDownloader
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for

app = Flask(__name__)
# app.secret_key = os.urandom(24)
downloader = ImageDownloader()


# ISBNdb API configuration
API_KEY = os.getenv('API_KEY')
HEADERS = {
    "Authorization": API_KEY,
    "Content-Type": "application/json"
}

def clean_isbns(raw_isbns):
    """Clean, normalize, and return list of valid ISBNs (10 or 13 digits)"""
    # Normalize all common separators into commas
    for sep in ['\n', ' ', ';', '\t']:
        raw_isbns = raw_isbns.replace(sep, ',')

    isbn_list = []
    for isbn in raw_isbns.split(','):
        cleaned = re.sub(r'[^0-9Xx]', '', isbn.strip())  # remove special chars, keep digits and X
        cleaned = cleaned.upper()

        if cleaned:
            if len(cleaned) == 10 and (cleaned[:9].isdigit() and (cleaned[9].isdigit() or cleaned[9] == 'X')):
                isbn_list.append(cleaned)
            elif len(cleaned) == 13 and cleaned.isdigit():
                isbn_list.append(cleaned)

    return isbn_list


def fetch_books_by_multiple_isbns(isbn_list):
    """Fetch book data for multiple cleaned ISBNs"""
    if not isbn_list:
        print("No valid ISBNs provided.")
        return

    payload = "isbns=" + ",".join(isbn_list)
    url = "https://api2.isbndb.com/books"

    response = requests.post(url, headers=HEADERS, json=payload)
    
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error {response.status_code}: {response.text}")
        return {"error": response.text}


def process_book_data(api_response, original_isbns):
    """Process API response into structured book data"""
    # if "error" in api_response:
    #     return {"error": api_response["error"]}
    
    # Create mapping from ISBN to book data
    book_map = {}
    for book in api_response.get("data", []):
        for isbn in [book.get("isbn10", ""), book.get("isbn13", "")]:
            if isbn:
                book_map[isbn] = book
    
    # Create results array preserving original ISBN order
    results = []
    for isbn in original_isbns:
        if isbn in book_map:
            book = book_map[isbn]
            results.append({
                "input": isbn,
                "title": book.get("title", "N/A"),
                "authors": ", ".join(book.get("authors", ["Unknown"])),
                "publisher": book.get("publisher", "N/A"),
                "isbn13": book.get("isbn13", ""),
                "year": book.get("date_published", "N/A")[:4] if book.get("date_published") else "N/A",
                "pages": book.get("pages", "N/A"),
                "image": book.get("image", ""),
                "synopsis": book.get("synopsis", "No description available"),
                "language": book.get("language", "N/A"),
                "binding": book.get("binding", "N/A"),
                "msrp": f"${book.get('msrp', '0.00')}" if book.get("msrp") else "N/A",
                "found": True
            })
        else:
            results.append({
                "input": isbn,
                "title": "Not Found",
                "authors": "",
                "publisher": "",
                "isbn13": "",
                "year": "",
                "pages": "",
                "image": "",
                "synopsis": "The book could not be found using the provided ISBN",
                "language": "",
                "binding": "",
                "msrp": "",
                "found": False
            })
    
    return {"total": len(original_isbns), "found": len(book_map), "results": results}

@app.route('/')
def index():
    """Render the main page with input options"""
    return render_template('index.html')

@app.route('/search/isbn', methods=['POST'])
def search_isbn():
    file = request.files.get('isbns_file')
    isbns_text = request.form.get('isbns_text')

    if file and file.filename:
        filename = file.filename.lower()
        try:
            if filename.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file)
            elif filename.endswith('.csv'):
                df = pd.read_csv(file)
            elif filename.endswith('.txt'):
                df = pd.DataFrame(file.read().decode('utf-8').splitlines())
            else:
                return render_template('index.html', error="Unsupported file format.")

            raw_isbns = ",".join(df.iloc[:, 0].astype(str).tolist())
            isbn_list = clean_isbns(raw_isbns)

            if not isbn_list:
                return render_template('index.html', error="No valid ISBNs found in file.")

            api_response = fetch_books_by_multiple_isbns(isbn_list)
            book_data = process_book_data(api_response, isbn_list)
            return render_template('results.html', search_type='isbn', book_data=book_data)
        except Exception as e:
            return render_template('index.html', error=f"Error reading file: {str(e)}")

    elif isbns_text:
        isbn_list = clean_isbns(isbns_text)
        if not isbn_list:
            return render_template('index.html', error="No valid ISBNs provided.")

        api_response = fetch_books_by_multiple_isbns(isbn_list)
        book_data = process_book_data(api_response, isbn_list)
        return render_template('results.html', search_type='isbn', book_data=book_data)

    return render_template("index.html", error="Please provide ISBNs via text or file.")


@app.route('/download-results', methods=['POST'])
def download_results():
    """Download search results as Excel file"""
    data = request.json
    if not data or "results" not in data:
        return jsonify({"error": "No data to download"}), 400
    
    # Create DataFrame from results
    df_data = []
    for book in data["results"]:
        df_data.append({
            "Input ISBN": book["input"],
            "Title": book["title"],
            "Authors": book["authors"],
            "Publisher": book["publisher"],
            "ISBN13": book["isbn13"],
            "Year": book["year"],
            "Edition": book.get("edition", "N/A"),
            "Pages": book["pages"],
            "Language": book["language"],
            "Binding": book["binding"],
            "Price": book["msrp"],
            "Synopsis": book["synopsis"],
            "Image URL": book["image"],
            "Subjects": ", ".join(book.get("subjects", [])),
            "isbn10": book.get("isbn10") or book.get("isbn") or "N/A",
            "Title_long": book.get("title_long", "N/A"),
            "Dimensions": book.get("dimensions", "N/A")
        })
    
    df = pd.DataFrame(df_data)
    
    # Create Excel file in memory
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Book Results')
    
    output.seek(0)
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name='book_search_results.xlsx'
    )

# Create image downloader instance
image_downloader = ImageDownloader()

@app.route('/download-images', methods=['POST'])
def download_images_route():
    """Endpoint to download book cover images"""
    try:
        isbns = []

        # 1. Check textarea input (image_isbns_text)
        text_input = request.form.get('image_isbns_text', '')
        if text_input:
            # Split by lines, commas, semicolons and flatten
            raw_isbns = re.split(r'[\n,;]+', text_input)
            isbns.extend(raw_isbns)
        
        # 2. Check file upload (image_isbns_file)
        uploaded_file = request.files.get('image_isbns_file')
        if uploaded_file and uploaded_file.filename != '':
            filename = uploaded_file.filename.lower()
            if filename.endswith(('.xlsx', '.xls')):
                
                df = pd.read_excel(uploaded_file)
                # Flatten all values into list of strings (assume first column contains ISBNs)
                for col in df.columns:
                    isbns.extend(df[col].astype(str).tolist())
            elif filename.endswith(('.csv', '.txt')):
                # Read CSV or TXT as text and split by lines, commas, semicolons
                content = uploaded_file.read().decode('utf-8')
                file_isbns = re.split(r'[\n,;]+', content)
                isbns.extend(file_isbns)
            else:
                return jsonify({"error": "Unsupported file type"}), 400
        
        # Clean and validate ISBNs
        cleaned_isbns = []
        for isbn in isbns:
            cleaned = re.sub(r'[^0-9X]', '', str(isbn).upper().strip())
            if cleaned and (len(cleaned) in [10, 13]):
                cleaned_isbns.append(cleaned)
        
        if not cleaned_isbns:
            return jsonify({"error": "No valid ISBNs provided"}), 400
        
        
        # Create temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            # Download images
            downloaded_files = image_downloader.download_images(cleaned_isbns, temp_dir)
            
            if not downloaded_files:
                return jsonify({"error": "No images found"}), 404
            
            # For single ISBN, return the image directly
            if len(cleaned_isbns) == 1:
                if downloaded_files:
                    return send_file(
                        downloaded_files[0],
                        as_attachment=True,
                        download_name=os.path.basename(downloaded_files[0])
                    )
                return jsonify({"error": "Image not found"}), 404
            
            # For multiple ISBNs, create zip
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in downloaded_files:
                    zipf.write(file_path, os.path.basename(file_path))
            zip_buffer.seek(0)
            
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name='book_images.zip'
            )
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run( host='0.0.0.0',port=5001, debug=True)