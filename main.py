from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import List
import os
import uuid
from datetime import datetime

app = FastAPI()

# ======== CORS (HTTP) ========
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======== IMAGE STORAGE CONFIG ========
UPLOAD_DIR = "/tmp/uploads"

# Make sure the upload directory exists
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Mount static files so images are served at /images/<filename>
app.mount("/images", StaticFiles(directory=UPLOAD_DIR), name="images")


@app.get("/")
async def root():
    return {"message": "FastAPI WebSocket chat server is running"}


# ========= CHAT WEBSOCKET (EXISTING) =========

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        # Send the message to all connected clients
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception as e:
                print("Error sending to a client:", e)


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            data = await websocket.receive_text()
            print(f"Received from client: {data}")

            # Broadcast whatever text we got (JSON from frontend)
            await manager.broadcast(data)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print("Unexpected error in websocket:", e)
        manager.disconnect(websocket)
        try:
            await websocket.close()
        except:
            pass


# ========= IMAGE UPLOAD & LISTING =========

@app.post("/upload-photo")
async def upload_photo(file: UploadFile = File(...)):
    """
    Upload a photo from React Native.
    Saves it to disk and returns info including a URL usable in the app.
    """

    print(f"/upload-photo called with filename={file.filename}, type={file.content_type}")

    # Basic validation – allow only some content types
    if file.content_type not in ("image/jpeg", "image/png", "image/jpg"):
        raise HTTPException(status_code=400, detail="Invalid image type")

    # Create a unique filename
    ext = os.path.splitext(file.filename)[1] or ".jpg"
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    # Save file to disk
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    # Build URL path (the React Native app will prefix with backend base URL)
    url_path = f"/images/{unique_name}"

    # Optional metadata (e.g., upload time)
    uploaded_at = datetime.utcnow().isoformat() + "Z"

    print(f" Saved file to {file_path}, url_path={url_path}")

    return {
        "filename": unique_name,
        "url": url_path,
        "uploaded_at": uploaded_at,
        "content_type": file.content_type,
    }


@app.get("/photos")
async def list_photos():
    """
    List all available photos in the uploads directory.
    Returns an array of { filename, url }.
    """

    files = []
    for fname in os.listdir(UPLOAD_DIR):
        # Simple filter: only image-looking files
        if fname.lower().endswith((".jpg", ".jpeg", ".png")):
            files.append(
                {
                    "filename": fname,
                    "url": f"/images/{fname}",
                }
            )

    # Sort: newest last (optional – here just alphabetical)
    files.sort(key=lambda x: x["filename"])

    return {"photos": files}

