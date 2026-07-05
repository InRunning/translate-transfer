package main

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strconv"
	"strings"
	"time"
)

func boolValue(value interface{}) bool {
	switch v := value.(type) {
	case bool:
		return v
	case string:
		parsed, _ := strconv.ParseBool(v)
		return parsed
	default:
		return false
	}
}

func mustJSONBytes(value interface{}) []byte {
	data, err := json.Marshal(value)
	if err != nil {
		return []byte(`{"error":"json marshal failed"}`)
	}
	return data
}

func randomHex(size int) string {
	buf := make([]byte, size)
	if _, err := rand.Read(buf); err != nil {
		return strconv.FormatInt(time.Now().UnixNano(), 16)
	}
	return hex.EncodeToString(buf)
}

func truncate(value string, max int) string {
	if len([]rune(value)) <= max {
		return value
	}
	runes := []rune(value)
	return string(runes[:max])
}

func getValue(values map[string]interface{}, key string) interface{} {
	if values == nil {
		return nil
	}
	return values[key]
}

func getString(values map[string]interface{}, key, fallback string) string {
	value := getValue(values, key)
	if value == nil {
		return fallback
	}
	return fmt.Sprint(value)
}

func getStringPtr(values map[string]interface{}, key string) *string {
	if values == nil {
		return nil
	}
	value, ok := values[key]
	if !ok {
		return nil
	}
	stringValue := fmt.Sprint(value)
	return &stringValue
}

func firstValue(values ...interface{}) interface{} {
	for _, value := range values {
		if value != nil {
			return value
		}
	}
	return nil
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}

func firstNonEmptyAllowBlank(fallback string, values ...*string) string {
	for _, value := range values {
		if value != nil {
			return *value
		}
	}
	return fallback
}

func toInt(value interface{}, fallback int) int {
	if value == nil {
		return fallback
	}
	switch v := value.(type) {
	case int:
		return v
	case int64:
		return int(v)
	case float64:
		return int(v)
	case string:
		parsed, err := strconv.Atoi(strings.TrimSpace(v))
		if err == nil {
			return parsed
		}
	}
	return fallback
}
