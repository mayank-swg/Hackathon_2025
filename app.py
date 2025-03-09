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

import pandas as pd
from lxml import html
import re, time
from datetime import datetime


def scrap_amazon_product(asin):

    #Create session
    session = requests.Session()

    #Define headers
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
        'DNT': '1',  # Do Not Track request header
        'Upgrade-Insecure-Requests': '1',
        'Referer': 'https://amazon.in/',
    }

    #Set auth cookies
    session.cookies.set('session-id', os.getenv("SESSION_ID"), domain='.amazon.in')
    session.cookies.set('ubid-main', os.getenv("UBID_MAIN"), domain='.amazon.in')
    session.cookies.set('session-token', os.getenv("SESSION_TOKEN"), domain='.amazon.in')


    comments_data = [] #Comments data for result dataframe
    print(f'/// ASIN {asin}')

    #Load asin page
    url = f'https://www.amazon.in/dp/{asin}'
    print(f'Load {url}...')
    response = session.get(url, headers=headers, verify=False)
    headers['Referer'] = url #save url as referrer for next query
    print(response)
    time.sleep(2)

    #Load comments page with paging
    page = 1

    while True:

        url = f'https://www.amazon.in/product-reviews/{asin}/ref=cm_cr_arp_d_viewopt_srt?ie=UTF8&reviewerType=all_reviews&sortBy=recent&pageNumber={page}'
        print(f'Page {page} | Load {url}...')
        response = session.get(url, headers=headers, verify=False)
        headers['Referer'] = url  # save url as referrer for next query
        print(response)
        time.sleep(2)

        #Get page tree and get reviews
        tree = html.fromstring(response.content)
        reviews = tree.xpath('//div[@data-hook="review"]')

        print(f'Reviews found on the page: {len(reviews)}')
        if(len(reviews)==0):
            print(response.content)

        # Iterating reviews
        for review in reviews:

            #Get review id
            review_id = review.xpath('./@id')
            review_id = review_id[0] if review_id else None

            # Get Author name
            name = review.xpath('.//span[@class="a-profile-name"]/text()')
            name = name[0] if name else None

            # Get Title
            title = review.xpath('.//a[@data-hook="review-title"]/span/text()')
            title = title[0] if title else None

            # Try get Title by alternative way
            if not title:
                title = review.xpath('.//span[@data-hook="review-title"]/span[@class="cr-original-review-content"]/text()')
                title = title[0] if title else None

            # Get Rating
            rating_str = review.xpath('.//i[@data-hook="review-star-rating"]/span/text()')
            rating_str = rating_str[0] if rating_str else None

            # Try Rating by alternative way
            if not rating_str:
                rating_str = review.xpath('.//i[@data-hook="cmps-review-star-rating"]/span[@class="a-icon-alt"]/text()')
                rating_str = rating_str[0] if rating_str else None

            # Get Author name
            date_str = review.xpath('.//span[@data-hook="review-date"]/text()')
            date_str = date_str[0] if date_str else None

            # Get Review Text
            review_text = review.xpath('.//span[@data-hook="review-body"]//span/text()')
            review_text = review_text[0] if review_text else None

            # Get Country and comment date from
            country = None
            date = None

            if date_str:
                match = re.search(r'Reviewed in ([A-Za-z\s]+) on ([A-Za-z]+\s\d{1,2},\s\d{4})', date_str)
                if match:

                    # Get country
                    country = match.group(1).strip()

                    # Get date and convert to datetime
                    date_strip = match.group(2).strip()
                    date = datetime.strptime(date_strip, '%B %d, %Y')


            # Get rating value from rating str
            rating = None

            if rating_str:
                match = re.search(r'(\d+(\.\d+)?)', rating_str)
                if match:
                    rating = float(match.group(1))

            #Print data
            print(f"Id: {review_id}")
            print(f"Name: {name}")
            print(f"Title: {title}")
            print(f"Rating: {rating}")
            print(f"Country: {country}")
            print(f"Date: {date}")
            print(f"Text: {review_text}")
            print("-" * 40)

            comments_data.append(dict(
                asin = asin,
                review_id = review_id,
                name = name,
                title = title,
                rating = rating,
                country = country,
                date = date,
                review_text = review_text
            ))

        next_page = tree.xpath("//ul[@class='a-pagination']/li[@class='a-last']/a[@href]")
        print('next_page=', next_page)
        if next_page:
            print('Next page found - go to the next page!')
            page += 1
        else:
            print('Next page not found! - Exit from the loop!')
            break

    #Create result dataframe
    frame = pd.DataFrame(comments_data)
    print(frame)

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