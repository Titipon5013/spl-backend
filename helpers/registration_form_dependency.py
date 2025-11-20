from fastapi import Form, File, UploadFile
from pydantic import EmailStr

def get_registration_form(
    name: str = Form(...),
    email: EmailStr = Form(...),
    plate_number: str = Form(...),
    photo: UploadFile = File(...)
):
    return {
        "name": name,
        "email": email,
        "plate_number": plate_number,
        "plate_photo": photo,
    }
