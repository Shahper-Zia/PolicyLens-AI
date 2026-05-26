from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class BrandAttribute(BaseModel):
    filename: Optional[str] = Field(default="")
    brand: Optional[str] = Field(default="")
    indication: Optional[str] = Field(default="")
    age: Optional[str] = Field(default="")
    step_therapy_requirements: Optional[str] = Field(default="")
    number_of_steps_brands: Optional[str] = Field(default="")
    number_of_steps_generic: Optional[str] = Field(default="")
    step_through_phototherapy: Optional[str] = Field(default="")
    tb_test_required: Optional[str] = Field(default="")
    initial_auth_duration: Optional[str] = Field(default="")
    reauthorization_duration: Optional[str] = Field(default="")
    reauthorization_required: Optional[str] = Field(default="")
    reauthorization_requirements: Optional[str] = Field(default="")
    specialist_types: Optional[str] = Field(default="")
    quantity_limits: Optional[str] = Field(default="")
    access_score: Optional[str] = Field(default="")

class ExtractionResponse(BaseModel):
    filename: Optional[str] = Field(default="")
    detected_brands: Optional[List[str]] = Field(default_factory=list)
    brand_attributes: Optional[List[BrandAttribute]] = Field(default_factory=list)