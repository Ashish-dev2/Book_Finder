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
    if 'isbns_text' in request.form:
        raw_isbns = request.form['isbns_text']
        isbn_list = clean_isbns(raw_isbns)
        if not isbn_list:
            return render_template('index.html', error="No valid ISBNs provided.")
        
        api_response = fetch_books_by_multiple_isbns(isbn_list)
        book_data = process_book_data(api_response, isbn_list)
        return render_template('results.html', search_type='isbn', book_data=book_data)

    elif 'isbns_file' in request.files:
        file = request.files['isbns_file']
        if file.filename == '':
            return render_template('index.html', error="No file selected.")

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

    return redirect(url_for('index'))

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

@app.route("/download-images", methods=["POST"])
def download_images():
    isbns = request.json.get("isbns", [])
    # print(f"Received ISBNs: {isbns}")
    if not isbns:
        return jsonify({"error": "No ISBNs provided"}), 400

    try:
        with tempfile.TemporaryDirectory() as tmpdirname:
            downloaded_images = downloader.download_images_sync(isbns, tmpdirname)

            if not downloaded_images:
                return jsonify({"error": "No images were downloaded."}), 404

            if len(downloaded_images) == 1:
                temp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                shutil.copyfile(downloaded_images[0], temp_img.name)
                temp_img.close()
                return send_file(temp_img.name, mimetype='image/png', as_attachment=True, download_name=os.path.basename(temp_img.name))

            # Multiple images → zip
            zip_path = os.path.join(tmpdirname, "images.zip")
            with zipfile.ZipFile(zip_path, "w") as zipf:
                for img_path in downloaded_images:
                    zipf.write(img_path, arcname=os.path.basename(img_path))

            temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
            shutil.copyfile(zip_path, temp_zip.name)
            temp_zip.close()

            return send_file(temp_zip.name, mimetype='application/zip', as_attachment=True, download_name="book_images.zip")


    except Exception as e:
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

if __name__ == "__main__":
    app.run(debug=True)

if __name__ == '__main__':
    app.run(debug=True)