APP_NAME := translate-transfer
BIN_DIR := bin
BIN := $(BIN_DIR)/$(APP_NAME)
PORT ?= $(shell sed -n 's/.*"port"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' config.json | head -1)

build:
	@echo "编译 Go 应用..."
	@mkdir -p $(BIN_DIR)
	go build -o $(BIN) .

run:
	go run .

deploy:
	@echo "开始部署..."
	@echo "1. 拉取最新代码..."
	git pull
	@echo "2. 编译 Go 应用..."
	@mkdir -p $(BIN_DIR)
	go build -o $(BIN) .
	@echo "3. 停止现有进程..."
	@lsof -ti:$(PORT) | xargs kill -9 2>/dev/null || echo "端口 $(PORT) 没有进程或进程已停止"
	@echo "4. 启动新应用..."
	@nohup ./$(BIN) > app.log 2>&1 &
	@echo "部署完成！"

.PHONY: build run deploy
