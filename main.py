from googleapiclient.discovery import build
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import csv
from fastapi.responses import StreamingResponse
from io import StringIO
import os
import stripe
from dotenv import load_dotenv
from pydantic import BaseModel
from services.question_classifier import extract_questions
from database import init_db
from contextlib import asynccontextmanager
from database import create_user, get_user_by_email, hash_password, verify_password
from database import start_pro, is_pro_user


load_dotenv()  # .envファイルの読み込み

# lifespan で起動時・終了時の処理を書く
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 起動時
    init_db()
    print("データベースを初期化しました")
    yield
    # 終了時（必要ならここに書く）
    print("アプリを終了します")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CommentRequest(BaseModel):
    videoId: str

class UserRegister(BaseModel):
    email: str
    password: str
    name: str = None

class UserLogin(BaseModel):
    email: str
    password: str

class StartProRequest(BaseModel):
    user_id: int
    days: int = 30

class CreateCheckoutRequest(BaseModel):
    user_id: int

API_KEY = os.getenv("YOUTUBE_API_KEY")     # ここに自分のAPIキー
VIDEO_ID = "3zdPyHTDR3M"    # 対象の動画ID

stripe.api_key = os.getenv("STRIPE_SECRET_KEY") # Stripeの設定

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

@app.post("/create-checkout-session")
def create_checkout_session(req: CreateCheckoutRequest):
    try:
        checkout_session = stripe.checkout.Session.create(
            line_items=[
                {
                    "price_data": {
                        "currency": "jpy",
                        "product_data": {
                            "name": "Proプラン（1ヶ月）",
                        },
                        "unit_amount": 980,  # 980円
                    },
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url="https://youtube-question-extractor-frontend.vercel.app?success=true&user_id=" + str(req.user_id),
            cancel_url="https://youtube-question-extractor-frontend.vercel.app?canceled=true",
            metadata={
                "user_id": req.user_id
            }
        )
        return {"url": checkout_session.url}
    except Exception as e:
        return {"error": str(e)}

@app.post("/register")
def register(user: UserRegister):
    # 既に存在するかチェック
    existing = get_user_by_email(user.email)
    if existing:
        return {"error": "このメールアドレスは既に登録されています"}
    
    # ユーザー作成
    password_hash = hash_password(user.password)
    user_id = create_user(user.email, password_hash, user.name)
    
    return {"message": "登録完了", "user_id": user_id}

@app.post("/login")
def login(user: UserLogin):
    db_user = get_user_by_email(user.email)
    if not db_user or not verify_password(user.password, db_user["password_hash"]):
        return {"error": "メールアドレスまたはパスワードが間違っています"}
    
    return {
        "message": "ログイン成功",
        "user_id": db_user["id"],
        "email": db_user["email"],
        "name": db_user["name"],
        "plan": db_user["plan"]
    }

@app.post("/start-pro")
def start_pro_plan(req: StartProRequest):
    # Proを開始
    sub_id = start_pro(req.user_id, days=req.days)
    
    return {
        "message": "Proプランを開始しました",
        "subscription_id": sub_id,
        "user_id": req.user_id
    }

@app.get("/payment-success")
def payment_success(user_id: int):
    # 決済成功後にProを開始
    start_pro(user_id, days=30)
    return {"message": "Proプランを開始しました", "user_id": user_id}

@app.get("/is-pro/{user_id}")
def check_pro(user_id: int):
    is_pro = is_pro_user(user_id)
    return {
        "user_id": user_id,
        "is_pro": is_pro
    }

# 質問コメントの抽出
@app.post("/comments")
def get_comments(req: CommentRequest):

    all_comments = get_all_comments(API_KEY, req.videoId)

    limited_comments = all_comments[:100]

    question_comments = extract_questions(
        limited_comments
    )

    return {
        "count": len(question_comments),
        "comments": question_comments
    }


# 質問コメントのCSVダウンロード
@app.get("/download_csv")
def download_csv(video_id: str):
    all_comments = get_all_comments(API_KEY, video_id)

    question_comments = extract_questions(all_comments)

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

