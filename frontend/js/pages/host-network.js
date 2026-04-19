/* Host Network Topology Page */
const HostNetworkPage = {
    container: null,
    hostId: null,
    host: null,
    data: null,
    canvas: null,
    ctx: null,
    pollTimer: null,
    animationFrame: null,

    async render({ container, hostId, host }) {
        this.cleanup();
        this.container = container;
        this.hostId = hostId;
        this.host = host || null;

        container.innerHTML = `
            <div class="host-network-topology">
                <canvas id="host-network-canvas" class="host-network-canvas"></canvas>
                <div class="host-network-legend">
                    <div class="host-network-legend-item">
                        <div class="host-network-legend-color" style="background:#10b981"></div>
                        <span>ESTABLISHED</span>
                    </div>
                    <div class="host-network-legend-item">
                        <div class="host-network-legend-color" style="background:#f59e0b"></div>
                        <span>TIME_WAIT</span>
                    </div>
                    <div class="host-network-legend-item">
                        <div class="host-network-legend-color" style="background:#3b82f6"></div>
                        <span>LISTEN</span>
                    </div>
                </div>
            </div>
        `;

        this.canvas = DOM.$('#host-network-canvas');
        if (this.canvas) {
            this.ctx = this.canvas.getContext('2d');
            this._resizeCanvas();
            window.addEventListener('resize', this._resizeCanvas.bind(this));
        }

        await this._refresh();
        this._startAnimation();

        // 定时刷新
        this.pollTimer = setInterval(() => this._refresh(), 10000);

        return () => this.cleanup();
    },

    async _refresh() {
        try {
            this.data = await API.getHostNetworkTopology(this.hostId);
        } catch (error) {
            console.error('Failed to fetch network topology:', error);
        }
    },

    _resizeCanvas() {
        if (!this.canvas) return;
        const rect = this.canvas.parentElement.getBoundingClientRect();
        this.canvas.width = rect.width;
        this.canvas.height = rect.height;
    },

    _startAnimation() {
        const animate = () => {
            this._draw();
            this.animationFrame = requestAnimationFrame(animate);
        };
        animate();
    },

    _draw() {
        if (!this.ctx || !this.data) return;

        const { width, height } = this.canvas;
        this.ctx.clearRect(0, 0, width, height);

        // 绘制中心主机节点
        const centerX = width / 2;
        const centerY = height / 2;
        const centerRadius = 40;

        this.ctx.fillStyle = '#3b82f6';
        this.ctx.beginPath();
        this.ctx.arc(centerX, centerY, centerRadius, 0, Math.PI * 2);
        this.ctx.fill();

        this.ctx.fillStyle = '#ffffff';
        this.ctx.font = '14px Inter';
        this.ctx.textAlign = 'center';
        this.ctx.textBaseline = 'middle';
        this.ctx.fillText(this.data.host.name, centerX, centerY);

        // 绘制远程 IP 节点
        const connections = this.data.connections.slice(0, 20); // 最多显示 20 个
        const angleStep = (Math.PI * 2) / connections.length;
        const radius = Math.min(width, height) / 3;

        connections.forEach((conn, index) => {
            const angle = angleStep * index - Math.PI / 2;
            const x = centerX + Math.cos(angle) * radius;
            const y = centerY + Math.sin(angle) * radius;
            const nodeRadius = 20;

            // 绘制连接线
            this.ctx.strokeStyle = this._getStateColor(conn.states);
            this.ctx.lineWidth = Math.min(conn.connection_count / 2, 5);
            this.ctx.beginPath();
            this.ctx.moveTo(centerX, centerY);
            this.ctx.lineTo(x, y);
            this.ctx.stroke();

            // 绘制节点
            this.ctx.fillStyle = '#1e293b';
            this.ctx.beginPath();
            this.ctx.arc(x, y, nodeRadius, 0, Math.PI * 2);
            this.ctx.fill();

            this.ctx.strokeStyle = this._getStateColor(conn.states);
            this.ctx.lineWidth = 2;
            this.ctx.stroke();

            // 绘制 IP 地址
            this.ctx.fillStyle = '#e2e8f0';
            this.ctx.font = '10px JetBrains Mono';
            this.ctx.textAlign = 'center';
            this.ctx.fillText(conn.remote_ip, x, y - nodeRadius - 10);

            // 绘制连接数
            this.ctx.fillStyle = '#94a3b8';
            this.ctx.fillText(`${conn.connection_count}`, x, y + nodeRadius + 15);
        });
    },

    _getStateColor(states) {
        if (states.ESTABLISHED || states.ESTAB) return '#10b981';
        if (states.TIME_WAIT) return '#f59e0b';
        if (states.LISTEN) return '#3b82f6';
        return '#6b7280';
    },

    cleanup() {
        if (this.pollTimer) {
            clearInterval(this.pollTimer);
            this.pollTimer = null;
        }
        if (this.animationFrame) {
            cancelAnimationFrame(this.animationFrame);
            this.animationFrame = null;
        }
        window.removeEventListener('resize', this._resizeCanvas.bind(this));
        this.canvas = null;
        this.ctx = null;
        this.data = null;
    }
};
