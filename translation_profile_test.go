package main

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestBuildOutgoingPayloadUsesTranslationProfile(t *testing.T) {
	incoming := map[string]interface{}{
		"messages": []interface{}{map[string]interface{}{"role": "user", "content": "I want to go home"}},
	}
	app := newApp(defaultConfig(), nil, nil)

	tagalogPayload, err := app.buildOutgoingPayload(incoming, tagalogTranslationProfile, false, nil)
	if err != nil {
		t.Fatalf("buildOutgoingPayload() error = %v", err)
	}
	tagalogMessages := tagalogPayload["messages"].([]map[string]interface{})
	tagalogPrompt := tagalogMessages[0]["content"].(string)
	if !strings.Contains(tagalogPrompt, "Tagalog（Filipino）") {
		t.Fatalf("Tagalog prompt = %q, want Tagalog instruction", tagalogPrompt)
	}

	chinesePayload, err := app.buildOutgoingPayload(incoming, chineseTranslationProfile, false, nil)
	if err != nil {
		t.Fatalf("buildOutgoingPayload() error = %v", err)
	}
	chineseMessages := chinesePayload["messages"].([]map[string]interface{})
	if got := chineseMessages[0]["content"]; got != chineseTranslationProfile.SentencePrompt {
		t.Fatalf("Chinese prompt = %q, want original prompt", got)
	}
}

func TestWordCacheKeyIncludesTargetLanguage(t *testing.T) {
	if wordCacheKey("zh-CN", "Example") == wordCacheKey("tl", "example") {
		t.Fatal("cache keys for Chinese and Tagalog must differ")
	}
	if got, want := wordCacheKey("tl", "Example"), "tl:example"; got != want {
		t.Fatalf("wordCacheKey() = %q, want %q", got, want)
	}
}

func TestTagalogRoutesAreRegistered(t *testing.T) {
	gin.SetMode(gin.TestMode)
	app := newApp(defaultConfig(), nil, nil)
	router := gin.New()
	app.registerRoutes(router)

	for _, path := range []string{
		"/anx-reader-tagalog",
		"/anx-reader-tagalog/chat/completions",
		"/anx-reader-tagalog/v1/chat/completions",
	} {
		req := httptest.NewRequest(http.MethodPost, path, strings.NewReader(`{}`))
		req.Header.Set("Content-Type", "application/json")
		resp := httptest.NewRecorder()
		router.ServeHTTP(resp, req)
		if resp.Code != http.StatusBadRequest {
			t.Errorf("POST %s status = %d, want registered route returning %d", path, resp.Code, http.StatusBadRequest)
		}
	}
}
