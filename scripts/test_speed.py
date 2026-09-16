import asyncio
import time
import os
import sys

# Add app to path
sys.path.append(os.getcwd())

from app.core.langgraph.graph import build_graph

async def test_processing_speed():
    print("🚀 INITIALIZING SPEED TEST (Strategies 2 & 4)...")
    
    # Simulate a long 12-minute transcript (~2000 words)
    long_transcript = """
    Patient presents with fever and cough for 3 days. 
    "I have been feeling very weak," says the patient.
    ASR Error: I took some parasite mall and it helped.
    Doctor: We should check for pharyngitis. 
    ASR Error: A tour of staten might be needed for your cholesterol.
    """ * 40 # Multiply to make it large
    
    initial_state = {
        "transcript": long_transcript,
        "historical_context": "No significant history.",
        "to_email": "test@example.com",
        "email_subject": "Speed Test"
    }
    
    graph = build_graph()
    
    start_time = time.time()
    print(f"📦 Input size: {len(long_transcript)} characters (~{len(long_transcript.split())} words)")
    print("🧪 Running parallelized graph...")
    
    # We use astream to verify Strategy 5 (Partial updates)
    events_received = 0
    async for event in graph.astream(initial_state):
        events_received += 1
        if not isinstance(event, dict): continue
        for node_name, state_update in event.items():
            elapsed = time.time() - start_time
            print(f"⏱️ [{elapsed:.2f}s] Node '{node_name}' completed.")
            if state_update and isinstance(state_update, dict):
                if "cleaned_text" in state_update:
                    print(f"   ✅ Cleanup done (Chunked & Parallel)")
                if "rx" in state_update:
                    print(f"   ✅ Extraction done (Speculative)")

    total_time = time.time() - start_time
    print(f"\n✨ SPEED TEST COMPLETE ✨")
    print(f"⏱️ Total Time: {total_time:.2f} seconds")
    print(f"📡 Total Events: {events_received}")
    
    if total_time < 15:
        print("✅ PERFORMANCE TARGET MET: Sub-15s for long transcript.")
    else:
        print("⚠️ PERFORMANCE TARGET MISSED: Optimization needed.")

if __name__ == "__main__":
    asyncio.run(test_processing_speed())
