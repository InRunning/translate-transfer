package main

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/gin-gonic/gin"
)

func TestProxyStreamRelaysSSEEventBoundariesAndDone(t *testing.T) {
	gin.SetMode(gin.TestMode)
	response := httptest.NewRecorder()
	context, _ := gin.CreateTestContext(response)
	upstream := &http.Response{
		Header: http.Header{"Content-Type": []string{"text/event-stream"}},
		Body: io.NopCloser(strings.NewReader(
			"data: {\"choices\":[{\"delta\":{\"content\":\"Kamusta\"}}]}\n\n" +
				"data: {\"choices\":[{\"delta\":{\"content\":\"!\"}}]}\n\n" +
				"data: [DONE]\n\n",
		)),
	}

	newApp(defaultConfig(), nil, nil).proxyStream(context, upstream, "tl", "", false)

	if got, want := response.Header().Get("Content-Type"), "text/event-stream"; got != want {
		t.Fatalf("Content-Type = %q, want %q", got, want)
	}
	want := "data: {\"choices\":[{\"delta\":{\"content\":\"Kamusta\"}}]}\n\n" +
		"data: {\"choices\":[{\"delta\":{\"content\":\"!\"}}]}\n\n" +
		"data: [DONE]\n\n"
	if got := response.Body.String(); got != want {
		t.Fatalf("SSE response = %q, want %q", got, want)
	}
}

func TestWriteCachedStreamEndsWithDone(t *testing.T) {
	gin.SetMode(gin.TestMode)
	response := httptest.NewRecorder()
	context, _ := gin.CreateTestContext(response)

	newApp(defaultConfig(), nil, nil).writeCachedStream(context, map[string]interface{}{
		"model": "DeepSeek-V3",
	}, "halimbawa")

	body := response.Body.String()
	if !strings.HasSuffix(body, "data: [DONE]\n\n") {
		t.Fatalf("cached SSE response must end with [DONE], got %q", body)
	}
	if !strings.Contains(body, `"content":"halimbawa"`) {
		t.Fatalf("cached SSE response must include cached translation, got %q", body)
	}
}
