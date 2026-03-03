import requests
from bs4 import BeautifulSoup

def test_scrape():
    url = "https://xmplaylist.com/station"
    response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(response.text, 'html.parser')
    links = soup.find_all('a', href=lambda h: h and '/station/' in h)
    
    for link in links[:5]:
        print("---")
        print("Text:", link.text)
        print("HTML:", link.decode_contents())

    print("\n\nLooking for 330:")
    for link in links:
        if '330' in link.text or '331' in link.text:
            print("Text:", link.text)
            print("HTML:", link.decode_contents())

if __name__ == "__main__":
    test_scrape()
