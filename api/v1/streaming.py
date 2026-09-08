from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from app.api.v1.auth import get_current_user_ws
from app.core.config import settings
import asyncio
import logging
import json
from uuid import uuid4

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/streaming", tags=["streaming"])

@router.websocket("/audio")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(None),
    customer_id: str = Query(None),
    to_email: str = Query(None),
    email_subject: str = Query(None)
):
    """
    Secure Real-time WebSocket Speech-to-Text Proxy.
    Exposes a WebSocket to the physician client, forwards binary audio to Sarvam AI,
    renders real-time partial/final transcripts, and triggers Celery LangGraph upon stop.
    """
    await websocket.accept()
    
    user = await get_current_user_ws(token)
    if not user:
        logger.warning("⚠️ WebSocket connection rejected: Unauthorized token.")
        await websocket.close(code=1008)  # Policy Violation
        return

    session_id = str(uuid4())
    logger.info(f"🎤 Real-time STT WebSocket session {session_id} established for user: {user.username}")
    
    base_url = settings.sarvam_base_url or "https://api.sarvam.ai"
    model = settings.sarvam_speech_model or "saaras:v3"
    sarvam_ws_url = (
        base_url.replace("https://", "wss://").replace("http://", "ws://").rstrip("/") 
        + f"/speech-to-text/ws?language-code=en-IN&model={model}&mode=transcribe&input_audio_codec=pcm_s16le&sample_rate=16000&vad_signals=true&high_vad_sensitivity=true"
    )
    
    headers = {
        "api-subscription-key": settings.sarvam_api_key
    }
    
    # Accumulators for real-time transcription
    committed_transcript = ""
    last_partial = ""
    
    try:
        import websockets
        async with websockets.connect(
            sarvam_ws_url,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=20
        ) as sarvam_ws:
            
            logger.info(f"🔌 Connected to Sarvam STT WebSocket cloud proxy for session {session_id}")
            
            stop_requested = False
            # Start a continuous FFmpeg process to transcode WebM chunks to raw PCM (s16le, 16000Hz, mono)
            ffmpeg_process = await asyncio.create_subprocess_exec(
                "ffmpeg",
                "-y",
                "-i", "pipe:0",
                "-f", "s16le",
                "-ac", "1",
                "-ar", "16000",
                "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL
            )
            
            # Forward binary audio data to Sarvam and listen for control text messages
            async def client_listener():
                nonlocal stop_requested
                try:
                    while not stop_requested:
                        # Receive either text control frame or binary audio
                        message = await websocket.receive()
                        
                        if "bytes" in message:
                            if ffmpeg_process.returncode is None:
                                try:
                                    ffmpeg_process.stdin.write(message["bytes"])
                                    await ffmpeg_process.stdin.drain()
                                except (BrokenPipeError, ConnectionResetError):
                                    logger.error("❌ ffmpeg stdin closed unexpectedly.")
                        elif "text" in message:
                            try:
                                data = json.loads(message["text"])
                                if data.get("action") == "stop":
                                    logger.info(f"⏹️ Session stop requested by doctor for session {session_id}")
                                    stop_requested = True
                                    break
                            except Exception:
                                pass
                except WebSocketDisconnect:
                    logger.info(f"📴 Client WebSocket disconnected for session: {session_id}")
                    stop_requested = True
                except Exception as ex:
                    logger.error(f"❌ Error in client listener loop: {ex}")
                    stop_requested = True
                finally:
                    if ffmpeg_process.returncode is None:
                        try:
                            ffmpeg_process.stdin.close()
                        except Exception:
                            pass
            
            # Read continuous PCM output from FFmpeg and stream to Sarvam
            async def ffmpeg_reader():
                import base64
                nonlocal stop_requested
                try:
                    while not stop_requested:
                        # Read 4096 bytes of PCM data at a time
                        pcm_chunk = await ffmpeg_process.stdout.read(4096)
                        if not pcm_chunk:
                            # EOF reached
                            break
                        
                        audio_b64 = base64.b64encode(pcm_chunk).decode("utf-8")
                        payload = {
                            "audio": {
                                "data": audio_b64,
                                "encoding": "audio/wav",
                                "sample_rate": 16000
                            }
                        }
                        await sarvam_ws.send(json.dumps(payload))
                except Exception as ex:
                    logger.error(f"❌ Error reading ffmpeg output: {ex}")
                finally:
                    if ffmpeg_process.returncode is None:
                        try:
                            ffmpeg_process.terminate()
                        except ProcessLookupError:
                            pass
            
            # Receive transcripts from Sarvam and pipe them back to the client
            async def sarvam_listener():
                nonlocal committed_transcript, last_partial, stop_requested
                try:
                    while not stop_requested:
                        try:
                            # Read streaming output from Sarvam WS
                            response = await asyncio.wait_for(sarvam_ws.recv(), timeout=1.0)
                            data = json.loads(response)
                            
                            msg_type = data.get("type", "")
                            
                            # Support both {"transcript": "text"} and {"type": "transcript", "text": "text"} formats
                            transcript_chunk = ""
                            if "transcript" in data:
                                transcript_chunk = data["transcript"]
                            elif "text" in data:
                                transcript_chunk = data["text"]
                            elif msg_type == "transcript" and "text" in data:
                                transcript_chunk = data["text"]
                                
                            is_final = data.get("is_final", msg_type == "transcript")
                            
                            if transcript_chunk:
                                chunk_str = transcript_chunk.strip()
                                if is_final and chunk_str:
                                    committed_transcript += " " + chunk_str
                                    last_partial = ""
                                else:
                                    last_partial = transcript_chunk
                                    
                                # Send real-time transcript update to browser client
                                await websocket.send_json({
                                    "type": "transcript",
                                    "session_id": session_id,
                                    "text": transcript_chunk,
                                    "is_final": is_final
                                })
                        except asyncio.TimeoutError:
                            # Keep-alive or periodic check
                            continue
                except websockets.exceptions.ConnectionClosed:
                    logger.info("🔌 Sarvam WebSocket closed connection.")
                except Exception as ex:
                    logger.error(f"❌ Error in Sarvam receiver loop: {ex}")

            # Run parallel listener/sender streams concurrently
            await asyncio.gather(client_listener(), ffmpeg_reader(), sarvam_listener())
            
    except Exception as e:
        logger.error(f"❌ WebSocket streaming pipeline error: {e}")
        try:
            await websocket.send_json({"type": "error", "message": "ASR streaming engine failed"})
        except Exception:
            pass
    finally:
        # Assemble final transcript combining committed and any leftover partial text
        final_transcript = committed_transcript.strip()
        if not final_transcript and last_partial.strip():
            final_transcript = last_partial.strip()
            
        logger.info(f"📜 Final assembled transcript for session {session_id}: {final_transcript[:100]}...")
        
        if final_transcript:
            from app.workers.ai_tasks import process_clinical_task
            
            # Trigger background parallel LangGraph swarm immediately using the pre-compiled transcript
            celery_task = process_clinical_task.delay(
                data_type="text",
                payload={
                    "transcript": final_transcript,
                    "to_email": to_email,
                    "email_subject": email_subject
                },
                doctor_id=str(user.id),
                customer_id=customer_id,
                username=user.username,
                clinic_id=user.clinic_id
            )
            logger.info(f"🚀 Spawned LangGraph Celery task {celery_task.id} for session {session_id}")
            
            try:
                # Share the task ID with the client so they can immediately subscribe to SSE updates
                await websocket.send_json({
                    "type": "completed",
                    "session_id": session_id,
                    "task_id": celery_task.id
                })
            except Exception:
                pass
        
        try:
            await websocket.close()
        except Exception:
            pass

@router.get("/events/{task_id}")
async def sse_task_events(task_id: str, token: str = Query(None)):
    """
    Task 59.3.1: Server-Sent Events (SSE) for real-time AI results.
    """
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse
    from app.workers.ai_tasks import process_clinical_task
    from app.api.v1.auth import get_current_user_ws

    user = await get_current_user_ws(token)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")

    async def event_generator():
        # Connect to Celery task result to monitor progress
        res = process_clinical_task.AsyncResult(task_id)
        
        last_node = None
        
        while not res.ready():
            if res.status == 'PROGRESS' or res.status == 'STARTED':
                info = res.info or {}
                current_node = info.get("current_node")
                partial = info.get("partial_result")
                
                if current_node and current_node != last_node:
                    last_node = current_node
                    yield f"data: {json.dumps({'event': 'node_complete', 'node': current_node, 'partial': partial})}\n\n"
            
            await asyncio.sleep(0.5)
            
        # Final result
        if res.successful():
            yield f"data: {json.dumps({'event': 'completed', 'result': res.result})}\n\n"
        else:
            yield f"data: {json.dumps({'event': 'failed', 'error': str(res.result)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
