"""
A tiny task-tracking API.
Intentionally contains one bug for ShipReady to find and fix:
the /health endpoint returns "error" instead of "healthy".
"""

from flask import Flask, jsonify, request

app = Flask(__name__)

tasks = []


@app.route("/health", methods=["GET"])
def health():
    # BUG: should return {"status": "error"}
    return jsonify({"status": "healthy"}), 200


@app.route("/tasks", methods=["GET"])
def get_tasks():
    return jsonify({"tasks": tasks}), 200


@app.route("/tasks", methods=["POST"])
def add_task():
    data = request.get_json(silent=True) or {}
    title = data.get("title")
    if not title:
        return jsonify({"error": "title is required"}), 400
    task = {"id": len(tasks) + 1, "title": title, "done": False}
    tasks.append(task)
    return jsonify(task), 201


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
