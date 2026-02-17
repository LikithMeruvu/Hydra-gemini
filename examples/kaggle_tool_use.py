import requests
import json
import time

# --- Configuration ---
# 🌍 Your public URL from Cloudflared
# (Make sure to remove any trailing slashes!)
BASE_URL = "https://mainland-literally-worthy-distribute.trycloudflare.com/v1"
API_KEY = "tui-1JHR5e_uigihPWNo-m1-i1qhJy-FMrCmtLnPPSZdQwU"

# --- 1. Define the Tool ---
# This is the standard OpenAI tool definition format
tool_definition = {
    "type": "function",
    "function": {
        "name": "get_current_weather",
        "description": "Get the current weather in a given location",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {
                    "type": "string",
                    "description": "The city and state, e.g. San Francisco, CA",
                },
                "unit": {
                    "type": "string",
                    "enum": ["celsius", "fahrenheit"],
                },
            },
            "required": ["location"],
        },
    },
}

# --- 2. Initial Request (with Tool) ---
print(f"📡 Sending request to {BASE_URL}...")

payload = {
    "model": "gemini-2.5-flash",
    "messages": [
        {"role": "user", "content": "What's the weather like in Tokyo right now?"}
    ],
    "tools": [tool_definition],
    "tool_choice": "auto"  # Let the model decide whether to call the tool
}

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {API_KEY}"
}

try:
    response = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()
    
    print("\n✅ Initial Response Received:")
    print(json.dumps(data, indent=2))
    
    # --- 3. Handle Tool Call ---
    message = data["choices"][0]["message"]
    tool_calls = message.get("tool_calls")
    
    if tool_calls:
        print(f"\n🛠️  Model called {len(tool_calls)} tool(s)!")
        
        # Simulate executing the tool
        # In a real app, you'd call your actual function here
        fake_weather_response = {
            "location": "Tokyo",
            "temperature": "22",
            "unit": "celsius",
            "description": "Sunny"
        }
        
        tool_call_id = tool_calls[0]["id"]
        function_name = tool_calls[0]["function"]["name"]
        function_args = json.loads(tool_calls[0]["function"]["arguments"])
        
        print(f"   Function: {function_name}")
        print(f"   Args: {function_args}")
        print(f"   -> Returning Simulated Result: {fake_weather_response}")
        
        # --- 4. Send Tool Result Back ---
        # Construct the conversation history:
        # User -> Assistant (with tool_calls) -> Tool (result)
        messages = payload["messages"]
        messages.append(message)  # Add the assistant's request to call tool
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": function_name,
            "content": json.dumps(fake_weather_response)
        })
        
        # Second request to get the final answer
        payload2 = {
            "model": "gemini-2.5-flash",
            "messages": messages,
             # We can omit tools here if we don't expect more tool calls, 
             # but keeping them is fine.
        }
        
        print("\n📡 Sending tool output back to model...")
        response2 = requests.post(f"{BASE_URL}/chat/completions", headers=headers, json=payload2)
        response2.raise_for_status()
        final_data = response2.json()
        
        print("\n✅ Final Answer:")
        print(final_data["choices"][0]["message"]["content"])
        
    else:
        print("\n⚠️ Model did not call the tool. It might have answered directly.")
        print(message["content"])

except requests.exceptions.RequestException as e:
    print(f"\n❌ Error: {e}")
    if hasattr(e, 'response') and e.response:
        print(f"Response Body: {e.response.text}")
