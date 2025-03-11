from flask import Flask, request, jsonify, render_template
import traceback  # For detailed error logging

# Import the AI agent
from workflow import chat_agent  # This now imports the ChatAgent instance

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('chat.html')

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    message = data.get('message', '')

    try:
        print(f"Received message: {message}")  # Debugging input

        # Process the message using the AI agent
        response = chat_agent.invoke(message)
        
        print(f"Chatbot Response: {response}")  # Debugging output

        return jsonify({
            "response": response,
            "state": {"last_message": message},
            "continue_chat": True
        })
    
    except Exception as e:
        print(f"Error: {e}")  # Print error message
        traceback.print_exc()  # Print full error traceback for debugging

        return jsonify({
            "response": "I apologize, but I couldn't process your request at this time. Please try again.",
            "state": {},
            "continue_chat": True
        })

if __name__ == '__main__':
    app.run(debug=True)