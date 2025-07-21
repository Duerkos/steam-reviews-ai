#main file
from os import link
import streamlit as st
import json
import time
import requests
import pandas as pd
import numpy as np
import textwrap
import re
import base64
from io import BytesIO
from PIL import Image
from mistralai import Mistral, UserMessage, SystemMessage
from requests.exceptions import SSLError
from pictex import Canvas, LinearGradient
from datetime import datetime, timedelta
from thefuzz import fuzz

from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base

from utils import add_summary_text_image, get_request, get_header_image, get_summary
        
@st.cache_data
def get_steam_df():
    """Return a list of all steam games.
    
    Returns
    -------
    
        list of all steam games
    """
    return pd.DataFrame(get_request("https://api.steampowered.com/ISteamApps/GetAppList/v2/?")["applist"]["apps"])

@st.cache_data
def get_steam_df_search(search_input):
    """Return a DataFrame of steam games matching the search input.
    """
    df = pd.DataFrame(get_steam_df())
    df["fuzzy_score"] = df["name"].apply(lambda x: fuzzy_phrase_match(x, search_input))
    df["len_name"] = df["name"].apply(lambda x: -len(x))
    df = df[df["fuzzy_score"] > 90]  # Filter out low fuzzy scores
    df = df.sort_values(by=["fuzzy_score","len_name"], ascending=False)
    df = df.head(30)  # Limit to 30 results for performance
    df["total_reviews"] = df["appid"].apply(lambda x: get_reviews(x))
    df = df[df["total_reviews"] > 0]  # Ensure only games with reviews are included
    return df

def fuzzy_phrase_match(text, target):
    def get_fuzzy_score(text_words, target_words):
        scores = []
        start_word= 0
        for tw in target_words:
            # Calculate the fuzzy score for each word in the target against all words in the text in order
            word_scores = [(fuzz.ratio(tw, word)) for word in text_words[start_word:]]
            best_score = max(word_scores) if word_scores else 0
            if best_score > 0:
                start_word += word_scores.index(best_score) + 1
            scores.append(best_score)
        avg_score = sum(scores) / len(scores)
        return avg_score
    #re.sub('[^\w\s]', '', x).lower(), re.sub('[^\w\s]', '', search_input).lower(), threshold=90)
    target_words = target.lower().split()
    text_words = text.lower().split()
    score_0 = get_fuzzy_score(text_words, target_words)
    score_1 = 0
    if bool(re.search(r'[^a-zA-Z0-9]', text)):
        # If there is punctuation, we will try to match without it
        target_words = re.sub('[^\w\s]', '', target).lower().split()
        text_words = re.sub('[^\w\s]', '', text).lower().split()
        score_1 = get_fuzzy_score(text_words, target_words) - 2
    return max(score_0, score_1)

def get_reviews(appid):
    """Return if there are reviews for a given appid."""
    return get_summary(appid)['total_reviews']

def handle_selection():
    st.session_state.selection_made = True

if 'selection_made' not in st.session_state:
    st.session_state.selection_made = False

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
    return True

initialize()

def format_string_search(df, appid):
    """Format the string for the selectbox."""
    low_reviews = "❔"
    enough_reviews = "✅"
    popular_game = "🔥"
    if df[df["appid"] == appid]["total_reviews"].values[0] < 50:
        review_emoji = low_reviews
    elif df[df["appid"] == appid]["total_reviews"].values[0] < 1000:
        review_emoji = enough_reviews
    else:
        review_emoji = popular_game
    return review_emoji+" "+df[df["appid"] == appid]["name"].values[0]

st.session_state.app_result = None
# Search for a game
search_input = st.text_input("Search Steam Game", key="search_input")
if search_input == "":
    search_request = False
    st.stop()
else:
    search_request = True
    if "generated_review" not in st.session_state:
        st.session_state.generated_review = False
    if "last_search" not in st.session_state:
        st.session_state.last_search = ""
        
    # Reset only if search input changed
    if search_input != st.session_state.last_search:
        st.session_state.generated_review = False
        st.session_state.last_search = search_input


if search_request:
    df = get_steam_df_search(search_input).copy()
    if df.empty:
        st.write("No games found for the search term.")
        st.stop()
    app_result = st.selectbox("Select game", df, disabled=not search_request, index=0, format_func = lambda appid: format_string_search(df, appid))
    st.session_state.app_result = app_result
    col_image, col_stats = st.columns(2)
    img = get_header_image(app_result)
    summary = get_summary(app_result)
    summary_image = add_summary_text_image(img, summary)
    im_file = BytesIO()
    summary_image.save(im_file, format="JPEG")
    im_bytes = im_file.getvalue()
    image_base64 = base64.b64encode(im_bytes).decode()
    link = f"https://store.steampowered.com/app/{app_result}"
    html = f"<a href='{link}'><img src='data:image/png;base64,{image_base64}'></a>"
    st.markdown(html, unsafe_allow_html=True)
    if summary["total_reviews"] == 0:
        st.write("No reviews found for this game.")
        st.stop()
    else:
        st.page_link("pages/1-Summary.py", label="Generate Review Analysis")