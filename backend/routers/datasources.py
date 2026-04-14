from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, cast, Text
from typing import List
import asyncio
import logging

from backend.database import get_db
from backend.models.datasource import Datasource
from backend.models.integration import Integration
from backend.models.soft_delete import alive_filter, alive_select, get_alive_by_id
from backend.schemas.datasource import (
    DatasourceCreate, DatasourceUpdate, DatasourceResponse, DatasourceTestResult, DatasourceTestRequest,
    DatasourceSilenceRequest, DatasourceSilenceResponse
)
from backend.utils.encryption import encrypt_value, decrypt_value
from backend.services.connection_diagnostic_service import ConnectionDiagnosticService
from backend.services.integration_scheduler import sync_datasource_schedule, unschedule_datasource
from backend.dependencies import get_current_user

logger = logging.getLogger(__name__)


def normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []

    normalized = []
    seen = set()
    for tag in tags:
        value = (tag or '').strip()
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(value)
    return normalized


async def validate_integration_binding(
    db: AsyncSession,
    metric_source: str | None,
    external_instance_id: str | None,
    inbound_source: dict | None,
):
    if metric_source != 'integration':
        return

    if not inbound_source:
        raise HTTPException(status_code=400, detail="使用集成采集时，必须配置 inbound_source")

    integration_ref = inbound_source.get("integration_id")
    if not integration_ref:
        raise HTTPException(status_code=400, detail="使用集成采集时，必须选择入站 Integration")

    integration = await get_alive_by_id(db, Integration, integration_ref)
    if not integration:
        raise HTTPException(status_code=400, detail="入站 Integration 不存在")

    if integration.integration_type != 'inbound_metric':
        raise HTTPException(status_code=400, detail="所选 Integration 不是入站指标集成")

    if integration.integration_id in {"builtin_aliyun_rds", "builtin_huaweicloud_rds", "builtin_tencentcloud_rds"} and not (external_instance_id or "").strip():
        raise HTTPException(status_code=400, detail="当前云厂商 RDS 外部采集必须填写实例 ID（external_instance_id）")


router = APIRouter(prefix="/api/datasources", tags=["datasources"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=List[DatasourceResponse])
async def list_datasources(
    q: str | None = None,
    db_type: str | None = None,
    importance_level: str | None = None,
    tags: str | None = None,
    db: AsyncSession = Depends(get_db)
):
    query = alive_select(Datasource)
    filters = []

    if q and q.strip():
        search = f"%{q.strip()}%"
        filters.append(
            or_(
                Datasource.name.ilike(search),
                Datasource.host.ilike(search),
                Datasource.database.ilike(search)
            )
        )

    if db_type and db_type.strip():
        filters.append(Datasource.db_type == db_type.strip())

    if importance_level and importance_level.strip():
        filters.append(Datasource.importance_level == importance_level.strip())

    filter_tags = normalize_tags((tags or '').replace('，', ',').split(','))
    for tag in filter_tags:
        filters.append(cast(Datasource.tags, Text).ilike(f'%"{tag}"%'))

    if filters:
        query = query.where(and_(*filters))

    result = await db.execute(query.order_by(Datasource.id.desc()))
    datasources = result.scalars().all()

    if filter_tags:
        lowered_tags = {tag.lower() for tag in filter_tags}
        datasources = [
            datasource for datasource in datasources
            if lowered_tags.issubset({(tag or '').strip().lower() for tag in (datasource.tags or []) if (tag or '').strip()})
        ]

    return datasources


@router.get("/latest-metrics")
async def get_datasources_latest_metrics(
    db: AsyncSession = Depends(get_db)
):
    """获取所有数据源的最新指标（轻量级接口，列表页使用）"""
    from sqlalchemy import select, desc
    from backend.models.metric_snapshot import MetricSnapshot

    # Get all datasources with their latest db_status metric
    result = await db.execute(
        select(MetricSnapshot)
        .where(MetricSnapshot.metric_type == 'db_status')
        .order_by(MetricSnapshot.datasource_id, desc(MetricSnapshot.id))
        .distinct(MetricSnapshot.datasource_id)
    )
    metrics = result.scalars().all()

    # Return as dict keyed by datasource_id
    return {
        m.datasource_id: {
            'cpu_usage': m.data.get('cpu_usage') if m.data else None,
            'qps': m.data.get('qps') if m.data else None,
            'connections_active': m.data.get('connections_active') if m.data else None,
        }
        for m in metrics
    }


@router.post("/check-status")
async def check_all_datasource_status(db: AsyncSession = Depends(get_db)):
    """批量检测所有数据源的连接状态"""
    from backend.utils.datetime_helper import now

    result = await db.execute(alive_select(Datasource).order_by(Datasource.id.desc()))
    datasources = result.scalars().all()
    diagnostic_service = ConnectionDiagnosticService(db)

    async def check_one(ds):
        diagnosis = await diagnostic_service.diagnose_datasource(ds.id, include_host_checks=False, include_tcp_checks=True)
        status = 'normal' if diagnosis.get('success') else 'failed'
        error = None if diagnosis.get('success') else diagnosis.get('summary') or diagnosis.get('message')
        return ds.id, status, error

    tasks = [check_one(ds) for ds in datasources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    checked_at = now()
    status_map = {}
    for r in results:
        if isinstance(r, Exception):
            continue
        ds_id, status, error = r
        status_map[ds_id] = {'status': status, 'error': error, 'checked_at': str(checked_at)}

    # 批量更新数据库
    for ds in datasources:
        if ds.id in status_map:
            ds.connection_status = status_map[ds.id]['status']
            ds.connection_error = status_map[ds.id]['error']
            ds.connection_checked_at = checked_at

    await db.commit()

    return status_map


@router.post("", response_model=DatasourceResponse)
async def create_datasource(data: DatasourceCreate, db: AsyncSession = Depends(get_db)):
    logger.info(f"Creating datasource: {data.name}")

    await validate_integration_binding(
        db,
        data.metric_source,
        data.external_instance_id,
        data.inbound_source,
    )

    # 先测试连接并获取版本信息
    db_version = None
    try:
        diagnostic_service = ConnectionDiagnosticService(db)
        result = await diagnostic_service.diagnose_connection_params(
            db_type=data.db_type,
            host=data.host,
            port=data.port,
            username=data.username,
            password=data.password,
            database=data.database,
            extra_params=data.extra_params,
            datasource_id=None,
            include_host_checks=False,
            include_tcp_checks=False,
        )
        if result.success:
            db_version = result.version
    except Exception as e:
        logger.warning(f"Failed to get version for datasource {data.name}: {e}")

    datasource = Datasource(
        name=data.name,
        db_type=data.db_type,
        host=data.host,
        port=data.port,
        username=data.username,
        password_encrypted=encrypt_value(data.password) if data.password else None,
        database=data.database,
        host_id=data.host_id,
        extra_params=data.extra_params,
        tags=normalize_tags(data.tags),
        importance_level=data.importance_level,
        metric_source=data.metric_source,
        external_instance_id=data.external_instance_id,
        inbound_source=data.inbound_source,
        db_version=db_version,
    )
    db.add(datasource)
    await db.commit()
    await db.refresh(datasource)
    await sync_datasource_schedule(datasource.id)

    logger.info(f"Created datasource {datasource.id}: {datasource.name}")
    return datasource


@router.get("/{datasource_id}", response_model=DatasourceResponse)
async def get_datasource(datasource_id: int, db: AsyncSession = Depends(get_db)):
    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")
    return datasource


@router.put("/{datasource_id}", response_model=DatasourceResponse)
async def update_datasource(datasource_id: int, data: DatasourceUpdate, db: AsyncSession = Depends(get_db)):
    logger.info(f"Updating datasource {datasource_id}")

    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    update_data = data.model_dump(exclude_unset=True)
    if "password" in update_data:
        pwd = update_data.pop("password")
        if pwd is not None:
            datasource.password_encrypted = encrypt_value(pwd)

    if "tags" in update_data:
        update_data["tags"] = normalize_tags(update_data["tags"])

    await validate_integration_binding(
        db,
        update_data.get("metric_source", datasource.metric_source),
        update_data.get("external_instance_id", datasource.external_instance_id),
        update_data.get("inbound_source", datasource.inbound_source),
    )

    for key, value in update_data.items():
        setattr(datasource, key, value)

    # 如果连接相关参数变化，重新采集版本信息
    connection_params_changed = any(k in update_data for k in ['host', 'port', 'username', 'password', 'database', 'db_type', 'extra_params'])
    if connection_params_changed:
        try:
            # 获取密码（可能是新密码或已加密的密码）
            password = update_data.get('password')
            if password is None and data.password is None:
                password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None

            diagnostic_service = ConnectionDiagnosticService(db)
            result = await diagnostic_service.diagnose_connection_params(
                db_type=update_data.get('db_type', datasource.db_type),
                host=update_data.get('host', datasource.host),
                port=update_data.get('port', datasource.port),
                username=update_data.get('username', datasource.username),
                password=password,
                database=update_data.get('database', datasource.database),
                extra_params=update_data.get('extra_params', datasource.extra_params),
                datasource_id=datasource_id,
                include_host_checks=False,
                include_tcp_checks=False,
            )
            if result.success:
                datasource.db_version = result.version
        except Exception as e:
            logger.warning(f"Failed to get version for datasource {datasource_id}: {e}")

    await db.commit()
    await db.refresh(datasource)
    await sync_datasource_schedule(datasource.id)

    logger.info(f"Updated datasource {datasource_id}: {datasource.name}")
    return datasource


@router.delete("/{datasource_id}")
async def delete_datasource(
    datasource_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    logger.info(f"Deleting datasource {datasource_id}")

    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    datasource.soft_delete(current_user.id)
    await db.commit()
    await unschedule_datasource(datasource_id)

    logger.info(f"Soft deleted datasource {datasource_id}")
    return {"message": "Datasource deleted"}


@router.post("/test", response_model=DatasourceTestResult)
async def test_datasource_connection(data: DatasourceTestRequest, db: AsyncSession = Depends(get_db)):
    """Test database connection with provided parameters (without saving to database)"""
    diagnostic_service = ConnectionDiagnosticService(db)
    try:
        password = data.password

        # If datasource_id is provided and password is None, use saved password
        if data.datasource_id is not None and password is None:
            result = await db.execute(select(Datasource).where(Datasource.id == data.datasource_id, alive_filter(Datasource)))
            datasource = result.scalar_one_or_none()
            if datasource and datasource.password_encrypted:
                password = decrypt_value(datasource.password_encrypted)

        return await diagnostic_service.diagnose_connection_params(
            db_type=data.db_type,
            host=data.host,
            port=data.port,
            username=data.username,
            password=password,
            database=data.database,
            extra_params=data.extra_params,
            datasource_id=data.datasource_id,
            include_host_checks=False,
            include_tcp_checks=True,
        )
    except Exception as e:
        logger.error(f"Failed to test connection to {data.host}:{data.port}: {e}", exc_info=True)
        return DatasourceTestResult(success=False, message=str(e))


@router.post("/{datasource_id}/test", response_model=DatasourceTestResult)
async def test_datasource(datasource_id: int, db: AsyncSession = Depends(get_db)):
    """Test database connection using saved datasource configuration"""
    from backend.utils.datetime_helper import now

    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    diagnostic_service = ConnectionDiagnosticService(db)
    diagnosis = await diagnostic_service.diagnose_datasource(
        datasource_id,
        include_host_checks=True,
        include_tcp_checks=True,
    )

    datasource.connection_status = 'normal' if diagnosis.get('success') else 'failed'
    datasource.connection_error = None if diagnosis.get('success') else diagnosis.get('summary') or diagnosis.get('message')
    datasource.connection_checked_at = now()

    # 更新版本信息
    if diagnosis.get('success') and diagnosis.get('version'):
        datasource.db_version = diagnosis.get('version')

    await db.commit()

    return diagnosis


@router.post("/{datasource_id}/silence", response_model=DatasourceSilenceResponse)
async def set_datasource_silence(
    datasource_id: int,
    request: DatasourceSilenceRequest,
    db: AsyncSession = Depends(get_db)
):
    """设置数据源临时静默（暂停监控和告警）"""
    from datetime import timedelta
    from backend.utils.datetime_helper import now

    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    # 计算静默截止时间
    silence_until = now() + timedelta(hours=request.hours)

    # 更新数据源
    datasource.silence_until = silence_until
    datasource.silence_reason = request.reason

    await db.commit()
    await db.refresh(datasource)

    logger.info(f"Set silence for datasource {datasource_id} ({datasource.name}) until {silence_until}, reason: {request.reason}")

    return DatasourceSilenceResponse(
        datasource_id=datasource_id,
        silence_until=silence_until,
        silence_reason=request.reason,
        is_silenced=True,
        remaining_hours=round(float(request.hours), 2)
    )


@router.delete("/{datasource_id}/silence", response_model=DatasourceSilenceResponse)
async def cancel_datasource_silence(
    datasource_id: int,
    db: AsyncSession = Depends(get_db)
):
    """取消数据源静默，恢复监控和告警"""
    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    # 清除静默配置
    datasource.silence_until = None
    datasource.silence_reason = None

    await db.commit()
    await db.refresh(datasource)

    logger.info(f"Cancelled silence for datasource {datasource_id} ({datasource.name})")

    return DatasourceSilenceResponse(
        datasource_id=datasource_id,
        silence_until=None,
        silence_reason=None,
        is_silenced=False,
        remaining_hours=None
    )


@router.get("/{datasource_id}/silence", response_model=DatasourceSilenceResponse)
async def get_datasource_silence_status(
    datasource_id: int,
    db: AsyncSession = Depends(get_db)
):
    """获取数据源静默状态"""
    from backend.utils.datetime_helper import now

    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    # 检查是否在静默期内
    is_silenced = False
    remaining_hours = None

    if datasource.silence_until:
        current_time = now()
        if current_time < datasource.silence_until:
            is_silenced = True
            remaining_seconds = (datasource.silence_until - current_time).total_seconds()
            remaining_hours = round(remaining_seconds / 3600, 2)
        else:
            # 静默已过期，自动清除
            datasource.silence_until = None
            datasource.silence_reason = None
            await db.commit()

    return DatasourceSilenceResponse(
        datasource_id=datasource_id,
        silence_until=datasource.silence_until,
        silence_reason=datasource.silence_reason,
        is_silenced=is_silenced,
        remaining_hours=remaining_hours
    )
