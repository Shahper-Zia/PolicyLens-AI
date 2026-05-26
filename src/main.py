from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import Optional

from src.orchestrator.orchestrator import PolicyOrchestrator
policy_orchestrator = PolicyOrchestrator()

app = FastAPI(
    title="PolicyLens-AI",
    description="Payer Policy Intelligence API",
    version="1.0.0"
)

# =========================================================
# HEALTH ENDPOINTS
# =========================================================

@app.get("/")
async def root():
    return {
        "message": "PolicyLens-AI API Running",
        "status": "healthy"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy"
    }

# =========================================================
# MAIN EXTRACTION ENDPOINT
# =========================================================

from src.validation.output_schema import ExtractionResponse

@app.post("/extract", response_model=ExtractionResponse)
async def extract_policy(
    pdf_file: UploadFile = File(...),
    indication: Optional[str] = "Psoriasis",
    brand_names: Optional[str] = Form(None)
):

    # -----------------------------------------------------
    # VALIDATE FILE
    # -----------------------------------------------------

    if not pdf_file.filename.endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are allowed"
        )
    
    response = await policy_orchestrator.process_pdf(pdf_file, brand_names, indication)
    return response