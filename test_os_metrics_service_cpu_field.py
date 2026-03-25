from backend.services.os_metrics_service import OSMetricsService


class FakeSSH:
    def execute_multi(self, commands, timeout=30):
        return {
            commands[0]: "37.2",
            commands[1]: "100 50 50 50",
            commands[2]: "100 50 50 50%",
            commands[3]: "0.1 0.2 0.3",
            commands[4]: "1 2",
            commands[5]: "3 4",
            commands[6]: "5",
        }


def test_os_metrics_service_outputs_cpu_usage():
    metrics = OSMetricsService(FakeSSH()).collect()

    assert metrics["cpu_usage"] == 37.2
    assert "cpu_usage_percent" not in metrics
