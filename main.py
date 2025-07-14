#main file
import streamlit as st
import json
import time
import requests
import pandas as pd
import numpy as np
import textwrap
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from mistralai import Mistral, UserMessage, SystemMessage
from requests.exceptions import SSLError
from pictex import Canvas

#Mistral shenanigans here: https://www.datacamp.com/tutorial/mistral-agents-api

stopwords_list = requests.get("https://gist.githubusercontent.com/rg089/35e00abf8941d72d419224cfd5b5925d/raw/12d899b70156fd0041fa9778d657330b024b959c/stopwords.txt").content
stopwords = set(stopwords_list.decode().splitlines())

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
    img = canvas.render(text).to_numpy()

    return img

def add_summary_text_image(header, summary, subtext):
    img = header.copy()  # Safer to work on a copy

    width, height = img.size

    # Load font from URL
    req = requests.get("https://github.com/googlefonts/roboto/blob/main/src/hinted/Roboto-Regular.ttf?raw=true")
    font = ImageFont.truetype(BytesIO(req.content), 32)

    # Text content
    text1 = f"Positive: {summary['total_positive'] / summary['total_reviews']:.2%}"
    text2 = subtext
    text = f"{text1}\n{text2}"
    
    canvas = (
        Canvas()
        .font_family("Roboto-Regular.ttf")
        .font_size(24)
        .color("white")
        .background_color("black")
        .padding(20)
        )
    img_text = canvas.render(text).to_pillow()
    img = img.resize((width, img_text.height), Image.Resampling.LANCZOS)
    total_width = img.width + img_text.width
    new_img = Image.new("RGB", (total_width, img_text.height), color=(255, 255, 255))

    new_img.paste(img, (0, 0))
    new_img.paste(img_text, (img.width, 0))

    st.image(new_img, use_container_width=True)




# Save or show the image
    return np.array(img)

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

def get_summary_reviews(reviews):
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
    with col_image:
        st.image(f"https://cdn.akamai.steamstatic.com/steam/apps/{df[df['name']==appname].index[0]}/header.jpg", use_container_width=True)
    with col_stats:
        col_total, col_summary = st.columns(2)
        appid = df[df["name"]==appname].index[0]
        summary = get_summary(appid)
        with col_total:
            st.write(f"**App ID:** {appid}")
            st.write(f"**Total Reviews:** {summary['total_reviews']}")
            st.write(f"**Positive Reviews:** {summary['total_positive']}")
            st.write(f"**Negative Reviews:** {summary['total_negative']}")
        with col_summary:
            st.write(f"**Positive Percentage:** {summary['total_positive']/ summary['total_reviews']:.2%}")
            st.write(f"**Review Score Desc:** {summary['review_score_desc']}")
    col_analysis, col_link = st.columns(2)
    with col_link:
        st.link_button("Store Link", f"https://store.steampowered.com/app/{df[df['name']==appname].index[0]}")
    with col_analysis:
        if st.button("Generate Review Analysis"):
            appid = df[df["name"]==appname].index[0]
            
            extra_stop_words = {"lot","10","h1","n't", "game", "games", "play", "steam", "valve", "played", "playing"}
            extra_stop_words = extra_stop_words.union(set(appname.lower().split()))
            stop_words = stopwords.union(extra_stop_words)
            
            good_review_list, bad_review_list, summary_not_needed = parse_steamreviews_request(appid)
            
            categorized_reviews = {
                "positive_reviews": good_review_list,
                "negative_reviews": bad_review_list
            }
            
            #raw_response = get_summary_reviews([{"content": json.dumps(categorized_reviews), "role": "user"}])
            #content = raw_response.choices[0].message.content
            
            with open('jsonexample.json') as json_file:
                content = json.load(json_file)
            #st.json(content)
            add_summary_text_image(img, summary, "something"),
            st.image(text_to_image(textwrap.fill(content["summary"], width=80) + "\n\n" +
                                   wrap_list_of_strings(content["positive_factors"], emoji="✅", width=80) +"\n" +
                                   wrap_list_of_strings(content["negative_factors"], emoji="❌", width=80),
                                   alignment="left", line_height=1.5))