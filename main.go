package main

import (
	"fmt"
	"log"

	"github.com/gin-gonic/gin"
)

func main() {
	config := loadConfig()
	localConfig := loadLocalConfig()

	if !config.Server.Debug {
		gin.SetMode(gin.ReleaseMode)
	}

	db, err := initDB(localConfig)
	if err != nil {
		log.Fatalf("数据库初始化失败: %v", err)
	}
	log.Println("数据库初始化完成")

	app := newApp(config, localConfig, db)
	router := gin.Default()
	app.registerRoutes(router)

	addr := fmt.Sprintf("%s:%d", config.Server.Host, config.Server.Port)
	log.Printf("启动翻译服务，监听地址: %s", addr)
	if err := router.Run(addr); err != nil {
		log.Fatalf("服务启动失败: %v", err)
	}
}
