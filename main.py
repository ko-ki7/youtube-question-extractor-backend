from googleapiclient.discovery import build
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import re
import csv
from fastapi.responses import StreamingResponse
from io import StringIO
import os
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()  # .envファイルの読み込み



app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CommentRequest(BaseModel):
    videoId: str
    mode: str

API_KEY = os.getenv("YOUTUBE_API_KEY")     # ここに自分のAPIキー
VIDEO_ID = "3zdPyHTDR3M"    # 対象の動画ID

def get_all_comments(api_key: str, video_id: str) -> list[str]:
    youtube = build("youtube", "v3", developerKey=api_key)

    comments: list[str] = []
    next_page_token = None

    while True:
        request = youtube.commentThreads().list(
            part="snippet",
            videoId=video_id,
            textFormat="plainText",
            maxResults=100,
            pageToken=next_page_token
        )
        response = request.execute()

        for item in response["items"]:
            text = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
            comments.append(text)

        if "nextPageToken" in response:
            next_page_token = response["nextPageToken"]
        else:
            break

    return comments

# 質問コメント判定
def is_question_comment(text: str) -> bool:
    # 驚き系の!?や?!を除外
    if re.search(r"[！？?!]{2,}", text):
        return False
    
    # 文末が? or ？なら質問とみなす
    if re.search(r"[?？]\s*$", text):
        return True
    
    # 「〜ですか」「〜でしょうか」などの質問文を判定
    question_patterns = [
        r".+ですか",
        r".+でしょうか",
        r".+ますか",
        r".+ましたか",
        r".+の？$",
        r".+なの？$",
    ]
    return any(re.search(p, text) for p in question_patterns)

# 質問コメントの抽出
@app.post("/comments")
def get_comments(req: CommentRequest):
    video_id = req.videoId
    mode = req.mode

    all_comments = get_all_comments(API_KEY, video_id)
    filtered_comments = [c for c in all_comments if is_question_comment(c)]

    return {
        "count": len(filtered_comments),
        "comments": filtered_comments
    }


# 質問コメントのCSVダウンロード
@app.get("/download_csv")
def download_csv(video_id: str):
    all_comments = get_all_comments(API_KEY, video_id)
    question_comments = [c for c in all_comments if is_question_comment(c)]

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["質問コメント"])
    for c in question_comments:
        writer.writerow([c])

    output.seek(0)
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=questions.csv"}
    )

