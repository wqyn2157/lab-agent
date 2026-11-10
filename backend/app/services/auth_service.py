from sqlalchemy.orm import Session
from app.common.exceptions import BusinessException
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, RegisterRequest
from app.schemas.user import UserResponse
from app.utils.JWT import create_access_token
from app.utils.password import hash_password, verify_password


def login(db: Session, data: LoginRequest):
    # 根据用户账号查询数据库
    user = db.query(User).filter(User.username == data.username).first()

    # 判断账号和密码是否正确
    if not user:
        raise BusinessException(message="账号不存在")
    if not verify_password(data.password, user.password):
        raise BusinessException(message="密码错误")
    # 判断账号是否被禁用
    if user.status == 0:
        raise BusinessException(message="账号已被禁用")
    # 创建token
    token = create_access_token(user.id)
    return LoginResponse(token=token, user=UserResponse.model_validate(user))


def register(db: Session, data: RegisterRequest):
    # 根据用户账号查询数据库
    user = db.query(User).filter(User.username == data.username).first()
    if user:
        raise BusinessException(message="账号已存在")
    user_model = User(
        username=data.username,
        password=hash_password(data.password),
        name=data.name or data.username,
        role="student",
        status=1,
    )
    db.add(user_model)
    db.commit()
    db.refresh(user_model)
