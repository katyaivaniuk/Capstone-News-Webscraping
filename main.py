from slack_sdk import WebClient
import os
import json
from dotenv import load_dotenv
from requests_html import HTMLSession
from time import sleep
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lex_rank import LexRankSummarizer
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
import newspaper
import hashlib

env_path = '.env'
load_dotenv(env_path)
client = WebClient(token=os.environ['SLACK_BOT_TOKEN'])
session = HTMLSession()
keywords = ["Ukraine", "invasion", "war", "attack"]
json_filename = 'article_data.json'



def load_existing_data():
    """
    Load existing data from the JSON file.
    """
    existing_data = {}

    if os.path.exists(json_filename):
        with open(json_filename, 'r') as json_file:
            try:
                existing_data = json.load(json_file)
            except json.decoder.JSONDecodeError:
                pass

    return existing_data


def summarize_article(url, summary_sentences):
    article = newspaper.Article(url)
    try:
        article.download()
        article.parse()
        article_text = article.text

        parser = PlaintextParser.from_string(article_text, Tokenizer("english"))
        stemmer = Stemmer("english")
        summarizer = LexRankSummarizer(stemmer)
        summarizer.stop_words = get_stop_words("english")

        summary = summarizer(parser.document, summary_sentences)
        summary_text = ' '.join(str(sentence) for sentence in summary)
        return summary_text
    except newspaper.article.ArticleException as e:
        print(f"Error occurred while processing article '{url}': {str(e)}")
        return ""


def save_existing_data(existing_data):
    """
    Save existing data to the JSON file.
    """
    with open(json_filename, 'w') as json_file:
        json.dump(existing_data, json_file)


def generate_article_id(url):
    url_core = url.split('?')[0] 
    hash_object = hashlib.sha256(url_core.encode())
    article_id = hash_object.hexdigest()  # Convert the hash object to a hexadecimal string

    return article_id

def scrape_articles(url, scroll_down=2):
    """
    Scrape articles from the given URL.
    """
    r = session.get(url)
    r.html.render(sleep=1, scrolldown=scroll_down, timeout=30)
    return r.html.find('article')


def check_new_articles(articles):
    """
    Check for new articles and filter out excluded articles.
    """
    new_articles = []
    base_url = "https://news.google.com"
    for item in articles:
        try:
            # newsitem = item.find('h3', first=True)
            newsitem = item.find('a.JtKRv', first=True)
            title = newsitem.text
            link = base_url + newsitem.attrs.get('href').translate({ord('.'): None})
            date_element = item.find('time', first=True)


            if date_element is not None:
                publication_date = date_element.attrs['datetime']
                publication_year = int(publication_date[:4])
                publication_month = int(publication_date[5:7])

                if publication_year == 2024 and publication_month >= 4:
                    article_id = generate_article_id(link)
                

                    if article_id in existing_data:
                        continue

                    # Check if the article has already been posted
                    if article_id in sent_articles:
                        continue

                    # Create a new article object
                    newsarticle = {
                        'title': title,
                        'link': link,
                        'article_id': article_id
                    }
                    new_articles.append(newsarticle)
        except:
            pass

    return new_articles


def send_articles_to_slack(articles):
    """
    Send new articles as messages to Slack.
    """
    for article in articles:
        article_id = article['article_id']  # Use the article_id directly from the article object

        if article_id in existing_data:
            if existing_data[article_id]["status"] == "skipped":
                print(f"Article '{article['title']}' was previously skipped. Skipping...")
                continue
            print(f"Article '{article['title']}' has already been posted. Skipping...")
            continue

        summary_sentences = 4  # Specify the number of summary sentences
        summary = summarize_article(article['link'], summary_sentences)  # Use article['link'] directly

        message = f"*Article:* {article['title']}\n*Summary:* {summary}\n*Link:* {article['link']}"

        # ask for approval before sending the article to Slack
        response = input(f"Do you want to send this article to Slack?\n{message}\n(yes/no): ")

        if response.lower() == 'yes':
            client.chat_postMessage(channel="#ukraine-latest-news", text=message)

            existing_data[article_id] = {
                'title': article['title'],
                'status': 'posted'
            }
            sent_articles.add(article_id)
        elif response.lower() == 'no':
            print(f"Article '{article['title']}' will not be posted to Slack.")
            
            # store the article in the existing data dictionary as skipped
            existing_data[article_id] = {
                'title': article['title'],
                'status': 'skipped'
            }
        else:
            print("Invalid response. Article will not be posted to Slack.")

        sleep(1)



if __name__ == "__main__":
    # Load existing data
    existing_data = load_existing_data()
    sent_articles = set()

    # while True:
    articles1 = scrape_articles('https://news.google.com/search?q=ukraine&hl=en-GB&gl=GB&ceid=GB%3Aen', scroll_down=3)
    articles2 = scrape_articles('https://news.google.com/topics/CAAqLAgKIiZDQkFTRmdvTkwyY3ZNVEZ5Y0dSaWNXcDZjeElGWlc0dFIwSW9BQVAB?hl=en-GB&gl=GB&ceid=GB%3Aen', scroll_down=3)
    
    articles = articles1 + articles2 
    new_articles = check_new_articles(articles)
    send_articles_to_slack(new_articles)

    if len(new_articles) == 0:
        message_not = "No new articles available at the moment."
        print(message_not)

    save_existing_data(existing_data)

    # delay before the next iteration (1 hour)
    sleep(60 * 60)



