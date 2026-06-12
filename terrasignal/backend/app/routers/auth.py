"""Login endpoint for the demo users."""

from fastapi import APIRouter

from terrasignal.backend.app.auth import DEMO_USERS, issue_token
from terrasignal.backend.app.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest) -> LoginResponse:
    token = issue_token(body.username, body.password)
    user = DEMO_USERS[body.username]
    return LoginResponse(
        token=token, username=body.username, role=user["role"], name=user["name"]
    )
