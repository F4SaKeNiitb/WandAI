
import requests
import time
import json
import sys

BASE_URL = "http://localhost:8000/api"

def run_test():
    print("🧪 Testing Agent-Level Ambiguity Checks...")
    
    # 1. Submit a request with a CLEAR high-level goal but an AMBIGUOUS specific step
    # We want the Orchestrator to pass (clarity > threshold) but the Analyst agent to fail
    payload = {
        "request": "Research Apple's 2024 revenue. Then analyze the data using the 'Zylophian consumption method' to calculate future growth."
    }
    
    print(f"\n1. Submitting request: {payload['request']}")
    response = requests.post(f"{BASE_URL}/execute", json=payload)
    if response.status_code != 200:
        print(f"❌ Failed to submit request: {response.text}")
        return
        
    session_id = response.json()["session_id"]
    print(f"✅ Session started: {session_id}")
    
    # 2. Poll status until we hit WAITING_STEP_CLARIFICATION or COMPLETED/ERROR
    step_clarification_needed = False
    step_id = None
    questions = []
    
    for i in range(60):
        time.sleep(2)
        status_res = requests.get(f"{BASE_URL}/status/{session_id}")
        data = status_res.json()
        status = data["status"]
        
        print(f"   Status: {status}")
        
        if status == "waiting_clarification":
            print("ℹ️ Orchestrator requested initial clarification (expected). Providing it...")
            clarify_payload = {
                "session_id": session_id,
                "clarifications": ["The Zylophian method is a fictional method for testing purposes."]
            }
            requests.post(f"{BASE_URL}/clarify", json=clarify_payload)
            continue

        if status == "waiting_step_clarification":
            step_clarification_needed = True
            step_id = data.get("step_clarification_step_id")
            questions = data.get("step_clarification_questions", [])
            print(f"✅ Detected Step Clarification State!")
            print(f"   Step ID: {step_id}")
            print(f"   Questions: {questions}")
            break
            
        if status in ["completed", "error"]:
            print(f"❌ Ended with status: {status} (Expected waiting_step_clarification)")
            if status == "error":
                print(f"   Error: {data.get('error_message')}")
            return
            
    if not step_clarification_needed:
        print("❌ Timed out waiting for step clarification")
        return
        
    # 3. Submit Step Clarification
    print(f"\n2. Submitting Step Clarification for step '{step_id}'...")
    clarify_payload = {
        "session_id": session_id,
        "step_id": step_id,
        "clarifications": ["Just calculate the standard growth rate based on 2024 data."]
    }
    
    clarify_res = requests.post(f"{BASE_URL}/step-clarify", json=clarify_payload)
    if clarify_res.status_code != 200:
        print(f"❌ Failed to submit clarification: {clarify_res.text}")
        return
        
    print("✅ Clarification submitted successfully")
    
    # 4. Wait for completion
    print("\n3. Waiting for completion...")
    for i in range(30):
        time.sleep(2)
        status_res = requests.get(f"{BASE_URL}/status/{session_id}")
        data = status_res.json()
        status = data["status"]
        
        print(f"   Status: {status}")
        
        if status == "completed":
            print("✅ Workflow Completed Successfully!")
            print(f"   Final Response: {data.get('final_response')[:100]}...")
            return
            
        if status == "error":
            print(f"❌ Workflow Failed: {data.get('error_message')}")
            return

    print("❌ Timed out waiting for completion")

if __name__ == "__main__":
    run_test()
