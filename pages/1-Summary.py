from os import link
import streamlit as st
import json
import time
import textwrap
import base64
from io import BytesIO
from PIL import Image
from mistralai import Mistral, UserMessage, SystemMessage
from pictex import Canvas, LinearGradient
from datetime import datetime, timedelta

from sqlalchemy import Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import declarative_base
from utils import get_header_image, get_summary, wrap_list_of_strings, add_summary_text_image, text_to_image, get_request

Base = declarative_base()

class Summary(Base):
    __tablename__ = "summaries"
    appid = Column(String, primary_key=True)
    summary_date = Column(DateTime)
    total_reviews = Column(Integer)
    json_object = Column(String)
    times_consulted = Column(Integer)
    bug = Column(Boolean)

class Report(Base):
    __tablename__ = "summary_bug"
    appid = Column(String, primary_key=True)
    summary_date = Column(DateTime)
    report_date = Column(DateTime)
    json_object_bug = Column(String)
    times_consulted = Column(Integer)
    reason = Column(String)

def check_fresh_summary(result, total_reviews):
    check_summary = result.json_object is not None
    check_date = result.summary_date >= datetime.now()-timedelta(days=30)
    check_reviews = total_reviews >= result.total_reviews*0.9
    return check_date & check_reviews & check_summary

def manage_summary_by_appid(target_appid: str, total_reviews: int, progress_status):
    date_cache = None
    try:
        #st.write("Connecting to database... try 1")
        conn = st.connection("neon", type="sql")
        session = conn.session
        result = session.get(Summary, target_appid)
    except Exception as e:
        time.sleep(5)  # Wait for a while before retrying
        #st.write(f"Retrying connection to database... Error: {e}")
        conn = st.connection("neon", type="sql")
        session = conn.session
        result = session.get(Summary, target_appid)
    json_summary = None
    if result is not None:
        if check_fresh_summary(result, total_reviews) and result.bug is False:
            json_summary = result.json_object
            result.times_consulted += 1
            date_cache = result.summary_date
            session.commit()
        else:
            progress_status.write("### Generating summary with AI...")
            json_ai = get_summary_reviews_ai(target_appid)
            result.json_object = json_ai
            result.total_reviews = total_reviews
            result.times_consulted += 1
            result.summary_date = datetime.now()
            result.bug = False
            session.commit()
            json_summary = json_ai
            #st.write("Updated summary in database.")
            #st.write(json_summary)
    else:
        json_ai = get_summary_reviews_ai(target_appid)
        new_summary = Summary(appid=target_appid, summary_date=datetime.now(), total_reviews=total_reviews, json_object=json_ai, times_consulted=1)
        session.add(new_summary)
        session.commit()
        json_summary = json_ai
        #st.write("Summary retrieved or created.")
        #st.write(json_summary)
    session.close()
    return json_summary, date_cache

def write_bug(appid, content, option_bug):
    """Write a bug report to the database."""
    try:
        conn = st.connection("neon", type="sql")
        session = conn.session
        result = session.get(Summary, str(appid))
    except Exception as e:
        time.sleep(5)  # Wait for a while before retrying
        conn = st.connection("neon", type="sql")
        session = conn.session
        result = session.get(Summary, str(appid))
    
    if result is not None:
        result.bug = True
        report = Report(appid=str(appid),
                        summary_date=result.summary_date,
                        report_date=datetime.now(),
                        json_object_bug=json.dumps(content),
                        times_consulted=result.times_consulted,
                        reason=option_bug)
        session.add(report)
        session.commit()
    else:
        st.write("No summary found for this appid.")
    session.close()

@st.cache_data
def parse_steamreviews_request(appid):
    num_per_page = 20
    max_review = 20  # max number of reviews to return
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
        if response is None or not hasattr(response, 'choices') or not response.choices:
            return get_json_response(reviews)  # Retry if no response or empty choices
        return response    
    except Exception as e:
        st.write(f"Error during web search: {str(e)}")
        return 0
    
def water_mark_image(text="Steam Reviews AI", font_size=24):
    """Create a watermark image."""
    canvas = (
        Canvas()
        .font_family("app/static/Roboto-Regular.ttf")
        .font_size(font_size)
        .color("white")
        .background_color(LinearGradient(["#00000000", "#ff8b00"]))
        .padding(10)
        .alignment("right")
    )
    img = canvas.render(text).to_pillow()
    return img

def get_summary_reviews_ai(appid):
    good_review_list, bad_review_list, summary_not_needed = parse_steamreviews_request(appid)
    
    categorized_reviews = {
        "positive_reviews": good_review_list,
        "negative_reviews": bad_review_list
    }
    
    raw_response = get_json_response([{"content": json.dumps(categorized_reviews), "role": "user"}])
    
    content_raw = raw_response.choices[0].message.content

    return content_raw

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

@st.fragment
def handle_bug_report():
    option_bug = st.text_input("Can you describe the issue?",placeholder="Write a reason or leave it empty")
    if st.button("Report Bug", type="primary"):
        write_bug(app_result, content, option_bug)
        st.rerun()

if "appid" in st.query_params:
    app_result = st.query_params["appid"]
elif "app_result" in st.session_state:
    app_result = st.session_state.app_result
    st.query_params["appid"] = str(app_result)
else:
    st.page_link("Search.py", label=":red-background[**Search a game first**]")
    st.stop()
        
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

col_banner = st.empty()
col_bug = st.container()
col_back, col_about, col_kofi = st.columns(3, vertical_alignment="center")
generated_review = False
img = get_header_image(app_result)
summary = get_summary(app_result)
with col_banner.container():
    progress_status = st.empty()
    progress_status.write("### Checking if summary exists in cache...")
    summary_image = add_summary_text_image(img, summary)
    im_file = BytesIO()
    summary_image.save(im_file, format="JPEG")
    im_bytes = im_file.getvalue()
    image_base64 = base64.b64encode(im_bytes).decode()
    link = f"https://store.steampowered.com/app/{app_result}"
    html = f"<a href='{link}'><img src='data:image/png;base64,{image_base64}'></a>"
    first_banner = st.empty()
    first_banner.markdown(html, unsafe_allow_html=True)
with col_back:
    st.page_link("Search.py", label=":red-background[**Search**]")
with col_about:
    st.page_link("pages/2-About.py", label=":red-background[**About**]")
with col_kofi:
    st.page_link("https://ko-fi.com/duerkos", label=":red-background[**Support me**]")
if summary["total_reviews"] == 0:
    st.write("No reviews found for this game.")
    st.stop()
content_raw, date_cache = manage_summary_by_appid(str(app_result), int(summary['total_reviews']), progress_status)
content = json.loads(content_raw)
content = trim_factors(content, summary['total_positive']/ summary['total_reviews'] * 10)
generated_review = True
if generated_review:
    with col_banner.container():
        first_banner.empty()
        review_img = stack_images_vertically(stack_images_vertically(add_summary_text_image(img, summary, content["score"]),
                    water_mark_image(text="www.steam-review.streamlit.app                                                                    by github.com/duerkos")),
                    text_to_image(textwrap.fill(content["summary"], width=80) + "\n\n" +
                    wrap_list_of_strings(content["positive_factors"], emoji="✅", width=80) +"\n" +
                    wrap_list_of_strings(content["negative_factors"], emoji="❌", width=80),
                    alignment="left", line_height=1.5))
        summary_file = BytesIO()
        review_img.save(summary_file, format="JPEG")
        im_bytes = summary_file.getvalue()
        image_base64 = base64.b64encode(im_bytes).decode()
        link = f"https://store.steampowered.com/app/{app_result}"
        html2 = f"<a href='{link}'><img src='data:image/png;base64,{image_base64}'></a>"
        st.markdown(html2, unsafe_allow_html=True)
    with col_bug:
        options_bug = [
            "Description is not correct",
            "Too long",
            "Missing information",
            "Wrong bullet points",
            "Bullet points repeat",
            "Other"
        ]
        with st.popover("Is the summary wrong?", icon="❗️"):
            handle_bug_report()
    if date_cache is not None:
        st.write("Summary retrieved from previous date at ", date_cache.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        st.write("Summary generated now using AI.")
    st.json(content, expanded=False)