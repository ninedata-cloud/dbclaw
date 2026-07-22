#!/usr/bin/env python3
"""
主机指标收集诊断脚本
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def diagnose():
    from backend.database import async_session
    from backend.models.host import Host
    from backend.models.host_metric import HostMetric
    from sqlalchemy import select, desc
    from datetime import datetime, timedelta

    print("=" * 60)
    print("Host Metric Collection Diagnostics")
    print("=" * 60)

    async with async_session() as db:
        # 1. 检查主机数量
        result = await db.execute(select(Host))
        host = result.scalars().all()
        print(f"\n1. Hosts: {len(host)}")

        if len(host) == 0:
            print("   ⚠ No hosts are configured")
            return

        # 2. 检查每个主机的指标
        for host in host:
            print(f"\n2. Host: {host.name} ({host.host}:{host.port})")
            print(f"   Username: {host.username}")
            print(f"   Authentication method: {host.auth_type}")

            # 获取最新指标
            metric_result = await db.execute(
                select(HostMetric)
                .where(HostMetric.host_id == host.id)
                .order_by(desc(HostMetric.collected_at))
                .limit(1)
            )
            metric = metric_result.scalar_one_or_none()

            if metric:
                print("   ✓ Metric data is available")
                print(f"   - CPU: {metric.cpu_usage:.1f}%")
                print(f"   - Memory: {metric.memory_usage:.1f}%")
                print(f"   - Disk: {metric.disk_usage:.1f}%")
                print(f"   - Collected at: {metric.collected_at}")

                # 检查数据新鲜度
                now = datetime.now()  # Use local time since DB stores local time
                # Make metric.collected_at timezone-aware if it isn't
                metric_time = metric.collected_at
                if metric_time.tzinfo is None:
                    # DB stores local time without timezone info
                    metric_time = metric_time
                age = (now - metric_time).total_seconds()
                if age > 300:
                    print(f"   ⚠ Data is stale (collected {age:.0f} seconds ago)")
                else:
                    print(f"   ✓ Data is fresh (collected {age:.0f} seconds ago)")
            else:
                print("   ✗ No metric data is available")

            # 获取最近5分钟的指标数量
            five_min_ago = datetime.now() - timedelta(minutes=5)
            count_result = await db.execute(
                select(HostMetric)
                .where(HostMetric.host_id == host.id)
                .where(HostMetric.collected_at >= five_min_ago)
            )
            recent_count = len(count_result.scalars().all())
            print(f"   Collections in the last 5 minutes: {recent_count}")

        # 3. 测试 SSH 连接
        print("\n3. Test SSH Connections")
        for host in host[:3]:  # 只测试前3个
            print(f"\n   Testing host: {host.name}")
            try:
                from backend.services.ssh_connection_pool import get_ssh_pool
                ssh_pool = get_ssh_pool()

                async with ssh_pool.get_connection(db, host.id) as ssh_client:
                    # 测试简单命令
                    loop = asyncio.get_event_loop()
                    stdin, stdout, stderr = await loop.run_in_executor(
                        None, ssh_client.exec_command, "echo 'test'"
                    )
                    output = await loop.run_in_executor(None, stdout.read)
                    result = output.decode('utf-8').strip()

                    if result == 'test':
                        print("   ✓ SSH connection is healthy")

                        # 测试指标采集命令
                        commands = {
                            "CPU": "top -bn1 | grep 'Cpu(s)' | awk '{print $2}' | cut -d'%' -f1",
                            "Memory": "free | grep Mem | awk '{print ($3/$2) * 100.0}'",
                            "Disk": "df -h / | tail -1 | awk '{print $5}' | cut -d'%' -f1"
                        }

                        for name, cmd in commands.items():
                            stdin, stdout, stderr = await loop.run_in_executor(
                                None, ssh_client.exec_command, cmd
                            )
                            output = await loop.run_in_executor(None, stdout.read)
                            error = await loop.run_in_executor(None, stderr.read)
                            result = output.decode('utf-8').strip()
                            err_msg = error.decode('utf-8').strip()

                            if result:
                                print(f"   ✓ {name} command: {result}")
                            else:
                                print(f"   ✗ {name} command failed")
                                if err_msg:
                                    print(f"      Error: {err_msg}")
                    else:
                        print("   ✗ SSH connection is unhealthy")

            except Exception as e:
                print(f"   ✗ Connection failed: {e}")

        print("\n" + "=" * 60)
        print("Diagnostics completed")
        print("=" * 60)

if __name__ == "__main__":
    asyncio.run(diagnose())
