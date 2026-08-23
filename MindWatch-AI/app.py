from flask import Flask, render_template, request
import pickle
import re
import nltk
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer

# -----------------------
# Load Model & Vectorizer
# -----------------------

with open("models/stress_model.pkl", "rb") as f:
    model = pickle.load(f)

with open("models/tfidf_vectorizer.pkl", "rb") as f:
    vectorizer = pickle.load(f)

with open("models/emotion_model.pkl", "rb") as f:
    emotion_model = pickle.load(f)

with open("models/tfidf_emotion.pkl", "rb") as f:
    emotion_vectorizer = pickle.load(f)

# -----------------------
# Text Cleaning Function
# -----------------------

stop_words = set(stopwords.words("english"))
lemmatizer = WordNetLemmatizer()

def clean_text(text):
    text = text.lower()
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"[^a-z\s]", "", text)
    tokens = text.split()
    tokens = [w for w in tokens if w not in stop_words]
    tokens = [lemmatizer.lemmatize(w) for w in tokens]
    return " ".join(tokens)

# -----------------------
# Flask App
# -----------------------

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def home():
    prediction = None
    emotion = None

    if request.method == "POST":
        text = request.form["text"]
        cleaned = clean_text(text)

        # Stress prediction
        vec_stress = vectorizer.transform([cleaned])
        prediction = model.predict(vec_stress)[0]

        # Emotion prediction
        vec_emotion = emotion_vectorizer.transform([cleaned])
        emotion = emotion_model.predict(vec_emotion)[0]

    return render_template("index.html", prediction=prediction, emotion=emotion)

if __name__ == "__main__":
    app.run(debug=True)
