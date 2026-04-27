import asyncio
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from backend.config import get_settings
from backend.database import async_session
from backend.models.user import User
from backend.models.host import Host
from backend.models.soft_delete import alive_filter, get_alive_by_id
from backend.services.session_service import SessionService
from backend.services.ssh_connection_pool import get_ssh_pool

logger = logging.getLogger(__name__)
router = APIRouter()


async def _authenticate_websocket(websocket: WebSocket) -> User | None:
    """验证 WebSocket 用户身份"""
    session_id = websocket.cookies.get(get_settings().session_cookie_name)
    async with async_session() as db:
        session = await SessionService.get_active_session(db, session_id)
        if not session:
            return None
        result = await db.execute(select(User).where(User.id == session.user_id, alive_filter(User)))
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            return None
        await SessionService.touch_session(db, session)
        await db.commit()
        return user


@router.websocket("/ws/terminal/{host_id}")
async def terminal_websocket(websocket: WebSocket, host_id: int):
    """主机 Terminal WebSocket 连接"""
    # 1. 认证
    user = await _authenticate_websocket(websocket)
    if not user:
        await websocket.close(code=1008, reason="Invalid or expired session")
        return

    # 2. 权限检查（仅管理员可访问 Terminal）
    if not user.is_admin:
        await websocket.close(code=1008, reason="Insufficient permissions")
        return

    # 3. 验证主机存在
    async with async_session() as db:
        host = await get_alive_by_id(db, Host, host_id)
        if not host:
            await websocket.close(code=1008, reason="Host not found")
            return

    await websocket.accept()
    logger.info(f"Terminal WebSocket connected for host {host_id}, user {user.id}")

    channel = None
    try:
        # 4. 获取 SSH 连接并创建 PTY
        async with async_session() as db:
            ssh_pool = get_ssh_pool()
            async with ssh_pool.get_connection(db, host_id) as ssh_client:
                # 创建交互式 shell
                loop = asyncio.get_event_loop()

                def _invoke_shell():
                    return ssh_client.invoke_shell(
                        term='xterm-256color',
                        width=80,
                        height=24
                    )

                channel = await loop.run_in_executor(None, _invoke_shell)
                logger.info(f"PTY shell created for host {host_id}")

                # 5. 启动双向转发任务
                async def forward_to_websocket():
                    """SSH PTY 输出 -> WebSocket"""
                    try:
                        while True:
                            if channel.recv_ready():
                                data = await loop.run_in_executor(None, lambda: channel.recv(4096))
                                if data:
                                    decoded = data.decode('utf-8', errors='replace')
                                    await websocket.send_json({'type': 'output', 'data': decoded})
                            else:
                                await asyncio.sleep(0.01)
                    except Exception as e:
                        logger.debug(f"Forward to websocket ended: {e}")

                async def forward_to_ssh():
                    """WebSocket 输入 -> SSH PTY"""
                    try:
                        while True:
                            msg = await websocket.receive_json()
                            if msg['type'] == 'input':
                                data = msg['data']
                                await loop.run_in_executor(None, lambda: channel.send(data))
                            elif msg['type'] == 'resize':
                                cols = msg.get('cols', 80)
                                rows = msg.get('rows', 24)
                                await loop.run_in_executor(None, lambda: channel.resize_pty(width=cols, height=rows))
                                logger.debug(f"Terminal resized to {cols}x{rows}")
                    except WebSocketDisconnect:
                        logger.info(f"WebSocket disconnected for host {host_id}")
                    except Exception as e:
                        logger.debug(f"Forward to ssh ended: {e}")

                # 并发执行双向转发
                await asyncio.gather(
                    forward_to_websocket(),
                    forward_to_ssh(),
                    return_exceptions=True
                )

    except Exception as e:
        logger.error(f"Terminal WebSocket error for host {host_id}: {e}")
        try:
            await websocket.send_json({'type': 'error', 'message': str(e)})
        except Exception:
            pass
    finally:
        # 清理资源
        if channel:
            try:
                channel.close()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass
        logger.info(f"Terminal WebSocket closed for host {host_id}")
