from flask import Flask, request, jsonify
from tasks import retriever_agent, analyzer_agent, writer_agent
from celery import chain

app = Flask(__name__)

@app.route('/process', methods=['POST'])
def manage_task():
    data = request.json
    user_query = data.get('query')
    
    if not user_query:
        return jsonify({"error": "No query provided"}), 400

    
    workflow = chain(
        retriever_agent.s(user_query),
        analyzer_agent.s(),
        writer_agent.s()
    ).apply_async()

    return jsonify({
        "status": "Task chains started",
        "task_id": workflow.id
    }), 202

@app.route('/result/<task_id>', methods=['GET'])
def get_status(task_id):
    result = writer_agent.AsyncResult(task_id)
    if result.ready():
        return jsonify({"status": "Completed", "report": result.result})
    return jsonify({"status": "Processing..."})

if __name__ == '__main__':
    app.run(debug=True)