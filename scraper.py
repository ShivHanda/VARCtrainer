import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai
from datetime import datetime
import time
import re

# --- CONFIG ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("CRITICAL ERROR: GEMINI_API_KEY not found in Secrets.")
    exit(1)

genai.configure(api_key=GEMINI_API_KEY)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def get_latest_essay_from_rss():
    """Fetches the latest essay link from Aeon's RSS Feed."""
    rss_url = "https://aeon.co/feed.rss"
    print(f"Checking RSS Feed: {rss_url}")
    try:
        response = requests.get(rss_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, 'xml')
        
        items = soup.find_all('item')
        for item in items:
            link = item.link.text
            if "/essays/" in link:
                print(f"Found Essay: {item.title.text}")
                return link, item.title.text
    except Exception as e:
        print(f"RSS Failed: {e}")
    return None, None

def scrape_text_from_url(url):
    print(f"Scraping Text: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Smart Text Extraction
        article_body = soup.find('div', class_='article__body')
        if not article_body: article_body = soup
            
        paragraphs = [p.get_text(strip=True) for p in article_body.find_all('p')]
        
        # Filter garbage
        clean_text = [p for p in paragraphs if len(p.split()) > 25 and "subscribe" not in p.lower()]
        
        if not clean_text: return None
        return clean_text
    except Exception as e:
        print(f"Scrape Error: {e}")
        return None

def clean_ai_json(raw_text):
    """
    Cleans the AI output to ensure it is valid JSON.
    Removes markdown code blocks (```json ... ```).
    """
    # Remove markdown backticks
    text = re.sub(r'```json', '', raw_text)
    text = re.sub(r'```', '', text)
    text = text.strip()
    return text

def generate_questions_real(text_chunk):
    """Generates REAL questions using Gemini."""
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    You are a CAT (Common Admission Test) Exam Setter.
    Create 3 high-quality Reading Comprehension questions based on the text below.
    
    TEXT:
    {text_chunk[:3000]}
    
    INSTRUCTIONS:
    1. Output MUST be a valid JSON Array.
    2. No Introduction. No Conclusion. JUST THE JSON.
    3. Format:
    [
        {{
            "question": "Question text here?",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_index": 0,
            "explanation": "Explanation here."
        }}
    ]
    """
    
    try:
        response = model.generate_content(prompt)
        cleaned_json = clean_ai_json(response.text)
        
        # Validate JSON
        data = json.loads(cleaned_json)
        if isinstance(data, list) and len(data) > 0:
            return data
        else:
            print("AI returned valid JSON but empty list.")
            return []
            
    except json.JSONDecodeError:
        print(f"JSON Parse Error. Raw AI Output: {response.text[:100]}...")
        return []
    except Exception as e:
        print(f"AI Gen Error: {e}")
        return []

def main():
    # 1. Get URL
    url, title = get_latest_essay_from_rss()
    if not url:
        print("Could not find any essay in RSS.")
        return

    # 2. Get Text
    paragraphs = scrape_text_from_url(url)
    if not paragraphs:
        print("Could not scrape text.")
        return

    # 3. Chunk Text
    chunks = []
    current = []
    w_count = 0
    for p in paragraphs:
        current.append(p)
        w_count += len(p.split())
        if w_count > 600:
            chunks.append("\n\n".join(current))
            current = []
            w_count = 0
    if current: chunks.append("\n\n".join(current))

    # 4. Generate AI Questions (THE REAL DEAL)
    final_passages = []
    print(f"Generating questions for {len(chunks)} passages...")
    
    for i, chunk in enumerate(chunks):
        print(f"Processing Chunk {i+1}/{len(chunks)}...")
        questions = generate_questions_real(chunk)
        
        # Retry logic: If empty, try one more time
        if not questions:
            print("Retrying AI generation...")
            time.sleep(2)
            questions = generate_questions_real(chunk)
            
        final_passages.append({
            "id": i+1,
            "text": chunk,
            "questions": questions # Should be real list now
        })
        
        # Rate Limit Protection
        time.sleep(4) 

    # 5. Save Data
    data = {
        "metadata": {
            "title": title,
            "source": url,
            "date_scraped": str(datetime.now().date())
        },
        "passages": final_passages
    }
    
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)
    print("Success: Real data.json generated.")

if __name__ == "__main__":
    main()
