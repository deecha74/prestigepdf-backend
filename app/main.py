from fastapi import FastAPI
from app.routers import (
    compress_word,
    pdf_image,
    image_to_pdf,
    protect_pdf,
    edit_pdf,
    watermark_pdf,
)
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="PrestigePDF API")
origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    # later: "https://prestigepdf.com"
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(compress_word.router)
app.include_router(pdf_image.router)
app.include_router(image_to_pdf.router)
app.include_router(protect_pdf.router)
app.include_router(edit_pdf.router)
app.include_router(watermark_pdf.router)
