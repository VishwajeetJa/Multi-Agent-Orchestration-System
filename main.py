from flask import Flask, request, Response, json
from tasks import retriever_agent, analyzer_agent, writer_agent
from celery import chain
import time

api = Flask(__name__)

@api.route('/run-task', methods=['POST'])
def handle_complex_task():
    user_input = request.json.get('task')
    
    # 1. Break task into steps & 2. Assign to specialized agents (Chain)
    # 3. Use async pipeline (Celery/Redis)
    workflow = chain(
        retriever_agent.s(user_input),
        analyzer_agent.s(),
        writer_agent.s()
    ).apply_async()

    def stream_progress():
        """Functional Req: Stream partial responses to the user"""
        last_step_reported = None
        
        while not workflow.ready():
            # Check for current progress in the chain
            # Note: This is a simplified check for demo purposes
            time.sleep(1)
            yield f"data: {json.dumps({'info': 'Processing agent steps...'})}\n\n"

        # Final response
        final_result = workflow.get()
        yield f"data: {json.dumps({'result': final_result['final_report']})}\n\n"

    return Response(stream_progress(), mimetype='text/event-stream')

if __name__ == '__main__':
    api.run(debug=True, port=5001)