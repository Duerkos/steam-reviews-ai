#main file
import streamlit as st
import time
import requests
import pandas as pd
import numpy as np
from wordcloud import WordCloud
import nltk
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab')
    nltk.download('wordnet')

from nltk.corpus import stopwords
from nltk.stem.wordnet import WordNetLemmatizer   
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from requests.exceptions import SSLError
from sklearn.decomposition import NMF
from sklearn.feature_extraction.text import TfidfVectorizer

stopwords_list = requests.get("https://gist.githubusercontent.com/rg089/35e00abf8941d72d419224cfd5b5925d/raw/12d899b70156fd0041fa9778d657330b024b959c/stopwords.txt").content
stopwords = set(stopwords_list.decode().splitlines())

def add_summary_text_image(header, summary,subtext):

    img = header

    # Get image dimensions
    width, height = img.size

    # Create a drawing object
    draw = ImageDraw.Draw(img)

    # Load a font (adjust the path and size as needed)

    req = requests.get("https://github.com/googlefonts/roboto/blob/main/src/hinted/Roboto-Regular.ttf?raw=true")

    font = ImageFont.truetype(BytesIO(req.content), 32)

    # Define text and position
    text1 = f"Positive: {summary['total_positive']/ summary['total_reviews']:.2%}"
    text2 = subtext

    # Calculate position (bottom-left)
    x = 10  # Small margin from the left
    y = height - 100  # Adjust based on font size

    # Get bounding box for multiline text
    text = f"{text1}\n{text2}"
    bbox = draw.multiline_textbbox((x, y), text, font=font)

    # Draw black rectangle behind text
    draw.rectangle((bbox[0] - 5, bbox[1] - 5, bbox[2] + 5, bbox[3] + 5), fill="black")

    # Draw text on top of the black background
    draw.multiline_text((x, y), text, font=font, fill="white")


# Save or show the image
    return np.array(img)

def generate_wordclouds(model, feature_names, n_top_words, n_components, pos_sum_percent, tot_sum, header, summary, subtext):
    sorted_indices = np.argsort(tot_sum)[::-1]  # Sort topics by descending tot_sum
    wordcloud_images = []

    # Create a color mapping from red (0) to white (0.5) to green (1)
    cmap = plt.get_cmap("RdYlGn")
    norm = mcolors.Normalize(vmin=0, vmax=1)  # Normalize pos_sum_percent to [0, 1]

    for topic_idx in sorted_indices[:n_components]:  # Limit to n_components
        topic = model.components_[topic_idx]
        top_features_ind = topic.argsort()[-n_top_words:]
        top_features = feature_names[top_features_ind]
        weights = topic[top_features_ind]

        # Create word frequency dictionary
        word_freq = {word: weight+0.01 for word, weight in zip(top_features, weights)}

        # Determine the RGB colors for words based on pos_sum_percent
        topic_color = cmap(norm(pos_sum_percent[topic_idx]))  # Get color from colormap
        rgb_color = f"rgb({int(topic_color[0]*255)}, {int(topic_color[1]*255)}, {int(topic_color[2]*255)})"

        # Generate word cloud using a single color
        wc = WordCloud(width=200, height=200, background_color="black", 
                       prefer_horizontal=1.0,
                       color_func=lambda *args, **kwargs: rgb_color,
                       normalize_plurals=True).generate_from_text(" ".join(top_features))


        # Convert to image
        img = wc.to_array()
        wordcloud_images.append(img)
    
    base_width = 1000
    wpercent = (base_width / float(header.size[0]))
    hsize = int((float(header.size[1]) * float(wpercent)))
    header = header.resize((base_width, hsize), Image.Resampling.LANCZOS)
    header = add_summary_text_image(header, summary, subtext)
    
    vertical_groups = []
    for i in range(0, len(wordcloud_images), 5):
        group = np.hstack(wordcloud_images[i:i+5])
        vertical_groups.append(group)

    vertical_stack = np.vstack([header]+vertical_groups)  # Combine groups vertically

    st.image(vertical_stack, use_container_width=True)

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
        
def plot_nmf_topics(good_review_list, bad_review_list, n_features, stop_words, n_components, n_top_words, init, img, summary, subtext):
    """Plot NMF topics."""
    tfidf_vectorizer = TfidfVectorizer(
        max_df=0.95, min_df=2, max_features=n_features, stop_words=stop_words
    )
    tfidf = tfidf_vectorizer.fit_transform(good_review_list+ bad_review_list)
    
    nmf = NMF(
    n_components=n_components,
    random_state=1,
    init=init,
    beta_loss="frobenius",
    alpha_W=0.00015,
    alpha_H=0.00015,
    l1_ratio=1,
    ).fit(tfidf)
    
    tfidf_feature_names = tfidf_vectorizer.get_feature_names_out()
    w = nmf.transform(tfidf)
    pos_sum = np.sum(w[:len(good_review_list)], axis=0)
    neg_sum = np.sum(w[len(good_review_list):], axis=0)
    tot_sum = pos_sum + neg_sum
    pos_sum_percent = pos_sum / (tot_sum+0.01)
    generate_wordclouds(
        nmf, tfidf_feature_names, n_top_words, n_components, pos_sum_percent, tot_sum, img, summary, subtext
    )
        
@st.cache_data
def get_steam_df():
    """Return a list of all steam games.
    
    Returns
    -------
    
        list of all steam games
    """
    return pd.DataFrame(get_request("https://api.steampowered.com/ISteamApps/GetAppList/v2/?")["applist"]["apps"]).set_index("appid")

@st.cache_data
def parse_steamreviews_request_balanced(appid):
    num_per_page = 100
    max_good_review = 100  # max number of good reviews to return
    max_bad_review = 100
    good_review_count = 0
    bad_review_count = 0
    good_review_list = []
    bad_review_list = []
    url = "https://store.steampowered.com/appreviews/" + str(appid)
    print(url)
    parameters = {"json": 1, "cursor": "*", "num_per_page": num_per_page, "language": "english", "purchase_type": "all", "review_type": "positive"}
    #see cursor
    #https://partner.steamgames.com/doc/store/getreviews
    json_data = get_request(url, parameters)
    summary = json_data['query_summary']
    wnl = WordNetLemmatizer()
    while good_review_count < max_good_review or bad_review_count < max_bad_review:
        # if we have not reached the maximum number of good or bad reviews, and there are still reviews to fetch
        if summary["num_reviews"] == 0:
            break
        # if we have not reached the maximum number of good reviews, and there are still good reviews to fetch
        if good_review_count < max_good_review:
            json_data = get_request(url, parameters)
            for review in json_data["reviews"]:
                good_review_count += 1
                lemmatized_string = ' '.join([wnl.lemmatize(words) for words in nltk.word_tokenize(review["review"])])
                good_review_list.append(lemmatized_string)
        # if we have not reached the maximum number of bad reviews, and there are still bad reviews to fetch
        elif bad_review_count < max_bad_review:
            parameters["review_type"] = "negative"
            if bad_review_count == 0:
                # reset the cursor to the beginning for bad reviews
                parameters["cursor"] = "*"
            json_data = get_request(url, parameters)
            for review in json_data["reviews"]:
                bad_review_count += 1
                bad_review_list.append(review["review"])
        # get next page of reviews
        parameters["cursor"] = json_data["cursor"]
        #st.write(json_data)
    return good_review_list, bad_review_list, summary

def get_summary(appid):
    """Return summary of reviews for a given appid."""
    url = "https://store.steampowered.com/appreviews/" + str(appid)
    parameters = {"json": 1, "purchase_type": "all", "review_type": "all"}
    json_data = get_request(url, parameters)
    return json_data['query_summary']

@st.cache_data
def parse_steamreviews_request_raw(appid):
    num_per_page = 100
    max_review = 300  # max number of good reviews to return
    review_count = 0
    good_review_list = []
    bad_review_list = []
    url = "https://store.steampowered.com/appreviews/" + str(appid)
    print(url)
    parameters = {"json": 1, "cursor": "*", "num_per_page": num_per_page, "language": "english", "purchase_type": "all", "review_type": "all"}
    #see cursor
    #https://partner.steamgames.com/doc/store/getreviews
    json_data = get_request(url, parameters)
    summary = json_data['query_summary']
    wnl = WordNetLemmatizer()
    while review_count < max_review:
        # if we have not reached the maximum number of good or bad reviews, and there are still reviews to fetch
        if summary["num_reviews"] == 0:
            break
        json_data = get_request(url, parameters)
        for review in json_data["reviews"]:
            lemmatized_string = ' '.join([wnl.lemmatize(words) for words in nltk.word_tokenize(review["review"])])
            review_count += 1
            if review["voted_up"]:
                good_review_list.append(lemmatized_string)
            else:
                bad_review_list.append(lemmatized_string)
        # get next page of reviews
        parameters["cursor"] = json_data["cursor"]
        summary = json_data['query_summary']
        #st.write(json_data)
    return good_review_list, bad_review_list, summary

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
            
            good_review_list, bad_review_list, summary_not_needed = parse_steamreviews_request_raw(appid)
            n_samples = 1000
            n_features = 400
            n_components = 30
            n_top_words = 4
            batch_size = 128
            init = "nndsvda"
            
            st.write("Summary of reviews:")
            plot_nmf_topics(good_review_list, bad_review_list, n_features, list(stop_words),
                            n_components, n_top_words, init, img, summary, "Popular Opinions")
            
            st.write(good_review_list)
            st.write(bad_review_list)

            good_review_list, bad_review_list, summary_not_needed = parse_steamreviews_request_balanced(appid)
            n_samples = 1000
            n_features = 400
            n_components = 30
            n_top_words = 4
            batch_size = 128
            init = "nndsvda"
            
            st.write("Comparison of good vs bad reviews:")
            plot_nmf_topics(good_review_list, bad_review_list, n_features, list(stop_words),
                            n_components, n_top_words, init, img, summary, "The Good & the Bad")
