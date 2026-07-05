package main

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

func (a *App) proxyDeepSeek(c *gin.Context, payload map[string]interface{}, word string) {
	cacheEnabled := a.cacheEnabled()
	if word != "" && cacheEnabled {
		if cacheContent, found := a.getCachedWord(word); found {
			if boolValue(payload["stream"]) {
				a.writeCachedStream(c, payload, cacheContent)
				return
			}

			c.Data(http.StatusOK, "application/json", mustJSONBytes(gin.H{
				"choices": []gin.H{
					{
						"message": gin.H{
							"role":    "assistant",
							"content": cacheContent,
						},
					},
				},
			}))
			return
		}
	}

	apiKey := ""
	targetURL := defaultURL
	if a.localConfig != nil {
		apiKey = a.localConfig.Relay.APIKey
		if strings.TrimSpace(a.localConfig.Relay.URL) != "" {
			targetURL = strings.TrimSpace(a.localConfig.Relay.URL)
		}
	}
	if apiKey == "" {
		apiKey = os.Getenv("DEEPSEEK_API_KEY")
	}

	body, err := json.Marshal(payload)
	if err != nil {
		c.Data(http.StatusInternalServerError, "application/json", mustJSONBytes(gin.H{"error": err.Error()}))
		return
	}

	wantStream := boolValue(payload["stream"])
	req, err := http.NewRequestWithContext(c.Request.Context(), http.MethodPost, targetURL, bytes.NewReader(body))
	if err != nil {
		c.Data(http.StatusInternalServerError, "application/json", mustJSONBytes(gin.H{"error": err.Error()}))
		return
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", "Bearer "+apiKey)

	client := a.httpClient
	if wantStream {
		client = a.streamClient
	}

	upstream, err := client.Do(req)
	if err != nil {
		c.Data(http.StatusInternalServerError, "application/json", mustJSONBytes(gin.H{"error": err.Error()}))
		return
	}
	defer upstream.Body.Close()

	contentType := upstream.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "application/json"
	}

	if upstream.StatusCode != http.StatusOK {
		responseBody, _ := io.ReadAll(upstream.Body)
		c.Data(upstream.StatusCode, contentType, responseBody)
		return
	}

	if wantStream {
		a.proxyStream(c, upstream, word, cacheEnabled)
		return
	}

	responseBody, err := io.ReadAll(upstream.Body)
	if err != nil {
		c.Data(http.StatusInternalServerError, "application/json", mustJSONBytes(gin.H{"error": err.Error()}))
		return
	}

	var responseData map[string]interface{}
	if err := json.Unmarshal(responseBody, &responseData); err == nil {
		if choices, ok := responseData["choices"].([]interface{}); ok && len(choices) > 0 {
			if word != "" && cacheEnabled {
				if _, found := a.getCachedWord(word); !found {
					if assistantMessage := assistantContent(choices[0]); assistantMessage != "" {
						a.cacheWordTranslation(word, assistantMessage)
					}
				}
			}
			c.Data(upstream.StatusCode, contentType, responseBody)
			return
		}

		c.Data(http.StatusInternalServerError, "application/json", mustJSONBytes(gin.H{
			"error":             "Empty choices in response",
			"original_response": responseData,
		}))
		return
	}

	c.Data(upstream.StatusCode, contentType, responseBody)
}

func (a *App) writeCachedStream(c *gin.Context, payload map[string]interface{}, cacheContent string) {
	c.Header("Content-Type", "text/event-stream")
	c.Status(http.StatusOK)

	id := "chat-" + randomHex(4)
	created := time.Now().Unix()
	model := defaultModel
	if v, ok := payload["model"].(string); ok && v != "" {
		model = v
	}

	initialChunk := gin.H{
		"id":      id,
		"object":  "chat.completion.chunk",
		"created": created,
		"model":   model,
		"choices": []gin.H{{
			"index":         0,
			"delta":         gin.H{"content": ""},
			"logprobs":      nil,
			"finish_reason": nil,
		}},
		"usage": gin.H{"prompt_tokens": 0, "total_tokens": 0, "completion_tokens": 0},
	}
	writeSSE(c, initialChunk)

	for _, char := range cacheContent {
		chunk := gin.H{
			"id":      id,
			"object":  "chat.completion.chunk",
			"created": created,
			"model":   model,
			"choices": []gin.H{{
				"index":         0,
				"delta":         gin.H{"content": string(char)},
				"logprobs":      nil,
				"finish_reason": nil,
			}},
			"usage": gin.H{"prompt_tokens": 0, "total_tokens": 0, "completion_tokens": 0},
		}
		if !writeSSE(c, chunk) {
			return
		}
	}

	finalChunk := gin.H{
		"id":      id,
		"object":  "chat.completion.chunk",
		"created": created,
		"model":   model,
		"choices": []gin.H{{
			"index":         0,
			"delta":         gin.H{"content": ""},
			"logprobs":      nil,
			"finish_reason": "stop",
			"stop_reason":   nil,
		}},
		"usage": gin.H{
			"prompt_tokens":     78,
			"total_tokens":      106,
			"completion_tokens": len([]rune(cacheContent)),
		},
	}
	writeSSE(c, finalChunk)
}

func (a *App) proxyStream(c *gin.Context, upstream *http.Response, word string, cacheEnabled bool) {
	contentType := upstream.Header.Get("Content-Type")
	if contentType == "" {
		contentType = "text/event-stream"
	}
	c.Header("Content-Type", contentType)
	c.Status(http.StatusOK)

	var translationBuffer strings.Builder
	scanner := bufio.NewScanner(upstream.Body)
	scanner.Buffer(make([]byte, 0, 64*1024), 1024*1024)

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if !strings.HasPrefix(line, "data: ") || len(line) <= 6 {
			continue
		}

		dataStr := strings.TrimSpace(line[6:])
		if dataStr == "[DONE]" {
			continue
		}

		var data map[string]interface{}
		if err := json.Unmarshal([]byte(dataStr), &data); err != nil {
			continue
		}

		choices, ok := data["choices"].([]interface{})
		if !ok || len(choices) == 0 {
			continue
		}

		if content := deltaContent(choices[0]); content != "" {
			translationBuffer.WriteString(content)
		}

		if _, err := c.Writer.Write([]byte(line + "\n")); err != nil {
			return
		}
		c.Writer.Flush()
	}

	if err := scanner.Err(); err != nil {
		errorChunk := fmt.Sprintf("data: %s\n\n", string(mustJSONBytes(gin.H{"error": "Stream error: " + err.Error()})))
		_, _ = c.Writer.Write([]byte(errorChunk))
		c.Writer.Flush()
		return
	}

	if word != "" && translationBuffer.Len() > 0 && cacheEnabled {
		if _, found := a.getCachedWord(word); !found {
			a.cacheWordTranslation(word, translationBuffer.String())
		}
	}
}

func writeSSE(c *gin.Context, data interface{}) bool {
	line := fmt.Sprintf("data: %s\n\n", string(mustJSONBytes(data)))
	if _, err := c.Writer.Write([]byte(line)); err != nil {
		return false
	}
	c.Writer.Flush()
	return true
}
