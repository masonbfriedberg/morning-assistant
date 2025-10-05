import requests
from datetime import datetime, timedelta
import pytz
import re
import openai
from openai import OpenAI
import json
import pandas_market_calendars as mcal
import os
from twilio.rest import Client

weather_api_key = os.environ["WEATHER_API_KEY"]
city = "San Francisco"
weather_url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={weather_api_key}&units=imperial"
weather_response = requests.get(weather_url)
weather_data = weather_response.json()

# Extract key info
current_temp = round(weather_data["main"]["temp"])
feels_like = round(weather_data["main"]["feels_like"])
condition = weather_data["weather"][0]["main"]
description = weather_data["weather"][0]["description"].capitalize()

# Outfit logic
def get_outfit(temp, condition):
    if condition.lower() not in ['rain', 'snow']:
        if temp < 40:
            return 'Big Puffer, Hoodie, Gloves, Beanie, Long Pants & Scarf'
        elif temp < 50:
            return 'Jacket, Hoodie, & Long Pants'
        elif temp < 60:
            return 'Hoodie, Jeans, & Maybe a Light Coat'
        elif temp < 66:
            return 'Long Sleeve, Jeans, & Maybe a Light Coat'
        elif temp < 73:
            return 'Long Sleeve & Jeans'
        elif temp < 80:
            return 'Tshirt & Jeans'
        else:
            return 'Tshirt & Shorts'
    
    elif condition.lower() == 'rain':
        if temp < 40:
            return 'Big Puffer, Hoodie, Gloves, Beanie, Long Pants, Rain Boots & Umbrella'
        elif temp < 50:
            return 'Rain Jacket, Hoodie, Long Pants, & Umbrella'
        elif temp < 60:
            return 'Rain Jacket, Hoodie, Jeans, & Umbrella'
        elif temp < 66:
            return 'Rain Jacket, Long Sleeve, Jeans, & Umbrella'
        elif temp < 73:
            return 'Rain Jacket, Long Sleeve & Jeans, & Umbrella'
        elif temp < 80:
            return 'Rain Jacket, Tshirt & Jeans, & Umbrella'
        else:
            return 'Tshirt, Shorts, Raincoat, & Umbrella'

    elif condition.lower() == 'snow':
        return 'Thermal Layers, Big Coat, Gloves, Scarf, Boots, Beanie — Bundle Up ❄️'

    else:
        return 'Default fit: Hoodie & Jeans. Can’t go wrong.'

# Generate weather message
outfit = get_outfit(current_temp, condition)
weather_message = (
    f"It's currently {current_temp}°F in {city} and feels like {feels_like}°F. "
    f"The skies are {description.lower()}. I recommend wearing: {outfit}."
)

# Get 10PM yesterday in UTC
pst = pytz.timezone("America/Los_Angeles")
now = datetime.now(pst)
yesterday_10pm = (now - timedelta(days=1)).replace(hour=22, minute=0, second=0, microsecond=0)
utc_time = yesterday_10pm.astimezone(pytz.utc).isoformat()

news_api_key = os.environ["NEWS_API_KEY"]

news_message = ""
topics = ["politics", "technology", "economy"]

# Keywords to skip (lowercase)
skip_keywords = ["instagram", "tiktok", "kardashian", "buzzfeed", "omg", "fashion", "celebrity", "debenhams"]

for topic in topics:
    news_url = f"https://newsapi.org/v2/everything?q={topic}&from={utc_time}&sortBy=publishedAt&language=en&apiKey={news_api_key}"
    news_response = requests.get(news_url)
    news_data = news_response.json()
    top_articles = news_data["articles"][:3]

    news_message += f"\n🧠 {topic.title()} Headlines:\n"
    for article in top_articles:
        if article["title"] and article["description"]:
            title_lower = article["title"].lower()
            desc_lower = article["description"].lower()
            if all(k not in title_lower and k not in desc_lower for k in skip_keywords):
                news_message += f"📰 {article['title']}\n"
                news_message += f"📝 {article['description'].strip()}\n\n"

market_message = ""
market_news_url = f"https://newsapi.org/v2/everything?q=stock%20market&from={utc_time}&sortBy=publishedAt&language=en&apiKey={news_api_key}"
market_news_response = requests.get(market_news_url)
market_news_data = market_news_response.json()
top_market_articles = market_news_data["articles"][:3]

market_news_output = []

for article in top_market_articles:
    if article.get("title") and article.get("description"):
        market_news_output.append({
            "title": article["title"],
            "description": article["description"].strip()
        })

# Initialize OpenAI client
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# Define the system prompt
system_prompt = """You are a financial news analyst. You will be given a list of news articles, each with a title and description. For each article:

1. Remove any ads, source links, or irrelevant content.
2. Summarize the core story in 2–3 professional, informative sentences.
3. Research the most relevant public stock ticker(s) (max 2) directly related to the article.
4. Return a clean JSON array where each object has:
   - "original_title"
   - "summary"
   - "ticker" (e.g., ["AAPL", "GOOGL"])
"""

# Call OpenAI Chat API using new SDK format
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": f"Here is the input list:\n\n{market_news_output}"}
    ],
    temperature=0.4
)

# Extract and print structured output
structured_output = response.choices[0].message.content

ALPHA_KEY = os.environ["APLHA_API_KEY"]

def fetch_quote(symbol):
    """Fetch global quote data for one symbol via Alpha Vantage."""
    url = (
        f"https://www.alphavantage.co/query?"
        f"function=GLOBAL_QUOTE&symbol={symbol}&apikey={ALPHA_KEY}"
    )
    resp = requests.get(url)
    j = resp.json()
    quote = j.get("Global Quote", {})
    price = quote.get("05. price", None)
    change_percent = quote.get("10. change percent", None)
    return {"symbol": symbol, "price": price, "change_percent": change_percent}

def build_market_message(news_summary_list):
    """
    news_summary_list is the output from ChatGPT, e.g.:
    [
       {"original_title": "...", "summary": "...", "ticker": ["DVLT"]},
       ...
    ]
    """
    market_message = ""
    # News portion
    market_message += "📰 Market News & Ticker Performance:\n"
    for item in news_summary_list:
        title = item["original_title"]
        summary = item["summary"]
        tickers = item.get("ticker", [])
        if tickers:
            # Use the first ticker as main
            sym = tickers[0]
            quote = fetch_quote(sym)
            price = quote["price"]
            chg = quote["change_percent"]
            market_message += f"- {title} — {summary} — {sym}: {price} ({chg})\n"
        else:
            market_message += f"- {title} — {summary}\n"
    market_message += "\n📈 Major Indices:\n"
    # Choose index tickers to fetch, e.g. SPY, DIA, QQQ or use symbols your API supports
    for idx in ["SPY", "DIA", "QQQ"]:
        q = fetch_quote(idx)
        if q["price"] and q["change_percent"]:
            market_message += f"{idx}: {q['price']} ({q['change_percent']})\n"
    return market_message

pst = pytz.timezone("America/Los_Angeles")
now = datetime.now(pst)
day_name = now.strftime("%A")
formatted_date = now.strftime("%B %d, %Y")
formatted_time = now.strftime("%-I:%M %p")

# Setup NYSE market calendar
nyse = mcal.get_calendar('NYSE')

# Get today’s date
today = now.date()

# Check if market is open today
schedule = nyse.schedule(start_date=today, end_date=today)
market_closed = schedule.empty  # True if no trading today

# Build closing line based on market status
if market_closed:
    day_name = now.strftime("%A")
    holiday_name = None

    # Attempt to get holiday name if it's a known market holiday
    market_holidays = nyse.holidays().holidays
    if today in market_holidays:
        holiday_name = today.strftime("%B %d")  # Fallback if name is unknown
        closing_line = f"Happy {day_name} — it’s a market holiday, so don’t worry about the markets today.\n\nHope you have a great day!"
    elif today.weekday() == 5:
        closing_line = "Happy Saturday — so don’t worry about the markets today.\n\nHope you have a great day!"
    elif today.weekday() == 6:
        closing_line = "Happy Sunday — so don’t worry about the markets today.\n\nHope you have a great day!"
    else:
        closing_line = f"Markets are closed today ({day_name}) — so don’t worry about the markets.\n\nHope you have a great day!"
else:
    closing_line = "Hope you have a great day!"

full_prompt = f"""
You are an AI assistant. Craft a personalized morning message for Mason using the details below. Write it in a friendly, intelligent tone.

Start with:
"Good Morning Mason, it's {formatted_time} Pacific Time on {formatted_date}."

Then include:

1. Weather summary:
- Describe the current weather and temperature. 
- Suggest what to wear based on temperature and conditions.
- Include how the weather will change throughout the day and offer useful advice (e.g., "it will get warmer later so you may want to take off your jacket," or "rain is expected this evening so pack an umbrella").

2. World news:
- Smoothly summarize each story into a single paragraph (no bullet points, no headlines).
- Write 2–3 sentences per story with relevant context.
- Keep it human — no robotic transitions like “in other news.”

(Skip 3 and 4 if the stock market is not open on {formatted_date} (Saturday, Sunday, or Stock Market Observed Holiday)

3. Ticker-specific market news:
- Summarize each relevant stock or ticker mentioned in the news.
- Format as: “NRG is trading at $89.23, up 1.2% today,” or similar.
- Include a few words of context or reasoning when available.

4. Market summary:
- Share updates on major indices like the S&P 500, Dow Jones, and NASDAQ.
- Briefly include gold, oil, and Bitcoin.

End with:
{closing_line}

Inputs:

Weather:
{weather_message}

News:
{news_message}

Market News (with tickers):
{market_news_output}

Markets:
{market_message}
"""

# Call OpenAI (new SDK)
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are a helpful, friendly AI that delivers personal morning updates."},
        {"role": "user", "content": full_prompt}
    ],
    temperature=0.7
)

# Output
final_message = response.choices[0].message.content

print(final_message)

def send_sms(message_text):
    account_sid = os.environ["ACCOUNT_SID"]
    auth_token = os.environ["AUTH_TOKEN"]
    from_number = os.environ["FROM_NUMBER"]
    to_number = os.environ["TO_NUMBER"]

    client = Client(account_sid, auth_token)
    message = client.messages.create(
        body=message_text,
        from_=from_number,
        to=to_number
    )
    print(f"Sent SMS: {message.sid}")

# Call it after defining
send_sms("This is a test message!")
