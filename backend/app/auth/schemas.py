from pydantic import BaseModel, EmailStr, Field

Password = Field(min_length=8, max_length=128)


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Password
    display_name: str = Field(min_length=1, max_length=50)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class RefreshIn(BaseModel):
    refresh_token: str = Field(max_length=100)


class EmailIn(BaseModel):
    email: EmailStr


class TokenIn(BaseModel):
    token: str = Field(max_length=100)


class ResetPasswordIn(BaseModel):
    token: str = Field(max_length=100)
    new_password: str = Password


class ChangePasswordIn(BaseModel):
    current_password: str | None = Field(
        default=None, max_length=128, description="Omit only if the account has no password yet"
    )
    new_password: str = Password


class GoogleIn(BaseModel):
    id_token: str = Field(max_length=4096)


class Message(BaseModel):
    message: str
