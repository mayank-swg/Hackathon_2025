import requests, logging, os, re
from flask import Flask, request, send_file, jsonify
from pytube import Search
from lxml import html
from deep_translator import GoogleTranslator
from gtts import gTTS
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)

PEOPLE_ENJOY_THIS_FOR = "people enjoy this for?"
CONCERNS_EXIST_FOR = "concerns exist for?"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ROLE_AND_GUIDELINES_PROMPT = "Role:\r\n\r\nYou are an expert data analyst specializing in retail insights. Your task is to analyze customer reviews, product descriptions, and ratings from retail website data to provide concise, accurate, and engaging responses to customer inquiries.\r\n\r\nGuidelines:\r\n\r\n1. Short & Precise Responses: Keep answers concise, avoiding unnecessary details.\r\n2. Data-Driven Analysis: Base responses on product reviews, ratings, and descriptions while identifying key trends.\r\n3. Avoid Personal Data: Do not reveal personal details (names, emails, phone numbers) found in reviews.\r\n4. Sales Optimization: If a customer shows purchase intent, subtly highlight product benefits to encourage a sale.\r\n5. Clarification When Needed: If a question is unclear, ask relevant follow-up questions before responding.\r\n6. Filter Out Gibberish: Ignore or politely redirect irrelevant, nonsensical, or off-topic queries.\r\n7. Maintain Natural Flow: Keep responses conversational and engaging, aligned with the customer\'s tone.\r\n8. Trend Detection: Identify recurring themes in reviews (e.g., common praises or complaints) to enhance recommendations.\r\n9. Sentiment Awareness: If a product has mixed reviews, provide a balanced response highlighting both pros and cons.\r\n10. Comparative Insights: If applicable, suggest similar or better-rated alternatives to guide customers in decision-making.\r\n11. Urgency & Scarcity: Mention limited stock or popular trends when relevant to create urgency.\r\n12. Concise Bullet Points: Don\'t provide more than 10 bullet points. \r\n\r\nBelow is the data for product name and corresponding details(reviews) followed by the user question. Try to answer the user question-"
MAX_YOUTUBE_VIDEOS = 3
YOUTUBE_SEARCH_PROMPT = "best review videos of"

header = { 
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7", 
    "Accept-Encoding": "gzip, deflate, br", 
    "Accept-Language": "en-US,en;q=0.9", 
    "Upgrade-Insecure-Requests": "1", 
    "Referer": "https://www.google.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }

# Get ASIN of the 1st Non-Ad Amazon Product
def scrape_amazon_product_asin(query):
    # Construct the search URL
    url = f"https://www.amazon.in/s?k={query.replace(' ', '+')}"
    headers = header

    response = requests.get(url, headers=headers)
    print("url to get ASIN", url)
    if response.status_code == 200:
        # Parse the HTML content using lxml
        tree = html.fromstring(response.content)

        # Find all product containers (non-ad results)
        products = tree.xpath("//div[@data-component-type='s-search-result' and not(.//span[contains(text(), 'Sponsored')])]")

        # Extract the ASIN of the first non-ad product
        if products:
            asin = products[0].get("data-asin")
            if asin:
                print("product_ASIN", asin)
                return asin
            else:
                print("ASIN not found in the first non-ad product.")
        else:
            print("No non-ad products found.")
    else:
        print(f"Failed to retrieve the page for ASIN. Status code: {response.status_code}")
    return None

# Get Amazon Product Details
def scrape_amazon_product_details(asin):

    # Load asin page
    url = f'https://www.amazon.in/dp/{asin}'
    headers = header
    print(f'Loading {url}...')
    response = requests.get(url, headers=headers, verify=False)
    headers['Referer'] = url  # Save the URL as referrer for the next query
    print(response.status_code)  # Check the response status code

    # Parse the product details
    tree = html.fromstring(response.content)

    # Extract product title
    title = tree.xpath('//span[@id="productTitle"]/text()')
    title = title[0].strip() if title else "N/A"

    # Extract product price
    price = tree.xpath('//span[@class="a-price-whole"]/text()')
    price = f"₹{price[0].strip()}" if price else "N/A"


    # Extract product rating
    rating = tree.xpath('//span[@class=""]/text()')
    rating = rating[0].strip() if rating else "N/A"

    # Extract availability status
    availability = tree.xpath('//div[@id="availability"]/span/text()')
    availability = availability[0].strip() if availability else "N/A"

    # Extract product description
    description_section = tree.xpath('//div[@id="feature-bullets"]//span[@class="a-list-item"]/text()')
    description = [desc.strip() for desc in description_section if desc.strip()] if description_section else ["N/A"]
    
    reviews = []
    review_elements = tree.xpath('//li[@data-hook="review"]')

    if len(review_elements) == 0:
        print(response)

    # Extract each review
    for review in review_elements:

        # Get review title
        review_title = review.xpath('.//a[@data-hook="review-title"]/span/text()')
        review_title = title[0] if title else None

        # Get review rating
        rating_str = review.xpath('.//i[@data-hook="review-star-rating"]/span/text()')
        rating_str = rating_str[0] if rating_str else None

        # Get review text
        review_text = review.xpath('.//span[@data-hook="review-body"]//span/text()')
        review_text = review_text[0] if review_text else None

        # Get review images
        review_images = review.xpath('.//div[@class="review-image-tile-section"]//img/@src')
        review_images = [img for img in review_images if img.endswith('.jpg') or img.endswith('.png')] if review_images else []

        # Get rating value
        review_rating = None
        if rating_str:
            match = re.search(r'(\d+(\.\d+)?)', rating_str)
            if match:
                review_rating = float(match.group(1))

        # Append the review data to the list
        reviews.append({
            'title': review_title,
            'rating': review_rating,
            'review_text': review_text,
            'review_images': review_images
        })

    return {
        "title": title,
        "price": price,
        "rating": rating,
        "availability": availability,
        "description": description,
        "reviews": reviews
    }

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

        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print("error occured in OpenAI Call", e)
        print("OpenAI Response", response.text)
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
    product_ASIN = scrape_amazon_product_asin(product_name)
    if not product_ASIN:
        return jsonify({"error": "Product not found"}), 404

    # Step 2: Get reviews for the product
    product_details = scrape_amazon_product_details(product_ASIN)
    if not product_details:
        return jsonify({"error": "No product details found"}), 404

    # Step 3: Call GPT API
    gpt_response = call_gpt_api(product_name, product_details, prompt)

    return jsonify({"response": gpt_response})

# API endpoint
@app.route("/product-asin", methods=["POST"])
def product_ASIN():
    data = request.json
    product_name = data.get("product_name")

    if not product_name:
        return jsonify({"error": "product_name is required"}), 400

    # Step 1: Search for the product on Amazon
    product_ASIN = scrape_amazon_product_asin(product_name)
    if not product_ASIN:
        logging.error("error: product not found")

    return jsonify({
        "product_ASIN": product_ASIN
    })

# API endpoint
@app.route("/product-details", methods=["POST"])
def product_details():
    data = request.json
    product_name = data.get("product_name")

    if not product_name:
        return jsonify({"error": "product_name is required"}), 400

    # Step 1: Search for the product on Amazon
    product_ASIN = scrape_amazon_product_asin(product_name)
    if not product_ASIN:
        logging.error("error: product not found")

    # Step 2: Get Details for the product
    product_details = scrape_amazon_product_details(product_ASIN)
    if not product_details:
        logging.error("error: No product details found")
    videos_links = search_youtube_videos(product_name)

    return jsonify({
        "product_details": product_details,
        "videos_links": videos_links
    })

# API endpoint
@app.route("/pdp-data", methods=["POST"])
def pdp_data():
    data = request.json
    product_name = data.get("product_name")

    if not product_name:
        return jsonify({"error": "product_name is required"}), 400

    # Step 1: Search for the product on Amazon
    product_ASIN = scrape_amazon_product_asin(product_name)
    if not product_ASIN:
        logging.error("error: product not found")

    # Step 2: Get reviews for the product
    product_details = scrape_amazon_product_details(product_ASIN)
    if not product_details:
        logging.error("error: No product details found")

    people_enjoy_this_for = call_gpt_api(product_name, product_details, PEOPLE_ENJOY_THIS_FOR)
    concerns_exist_for = call_gpt_api(product_name, product_details, CONCERNS_EXIST_FOR)

    videos_links = search_youtube_videos(product_name)

    # Return all details as JSON
    return jsonify({
        "product_details": product_details,
        "people_enjoy_this_for": people_enjoy_this_for,
        "concerns_exist_for": concerns_exist_for,
        "videos_links": videos_links
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
    return jsonify({"response": translated_text})

# API endpoint
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
    return jsonify({
        "videos_links": videos_links
    })

if __name__ == "__main__":
    app.run(debug=True)