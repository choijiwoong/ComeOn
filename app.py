from flask import Flask, request, render_template, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return render_template("index.html")

@app.route('/result')
def result():
    query = request.args.get('query')
    return render_template("result.html", query=query)

@app.route('/api/search')
def search_api():
    query = request.args.get('query')
    # 여기에 실제 검색 로직 구현
    result = f"'{query}'에 대한 검색 결과입니다."
    return jsonify({"result": result})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

