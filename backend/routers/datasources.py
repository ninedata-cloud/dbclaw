from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, cast, Text
from typing import List
import asyncio
import logging

from backend.database import get_db, async_session
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
async def list_datasource(
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
    datasource = result.scalars().all()

    if filter_tags:
        lowered_tags = {tag.lower() for tag in filter_tags}
        datasource = [
            datasource for datasource in datasource
            if lowered_tags.issubset({(tag or '').strip().lower() for tag in (datasource.tags or []) if (tag or '').strip()})
        ]

    return datasource


@router.get("/latest-metrics")
async def get_datasource_latest_metrics(
    db: AsyncSession = Depends(get_db)
):
    """获取所有数据源的最新指标（轻量级接口，列表页使用）"""
    from sqlalchemy import select, desc
    from backend.models.datasource_metric import DatasourceMetric

    # Get all datasource with their latest db_status metric
    result = await db.execute(
        select(DatasourceMetric)
        .where(DatasourceMetric.metric_type == 'db_status')
        .order_by(DatasourceMetric.datasource_id, desc(DatasourceMetric.id))
        .distinct(DatasourceMetric.datasource_id)
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
    datasource = result.scalars().all()
    diagnostic_service = ConnectionDiagnosticService(db)

    async def check_one(ds):
        diagnosis = await diagnostic_service.diagnose_datasource(ds.id, include_host_checks=False, include_tcp_checks=True)
        status = 'normal' if diagnosis.get('success') else 'failed'
        error = None if diagnosis.get('success') else diagnosis.get('summary') or diagnosis.get('message')
        return ds.id, status, error

    tasks = [check_one(ds) for ds in datasource]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    checked_at = now()
    status_map = {}
    for r in results:
        if isinstance(r, Exception):
            continue
        ds_id, status, error = r
        status_map[ds_id] = {'status': status, 'error': error, 'checked_at': str(checked_at)}

    # 批量更新数据库
    for ds in datasource:
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

    # 清理指标标准化器缓存，防止内存泄漏
    from backend.services.metric_normalizer import MetricNormalizer
    MetricNormalizer.clear_cache(datasource_id)

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


@router.get("/{datasource_id}/top-sql")
async def get_datasource_top_sql(
    datasource_id: int,
    limit: int = 100,
    db: AsyncSession = Depends(get_db)
):
    """获取数据源 TOP SQL 统计信息"""
    from backend.services.mysql_service import MySQLConnector
    from backend.services.postgres_service import PostgreSQLConnector
    from backend.services.sqlserver_service import SQLServerConnector
    from backend.services.oracle_service import OracleConnector
    from backend.services.opengauss_service import OpenGaussConnector
    from backend.services.hana_service import HANAConnector
    from backend.utils.encryption import decrypt_value

    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    try:
        password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None

        # 根据数据库类型创建服务
        if datasource.db_type in {"mysql", "tdsql-c-mysql"}:
            service = MySQLConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
            )
        elif datasource.db_type == "postgresql":
            service = PostgreSQLConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
            )
        elif datasource.db_type == "sqlserver":
            service = SQLServerConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
                **(datasource.extra_params or {}),
            )
        elif datasource.db_type == "oracle":
            service = OracleConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
                **(datasource.extra_params or {}),
            )
        elif datasource.db_type == "opengauss":
            service = OpenGaussConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
            )
        elif datasource.db_type == "hana":
            service = HANAConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
                **(datasource.extra_params or {}),
            )
        else:
            raise HTTPException(status_code=400, detail=f"不支持的数据库类型: {datasource.db_type}")

        # 检查服务是否支持 get_top_sql 方法
        if not hasattr(service, 'get_top_sql'):
            raise HTTPException(
                status_code=400,
                detail=f"数据库类型 {datasource.db_type} 暂不支持 TOP SQL 功能"
            )

        top_sql_list = await service.get_top_sql(limit=min(limit, 500))
        return {
            "datasource_id": datasource_id,
            "datasource_name": datasource.name,
            "db_type": datasource.db_type,
            "total_count": len(top_sql_list),
            "data": top_sql_list,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get TOP SQL for datasource {datasource_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取 TOP SQL 失败: {str(e)}")


@router.post("/{datasource_id}/explain-sql")
async def explain_sql(
    datasource_id: int,
    request: dict,
    db: AsyncSession = Depends(get_db)
):
    """获取 SQL 执行计划"""
    from backend.services.mysql_service import MySQLConnector
    from backend.services.postgres_service import PostgreSQLConnector
    from backend.services.sqlserver_service import SQLServerConnector
    from backend.services.oracle_service import OracleConnector
    from backend.services.opengauss_service import OpenGaussConnector
    from backend.services.hana_service import HANAConnector
    from backend.utils.encryption import decrypt_value

    sql_text = request.get("sql_text")
    if not sql_text:
        raise HTTPException(status_code=400, detail="SQL 文本不能为空")

    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    try:
        password = decrypt_value(datasource.password_encrypted) if datasource.password_encrypted else None

        # 根据数据库类型创建服务
        if datasource.db_type in {"mysql", "tdsql-c-mysql"}:
            service = MySQLConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
            )
        elif datasource.db_type == "postgresql":
            service = PostgreSQLConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
            )
        elif datasource.db_type == "sqlserver":
            service = SQLServerConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
                **(datasource.extra_params or {}),
            )
        elif datasource.db_type == "oracle":
            service = OracleConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
                **(datasource.extra_params or {}),
            )
        elif datasource.db_type == "opengauss":
            service = OpenGaussConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
            )
        elif datasource.db_type == "hana":
            service = HANAConnector(
                host=datasource.host,
                port=datasource.port,
                username=datasource.username,
                password=password,
                database=datasource.database,
                **(datasource.extra_params or {}),
            )
        else:
            raise HTTPException(status_code=400, detail=f"不支持的数据库类型: {datasource.db_type}")

        # 检查服务是否支持 explain_sql 方法
        if not hasattr(service, 'explain_sql'):
            raise HTTPException(
                status_code=400,
                detail=f"数据库类型 {datasource.db_type} 暂不支持执行计划功能"
            )

        explain_result = await service.explain_sql(sql_text)
        return {
            "datasource_id": datasource_id,
            "sql_text": sql_text,
            "explain_result": explain_result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to explain SQL for datasource {datasource_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取执行计划失败: {str(e)}")


@router.post("/{datasource_id}/diagnose-sql")
async def diagnose_sql(
    datasource_id: int,
    request: dict,
    db: AsyncSession = Depends(get_db)
):
    """AI 诊断 SQL 性能问题"""
    from backend.services.ai_agent import get_ai_client, request_text_response
    from backend.models.ai_model import AIModel
    from backend.routers.ai_models import decrypt_api_key
    from sqlalchemy import select

    sql_text = request.get("sql_text")
    sql_stats = request.get("sql_stats", {})

    if not sql_text:
        raise HTTPException(status_code=400, detail="SQL 文本不能为空")

    datasource = await get_alive_by_id(db, Datasource, datasource_id)
    if not datasource:
        raise HTTPException(status_code=404, detail="数据源不存在")

    try:
        # 构建诊断提示词
        prompt_parts = [
            "请你作为资深数据库运维专家，针对下面这个 SQL 语句的性能问题做诊断分析。",
            "",
            "【分析目标】",
            "请判断该 SQL 是否存在性能问题、风险等级如何，并给出优化建议。",
            "",
            "【实例信息】",
            f"- 实例名称：{datasource.name}",
            f"- 数据库类型：{datasource.db_type}",
            f"- 主机：{datasource.host}:{datasource.port}",
        ]

        if datasource.database:
            prompt_parts.append(f"- 数据库：{datasource.database}")

        prompt_parts.extend([
            "",
            "【SQL 统计信息】",
        ])

        if sql_stats:
            if sql_stats.get("exec_count"):
                prompt_parts.append(f"- 执行次数：{sql_stats['exec_count']}")
            if sql_stats.get("total_time_sec"):
                prompt_parts.append(f"- 总执行时间：{sql_stats['total_time_sec']} 秒")
            if sql_stats.get("avg_time_sec"):
                prompt_parts.append(f"- 平均执行时间：{sql_stats['avg_time_sec']} 秒")
            if sql_stats.get("total_rows_scanned"):
                prompt_parts.append(f"- 总扫描行数：{sql_stats['total_rows_scanned']}")
            if sql_stats.get("avg_rows_scanned"):
                prompt_parts.append(f"- 平均扫描行数：{sql_stats['avg_rows_scanned']}")
            if sql_stats.get("total_wait_time_sec"):
                prompt_parts.append(f"- 总等待时间：{sql_stats['total_wait_time_sec']} 秒")

        prompt_parts.extend([
            "",
            "【SQL 文本】",
            sql_text[:3000] if len(sql_text) > 3000 else sql_text,
            "",
            "【输出要求】",
            "1. SQL 性能状态判断（是否存在性能问题）",
            "2. 主要性能瓶颈或风险点",
            "3. 可能的根因分析",
            "4. 具体的优化建议（索引、改写、配置等）",
            "5. 如果信息不足，请明确指出需要补充哪些信息（如执行计划、表结构等）",
        ])

        prompt = "\n".join(prompt_parts)

        # 获取 AI 模型配置
        result = await db.execute(
            select(AIModel)
            .filter(AIModel.is_active == True)
            .order_by(AIModel.is_default.desc(), AIModel.id.asc())
        )
        model = result.scalars().first()
        if not model:
            raise HTTPException(status_code=500, detail="未配置可用的 AI 模型")

        ai_client = get_ai_client(
            api_key=decrypt_api_key(model.api_key_encrypted),
            base_url=model.base_url,
            model_name=model.model_name,
            protocol=getattr(model, "protocol", "openai"),
            reasoning_effort=getattr(model, "reasoning_effort", None),
        )
        if not ai_client:
            raise HTTPException(status_code=500, detail="AI 客户端初始化失败")

        diagnosis_result = await request_text_response(
            ai_client=ai_client,
            messages=[{"role": "user", "content": prompt}]
        )

        return {
            "datasource_id": datasource_id,
            "sql_text": sql_text,
            "diagnosis": diagnosis_result,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to diagnose SQL for datasource {datasource_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI 诊断失败: {str(e)}")
