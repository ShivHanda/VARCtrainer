import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai
from datetime import datetime
import time
import random

# --- CONFIG ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# We need headers to look like a real browser, otherwise Aeon blocks us
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Referer': 'https://aeon.co/'
}

def get_live_essay_url():
    """
    Visits the main Aeon Essays page and finds the first valid essay link.
    """
    feed_url = "https://aeon.co/essays"
    print(f"Searching for latest essay at: {feed_url}")
    
    try:
        response = requests.get(feed_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Find all links that point to /essays/...
        links = soup.find_all('a', href=True)
        
        valid_urls = []
        for link in links:
            href = link['href']
            # We want links that are deep (e.g. /essays/slug) not just /essays or /essays/popular
            if '/essays/' in href and href.count('/') > 1:
                full_url = f"https://aeon.co{href}"
                if full_url not in valid_urls:
                    valid_urls.append(full_url)
        
        if valid_urls:
            # Pick the first one (usually the latest)
            print(f"Found live URL: {valid_urls[0]}")
            return valid_urls[0]
            
    except Exception as e:
        print(f"Error finding dynamic URL: {e}")
    
    # FALLBACK: If dynamic search fails, use the working URL you provided
    print("Dynamic search failed. Using fallback URL.")
    return "https://aeon.co/essays/how-a-playful-literary-hoax-illuminates-classical-queerness"

def scrape_essay(url):
    print(f"Scraping content from: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"Failed to load page. Status: {response.status_code}")
            return None, None
            
        soup = BeautifulSoup(response.content, 'html.parser')

        # 1. Get Title
        h1 = soup.find('h1')
        title = h1.get_text(strip=True) if h1 else "Aeon Essay"

        # 2. Get Text - Try multiple selectors to be safe
        # Aeon usually puts text in 'article__body' or just standard p tags in the main container
        paragraphs = []
        
        # Strategy A: Look for specific class
        body_div = soup.find('div', class_='article__body')
        if body_div:
            paragraphs = body_div.find_all('p')
        else:
            # Strategy B: Grab all paragraphs and filter strictly
            paragraphs = soup.find_all('p')

        clean_text = []
        for p in paragraphs:
            text = p.get_text(strip=True)
            # Filter garbage (menus, footers, newsletters)
            if len(text.split()) > 25 and "subscribe" not in text.lower():
                clean_text.append(text)
                
        if not clean_text:
            print("Warning: No text paragraphs found.")
            return None, None
            
        return title, clean_text

    except Exception as e:
        print(f"Scraping Error: {e}")
        return None, None

def chunk_text(paragraphs, chunk_size=550):
    chunks = []
    current_chunk = []
    word_count = 0
    
    for p in paragraphs:
        w_len = len(p.split())
        current_chunk.append(p)
        word_count += w_len
        
        if word_count >= chunk_size:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
            word_count = 0
            
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))
    return chunks

def generate_cat_questions(text_chunk):
    if not GEMINI_API_KEY:
        return []
    
    # Simplified logic to prevent errors
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    Create 3 Reading Comprehension questions (CAT Exam style) for this text.
    Text: {text_chunk[:2000]}
    
    Output strictly as this JSON format:
    [
        {{
            "question": "...",
            "options": ["A", "B", "C", "D"],
            "correct_index": 0,
            "explanation": "..."
        }}
    ]
    """
    try:
        response = model.generate_content(prompt)
        clean = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean)
    except:
        return []

def main():
    # 1. Find a working URL
    target_url = get_live_essay_url()
    
    # 2. Scrape it
    title, paragraphs = scrape_essay(target_url)
    
    if not paragraphs:
        print("CRITICAL: Scraper returned no content. Exiting.")
        # Create a dummy error file so we know it failed
        with open('data.json', 'w') as f:
            json.dump({"metadata": {"title": "Error - Scraping Failed"}, "passages": []}, f)
        return

    # 3. Process
    passages = chunk_text(paragraphs)
    data = {
        "metadata": {
            "title": title,
            "source": target_url,
            "date_scraped": str(datetime.now().date())
        },
        "passages": []
    }
    
    print(f"Generating AI questions for {len(passages)} passages...")
    for i, p_text in enumerate(passages):
        questions = generate_cat_questions(p_text)
        data["passages"].append({
            "id": i + 1,
            "text": p_text,
            "questions": questions
        })
        time.sleep(2)

    # 4. Save
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)
    print("Success: data.json updated with REAL content.")

if __name__ == "__main__":
    main()
