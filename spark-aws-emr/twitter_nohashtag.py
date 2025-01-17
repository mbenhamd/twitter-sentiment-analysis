import os
import sys
import re
import datetime
import json
import requests
from emoji.unicode_codes import UNICODE_EMOJI
from pyspark import SparkContext
from pyspark.sql import SparkSession
from textblob import TextBlob
from sklearn.externals import joblib


class Tweet:
    def __init__(self):
        url = "https://s3.eu-central-1.amazonaws.com/bucket/filename.pkl"
        r = requests.get(url)
        open('filename.pkl', 'wb').write(r.content)
        self.ml = joblib.load("filename.pkl")

    def extract_emojis(self, str):
        emojis = [UNICODE_EMOJI[c] for c in str if c in UNICODE_EMOJI]
        return list(set(emojis))

    def clean_text(self, datas):
        text = self.get_text(datas)
        line = re.sub('[A-Za-z0-9@#!.():/]', '', text)
        emojis = self.extract_emojis(line)
        tw = ' '.join(re.sub("(@[A-Za-z0-9]+)|([^.'’0-9A-Za-z \t])|(\w+:\/\/\S+)"," ",text).split())
        tw = tw.replace("RT", "")
        tw = re.sub(r"http\S+", "", tw.strip())
        datas["text_cleaned"] = tw.lower()
        datas["emojis"] = emojis
        return datas

    def get_text(self, data):
        if "retweeted_status" in data:
            if data["retweeted_status"]:
                if "extended_tweet" in data["retweeted_status"]:
                    return data["retweeted_status"]["extended_tweet"]["full_text"]
                return data["retweeted_status"]["text"]

        if "extended_tweet" in data:
            if data["extended_tweet"]:
                return data["extended_tweet"]["full_text"]
        return data["text"]

    def sentiment_analysis(self, data):
        analysis = TextBlob(data["text_cleaned"])
        if analysis.sentiment.polarity > 0:
            st = 'positive'
        elif analysis.sentiment.polarity == 0:
            st = 'neutral'
        else:
            st = 'negative'
        data["sentiment"] = st
        return data

    def emotion_analysis(self, data):
        txt = data["text_cleaned"]+" "+" ".join(data["emojis"])
        emotion = self.ml.predict([txt])
        data["emotion"] = emotion[0]
        return data

    def formatter(self, data):
        dd = datetime.datetime.strptime(data['created_at'], '%a %b %d %H:%M:%S +0000 %Y')
        if data["sentiment"] == "positive":
            data["sentiment"] = [1, 0, 0]
        if data["sentiment"] == "negative":
            data["sentiment"] = [0, 0, 1]
        if data["sentiment"] == "neutral":
            data["sentiment"] = [0, 1, 0]
        if data["emotion"] == "joy":
            data["emotion"] = [1, 0, 0, 0, 0]
        if data["emotion"] == "fear":
            data["emotion"] = [0, 1, 0, 0, 0]
        if data["emotion"] == "anger":
            data["emotion"] = [0, 0, 1, 0, 0]
        if data["emotion"] == "surprise":
            data["emotion"] = [0, 0, 0, 1, 0]
        if data["emotion"] == "sadness":
            data["emotion"] = [0, 0, 0, 0, 1]
        res = {
            "id" : data["id"],
            "user" : data["user"]["screen_name"],
            "emotion": data["emotion"],
            "sentiment": data["sentiment"],
            "retweet" : None,
            "year": 2017,
            "month" : dd.month,
            "day": dd.day,
            "hour": dd.hour,
            "minute":dd.minute
        }

        if "retweeted_status" in data :
            res["retweet"] = data["retweeted_status"]["user"]["screen_name"]

        return json.dumps(res)


def split(arr, size):
    arrs = []
    while len(arr) > size:
        pice = arr[:size]
        arrs.append(pice)
        arr = arr[size:]
    arrs.append(arr)
    return arrs

if __name__ == "__main__":
    tw = Tweet()
    sc = SparkContext()
    sc.setSystemProperty("com.amazonaws.services.s3.enableV4", "true")
    sc._jsc.hadoopConfiguration().set("com.amazonaws.services.s3.enableV4", "true")
    sc._jsc.hadoopConfiguration().set("mapreduce.fileoutputcommitter.algorithm.version", "2")
    sc._jsc.hadoopConfiguration().set("speculation", "false")
    sc._jsc.hadoopConfiguration().set("fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
    sc._jsc.hadoopConfiguration().set("fs.s3a.fast.upload", "true")
    sc._jsc.hadoopConfiguration().set("fs.s3a.endpoint", "s3-eu-central-1.amazonaws.com")

    sc._jsc.hadoopConfiguration().set("fs.s3a.access.key", "xxxxxxxxxx")
    sc._jsc.hadoopConfiguration().set("fs.s3a.secret.key", "xxxxxxxxxx")

    myRDD = sc.textFile("s3a://descartes-bdd/"+sys.argv[1])

    analyzed = myRDD.map(lambda line: json.loads(line))\
        .filter(lambda line: "lang" in line and line["lang"] == "en" )\
        .filter(lambda line: len(line["entities"]["hashtags"]) == 0 )\
        .map(tw.clean_text)\
        .map(tw.sentiment_analysis)\
        .map(tw.emotion_analysis)\
        .map(tw.formatter)

    analyzed.saveAsTextFile("s3a://descartes-bdd-processing/nohashtag/" + sys.argv[2] + "/")
