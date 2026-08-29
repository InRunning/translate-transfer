package main

import (
	"encoding/json"
	"errors"
	"log"
	"os"

	"gopkg.in/yaml.v3"
)

type AppConfig struct {
	Server struct {
		Host     string `json:"host"`
		Port     int    `json:"port"`
		Debug    bool   `json:"debug"`
		Threaded bool   `json:"threaded"`
	} `json:"server"`
	Routes map[string]string `json:"routes"`
}

type LocalConfig struct {
	Relay struct {
		Model       string      `yaml:"Model"`
		URL         string      `yaml:"Url"`
		APIKey      string      `yaml:"ApiKey"`
		Temperature interface{} `yaml:"Temperature"`
		Stream      *bool       `yaml:"Stream"`
		Cache       *bool       `yaml:"Cache"`
	} `yaml:"Relay"`
	Database DatabaseConfig `yaml:"Database"`
}

func defaultConfig() AppConfig {
	var cfg AppConfig
	cfg.Server.Host = "0.0.0.0"
	cfg.Server.Port = 13234
	cfg.Server.Debug = true
	cfg.Server.Threaded = true
	cfg.Routes = map[string]string{
		"zotero":             "/zotero",
		"zotero_json":        "/zotero/json",
		"anx_reader":         "/anx-reader",
		"anx_reader_tagalog": "/anx-reader-tagalog",
		"health":             "/health",
		"index":              "/",
	}
	return cfg
}

func loadConfig() AppConfig {
	cfg := defaultConfig()

	data, err := os.ReadFile("config.json")
	if err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			log.Printf("读取 config.json 失败，使用默认配置: %v", err)
		}
		return cfg
	}

	if err := json.Unmarshal(data, &cfg); err != nil {
		log.Printf("解析 config.json 失败，使用默认配置: %v", err)
		return defaultConfig()
	}

	if cfg.Server.Host == "" {
		cfg.Server.Host = "0.0.0.0"
	}
	if cfg.Server.Port == 0 {
		cfg.Server.Port = 13234
	}
	if cfg.Routes == nil {
		cfg.Routes = defaultConfig().Routes
	}
	return cfg
}

func loadLocalConfig() *LocalConfig {
	data, err := os.ReadFile("local.yaml")
	if err != nil {
		if !errors.Is(err, os.ErrNotExist) {
			log.Printf("读取 local.yaml 失败: %v", err)
		}
		return nil
	}

	var cfg LocalConfig
	if err := yaml.Unmarshal(data, &cfg); err != nil {
		log.Printf("解析 local.yaml 失败: %v", err)
		return nil
	}
	return &cfg
}
