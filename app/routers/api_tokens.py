"""
API Token 管理路由
用户可以创建和管理 API Token，用于第三方应用调用
"""
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
import sqlite3
import hashlib
from app.core.database import SYSTEM_DB_PATH
from app.core.jwt_token import create_api_token, verify_api_token
from app.core.config import cfg

router = APIRouter()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class CreateTokenRequest(BaseModel):
    name: str  # Token 名称（如 "Home Assistant", "n8n" 等）
    expires_hours: Optional[int] = 24 * 30  # 默认 30 天


class TokenResponse(BaseModel):
    token: str
    name: str
    expires_at: str
    created_at: str


@router.post("/api/tokens/create")
async def create_token(request: Request, data: CreateTokenRequest):
    """创建 API Token"""
    # 检查登录状态
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")

    # 检查过期时间上限
    MAX_TOKEN_EXPIRE_HOURS = 24 * 365  # 最大 1 年
    if data.expires_hours and data.expires_hours > MAX_TOKEN_EXPIRE_HOURS:
        raise HTTPException(status_code=400, detail=f"过期时间不能超过 {MAX_TOKEN_EXPIRE_HOURS // 24} 天")

    # 检查是否为管理员
    is_admin = user.get("is_admin", False)
    
    # 创建 Token
    token = create_api_token(
        user_id=user.get("id", ""),
        username=user.get("name", ""),
        is_admin=is_admin
    )
    
    # 保存到数据库
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 计算过期时间
        from datetime import datetime, timedelta
        expires_at = datetime.utcnow() + timedelta(hours=data.expires_hours)
        created_at = datetime.utcnow()
        
        token_hash = _hash_token(token)
        c.execute("""
            INSERT INTO api_tokens (user_id, token, name, expires_at, created_at)
            VALUES (?, ?, ?, ?, ?)
        """, (
            user.get("id"),
            token_hash,
            data.name,
            expires_at.isoformat(),
            created_at.isoformat()
        ))
        
        conn.commit()
        conn.close()
        
        return {
            "status": "success",
            "token": token,
            "name": data.name,
            "expires_at": expires_at.isoformat(),
            "created_at": created_at.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建失败: {str(e)}")


@router.get("/api/tokens/list")
async def list_tokens(request: Request):
    """列出用户的所有 API Token"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        c.execute("""
            SELECT id, name, expires_at, created_at, last_used_at
            FROM api_tokens
            WHERE user_id = ?
            ORDER BY created_at DESC
        """, (user.get("id"),))
        
        tokens = []
        for row in c.fetchall():
            tokens.append({
                "id": row[0],
                "name": row[1],
                "expires_at": row[2],
                "created_at": row[3],
                "last_used_at": row[4]
            })
        
        conn.close()
        
        return {
            "status": "success",
            "tokens": tokens
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")


@router.delete("/api/tokens/{token_id}")
async def delete_token(request: Request, token_id: int):
    """删除 API Token"""
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="未登录")
    
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        
        # 只能删除自己的 Token
        c.execute("DELETE FROM api_tokens WHERE id = ? AND user_id = ?", 
                  (token_id, user.get("id")))
        
        conn.commit()
        conn.close()
        
        return {"status": "success", "message": "Token 已删除"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除失败: {str(e)}")


@router.get("/api/tokens/verify")
async def verify_token(request: Request):
    """验证 API Token（通过 Header 传递）"""
    # 从 Header 获取 Token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="缺少 Token")
    
    token = auth_header.replace("Bearer ", "")
    
    # 验证 Token
    payload = verify_api_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")
    
    # 更新最后使用时间
    try:
        conn = sqlite3.connect(SYSTEM_DB_PATH)
        c = conn.cursor()
        token_hash = _hash_token(token)
        c.execute("""
            UPDATE api_tokens
            SET last_used_at = datetime('now')
            WHERE token = ?
        """, (token_hash,))
        conn.commit()
        conn.close()
    except:
        pass  # 忽略更新失败
    
    return {
        "status": "success",
        "user": payload
    }
