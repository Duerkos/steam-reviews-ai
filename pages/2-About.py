import streamlit as st

st.page_link("Search.py", label=":red-background[**Back to search**]")

st.title("About Steam Reviews AI")

st.markdown("""
## Project Summary

**Steam Reviews AI** is a Streamlit-powered web application that analyzes and summarizes user reviews for Steam games using a cloud LLM.  
It fetches reviews directly from the Steam API, checks previous history in a cloud database, and generates concise summaries to help users quickly understand the strengths and weaknesses of any game.

### How it Works

1. **Game Search:**  
   - Gets the current list of all games from the Steam API. https://api.steampowered.com/ISteamApps/GetAppList/v2/?
   - Searches by title using fuzzy matching for similarity.
   - Shows up to 30 most likely games, with review stats and icons.

2. **Game Analysis:**  
   - When you select a game, a banner and its stats appear.
   - Clicking "analysis" fetches the top 20 English reviews (using Steam's own ranking).  https://partner.steamgames.com/doc/store/getreviews 
   - These reviews are sent to Mistral AI for summarization.
   - If a recent summary (less than 30 days old, with at least 90% of current reviews) exists in the Neon database, it is reused for speed.

3. **Summary Output:**  
   - The agent summarizes the reviews, infers a description, gives a score (0–10), and lists positive/negative factors.
   - Results are shown as images and markdown for easy reading.
   - Users can report issues to help improve future summaries, by giving feedback to change the prompt or model.

---

## Why?

I've always wanted a quick way to see what a game is about and what Steam users really think—especially the negative opinions. I would love for Steam to have something like this. 
Often I try reading reviews to find out why a game had a low or high score, but it takes too long to find out.
This project also helped me practice Streamlit, set up my first cloud database, and experiment with agentic AI.
One of the goals of this project is to try getting Valve attention to add a feature like this to Steam.

I have a previous project that tries doing something similar with no LLM involved, it was a bravado of "I am sure this can be done without LLMs". You can check it here https://steam-reviews.streamlit.app/ or here, since it is easy to deploy or use locally https://github.com/Duerkos/steam-reviews. The results are fun but it feels a bit like going to an oracle that speaks in riddles to know about something...

---

## Setup

- **Hosting:** Streamlit Cloud (free tier)
- **Database:** Neon (cloud, free tier)
- **AI Provider:** Mistral (model: small-latest, free tier)
- **Tech:** Python and libraries, Streamlit, Pictex (new library!), Pillow

You may encounter rate limits due to free tiers.

---

## Prompt Used for Summarization

> You are going to get some reviews for a specific videogame on Steam. Sometimes they contain jokes or sarcasm reviews, these should be ignored. Try to infer a description of the game based on the reviews in a short paragraph with at most 100 words, then give it a score from 0 to 10 based on the feelings. Then list positive factors, and negative factors by order of importance, at most 10 total factors, around 5 words each. If the game is more positive than negative, give more positive factors than negative. In example, if the game has a score of 8 you should list 8 positive factors and 2 negative factors. Try to always give one negative or positive factor at least. Give the output in json.

**Notes:**  
The AI often ignores the limits on factors, so the code enforces them. The prompt was refined to improve results—requesting the score before the factors works best. You can inspect the full output by clicking the three dots at the end of any summary page.

---

## About the Developer

This project was created by Vicente Arce David, with the alias "Duerkos".
You can find me on [GitHub](https://github.com/Duerkos/). I also have a landing page at https://duerkos.github.io/landing-page/.
I have setup a [Ko-fi](https://ko-fi.com/duerkos) page to support my work, if you like this project consider supporting me there.

---

## Contributing
If you want to contribute, feel free to open an issue or pull request on the [GitHub repository](https://github.com/Duerkos/steam-reviews-ai).
If you want to make your own version, you can fork it or just grab the idea and do your own thing. If you make something public, I would love to be citated but what I really want is you to let me know about the new project!

In case you want to provide links here, remember the summary can be provided directly by http://steam-review.streamlit.app/Summary?appid=<appid>.
Please do not do scraping! the setup is on free tiers and it is easy to replicate if you already have a web app.

---

## Issues or feedback
If you find any issues or bugs, or just want to share your thoughts, please use the [GitHub issues page](https://github.com/Duerkos/steam-reviews-ai/issues).

Most of UI weirdness is due to streamlit. Currently on mobile you can't put two elements side by side. I think it is planned for the future, but it is not available yet.

---

## License

This project is licensed under the [MIT License](https://opensource.org/licenses/MIT).

```
MIT License

Copyright (c) 2025 Vicente Arce David, "Duerkos"

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### Citation

If you use this project in your research or publication, please cite as:

```
@software{steam_reviews_ai_2025,
  author = {Vicente Arce David, "Duerkos"},
  title = {Steam Reviews AI},
  year = {2025},
  url = {https://github.com/Duerkos/steam-reviews-ai}
}
```
""")