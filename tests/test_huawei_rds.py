import os
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkces.v1.region.ces_region import CesRegion
from huaweicloudsdkces.v1 import *
import time

def get_rds_metrics():
    # 1. 配置认证信息
    # 建议通过环境变量获取，避免硬编码
    ak = "您的Access Key ID"
    sk = "您的Secret Access Key"
    project_id = "您的项目ID"
    region_id = "cn-north-4" # 例如华北-北京四

    credentials = BasicCredentials(ak, sk, project_id)

    # 2. 初始化客户端
    client = CesClient.new_builder() \
        .with_credentials(credentials) \
        .with_region(CesRegion.value_of(region_id)) \
        .build()

    try:
        # 3. 构造请求参数
        # RDS 的命名空间固定为 'SYS.RDS'
        namespace = "SYS.RDS"
        metric_name = "cpu_util"
        instance_id = "你的RDS实例ID" # 在RDS控制台实例详情页查看

        # 设置查询时间范围（毫秒时间戳）
        end_time = int(time.time() * 1000)
        start_time = end_time - (3600 * 1000) # 获取过去1小时数据

        request = ListMetricsDataRequest(
            namespace=namespace,
            metric_name=metric_name,
            # dim.0=instance_id 是固定格式
            dim_0=f"instance_id,{instance_id}",
            from_=start_time,
            to=end_time,
            period="300", # 采样周期（秒），如300秒（5分钟）
            filter="average" # 聚合方式：average, min, max, sum
        )

        # 4. 执行并打印结果
        response = client.list_metrics_data(request)
        for data in response.datapoints:
            print(f"时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data.timestamp/1000))} | "
                  f"CPU利用率: {data.average}%")

    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    get_rds_metrics()