import paramiko
import io
from typing import Optional


class SSHService:
    """SSH command execution service using paramiko."""

    def __init__(self, host: str, port: int = 22, username: str = "",
                 password: str = None, private_key: str = None, use_agent: bool = False):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.private_key = private_key
        self.use_agent = use_agent

    def _get_client(self) -> paramiko.SSHClient:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            "hostname": self.host,
            "port": self.port,
            "username": self.username,
            "timeout": 10,
        }

        if self.use_agent:
            # Use SSH agent for authentication
            connect_kwargs["allow_agent"] = True
            connect_kwargs["look_for_keys"] = True
        elif self.private_key:
            key_file = io.StringIO(self.private_key)
            try:
                pkey = paramiko.RSAKey.from_private_key(key_file)
            except Exception:
                key_file.seek(0)
                pkey = paramiko.Ed25519Key.from_private_key(key_file)
            connect_kwargs["pkey"] = pkey
            connect_kwargs["allow_agent"] = False
            connect_kwargs["look_for_keys"] = False
        elif self.password:
            connect_kwargs["password"] = self.password
            connect_kwargs["allow_agent"] = False
            connect_kwargs["look_for_keys"] = False

        client.connect(**connect_kwargs)
        return client

    def execute(self, command: str, timeout: int = 30) -> str:
        client = self._get_client()
        try:
            stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            output = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            if err and not output:
                return err
            return output
        finally:
            client.close()

    def execute_multi(self, commands: list[str], timeout: int = 30) -> dict[str, str]:
        client = self._get_client()
        try:
            results = {}
            for cmd in commands:
                stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
                output = stdout.read().decode("utf-8", errors="replace")
                results[cmd] = output.strip()
            return results
        finally:
            client.close()
