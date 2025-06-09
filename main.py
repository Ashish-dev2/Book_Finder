import requests

def process_csv_file(file_path):
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            for line in lines:
                isbns = line.strip()
                
            return isbns
        
    except FileNotFoundError:
        print(f"File {file_path} not found.")
    except Exception as e:
        print(f"An error occurred: {e}")

API_KEY = '61725_4fdb26f4af6dd6188dbc9f780c81ca10'
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": API_KEY
}

def fetch_book_by_isbn(isbn):
    
    isbn = isbn.strip()
    if not isbn:
        print("ISBN cannot be empty.")
        return

    url = f"https://api2.isbndb.com/book/{isbn}"

    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        data = response.json()
        print(data['book']) 
    else:
        print(f"Error {response.status_code}: {response.text}")

def fetch_book_by_multiple_isbns(raw_isbns):

    raw_isbns = raw_isbns.strip()
    
    for sep in ['\n', ' ', ';']:
        raw_isbns = raw_isbns.replace(sep, ',')
    isbn_list = [isbn.strip() for isbn in raw_isbns.split(',') if isbn.strip()]
    
    if not isbn_list:
        print("No valid ISBNs provided.")
        return
    
    # Create payload string as required by ISBNdb
    payload = "isbns=" + ",".join(isbn_list)
    
    url = "https://api2.isbndb.com/books"
    
    response = requests.post(url, headers=HEADERS, json=payload)
    
    if response.status_code == 200:
        data = response.json()
        print(data)
    else:
        print(f"Error {response.status_code}: {response.text}")

def fetch_book_by_title(title):
    title = title.strip()
    if not title:
        print("ISBN cannot be empty.")
        return

    url = f"https://api2.isbndb.com/books/{title}?page=1&pageSize=20&shouldMatchAll=1"

    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        data = response.json()
        print(data['books']) 
    else:
        print(f"Error {response.status_code}: {response.text}")

def fetch_book_by_author(author):
    author = author.strip()
    if not author:
        print("Author cannot be empty.")
        return

    url = f"https://api2.isbndb.com/books?author={author}&page=1&pageSize=20"

    response = requests.get(url, headers=HEADERS)
    
    if response.status_code == 200:
        data = response.json()
        print(data['books']) 
    else:
        print(f"Error {response.status_code}: {response.text}")



def search_books():
    choice = input("Search by (1) Title or(2) ISBNs? : ")
    if choice == '1' or choice.lower() == 'title' or choice.lower() == "Title":
        title = input("Enter book title: ")
        fetch_book_by_title(title)
    elif choice == '2' or choice.lower() == 'isbns' or choice.lower() == "ISBNs":
        isbns = input("Enter ISBNs: ")
        fetch_book_by_multiple_isbns(isbns)

if __name__ == "__main__":
    search_books()