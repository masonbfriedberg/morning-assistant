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

# Keys
client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
weather_api_key = os.environ["WEATHER_API_KEY"]
news_api_key = os.environ["NEWS_API_KEY"]
ALPHA_KEY = os.environ["APLHA_API_KEY"]

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
weather_input = (
    f"Temp: {current_temp}°F, City: {city}, feels like {feels_like}°F, skies: {description.lower()}, outfit recommendation {outfit}."
)
response = client.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are a Butler of Mason uses the input to provide an expert weather update. Don't forget to mention how the weather may change throughout the day and how that may affect the outfit."},
        {"role": "user", "content": f"Here is the story: {weather_input}"}
    ],
    temperature=0.7)
weather_message = response.choices[0].message.content.strip()

# Get 10PM yesterday in UTC
pst = pytz.timezone("America/Los_Angeles")
now = datetime.now(pst)
yesterday_10pm = (now - timedelta(days=1)).replace(hour=22, minute=0, second=0, microsecond=0)
utc_time = yesterday_10pm.astimezone(pytz.utc).isoformat()

news_message = ""
topics = ["politics", "technology", "economy"]

# Keywords to skip (lowercase)
skip_keywords = ["instagram", "tiktok", "kardashian", "buzzfeed", "omg", "fashion", "celebrity", "debenhams"]

for topic in topics:
    news_url = f"https://newsapi.org/v2/everything?q={topic}&from={utc_time}&sortBy=publishedAt&language=en&apiKey={news_api_key}"
    news_response = requests.get(news_url)
    news_data = news_response.json()
    top_articles = news_data["articles"][:3]

    news_message += f"\n{topic.title()} Headlines:\n"
    for article in top_articles:
        if article["title"] and article["description"]:
            title_lower = article["title"].lower()
            desc_lower = article["description"].lower()
            if all(k not in title_lower and k not in desc_lower for k in skip_keywords):
                response = client.chat.completions.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": "You are an expert news reporter who researches and summarizes news in a central viewpoint."},
                        {"role": "user", "content": f"Here is the story: {article}"}
                    ],
                    temperature=0.7)
                summary = response.choices[0].message.content.strip()
                news_message += f"{article['title']}\n{summary}\n\n"

market_news_url = f"https://newsapi.org/v2/everything?q=stock%20market&from={utc_time}&sortBy=publishedAt&language=en&apiKey={news_api_key}"
market_news_response = requests.get(market_news_url)
market_news_data = market_news_response.json()
top_market_articles = market_news_data["articles"][:3]

market_news_message = ""

def fetch_quote(symbol):
    """Fetch global quote data for one or more symbols via Alpha Vantage."""
    if isinstance(symbol, list):
        results = []
        for s in symbol:
            url = (
                f"https://www.alphavantage.co/query?"
                f"function=GLOBAL_QUOTE&symbol={s}&apikey={ALPHA_KEY}"
            )
            resp = requests.get(url)
            j = resp.json()
            quote = j.get("Global Quote", {})
            price = quote.get("05. price", None)
            change_percent = quote.get("10. change percent", None)
            results.append({"symbol": s, "price": price, "change_percent": change_percent})
        return results
    else:
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

for article in top_market_articles:
    if article.get("title") or article.get("description"):
        # --- Get related ticker(s)
        ticker_response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Research the input to find the related ticker or tickers being mentioned "
                        "and return them as a comma-separated list in this format: (e.g ['AAPL','NVDA'])"
                    ),
                },
                {"role": "user", "content": f"Here is the story: {article}"},
            ],
            temperature=0.7,
        )
        tickers_text = ticker_response.choices[0].message.content.strip()
        try:
            tickers = eval(tickers_text)
            if not isinstance(tickers, list):
                tickers = [tickers_text]
        except Exception:
            tickers = [tickers_text]
        summary_response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert financial news reporter who researches and summarizes news in a central viewpoint. You may use the internet to find more information on thee stories.",
                },
                {"role": "user", "content": f"Here is the story: {article}"},
            ],
            temperature=0.7,
        )
        summary = summary_response.choices[0].message.content.strip()
        if tickers and all(t.strip() for t in tickers):
            quotes = fetch_quote(tickers)
            if isinstance(quotes, dict):
                quotes = [quotes]  # unify single and multi
            for q in quotes:
                sym = q["symbol"]
                price = q["price"] or "N/A"
                change = q["change_percent"] or "N/A"
                market_news_message += (
                    f"{sym}: {article['title']}\n{summary}\n"
                    f"Price: {price} | Change: {change}\n\n"
                )
        else:
            market_news_message += f"{article['title']}\n{summary}\n\n"

market_message = ""

# Major Indices
market_message += "Major Indices:\n"
for idx in ["SPY", "DIA", "QQQ"]:
    q = fetch_quote(idx)
    if q.get("price") and q.get("change_percent"):
        market_message += f"{idx}: {q['price']} ({q['change_percent']})\n"

# Bitcoin
btc = fetch_quote("BTCUSD")
if btc.get("price") and btc.get("change_percent"):
    market_message += f"\nBitcoin: {btc['price']} ({btc['change_percent']})\n"

# U.S. Dollar Index (try fallback symbol)
for sym in ["DX-Y.NYB", "DXY", "USDOLLAR"]:
    dxy = fetch_quote(sym)
    if dxy.get("price") and dxy.get("change_percent"):
        market_message += f"\nU.S. Dollar Index: {dxy['price']} ({dxy['change_percent']})\n"
        break

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

You are Mason's butler providing his morning update. Speak directly to Mason in a natural, conversational tone — intelligent, warm, and personal — as if you’re briefing him in person.
Your role is to assemble the provided content into a smooth morning briefing without summarizing, reinterpreting, or omitting meaningful details. 
Preserve all descriptive information from the stories exactly as given, only removing filler sentences or repetition. 
Make transitions between sections sound fluid and natural, like a real person would when talking.

Begin with:
"Good morning Mason, it's {formatted_time} Pacific Time on {formatted_date}."

Then include:

1. Weather summary:
{weather_message}

2. World news:
{news_message}

If the stock market is closed on {formatted_date} (Saturday, Sunday, or a U.S. Stock Market Observed Holiday),
**skip sections 3 and 4 completely** and go straight to the closing line — do not include any message about skipping or waiting for markets to open.

3. Market-related headlines (if market is open):
{market_news_message}

4. Market summary (if market is open):
{market_message}

End with:
{closing_line}

Additional style rules:
- Speak in full sentences with natural phrasing.
- Avoid robotic or report-like tone.
- Never introduce or invent new information.
- Never include the literal section numbers or headings (e.g., don’t say “1. Weather summary”).
- If the market is closed, there should be **no mention of stocks, tickers, or financial news** at all.
- The message should read as a single smooth narrative, not a segmented report.
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
