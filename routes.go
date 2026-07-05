package main

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
)

func (a *App) registerRoutes(router *gin.Engine) {
	zoteroRoute := a.route("zotero", "/zotero")
	zoteroJSONRoute := a.route("zotero_json", "/zotero/json")
	anxReaderRoute := a.route("anx_reader", "/anx-reader")
	healthRoute := a.route("health", "/health")
	indexRoute := a.route("index", "/")

	router.POST(zoteroRoute, func(c *gin.Context) {
		a.translationProxy(c, "Zotero", false)
	})
	router.POST(zoteroJSONRoute, func(c *gin.Context) {
		a.translationProxy(c, "Zotero JSON", true)
	})
	router.POST(anxReaderRoute, func(c *gin.Context) {
		a.translationProxy(c, "Anx-Reader", false)
	})
	router.POST("/anx-reader/chat/completions", func(c *gin.Context) {
		a.translationProxy(c, "Anx-Reader", false)
	})
	router.POST("/anx-reader/v1/chat/completions", func(c *gin.Context) {
		a.translationProxy(c, "Anx-Reader", false)
	})
	router.GET(healthRoute, func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy"})
	})
	router.GET(indexRoute, func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"message":   "翻译服务",
			"version":   "1.0.0",
			"endpoints": a.config.Routes,
		})
	})
}

func (a *App) route(key, fallback string) string {
	if a.config.Routes == nil {
		return fallback
	}
	if route := strings.TrimSpace(a.config.Routes[key]); route != "" {
		return route
	}
	return fallback
}
