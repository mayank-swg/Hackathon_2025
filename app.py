import requests
import logging
import os
from flask import Flask, request, send_file, jsonify
from pytube import Search
from deep_translator import GoogleTranslator
from gtts import gTTS
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)

# Replace with your actual API keys
SCRAPINGBEE_API = "https://app.scrapingbee.com/api/v1/"
SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY")
BLOCK_ADS = True
PRODUCT_ASIN_AI_QUERY = "ASIN of first result"
PRODUCT_DETAILS_AI_QUERY = "Product information, Important information, Product description, About this item, Reviews"
PRODUCT_REVIEWS_AI_QUERY = "Reviews"
PEOPLE_ENJOY_THIS_FOR = "people enjoy this for?"
CONCERNS_EXIST_FOR = "concerns exist for?"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SHOW_DATA_PROMPT = "Give me this answer in tags which are short, crisp, easy to read quickly."
ROLE_AND_GUIDELINES_PROMPT = "Role:\r\n\r\nYou are an expert data analyst specializing in retail insights. Your task is to analyze customer reviews, product descriptions, and ratings from retail website data to provide concise, accurate, and engaging responses to customer inquiries.\r\n\r\nGuidelines:\r\n\r\n1. Short & Precise Responses: Keep answers concise, avoiding unnecessary details.\r\n2. Data-Driven Analysis: Base responses on product reviews, ratings, and descriptions while identifying key trends.\r\n3. Avoid Personal Data: Do not reveal personal details (names, emails, phone numbers) found in reviews.\r\n4. Sales Optimization: If a customer shows purchase intent, subtly highlight product benefits to encourage a sale.\r\n5. Clarification When Needed: If a question is unclear, ask relevant follow-up questions before responding.\r\n6. Filter Out Gibberish: Ignore or politely redirect irrelevant, nonsensical, or off-topic queries.\r\n7. Maintain Natural Flow: Keep responses conversational and engaging, aligned with the customer\'s tone.\r\n8. Trend Detection: Identify recurring themes in reviews (e.g., common praises or complaints) to enhance recommendations.\r\n9. Sentiment Awareness: If a product has mixed reviews, provide a balanced response highlighting both pros and cons.\r\n10. Comparative Insights: If applicable, suggest similar or better-rated alternatives to guide customers in decision-making.\r\n11. Urgency & Scarcity: Mention limited stock or popular trends when relevant to create urgency.\r\n12. Concise Bullet Points: Don\'t provide more than 10 bullet points. \r\n\r\nBelow is the data for product name and corresponding details(reviews) followed by the user question. Try to answer the user question-"
MAX_YOUTUBE_VIDEOS = 3
YOUTUBE_SEARCH_PROMPT = "best review videos of"


import time
import pandas as pd
import chromedriver_autoinstaller
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

def scrap_amazon_product(asin):
    # Install the correct ChromeDriver version
    chromedriver_autoinstaller.install()

    # Setup Selenium WebDriver
    options = Options()
    options.add_argument("--headless")  # Run in headless mode
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # Amazon product URL (replace with actual product URL)
    product_url = f"https://www.amazon.in/dp/{asin}"
    print("product_url", product_url)
    driver.get(product_url)
    time.sleep(3)  # Wait for the page to load

    # Extract page source and parse with BeautifulSoup
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Extract product details
    title = soup.find("span", id="productTitle")
    title = title.get_text(strip=True) if title else "N/A"

    price = soup.find("span", class_="a-price-whole")
    price = price.get_text(strip=True) if price else "N/A"

    rating = soup.find("span", class_="a-icon-alt")
    rating = rating.get_text(strip=True) if rating else "N/A"

    availability = soup.find("div", id="availability")
    availability = availability.get_text(strip=True) if availability else "N/A"

    # Extract product description
    desc_section = soup.find("div", id="feature-bullets")
    description = [bullet.get_text(strip=True) for bullet in desc_section.find_all("span", class_="a-list-item")] if desc_section else ["N/A"]

    # Click on "See all reviews" link
    try:
        see_all_reviews_link = driver.find_element(By.PARTIAL_LINK_TEXT, "See all reviews")
        see_all_reviews_link.click()
        time.sleep(3)  # Allow reviews page to load
    except Exception as e:
        print("No 'See all reviews' link found. Scraping reviews from the main page.")

    reviews = []
    max_pages = 5  # Set the number of pages to scrape
    current_page = 1

    print("title", title)
    print("price", price)
    print("rating", rating)
    print("availability", availability)
    print("description", description)
    while current_page <= max_pages:
        print(f"Scraping page {current_page}...")

        # Scroll down to load reviews
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)  # Wait for reviews to load

        # Extract reviews
        review_elements = driver.find_elements(By.CSS_SELECTOR, "span[data-hook='review-body']")
        image_elements = driver.find_elements(By.CSS_SELECTOR, "div.review-image-tile-section img")

        for i in range(len(review_elements)):
            review_text = review_elements[i].text.strip()
            review_image = image_elements[i].get_attribute("src") if i < len(image_elements) else "No Image"

            reviews.append({
                "Review": review_text,
                "Review Image": review_image
            })

        # Try to find and click the "Next page" link
        try:
            next_page_link = driver.find_element(By.PARTIAL_LINK_TEXT, "Next")
            next_page_link.click()
            time.sleep(3)  # Allow next page to load
            current_page += 1
        except Exception as e:
            print("No more review pages found.")
            break
    
    print("reviews", reviews)
    # Close the browser
    driver.quit()

    # Store data in a DataFrame
    df = pd.DataFrame([{
        "Title": title,
        "Price": price,
        "Rating": rating,
        "Availability": availability,
        "Description": description,
        "Reviews": reviews
    }])

    # Print DataFrame
    print(df)

# Get ASIN of the 1st Amazon Product
def search_amazon_product_ASIN(product_name):
    url = f'{SCRAPINGBEE_API}?url=https://www.amazon.in/s?k={product_name.replace(" ", "+")}&ai_query={PRODUCT_ASIN_AI_QUERY.replace(" ", "+")}&api_key={SCRAPINGBEE_API_KEY}&block_ads={BLOCK_ADS}'
    response = requests.get(url, verify=False)
    if response.status_code == 200:
        print("asin_url", url)
        return response.text
    return None

# Get Product Details from Amazon
def search_amazon_product_details(ASIN, details_prompt):
    url = f'{SCRAPINGBEE_API}?url=https://www.amazon.in/dp/{ASIN}&ai_query={details_prompt.replace(" ", "+")}&api_key={SCRAPINGBEE_API_KEY}&block_ads={BLOCK_ADS}'
    response = requests.get(url, verify=False)
    if response.status_code == 200:
        print("product_url", url)
        return response.json()
    return None

# Call GPT to get the response for the given prompt
def call_gpt_api(product_name, product_details, prompt):
    gpt_prompt = f"{ROLE_AND_GUIDELINES_PROMPT}\nProduct: {product_name}\nProduct Details:\n{product_details}\nQuestion: {prompt}"
    try:
        print("calling gpt api")
        url = "https://api.openai.com/v1/chat/completions"
        data = {
            "model": "gpt-4o-mini",
            "store": True,
            "messages": [
                {
                    "role": "user",
                    "content": gpt_prompt
                }
            ]
        }
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
            "Content-Type": "application/json"
        }
        # print("gpt_prompt", gpt_prompt)
        response = requests.post(url, headers=headers, json=data)

        print("final_response", response.text)

        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(e)
        return "Sorry, I'm unable to help!"

# Get Top 3 Youtube Videos Links
def search_youtube_videos(search_query):
    try:
        # Perform the search
        search_results = Search(f"{YOUTUBE_SEARCH_PROMPT} {search_query}")
        
        # Extract video links
        video_links = []
        for video in search_results.results[:MAX_YOUTUBE_VIDEOS]:
            video_links.append(f"https://www.youtube.com/watch?v={video.video_id}")
        
        return video_links
    
    except Exception as e:
        print(f"An error occurred while getting videos: {e}")
        return []

# Translate the given text
def translate_text(text, target_language="en"):
    try:
        return GoogleTranslator(source="auto", target=target_language).translate(text)
    except Exception as e:
        print(f"Translation error: {e}")
        return None

# API endpoint
@app.route("/analyze-product", methods=["POST"])
def analyze_product():
    data = request.json
    product_name = data.get("product_name")
    prompt = data.get("prompt")

    if not product_name or not prompt:
        return jsonify({"error": "product_name and prompt are required"}), 400

    # Step 1: Search for the product on Amazon
    product_ASIN = search_amazon_product_ASIN(product_name)
    if not product_ASIN:
        return jsonify({"error": "Product not found"}), 404
    
    print("product_ASIN", product_ASIN)

    # Step 2: Get reviews for the product
    product_details = search_amazon_product_details(product_ASIN, PRODUCT_DETAILS_AI_QUERY)
    if not product_details:
        return jsonify({"error": "No product details found"}), 404
    
    print("amazon_product_details", product_details)

    # Step 3: Call GPT API
    gpt_response = call_gpt_api(product_name, product_details, prompt)

    return jsonify({"response": gpt_response})


# API endpoint
@app.route("/product-details", methods=["POST"])
def product_details():
    data = request.json
    product_name = data.get("product_name")

    if not product_name:
        return jsonify({"error": "product_name is required"}), 400

    # Step 1: Search for the product on Amazon
    product_ASIN = search_amazon_product_ASIN(product_name)
    if not product_ASIN:
        logging.error("error: product not found")
    
    print("product_ASIN", product_ASIN)

    # Step 2: Get Details for the product
    product_details = search_amazon_product_details(product_ASIN, PRODUCT_DETAILS_AI_QUERY)
    if not product_details:
        logging.error("error: No product details found")
    videos_links = search_youtube_videos(product_name)

    print("amazon_product_details", product_details)
    return jsonify({
        "product_details": product_details,
        "videos_links": videos_links
    })

# API endpoint
@app.route("/product-reviews", methods=["POST"])
def product_reviews():
    data = request.json
    product_name = data.get("product_name")

    if not product_name:
        return jsonify({"error": "product_name is required"}), 400

    # Step 1: Search for the product on Amazon
    product_ASIN = search_amazon_product_ASIN(product_name)
    if not product_ASIN:
        logging.error("error: product not found")
    
    print("product_ASIN", product_ASIN)

    # Step 2: Get reviews for the product
    product_reviews = search_amazon_product_details(product_ASIN, PRODUCT_REVIEWS_AI_QUERY)
    if not product_reviews:
        logging.error("error: No product reviews found")
    
    print("amazon_product_reviews", product_reviews)
    return jsonify({"product_reviews": product_reviews})

# API endpoint
@app.route("/pdp-data", methods=["POST"])
def pdp_data():
    data = request.json
    product_name = data.get("product_name")

    if not product_name:
        return jsonify({"error": "product_name is required"}), 400

    # Step 1: Search for the product on Amazon
    product_ASIN = search_amazon_product_ASIN(product_name)
    if not product_ASIN:
        logging.error("error: product not found")
    
    print("product_ASIN", product_ASIN)

    # Step 2: Get reviews for the product
    product_details = search_amazon_product_details(product_ASIN, PRODUCT_DETAILS_AI_QUERY)
    if not product_details:
        logging.error("error: No product details found")
    
    print("amazon_product_details", product_details)

    people_enjoy_this_for = call_gpt_api(product_name, product_details, PEOPLE_ENJOY_THIS_FOR)
    concerns_exist_for = call_gpt_api(product_name, product_details, CONCERNS_EXIST_FOR)
    # Return all details as JSON
    return jsonify({
        "product_details": product_details,
        "people_enjoy_this_for": people_enjoy_this_for,
        "concerns_exist_for": concerns_exist_for,
    })

# API endpoint
@app.route("/prompt", methods=["POST"])
def promptAPI():
    data = request.json
    product_name = data.get("product_name")
    product_details = data.get("product_details")
    prompt = data.get("prompt")

    if not product_name or not prompt:
        return jsonify({"error": "product_name and prompt are required"}), 400
    
    # Call GPT API
    gpt_response = call_gpt_api(product_name, product_details, prompt)
    print("gpt_response", gpt_response)
    return jsonify({"response": gpt_response})

# API endpoint
@app.route("/translate", methods=["POST"])
def translate():
    data = request.json
    text = data.get("text")
    target_language = data.get("target_language")  # Change this to your desired language code

    if not text:
        return jsonify({"error": "Text is required"}), 400

    # Translate the text
    translated_text = translate_text(text, target_language)
    print("translated_text", translated_text)
    return jsonify({"response": translated_text})

# Endpoint to convert text to speech
@app.route('/text-to-speech', methods=['POST'])
def text_to_speech():
    # Get JSON data from the request
    data = request.json
    text = data.get('text')
    lang = data.get('target_language', 'en')  # Default to English if language is not provided

    if not text:
        return jsonify({"error": "Text is required"}), 400

     # Translate the text
    translated_text = translate_text(text, lang)

    # Convert text to speech
    tts = gTTS(text=translated_text, lang=lang, slow=False)
    audio_file = BytesIO()
    tts.write_to_fp(audio_file)
    audio_file.seek(0)

    # Return the audio file
    return send_file(audio_file, mimetype='audio/mpeg')

# API endpoint
@app.route("/videos", methods=["POST"])
def getVideos():
    data = request.json
    product_name = data.get("product_name")

    if not product_name:
        return jsonify({"error": "product_name is required"}), 400
    
    videos_links = search_youtube_videos(product_name)
    print("videos_links", videos_links)
    return jsonify({
        "videos_links": videos_links
    })

# API endpoint
@app.route("/scrap-details", methods=["POST"])
def get_product_details():
    data = request.json
    asin = data.get("asin")

    if not asin:
        return jsonify({"error": "ASIN is required"}), 400

    # Scrape product details
    product_details = scrap_amazon_product(asin)

    # Return the product details as JSON
    return jsonify({
        "product_details": product_details
    })

if __name__ == "__main__":
    app.run(debug=True)