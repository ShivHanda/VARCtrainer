import requests
from bs4 import BeautifulSoup
import json
import os
import google.generativeai as genai
from datetime import datetime
import time
import random
import re # Import regex for cleaner JSON extraction

# --- CONFIG ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# --- BACKUP CONTENT ---
BACKUP_TITLE = "The case for idleness"
BACKUP_SOURCE = "[https://aeon.co/essays/the-case-for-idleness](https://aeon.co/essays/the-case-for-idleness)"
BACKUP_TEXT = """
Work is the defining characteristic of our society. We are taught that the devil finds work for idle hands, and that we should always be busy. But is this true? For most of human history, leisure was the goal of life. The Greeks saw work as a means to an end, not an end in itself. Aristotle argued that we work in order to have leisure. Today, however, we have reversed this. We treat leisure as a time to recharge so that we can work more. 

This obsession with productivity is damaging our mental health and our creativity. When we are constantly busy, we do not have time to think. Deep thought requires silence and stillness. It requires the ability to let the mind wander. History's greatest thinkers were often idlers. Bertrand Russell wrote a famous essay in praise of idleness, arguing that if we all worked four hours a day, there would be enough for everyone, and we would all have time to pursue our passions.

The modern economy, however, is built on the consumption of goods and services, which requires constant production. We are trapped in a cycle of earning and spending. To break this, we need to redefine what it means to live a good life. We need to value time over money, and experiences over possessions. We need to learn how to do nothing.

Doing nothing is not easy. We are addicted to stimulation. We reach for our phones the moment we are bored. But boredom is the gateway to creativity. When we are bored, our brains start to make new connections. We start to dream. If we want to solve the complex problems of the 21st century, we need more dreamers and fewer worker bees. We need to reclaim our right to be idle.
"""

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
}

def get_latest_essay_from_rss():
    rss_url = "[https://aeon.co/feed.rss](https://aeon.co/feed.rss)"
    print(f"Checking RSS Feed: {rss_url}")
    try:
        response = requests.get(rss_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')
        for item in items:
            link = item.link.text
            if "/essays/" in link:
                print(f"Found RSS Link: {link}")
                return link
    except Exception as e:
        print(f"RSS Failed: {e}")
    return None

def scrape_essay(url):
    print(f"Scraping: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(response.content, 'html.parser')
        h1 = soup.find('h1')
        title = h1.get_text(strip=True) if h1 else "Aeon Essay"
        
        article = soup.find('div', class_='article__body')
        if not article: article = soup
             
        paragraphs = article.find_all('p')
        clean_text = []
        for p in paragraphs:
            txt = p.get_text(strip=True)
            if len(txt.split()) > 25 and "subscribe" not in txt.lower():
                clean_text.append(txt)
                
        if not clean_text: return None, None
        return title, clean_text
    except Exception as e:
        print(f"Scrape Error: {e}")
        return None, None

# --- ROBUST AI GENERATION ---
def generate_cat_questions(text_chunk, retries=3):
    if not GEMINI_API_KEY: return []
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
    You are a CAT (IIM) Exam Setter. Create 3 Reading Comprehension questions for this text.
    
    TEXT:
    {text_chunk[:3000]}
    
    REQUIREMENTS:
    1. Question 1: Inference based.
    2. Question 2: Main Idea / Structure.
    3. Question 3: Detail based (Direct).
    
    OUTPUT FORMAT:
    Return ONLY a raw JSON array. Do NOT use markdown formatting like ```json. Just the raw array [ ... ].
    [
        {{
            "question": "...",
            "options": ["A", "B", "C", "D"],
            "correct_index": 0,
            "explanation": "..."
        }}
    ]
    """
    
    for attempt in range(retries):
        try:
            response = model.generate_content(prompt)
            raw_text = response.text.strip()
            
            # Cleaner: Remove markdown if AI adds it despite instructions
            cleaned_text = re.sub(r"```json|```", "", raw_text).strip()
            
            questions = json.loads(cleaned_text)
            
            # Validate structure
            if isinstance(questions, list) and len(questions) > 0 and "question" in questions[0]:
                return questions
            else:
                 print(f"Attempt {attempt+1}: Invalid JSON structure generated.")

        except Exception as e:
            print(f"Attempt {attempt+1} Failed: {e}")
            time.sleep(2 ** attempt) # Exponential backoff (wait 1s, 2s, 4s)
            
    print("Error: Failed to generate questions after all retries.")
    # Return a dummy question so the frontend doesn't crash
    return [{
        "question": "AI Generation Failed for this passage. Please skip.",
        "options": ["Skip", "Skip", "Skip", "Skip"],
        "correct_index": 0,
        "explanation": "Check API key or logs."
    }]

def main():
    url = get_latest_essay_from_rss()
    title = None
    paragraphs = None
    
    if url:
        title, paragraphs = scrape_essay(url)
    
    if not paragraphs:
        print("CRITICAL: Scraper failed. Loading BACKUP Content.")
        title = BACKUP_TITLE
        url = BACKUP_SOURCE
        paragraphs = [p.strip() for p in BACKUP_TEXT.split('\n') if p.strip()]

    chunks = []
    current_chunk = []
    w_count = 0
    
    for p in paragraphs:
        w_len = len(p.split())
        current_chunk.append(p)
        w_count += w_len
        if w_count > 500:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
            w_count = 0
    if current_chunk: chunks.append("\n\n".join(current_chunk))
    
    data = {
        "metadata": {"title": title, "source": url, "date_scraped": str(datetime.now().date())},
        "passages": []
    }
    
    print(f"Generating questions for {len(chunks)} passages. This will take time...")
    for i, txt in enumerate(chunks):
        print(f"Processing Passage {i+1}/{len(chunks)}...")
        q = generate_cat_questions(txt)
        data["passages"].append({
            "id": i+1,
            "text": txt,
            "questions": q
        })
        # Important delay between AI calls
        time.sleep(5)

    with open('data.json', 'w') as f:
        json.dump(data, f, indent=4)
    print("Success: data.json updated with text AND questions.")

if __name__ == "__main__":
    main()
