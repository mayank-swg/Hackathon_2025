from flask import Flask, request, jsonify
import requests
import logging
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)

# Replace with your actual API keys
SCRAPINGBEE_API = "https://app.scrapingbee.com/api/v1/"
SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY")
BLOCK_ADS = True
PRODUCT_ASIN_AI_QUERY = "ASIN of first result"
PRODUCT_DETAILS_AI_QUERY = "Product information, Important information, Product description, About this item, Reviews"
PEOPLE_ENJOY_THIS_FOR = "people enjoy this for?"
CONCERNS_EXIST_FOR = "concerns exist for?"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
SHOW_DATA_PROMPT = "Give me this answer in tags which are short, crisp, easy to read quickly."

def search_amazon_product_ASIN(product_name):
    url = f'{SCRAPINGBEE_API}?url=https://www.amazon.in/s?k={product_name.replace(" ", "+")}&ai_query={PRODUCT_ASIN_AI_QUERY.replace(" ", "+")}&api_key={SCRAPINGBEE_API_KEY}&block_ads={BLOCK_ADS}'
    response = requests.get(url, verify=False)
    if response.status_code == 200:
        print("asin_url", url)
        return response.text
    return None

def search_amazon_product_details(ASIN):
    url = f'{SCRAPINGBEE_API}?url=https://www.amazon.in/dp/{ASIN}&ai_query={PRODUCT_DETAILS_AI_QUERY.replace(" ", "+")}&api_key={SCRAPINGBEE_API_KEY}&block_ads={BLOCK_ADS}'
    response = requests.get(url, verify=False)
    if response.status_code == 200:
        print("product_url", url)
        return response.text
    return None

def call_gpt_api(product_name, product_details, prompt):
    product_details_text = "\n".join(product_details)
    gpt_prompt = f"Product: {product_name}\nProduct Details:\n{product_details_text}\nQuestion: {prompt}"
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
        print("headers", headers)
        response = requests.post(url, headers=headers, json=data, verify=False)

        print("final_response", response.text)

        return response.json()["choices"][0]["message"]["content"]
    except Exception as e:
        print(e)
        return "Sorry, I'm unable to help!"

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
    product_details = search_amazon_product_details(product_ASIN)
    if not product_details:
        return jsonify({"error": "No product details found"}), 404
    
    print("amazon_product_details", product_details)

    gpt_prompt = f"{prompt}\n{SHOW_DATA_PROMPT}"
    # Step 3: Call GPT API
    gpt_response = call_gpt_api(product_name, product_details, gpt_prompt)

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

    # Step 2: Get reviews for the product
    product_details = search_amazon_product_details(product_ASIN)
    if not product_details:
        logging.error("error: No product details found")
    
    print("amazon_product_details", product_details)
    return product_details

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
    product_details = search_amazon_product_details(product_ASIN)
    if not product_details:
        logging.error("error: No product details found")
    
    print("amazon_product_details", product_details)

    prompt1 = f"{PEOPLE_ENJOY_THIS_FOR}\n{SHOW_DATA_PROMPT}"
    prompt2 = f"{CONCERNS_EXIST_FOR}\n{SHOW_DATA_PROMPT}"
    # prompt3 = "Give me the youtube video link"

    people_enjoy_this_for = call_gpt_api(product_name, product_details, prompt1)
    concerns_exist_for = call_gpt_api(product_name, product_details, prompt2)
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

    gpt_prompt = f"{prompt}\n{SHOW_DATA_PROMPT}"
    # Call GPT API
    gpt_response = call_gpt_api(product_name, product_details, gpt_prompt)
    print("gpt_response", gpt_response)
    return jsonify({"response": gpt_response})

if __name__ == "__main__":
    app.run(debug=True)