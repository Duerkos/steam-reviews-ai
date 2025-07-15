#main file
import streamlit as st
import json
import time
import requests
import pandas as pd
import numpy as np
import textwrap
from io import BytesIO
from PIL import Image
from mistralai import Mistral, UserMessage, SystemMessage
from requests.exceptions import SSLError
from pictex import Canvas
from datetime import datetime, timedelta

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class Summary(Base):
    __tablename__ = "summaries"
    appid = Column(String, primary_key=True)
    summary_date = Column(DateTime)
    total_reviews = Column(Integer)
    json_object = Column(String)
    times_consulted = Column(Integer)

def check_fresh_summary(result, total_reviews):
    check_date = result.summary_date >= datetime.now()-timedelta(days=30)
    check_reviews = total_reviews >= result.total_reviews*0.9
    return check_date & check_reviews

def manage_summary_by_appid(target_appid: str, total_reviews: int):
    conn = st.connection("neon", type="sql")
    session = conn.session
    result = session.get(Summary, target_appid)
    json_summary = None
    if result is not None:
        if check_fresh_summary(result, total_reviews):
            json_summary = result.json_object
            result.times_consulted += 1
            session.commit()
        else:
            json_ai = get_summary_reviews_ai(target_appid)
            result.json_object = json_ai
            result.total_reviews = total_reviews
            result.times_consulted += 1
            result.summary_date = datetime.now()
            session.commit()
            json_summary = json_ai
    else:
        json_ai = get_summary_reviews_ai(target_appid)
        new_summary = Summary(appid=target_appid, summary_date=datetime.now(), total_reviews=total_reviews, json_object=json_ai, times_consulted=1)
        session.add(new_summary)
        session.commit()
        json_summary = json_ai
    session.close()
    return json_summary

def text_to_image(text, alignment="left", line_height=1.1):
    canvas = (
    Canvas()
    .font_family("Roboto-Regular.ttf")
    .font_size(24)
    .color("white")
    .background_color("black")
    .padding(20)
    .alignment(alignment)
    .line_height(line_height)
    )
    img = canvas.render(text).to_pillow()

    return img

def add_summary_text_image(header, summary, score=None):
    img = header.copy()  # Safer to work on a copy
    width, height = img.size
    # Text content
    text =  f"App ID: {summary['appid']}\n" + \
            f"Total Reviews: {summary['total_reviews']}\n" + \
            f"Positive Reviews: {summary['total_positive']}\n" + \
            f"Negative Reviews: {summary['total_negative']}\n" + \
            f"Positive Percentage: {summary['total_positive']/ summary['total_reviews']:.2%}\n" + \
            f"Review Score Desc: {summary['review_score_desc']}\n"
    if score:
        text += f"AI Score: {str(score)}\n"

    canvas = (
        Canvas()
        .font_family("Roboto-Regular.ttf")
        .font_size(40)
        .color("white")
        .background_color("black")
        .padding(20)
        .line_height(1.5)
        )
    img_text = canvas.render(text).to_pillow()
    img = img.resize((int(width*img_text.height/height), img_text.height), Image.Resampling.LANCZOS)
    total_width = img.width + img_text.width
    new_img = Image.new("RGB", (total_width, img_text.height), color=(255, 255, 255))

    new_img.paste(img, (0, 0))
    new_img.paste(img_text, (img.width, 0))

    return new_img

def stack_images_vertically(img_1, img_2):
    # Resize img_1 to match img_2 width
    new_width = img_2.width
    aspect_ratio = img_1.height / img_1.width
    new_height = int(new_width * aspect_ratio)
    img_1_resized = img_1.resize((new_width, new_height), Image.Resampling.LANCZOS)

    # Create new image with enough height to hold both
    total_height = img_1_resized.height + img_2.height
    stacked_img = Image.new("RGB", (new_width, total_height), color=(255, 255, 255))

    # Paste images
    stacked_img.paste(img_1_resized, (0, 0))
    stacked_img.paste(img_2, (0, img_1_resized.height))

    return stacked_img

def get_request(url,parameters=None, steamspy=False):
    """Return json-formatted response of a get request using optional parameters.
    
    Parameters
    ----------
    url : string
    parameters : {'parameter': 'value'}
        parameters to pass as part of get request
    
    Returns
    -------
    json_data
        json-formatted response (dict-like)
    """
    try:
        response = requests.get(url=url, params=parameters)
    except SSLError as s:
        print('SSL Error:', s)
        
        for i in range(5, 0, -1):
            print('\rWaiting... ({})'.format(i), end='')
            time.sleep(1)
        print('\rRetrying.' + ' '*10)
        
        # recursively try again
        return get_request(url, parameters, steamspy)
    
    if response:
        return response.json()
    else:
        # We do not know how many pages steamspy has... and it seems to work well, so we will use no response to stop.
        if steamspy:
            return "stop"
        else :
            # response is none usually means too many requests. Wait and try again 
            print('No response, waiting 10 seconds...')
            time.sleep(10)
            print('Retrying.')
            return get_request(url, parameters, steamspy)
        
@st.cache_data
def get_steam_df():
    """Return a list of all steam games.
    
    Returns
    -------
    
        list of all steam games
    """
    return pd.DataFrame(get_request("https://api.steampowered.com/ISteamApps/GetAppList/v2/?")["applist"]["apps"]).set_index("appid")
def wrap_list_of_strings(strings, width=40, emoji=None):
    """Wrap a list of strings to a specified width."""
    wrapped_strings = []
    for string in strings:
        wrapped_string = textwrap.fill(string, width=width)
        if emoji:
            wrapped_string = f"{emoji} {wrapped_string}"
        wrapped_strings.append(wrapped_string)
    return "\n".join(wrapped_strings)

def get_summary(appid):
    """Return summary of reviews for a given appid."""
    url = "https://store.steampowered.com/appreviews/" + str(appid)
    parameters = {"json": 1, "purchase_type": "all", "review_type": "all"}
    json_data = get_request(url, parameters)
    return json_data['query_summary']

@st.cache_data
def parse_steamreviews_request(appid):
    num_per_page = 50
    max_review = 50  # max number of reviews to return
    review_count = 0
    good_review_list = []
    bad_review_list = []
    url = "https://store.steampowered.com/appreviews/" + str(appid)
    print(url)
    parameters = {"json": 1, "cursor": "*", "num_per_page": num_per_page, "language": "english", "purchase_type": "all", "review_type": "all", "day_range": "365"}
    #see cursor
    #https://partner.steamgames.com/doc/store/getreviews
    json_data = get_request(url, parameters)
    summary = json_data['query_summary']
    while review_count < max_review:
        # if we have not reached the maximum number of good or bad reviews, and there are still reviews to fetch
        if summary["num_reviews"] == 0:
            break
        json_data = get_request(url, parameters)
        for review in json_data["reviews"]:
            review_count += 1
            if review["voted_up"]:
                good_review_list.append(review["review"])
            else:
                bad_review_list.append(review["review"])
        # get next page of reviews
        parameters["cursor"] = json_data["cursor"]
        summary = json_data['query_summary']
        #st.write(json_data)
    return good_review_list, bad_review_list, summary
# Mistral model 
mistral_model = "mistral-small-latest"
client = Mistral(st.secrets["MISTRAL_API_KEY"])
# Agent IDs
review_summary_id = "review_summary_agent"
# Initialize everything
def initialize():
    check_client()
# Check if the client is initialized
def is_client_initialized():
    return client is not None and st.secrets["MISTRAL_API_KEY"] is not None
def check_client():
    if not is_client_initialized():
        st.write("Mistral client is not initialized. Please check your API key.")
        return False
    st.write("Mistral client is initialized.")
    return True

initialize()

def trim_factors(content, steam_score):
    """Trim the factors based on the steam review score, with a score of 8 two negative factors and 8 positive factors."""
    steam_score = int(steam_score)
    if len(content["positive_factors"]) > steam_score:
        content["positive_factors"] = content["positive_factors"][:steam_score+1]
    if len(content["negative_factors"]) > (10-steam_score):
        content["negative_factors"] = content["negative_factors"][:(10-steam_score+1)]
    return content

def get_json_response(reviews):
    try:
        response = client.agents.complete(
            agent_id=st.secrets["review_agent"],
            messages=reviews,
            stream=False,
            response_format={"type": "json_object"}
            )
        return response    
    except Exception as e:
        st.write(f"Error during web search: {str(e)}")
        return 0

def get_summary_reviews_ai(appid):
    good_review_list, bad_review_list, summary_not_needed = parse_steamreviews_request(appid)
    
    categorized_reviews = {
        "positive_reviews": good_review_list,
        "negative_reviews": bad_review_list
    }
    
    raw_response = get_json_response([{"content": json.dumps(categorized_reviews), "role": "user"}])
    
    content_raw = raw_response.choices[0].message.content

    return content_raw

search_input = st.text_input("Search Steam Game", key="search_input")
if search_input == "":
    search_request = False
else:
    search_request = True
df = pd.DataFrame(get_steam_df())
df = df[df["name"].str.contains(search_input, case=False, na=False)]
if search_request:
    appname = st.selectbox("Select game", df["name"], disabled=not search_request, index=0)
    col_image, col_stats = st.columns(2)
    response = requests.get(f"https://cdn.akamai.steamstatic.com/steam/apps/{df[df['name']==appname].index[0]}/header.jpg")
    img = Image.open(BytesIO(response.content))
    appid = df[df["name"]==appname].index[0]
    summary = get_summary(appid)
    summary["appid"] = df[df["name"]==appname].index[0]
    col_banner = st.container()
    col_analysis, col_link = st.columns(2)
    with col_link:
        st.link_button("Store Link", f"https://store.steampowered.com/app/{df[df['name']==appname].index[0]}")
    with col_analysis:
        if st.button("Generate Review Analysis"):
            appid = df[df["name"]==appname].index[0]
            content_raw = manage_summary_by_appid(str(appid), total_reviews=int(summary['total_reviews']))
            content = json.loads(content_raw)
            content = trim_factors(content, summary['total_positive']/ summary['total_reviews'] * 10)
            with col_banner:
                st.image(stack_images_vertically(add_summary_text_image(img, summary, content["score"]),
                                   text_to_image(textwrap.fill(content["summary"], width=80) + "\n\n" +
                                   wrap_list_of_strings(content["positive_factors"], emoji="✅", width=80) +"\n" +
                                   wrap_list_of_strings(content["negative_factors"], emoji="❌", width=80),
                                   alignment="left", line_height=1.5)))
            st.json(content, expanded=False)
        else: 
            with col_banner:
                st.image(add_summary_text_image(img, summary))