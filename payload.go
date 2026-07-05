package main

import (
	"errors"
	"log"
	"strings"
)

func (a *App) buildOutgoingPayload(incoming map[string]interface{}, isWordInput bool, userTextOverride *string) (map[string]interface{}, error) {
	systemPrompt := "你是一个智能翻译助手，下面是句子，请给出该句子的释义。示例：输入：I want to go home 输出: 我想回家 ./no_think"
	if isWordInput {
		systemPrompt = "你是一个智能翻译助手，下面是单词，你需要给出该单词最常用的一个释义，并给出美式音标和英式音标，示例：输入：example 输出格式: 例子\n 美式音标：/ɪɡˈzæmpəl/ \n英式音标：/ɪɡˈzɑːmpəl/ ./no_think"
	}

	outgoing := make(map[string]interface{}, len(incoming)+2)
	for key, value := range incoming {
		outgoing[key] = value
	}

	configuredModel := ""
	if a.localConfig != nil {
		configuredModel = strings.TrimSpace(a.localConfig.Relay.Model)
	}
	incomingModel, _ := incoming["model"].(string)
	model := firstNonEmpty(configuredModel, incomingModel, defaultModel)
	outgoing["model"] = model

	if streamValue, exists := incoming["stream"]; exists && streamValue != nil {
		outgoing["stream"] = streamValue
	} else if a.localConfig != nil && a.localConfig.Relay.Stream != nil {
		outgoing["stream"] = *a.localConfig.Relay.Stream
	}

	if tempValue, exists := incoming["temperature"]; (!exists || tempValue == nil) && a.localConfig != nil && a.localConfig.Relay.Temperature != nil {
		outgoing["temperature"] = a.localConfig.Relay.Temperature
	}

	rawMessages, ok := incoming["messages"].([]interface{})
	if !ok || len(rawMessages) == 0 {
		return nil, errors.New("Messages cannot be empty")
	}

	outgoingMessages := make([]map[string]interface{}, 0, len(rawMessages)+1)
	outgoingMessages = append(outgoingMessages, map[string]interface{}{
		"role":    "system",
		"content": systemPrompt,
	})

	copiedMessages := make([]map[string]interface{}, 0, len(rawMessages))
	for _, raw := range rawMessages {
		msg, ok := raw.(map[string]interface{})
		if !ok || msg["role"] == nil || msg["content"] == nil {
			return nil, errors.New("Invalid message format")
		}
		copied := make(map[string]interface{}, len(msg))
		for key, value := range msg {
			copied[key] = value
		}
		copiedMessages = append(copiedMessages, copied)
	}

	if userTextOverride != nil {
		for i := len(copiedMessages) - 1; i >= 0; i-- {
			if role, _ := copiedMessages[i]["role"].(string); role == "user" {
				copiedMessages[i]["content"] = *userTextOverride
				break
			}
		}
	}

	outgoingMessages = append(outgoingMessages, copiedMessages...)
	outgoing["messages"] = outgoingMessages

	if configuredModel != "" && incomingModel != "" && configuredModel != incomingModel {
		log.Printf("检测到客户端模型与上游配置模型不一致，已使用 Relay.Model。incoming_model=%q, relay_model=%q", incomingModel, configuredModel)
	}

	return outgoing, nil
}

func assistantContent(choice interface{}) string {
	choiceMap, ok := choice.(map[string]interface{})
	if !ok {
		return ""
	}
	message, ok := choiceMap["message"].(map[string]interface{})
	if !ok {
		return ""
	}
	content, _ := message["content"].(string)
	return content
}

func deltaContent(choice interface{}) string {
	choiceMap, ok := choice.(map[string]interface{})
	if !ok {
		return ""
	}
	delta, ok := choiceMap["delta"].(map[string]interface{})
	if !ok {
		return ""
	}
	content, _ := delta["content"].(string)
	return content
}
