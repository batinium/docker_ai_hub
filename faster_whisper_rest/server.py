from fastapi import FastAPI, UploadFile, File, Form
from pydantic import BaseModel
from faster_whisper import WhisperModel
import tempfile, os

app = FastAPI()

MODEL_SIZE = os.getenv("WHISPER_MODEL", "small.en")
DEVICE = os.getenv("DEVICE", "cpu")
COMPUTE_TYPE = os.getenv("COMPUTE_TYPE", "int8")

model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)

class TranscribeResponse(BaseModel):
    text: str

@app.post("/v1/audio/transcriptions", response_model=TranscribeResponse)
async def transcribe(
    file: UploadFile = File(...),
    model_size: str = Form(None),
    language: str = Form("en")
):
    # Save the uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
        contents = await file.read()
        tmp.write(contents)
        tmp_path = tmp.name

    # If a model_size override was sent:
    if model_size and model_size != MODEL_SIZE:
        # optional: load a new model dynamically (but for simplicity we ignore)
        pass

    segments, _ = model.transcribe(tmp_path, language=language)
    os.remove(tmp_path)

    full_text = " ".join([seg.text for seg in segments])
    return TranscribeResponse(text=full_text)