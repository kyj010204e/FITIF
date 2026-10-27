from fastapi import FastAPI
from ocr_router import router

app = FastAPI()
app.include_router(router)