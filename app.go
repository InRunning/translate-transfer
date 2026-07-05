package main

import (
	"net/http"
	"sync"
	"time"

	"gorm.io/gorm"
)

type App struct {
	config       AppConfig
	localConfig  *LocalConfig
	db           *gorm.DB
	httpClient   *http.Client
	streamClient *http.Client
	wordCache    sync.Map
}

func newApp(config AppConfig, localConfig *LocalConfig, db *gorm.DB) *App {
	return &App{
		config:      config,
		localConfig: localConfig,
		db:          db,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		streamClient: &http.Client{},
	}
}
