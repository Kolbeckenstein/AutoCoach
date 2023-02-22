import praw, time, json
import urllib3
from dataclasses import dataclass
from os import makedirs, environ
from os.path import exists

@dataclass(unsafe_hash=True)
class FormcheckPost:
    url: str
    hash: str


class Credentials:
    client_id = os.environ["REDDIT_CLIENT_ID"]
    client_secret = os.environ["REDDIT_CLIENT_SECRET"]
    user_agent = "AutoCoach Scraper by u/kolbeckenstein_dev"

class VideoDownloader:
    
    def __init__(self, download_path: str):
        self.download_path = download_path

    def download(self, url: str, flair_target: str):
        chunk_size = 8192

        http = urllib3.PoolManager()
        r = http.request('GET', url, preload_content=False)

        directory_path = self.download_path + "/" + flair_target + "/"

        if not exists(directory_path):
            makedirs(directory_path)

        with open(directory_path + url.split("/")[-2] + ".mp4", 'wb') as out:
            while True:
                data = r.read(chunk_size)
                if not data:
                    break
                out.write(data)

        r.release_conn()

class Scrapper:
    def scrape(credentials: Credentials, flair_target: str):
        reddit = praw.Reddit(client_id = credentials.client_id, 
                            client_secret = credentials.client_secret, 
                            user_agent = credentials.user_agent) 

        subreddit = reddit.subreddit('formcheck')

        # posts = subreddit.hot(limit=100)
        posts = subreddit.search('flair:"' + flair_target + '}"', limit=10, syntax='lucene')

        #  for submission in subReddit.search('flair:"'+flairName[0]+'"', sort='new', syntax='lucene', limit=999):
        # submission.flair.select(flairName[1])
        # print(submission.title)

        vids = []

        print(vids)

        for post in posts:
            try:
                url = post.media['reddit_video']['fallback_url']
                print(url)
                url = url.split("?")[0]
                name = post.title[:30].rstrip() + ".mp4"
                vids.append((url, name, post))
            except:
                pass

        print(f"{len(vids)} {flair_target} videos found")

        downloader = VideoDownloader("./data")
        for vid in vids:
            downloader.download(vid[0], flair_target)
            print("downloaded video")
            name = vid[0].split("/")[-2]
            with open(f"./data/{flair_target}/{name}.json", "w+") as outfile:
                json_dict = {"lift" : flair_target}
                outfile.write(json.dumps(json_dict))
                print("wrote json")
            time.sleep(2)
            

if __name__ == "__main__":
    lifts = ["Deadlift", "Squat", "Bench Press"]
    for lift in lifts:
        Scrapper.scrape(Credentials(), lift)

"""
Iteration 1:
script calls for last x videos
create a 
"""

#Algorithm: Dynamic Time Warping