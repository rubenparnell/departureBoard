import requests
from bs4 import BeautifulSoup
import json

def get_jamjar_films():
    """
    Scrapes the 'Now Playing' page of Jam Jar Cinema to extract movie details
    from elements with the class 'movie-container'.
    """
    url = "https://www.jamjarcinema.com/now-playing"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }

    try:
        # Send a GET request to the URL
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)

        # Parse the HTML content of the page
        soup = BeautifulSoup(response.text, 'html.parser')

        movies = soup.find('div', id='q-app').find_all('a')

        movie_data = {}

        i = 0
        while i < len(movies)-1:
            url1 = movies[i].get('href')
            url2 = movies[i+1].get('href')

            if "/movie/" in url1 and "/checkout/" in url2:
                title = movies[i].get_text(strip=True)
                movie_data[title] = []

                while "/checkout" in url2:
                    time = movies[i+1].get_text(strip=True)
                    if "PM" in time:
                        time = time.replace("PM", "").split(":")
                        time = f"{int(time[0])+12}:{time[1]}"
                    elif "AM" in time:
                        time = time.replace("AM", "").split(":")
                        time = f"{int(time[0]):02}:{time[1]}"
                    movie_data[title].append(time)
                    i += 1
                    url2 = movies[i+1].get('href')

            else:
                i += 1

        return movie_data

    except requests.exceptions.RequestException as e:
        print(f"Error fetching the URL: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

if __name__ == "__main__":
    print("Starting Jam Jar Cinema scraper...")
    films = get_jamjar_films()

    if films:
        print(f"\nSuccessfully extracted {len(films)} movies:")
        # Pretty print the extracted data
        print(json.dumps(films, indent=4))
    else:
        print("\nFailed to extract movie data.")

