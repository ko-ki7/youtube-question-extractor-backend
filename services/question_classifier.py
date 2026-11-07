from services.openai_service import classify_question

QUESTION_PATTERNS = [
    "?",
    "？",
    "ですか",
    "ますか",
    "でしょうか",
]


def extract_questions(comments):

    questions = []

    for comment in comments:

        # ①ルール判定
        if any(word in comment for word in QUESTION_PATTERNS):
            questions.append(comment)
            continue

        # ②GPT判定
        try:
            if classify_question(comment):
                questions.append(comment)

        except Exception as e:
            print(e)

    return questions