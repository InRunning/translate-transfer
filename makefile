deploy:
	@echo "开始部署..."
	@echo "1. 拉取最新代码..."
	git pull
	@echo "2. 停止现有进程..."
	@lsof -ti:10283 | xargs kill -9 2>/dev/null || echo "端口 10283 没有进程或进程已停止"
	@echo "3. 启动新应用..."
	@nohup ./venv/bin/python app.py > app.log 2>&1 &
	@echo "部署完成！"

.PHONY: deploy