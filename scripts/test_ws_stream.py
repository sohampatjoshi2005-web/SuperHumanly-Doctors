import sys
import os
import json
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from app.main import app
from app.core.config import settings
from app.api.v1.auth import create_access_token
from app.db_models import User
from app.db import get_session

def test_websocket_streaming():
    """
    Self-contained integration test for the Real-time STT WebSocket Proxy.
    Mocks external Sarvam connection and asserts binary forwarding and Celery task execution.
    """
    print("🚀 Starting WebSocket streaming integration test...")
    
    # 1. Create a mock user token
    with get_session() as session:
        from sqlmodel import select
        # Use an existing seed user or admin
        user = session.exec(select(User)).first()
        if not user:
            print("⚠️ No user found in database. Seeding a temp test user...")
            from app.api.v1.auth import get_password_hash
            user = User(
                username="test_ws_doctor",
                email="test_ws@superhumanly.com",
                hashed_password=get_password_hash("password123"),
                role="doctor",
                full_name="WS Tester",
                is_active=True
            )
            session.add(user)
            session.commit()
            session.refresh(user)

    token = create_access_token(data={"sub": user.username})
    
    # 2. Mock websockets.connect context manager
    mock_sarvam_ws = AsyncMock()
    
    # Simulate receiving a transcript frame from Sarvam
    mock_sarvam_ws.recv.side_effect = [
        json.dumps({"transcript": "Hello Doctor", "is_final": True}),
        # Keep waiting after that to simulate idle
        asyncio.TimeoutError()
    ]
    
    mock_connect = MagicMock()
    mock_connect.__aenter__.return_value = mock_sarvam_ws
    
    # 3. Patch Celery process_clinical_task and websockets.connect
    mock_task_obj = MagicMock()
    mock_task_obj.delay.return_value = MagicMock(id="mock_celery_task_12345")
    
    with patch("websockets.connect", return_value=mock_connect), \
         patch("app.workers.ai_tasks.process_clinical_task", new=mock_task_obj):
        
        client = TestClient(app)
        
        # Connect to endpoint
        ws_url = f"/v1/streaming/audio?token={token}&customer_id=123&to_email=test@rx.com&email_subject=WS_Rx"
        
        with client.websocket_connect(ws_url) as websocket:
            print("✓ WebSocket connection accepted by FastAPI backend.")
            
            # Send initial binary audio frame
            websocket.send_bytes(b"\x00\x00\x00\x00")
            print("✓ Sent binary audio chunk.")
            
            # Receive real-time transcript response from Sarvam proxy
            response = websocket.receive_json()
            print(f"✓ Received streaming transcript frame: {response}")
            assert response["type"] == "transcript"
            assert response["text"] == "Hello Doctor"
            
            # Send stop command frame
            websocket.send_json({"action": "stop"})
            print("✓ Sent STOP command frame.")
            
            # Receive final completed frame with Celery task ID
            final_response = websocket.receive_json()
            print(f"✓ Received final completion frame: {final_response}")
            assert final_response["type"] == "completed"
            assert final_response["task_id"] == "mock_celery_task_12345"
            
            # 4. Verify Celery task was triggered with correct arguments
            mock_task_obj.delay.assert_called_once()
            args, kwargs = mock_task_obj.delay.call_args
            assert kwargs["data_type"] == "text"
            assert kwargs["payload"]["transcript"] == "Hello Doctor"
            assert kwargs["payload"]["to_email"] == "test@rx.com"
            assert kwargs["customer_id"] == "123"
            assert kwargs["doctor_id"] == str(user.id)
            print("✅ All assertions passed! WebSocket Proxy successfully forwards audio, bridges to Sarvam, and triggers Celery Swarm.")

if __name__ == "__main__":
    test_websocket_streaming()
