from pydantic import BaseModel, EmailStr, field_validator


class UserOut(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None = None
    company_name: str | None = None


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None
    company_name: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if len(v) > 128:
            raise ValueError("Password must not exceed 128 characters.")
        has_letter = any(c.isalpha() for c in v)
        has_digit_or_symbol = any(not c.isalpha() for c in v)
        if not (has_letter and has_digit_or_symbol):
            raise ValueError("Password must contain at least one letter and one number or special character.")
        return v



class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class SSORequest(BaseModel):
    provider: str  # "google" | "microsoft" | "outlook" | "gmail"
    email: EmailStr | None = None
    full_name: str | None = None
    company_name: str | None = None



class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds, for the access token


class LoginResponse(BaseModel):
    user: UserOut
    tokens: TokenPair


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
