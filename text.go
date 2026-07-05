package main

import (
	"log"
	"regexp"
	"strings"
	"unicode"
)

var (
	wordPattern   = regexp.MustCompile(`^[a-zA-Z]{1,50}$`)
	sourcePattern = regexp.MustCompile(`sourceText:\s*(.+?)(?:\n|$)`)
)

func extractUserMessageText(messages []interface{}) string {
	for i := len(messages) - 1; i >= 0; i-- {
		msg, ok := messages[i].(map[string]interface{})
		log.Printf("检查消息 %d: %+v", len(messages)-1-i, messages[i])
		if !ok {
			continue
		}
		role, _ := msg["role"].(string)
		if role != "user" {
			continue
		}
		content, _ := msg["content"].(string)
		userMessageText := strings.TrimSpace(content)
		log.Printf("找到用户消息: %q", userMessageText)

		if match := sourcePattern.FindStringSubmatch(userMessageText); len(match) > 1 {
			actualWord := strings.TrimSpace(match[1])
			log.Printf("提取到的实际单词: %q", actualWord)
			userMessageText = actualWord
		}
		return userMessageText
	}

	return ""
}

func normalizeWordText(text string) string {
	var b strings.Builder
	for _, r := range strings.TrimSpace(text) {
		if unicode.IsPunct(r) {
			continue
		}
		b.WriteRune(r)
	}
	return strings.TrimSpace(b.String())
}

func isWord(text string) bool {
	return wordPattern.MatchString(normalizeWordText(text))
}

func userTextOverride(enabled bool, text string) *string {
	if !enabled {
		return nil
	}
	return &text
}
